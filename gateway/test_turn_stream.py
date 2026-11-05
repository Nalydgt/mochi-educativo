import asyncio
import threading

import anyio
from fastapi.testclient import TestClient
import pytest

from app import Settings, create_app, TurnTiming
from test_gateway import Brain, Speech as BaseSpeech, HEADERS, TOKEN
from turn_stream import StreamingTurn, speech_parts, prefetched_reply, owned_call


PCM = b'\x01\x02' * 1600


class Speech(BaseSpeech):
    def warmup(self): pass


def test_parts_preserve_words_decimals_and_punctuation():
    text = 'Tengo 3.14 puntos. ¿Jugamos? ' + 'Una frase bastante larga para comprobar todos los límites sin perder palabras. ' * 3
    parts = speech_parts(text)
    assert ' '.join(parts) == text.strip()
    assert '3.14' in parts[0]
    assert all(len(part) <= 110 for part in parts)


def test_lowercase_continuation_does_not_delay_the_first_sentence():
    assert speech_parts('Estoy muy contento. podemos jugar con 3.14 puntos.') == [
        'Estoy muy contento.', 'podemos jugar con 3.14 puntos.']


def test_short_first_fragment_keeps_every_word_of_a_long_sentence():
    text='La nieve nace en las nubes cuando el vapor de agua se congela alrededor de pequeñas partículas de polvo.'
    parts=speech_parts(text)
    assert len(parts[0])<=48
    assert ' '.join(parts)==text


def test_first_synthesis_overlaps_hermes_and_is_returned_without_a_second_render():
    started=threading.Event();calls=[]
    def render(text):
        calls.append(text);started.set();return PCM
    class StreamingBrain:
        def reply_streaming(self,messages,prepare):
            prepare('Estoy feliz.')
            assert started.wait(3)
            return {'text':'Estoy feliz. ¿Jugamos?','emotion':'happy'}
    answer,pcm=prefetched_reply(StreamingBrain(),[],render,TurnTiming())
    assert pcm==PCM and calls==['Estoy feliz.'] and answer['text'].endswith('¿Jugamos?')


def test_failed_hermes_turn_joins_inflight_speech_before_releasing_ownership():
    started=threading.Event();finish=threading.Event();exited=threading.Event()
    def render(text):
        started.set();assert finish.wait(3);return PCM
    class FailedBrain:
        def reply_streaming(self,messages,prepare):
            prepare('Estoy feliz.')
            assert started.wait(3)
            raise RuntimeError('synthetic interrupted reply')
    def run():
        try:
            with pytest.raises(RuntimeError,match='synthetic interrupted'):
                prefetched_reply(FailedBrain(),[],render,TurnTiming())
        finally:exited.set()
    thread=threading.Thread(target=run);thread.start()
    try:
        assert started.wait(3)
        assert not exited.wait(.05)
    finally:finish.set();thread.join(3)
    assert exited.is_set()


def test_cancellation_waits_for_the_owned_cpu_worker():
    async def check():
        started=threading.Event();finish=threading.Event()
        def work():started.set();assert finish.wait(3)
        task=asyncio.create_task(owned_call(work))
        try:
            assert await asyncio.to_thread(started.wait,2)
            task.cancel()
            await asyncio.sleep(.02)
            assert not task.done()
            finish.set()
            with pytest.raises(asyncio.CancelledError):await task
        finally:finish.set()
    anyio.run(check)


def test_first_audio_is_available_while_next_sentence_is_still_rendering():
    async def check():
        started, finish = threading.Event(), threading.Event()
        committed = []
        def render(text):
            started.set()
            assert finish.wait(3)
            return PCM
        response = StreamingTurn(PCM, ['Segunda frase.'], render,
                                 lambda: committed.append(True), lambda: None, {})
        iterator = response.body_iterator
        try:
            assert await iterator.__anext__() == PCM
            assert await asyncio.to_thread(started.wait, 2)
            assert not committed
            finish.set()
            assert await iterator.__anext__() == PCM
            with pytest.raises(StopAsyncIteration): await iterator.__anext__()
            assert committed == [True]
        finally:
            finish.set()
            await iterator.aclose()
    anyio.run(check)


