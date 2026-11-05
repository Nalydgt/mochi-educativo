"""ElevenLabs speech for the existing PCM16 device protocol.

Only text is sent to ElevenLabs during conversations. Recognition and the
conversation model stay on the NAS. Requests are never retried implicitly.
"""
import re
from time import perf_counter

import httpx

from speech import MAX_SECONDS, RATE
from voice_cache import clean_text, voice_key


class ElevenLabsVoice:
    def __init__(self, api_key, voice_id, model_id='eleven_flash_v2_5', *,
                 revision='', transport=None):
        if not isinstance(api_key, str) or len(api_key.strip()) < 16 or any(c.isspace() for c in api_key):
            raise ValueError('A private ElevenLabs API key is required')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', voice_id):
            raise ValueError('An ElevenLabs voice ID is required')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', model_id):
            raise ValueError('Invalid ElevenLabs model ID')
        self.voice_id, self.model_id = voice_id, model_id
        self.voice_settings = {'stability': .65, 'similarity_boost': .85,
                               'style': 0, 'use_speaker_boost': False, 'speed': 1.0}
        self.profile = voice_key({'provider': 'elevenlabs', 'voice_id': voice_id,
            'model_id': model_id, 'revision': revision, 'settings': self.voice_settings,
            'language': 'es', 'format': 'pcm16-mono-16000-v1'})
        self.client = httpx.Client(base_url='https://api.elevenlabs.io',
            headers={'xi-api-key': api_key}, follow_redirects=False,
            timeout=httpx.Timeout(30, connect=5), transport=transport)

    def close(self):
        self.client.close()

    def status(self):
        # Inspect the selected voice without generating billable speech.
        try:
            response = self.client.get('/v1/voices/' + self.voice_id, timeout=5)
            response.raise_for_status()
            data = response.json()
            return {'ready': isinstance(data, dict) and data.get('voice_id') == self.voice_id}
        except (httpx.HTTPError, ValueError):
            return {'ready': False}

    def ready(self):
        return self.status()['ready']

    def generate(self, text):
        return self.generate_measured(text)[0]

    def generate_measured(self, text):
        """Return validated PCM and actual network TTFB/full-phrase timings.

        The gateway currently waits for the first complete short phrase before
        delivery. Provider TTFB alone is not device response latency.
        """
        text = clean_text(text)
        start = perf_counter()
        first = None
        pcm = bytearray()
        with self.client.stream('POST', '/v1/text-to-speech/' + self.voice_id + '/stream',
                params={'output_format': 'pcm_16000'}, json={'text': text,
                    'model_id': self.model_id, 'language_code': 'es',
                    'voice_settings': self.voice_settings}) as response:
            response.raise_for_status()
            if response.headers.get('content-type', '').split(';')[0].lower() not in {
                    'application/octet-stream', 'audio/pcm', 'audio/x-pcm'}:
                raise ValueError('Expected raw ElevenLabs PCM16')
            for chunk in response.iter_bytes():
                if chunk and first is None:
                    first = perf_counter() - start
                pcm.extend(chunk)
                if len(pcm) > RATE * 2 * MAX_SECONDS:
                    raise ValueError('ElevenLabs response too long')
        if not pcm or len(pcm) % 2 or pcm[:4] in (b'RIFF', b'OggS') or pcm[:3] == b'ID3':
            raise ValueError('Invalid ElevenLabs PCM')
        return bytes(pcm), {'first_pcm_seconds': first,
            'phrase_seconds': perf_counter() - start, 'audio_seconds': len(pcm) / (RATE * 2),
            'pcm_bytes': len(pcm), 'model_id': self.model_id}
