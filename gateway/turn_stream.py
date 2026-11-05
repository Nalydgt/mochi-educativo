"""Bounded PCM delivery while the same speaker prepares the next sentence."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
import re
from time import perf_counter

import anyio
from fastapi.responses import StreamingResponse

from speech import MAX_SECONDS, RATE
from voice_cache import valid_pcm

logger = logging.getLogger('uvicorn.error')


async def owned_call(function,*args,**kwargs):
    """Cancellation cannot release a turn while its CPU worker still runs."""
    task=asyncio.create_task(asyncio.to_thread(function,*args,**kwargs))
    try:return await asyncio.shield(task)
    except asyncio.CancelledError:
        with anyio.CancelScope(shield=True):
            try:await asyncio.shield(task)
            except Exception:pass
        raise


def prefetched_reply(brain,messages,render,timing):
    """Overlap one TTS job with the tail of Hermes; join it on every exit."""
    future=None;prepared_text=None
    def synthesize(text):
        with timing.stage('tts_first'):return render(text)
    with ThreadPoolExecutor(max_workers=1,thread_name_prefix='mochi-first-sentence') as pool:
        def prepare(text):
            nonlocal future,prepared_text
            if future is None:
                prepared_text=text;future=pool.submit(synthesize,text)
        with timing.stage('hermes'):
            answer=brain.reply_streaming(messages,prepare)
        parts=speech_parts(answer['text'])
        if future is not None:
            first=future.result()
            if prepared_text==parts[0]:return answer,first
        return answer,synthesize(parts[0])


def speech_parts(text):
    """Keep every word, decimals and punctuation; bound long first sentences."""
    # Hermes may begin its continuation with lowercase. A completed sentence
    # still has to be delivered immediately; case must not join both TTS jobs.
    sentences = re.split(r'(?<=[.!?…])\s+', text.strip())
    parts = []
    for sentence in sentences:
        limit=48 if not parts else 110
        while len(sentence) > limit:
            # Prefer a natural clause boundary; never truncate speech or split
            # a word. A single oversized token is left whole for compatibility.
            clauses=list(re.finditer(r'[,;:]\s+',sentence[:limit+1]))
            cut=clauses[-1].start()+1 if clauses and clauses[-1].start()>=20 else sentence.rfind(' ', 1, limit+1)
            if cut < 0:
                break
            parts.append(sentence[:cut])
            sentence = sentence[cut + 1:]
            limit=110
        if sentence:
            parts.append(sentence)
    return parts


class StreamingTurn(StreamingResponse):
    """Own the turn lock and foreground lease through disconnect and cleanup.

    Only one future sentence is rendered ahead. A disconnected client cannot
    release the lock while its synchronous synthesis still uses the speaker.
    """
    def __init__(self, first, remaining, render, commit, release, headers):
        if not valid_pcm(first):
            raise ValueError('Invalid first PCM segment')
        self.first, self.remaining = first, remaining
        self.render, self.commit, self.release = render, commit, release
        self.pending = None
        self.total = len(first)
        self.started = perf_counter()
        super().__init__(self.audio(), media_type='application/octet-stream', headers={
            **headers, 'X-Mochi-Stream': 'pcm16', 'Cache-Control': 'no-store'})

    async def audio(self):
        chunk = self.first
        for index in range(len(self.remaining) + 1):
            if index < len(self.remaining):
                self.pending = asyncio.create_task(asyncio.to_thread(self.render, self.remaining[index]))
            yield chunk
            if self.pending is not None:
                try:
                    chunk = await asyncio.shield(self.pending)
                except Exception:
                    raise RuntimeError('stream_synthesis_failed') from None
                self.pending = None
                if not valid_pcm(chunk) or self.total + len(chunk) > RATE * 2 * MAX_SECONDS:
                    raise ValueError('Invalid subsequent PCM segment')
                self.total += len(chunk)
        await asyncio.to_thread(self.commit)
        logger.info('Mochi stream complete bytes=%d delivery_ms=%.2f', self.total,
                    (perf_counter() - self.started) * 1000)

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Starlette may cancel its task group on disconnect. Finish the
            # already-running CPU call before allowing another conversation.
            with anyio.CancelScope(shield=True):
                try:
                    if self.pending is not None:
                        await asyncio.shield(self.pending)
                except Exception:
                    logger.warning('Mochi stream interrupted during synthesis')
                finally:
                    self.release()