def test_disconnect_keeps_ownership_until_inflight_synthesis_finishes():
    async def check():
        started, finish = threading.Event(), threading.Event()
        released, committed = [], []
        disconnect = asyncio.Event()
        def render(text):
            started.set()
            assert finish.wait(3)
            return PCM
        response = StreamingTurn(PCM, ['Segunda frase.'], render,
                                 lambda: committed.append(True), lambda: released.append(True), {})
        async def send(message):
            if message['type'] == 'http.response.body':
                disconnect.set()
                await asyncio.sleep(0)
        async def receive():
            await disconnect.wait()
            return {'type': 'http.disconnect'}
        task = asyncio.create_task(response({'type': 'http', 'asgi': {'spec_version': '2.3'}}, receive, send))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            await asyncio.sleep(.02)
            assert not released and not task.done()
            finish.set()
            await task
            assert released == [True] and not committed
        finally:
            finish.set()
            await task
    anyio.run(check)


def test_streaming_turn_preserves_pcm_contract_and_commits_only_complete_answer(tmp_path):
    class TwoSentences(Brain):
        def reply(self, messages): return {'text': 'Hola. ¿Jugamos?', 'emotion': 'happy'}
    speech = Speech()
    app = create_app(Settings(TOKEN, tmp_path, tmp_path / 'voice.onnx'), TwoSentences(), speech)
    with TestClient(app) as client:
        headers = {**HEADERS, 'Content-Type': 'application/octet-stream', 'X-Mochi-Stream': 'pcm16'}
        response = client.post('/v1/turn', headers=headers, content=b'\0\0' * 16000)
        assert response.status_code == 200 and response.content == b'\0\x01' * 3200
        assert response.headers['X-Mochi-Stream'] == 'pcm16'
        assert response.headers['X-Mochi-Sample-Rate'] == '16000'
        assert 'tts_first' in response.headers['Server-Timing']
        assert app.state.memory.history('mochi')[-1]['content'] == 'Hola. ¿Jugamos?'
        assert not app.state.jobs.conversation_active()


def test_first_segment_failure_is_http_error_and_releases_turn(tmp_path):
    class Broken(Speech):
        def speak(self, text): raise RuntimeError('private failure')
    app = create_app(Settings(TOKEN, tmp_path, tmp_path / 'voice.onnx'), Brain(), Broken())
    with TestClient(app) as client:
        headers = {**HEADERS, 'Content-Type': 'application/octet-stream', 'X-Mochi-Stream': 'pcm16'}
        response = client.post('/v1/turn', headers=headers, content=b'\0\0' * 16000)
        assert response.status_code == 503 and 'private' not in response.text
        assert not app.state.memory.history('mochi')
        assert not app.state.jobs.conversation_active()
        assert client.post('/v1/chat', headers=HEADERS, json={'text': 'Hola'}).status_code == 200


def test_synthetic_stream_preview_never_calls_brain_or_changes_history(tmp_path):
    brain = Brain()
    app = create_app(Settings(TOKEN, tmp_path, tmp_path / 'voice.onnx'), brain, Speech())
    with TestClient(app) as client:
        response = client.post('/v1/say', headers={**HEADERS, 'X-Mochi-Stream': 'pcm16'},
                               json={'text': 'Hola. ¿Jugamos?'})
        assert response.status_code == 200 and len(response.content) == 6400
        assert response.headers['X-Mochi-Stream'] == 'pcm16'
        assert not brain.calls and not app.state.memory.history('mochi')
        assert not app.state.jobs.conversation_active()


@pytest.mark.parametrize('stream',['','pcm16'])
@pytest.mark.parametrize('provider',['native','local'])
def test_uncached_nas_diagnostic_generates_again_without_erasing_cached_audio(tmp_path,monkeypatch,stream,provider):
    calls=[]
    class Native:
        def __init__(self,*args):pass
        def generate(self,text):calls.append(text);return PCM
    monkeypatch.setattr('voice_service.NativeVoice',Native)
    class Local(Speech):
        def speak(self,text):calls.append(text);return PCM
    settings=Settings(TOKEN,tmp_path,tmp_path/'voice.onnx',voice_provider=provider,
        native_voice_url='http://nas:8772',native_voice_token='s'*40,native_voice_profile='a'*64)
    app=create_app(settings,Brain(),Local())
    headers={**HEADERS,'Content-Type':'application/octet-stream','X-Mochi-Stream':stream}
    with TestClient(app) as client:
        for _ in range(2):
            assert client.post('/v1/turn',headers=headers,content=b'\0\0'*16000).content==PCM
        assert len(calls)==1
        response=client.post('/v1/turn',headers={**headers,'X-Mochi-Audio-Cache':'bypass'},content=b'\0\0'*16000)
        assert response.content==PCM and response.headers['X-Mochi-Audio-Cache']=='bypass'
        assert len(calls)==2
        assert client.post('/v1/turn',headers=headers,content=b'\0\0'*16000).content==PCM
        assert len(calls)==2


def test_uncached_diagnostic_cannot_trigger_an_external_voice_provider(tmp_path,monkeypatch):
    class Native:
        def __init__(self,*args):pass
        def generate(self,text):raise AssertionError('External synthesis must not run')
    monkeypatch.setattr('voice_service.NativeVoice',Native)
    settings=Settings(TOKEN,tmp_path,tmp_path/'voice.onnx',voice_provider='native',native_voice_source='huggingface',
        native_voice_url='http://cloud-adapter:8768',native_voice_token='s'*40,native_voice_profile='a'*64)
    with TestClient(create_app(settings,Brain(),Speech())) as client:
        response=client.post('/v1/turn',headers={**HEADERS,'Content-Type':'application/octet-stream',
            'X-Mochi-Audio-Cache':'bypass'},content=b'\0\0'*16000)
        assert response.status_code==422


def test_invalid_later_segment_never_commits_partial_conversation():
    async def check():
        committed = []
        response = StreamingTurn(PCM, ['Otra frase.'], lambda text: b'x',
                                 lambda: committed.append(True), lambda: None, {})
        iterator = response.body_iterator
        assert await iterator.__anext__() == PCM
        with pytest.raises(ValueError, match='Invalid subsequent'): await iterator.__anext__()
        assert not committed
    anyio.run(check)


def test_disconnect_before_first_audio_skips_later_synthesis_and_memory(tmp_path):
    async def check():
        started, finish = threading.Event(), threading.Event()
        disconnected = asyncio.Event()
        calls = []
        class TwoSentences(Brain):
            def reply(self, messages): return {'text': 'Hola. ¿Jugamos?', 'emotion': 'happy'}
        class Slow(Speech):
            def speak(self, text):
                calls.append(text)
                started.set()
                assert finish.wait(3)
                return PCM
        app = create_app(Settings(TOKEN, tmp_path, tmp_path/'voice.onnx'), TwoSentences(), Slow())
        body_sent = False
        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {'type': 'http.request', 'body': b'\0\0'*16000, 'more_body': False}
            await disconnected.wait()
            return {'type': 'http.disconnect'}
        async def send(message): pass
        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.3'},
                 'http_version': '1.1', 'method': 'POST', 'scheme': 'http', 'path': '/v1/turn',
                 'raw_path': b'/v1/turn', 'query_string': b'', 'root_path': '',
                 'server': ('test',80), 'client': ('test',1234),
                 'headers': [(b'authorization', ('Bearer '+TOKEN).encode()),
                             (b'content-type', b'application/octet-stream'), (b'x-mochi-stream',b'pcm16')]}
        task = asyncio.create_task(app(scope, receive, send))
        try:
            assert await asyncio.to_thread(started.wait,2)
            disconnected.set()
            finish.set()
            await task
            assert len(calls) == 1
            assert not app.state.memory.history('mochi')
            assert not app.state.jobs.conversation_active()
        finally:
            finish.set()
            await task
    anyio.run(check)
