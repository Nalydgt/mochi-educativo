import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import Settings, create_app
from elevenlabs_voice import ElevenLabsVoice
from test_gateway import Brain, Speech, HEADERS, TOKEN
from voice_service import VoiceService

KEY = 'test-private-elevenlabs-key'
PCM = b'\x01\x02' * 1600


class Local(Speech):
    def warmup(self): pass


def voice(handler, **kwargs):
    return ElevenLabsVoice(KEY, 'selected_voice', transport=httpx.MockTransport(handler), **kwargs)


def test_spanish_raw_pcm_uses_selected_clone_and_authenticated_official_endpoint():
    def handler(request):
        assert request.url.host == 'api.elevenlabs.io'
        assert request.url.path == '/v1/text-to-speech/selected_voice/stream'
        assert request.url.params['output_format'] == 'pcm_16000'
        assert request.headers['xi-api-key'] == KEY
        body = json.loads(request.content)
        assert body['text'] == '¡Hola, soy Mochi!'
        assert body['language_code'] == 'es'
        assert body['model_id'] == 'eleven_flash_v2_5'
        return httpx.Response(200, content=PCM, headers={'content-type': 'application/octet-stream'})
    selected = voice(handler)
    try:
        audio, metrics = selected.generate_measured('  ¡Hola, soy Mochi!  ')
        assert audio == PCM
        assert 0 <= metrics['first_pcm_seconds'] <= metrics['phrase_seconds']
        assert metrics['audio_seconds'] == .1
    finally:
        selected.close()


@pytest.mark.parametrize('content,media', [(b'x', 'audio/pcm'), (b'', 'audio/pcm'),
    (b'ID3xxx', 'audio/pcm'), (b'RIFFxxxx', 'audio/pcm'), (PCM, 'audio/mpeg'),
    (PCM, 'application/json'), (b'\x01\x02' * 720001, 'audio/pcm')],
    ids=['odd', 'empty', 'mp3-header', 'wav-header', 'mp3-type', 'json-type', 'oversize'])
def test_invalid_or_oversized_audio_is_rejected(content, media):
    selected = voice(lambda r: httpx.Response(200, content=content, headers={'content-type': media}))
    try:
        with pytest.raises(ValueError):
            selected.generate('Hola')
    finally:
        selected.close()


def test_quota_failure_is_not_retried():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(429, json={'detail': 'quota_exceeded'})
    selected = voice(handler)
    try:
        with pytest.raises(httpx.HTTPStatusError):
            selected.generate('Hola')
        assert len(requests) == 1
    finally:
        selected.close()


def test_readiness_requires_selected_voice_and_never_generates_audio():
    def handler(request):
        assert request.method == 'GET'
        assert request.url.path == '/v1/voices/selected_voice'
        return httpx.Response(200, json={'voice_id': 'another_voice'})
    selected = voice(handler)
    try:
        assert selected.status() == {'ready': False}
    finally:
        selected.close()


@pytest.mark.parametrize('voice_id', ['', '../voices', 'id?redirect=1'])
def test_voice_id_cannot_change_api_route(voice_id):
    with pytest.raises(ValueError):
        ElevenLabsVoice(KEY, voice_id)


def settings(tmp_path, **kwargs):
    return Settings(TOKEN, tmp_path, tmp_path/'unused.onnx', voice_provider='elevenlabs',
        elevenlabs_api_key=KEY, elevenlabs_voice_id='selected_voice', **kwargs)


def test_cache_changes_with_clone_model_and_reference_revision(tmp_path):
    a = VoiceService(settings(tmp_path), Speech())
    b = VoiceService(settings(tmp_path, elevenlabs_model_id='eleven_multilingual_v2'), Speech())
    c = VoiceService(settings(tmp_path, elevenlabs_voice_revision='new-reference'), Speech())
    try:
        assert len({a.cache_id, b.cache_id, c.cache_id}) == 3
        a.cache.put(a.cache_id, 'Hola', PCM)
        assert a.speak('Hola') == PCM
        assert b.cached('Hola') is None
        assert KEY not in repr(a.settings)
    finally:
        for service in (a, b, c): service.close()


def test_elevenlabs_warmup_only_loads_recognition_and_closes_client(tmp_path):
    calls = []
    class RecognitionOnly(Speech):
        def warmup_transcriber(self): calls.append('asr')
        def warmup(self): raise AssertionError('Piper must not be loaded')
    app = create_app(settings(tmp_path), Brain(), RecognitionOnly())
    with TestClient(app):
        assert calls == ['asr']
    assert app.state.voice.elevenlabs.client.is_closed


def test_cloud_health_reports_provider_without_exposing_key(tmp_path):
    app = create_app(settings(tmp_path), Brain(), Local())
    selected = app.state.voice.elevenlabs
    selected.client.close()
    selected.client = httpx.Client(base_url='https://api.elevenlabs.io', transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={'voice_id': 'selected_voice'})))
    with TestClient(app) as client:
        response = client.get('/health', headers=HEADERS)
        data = response.json()
        assert data['voice_location'] == 'elevenlabs'
        assert data['voice_installed'] is True
        assert data['elevenlabs_voice_id'] == 'selected_voice'
        assert KEY not in response.text


def test_secret_file_overrides_inline_key_without_exposing_it(monkeypatch, tmp_path):
    keyfile = tmp_path/'secret.key'; keyfile.write_text(KEY+'\n')
    monkeypatch.setenv('ELEVENLABS_API_KEY_FILE', str(keyfile))
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'unused-inline-secret')
    selected = Settings.from_env()
    assert selected.elevenlabs_api_key == KEY
    assert KEY not in repr(selected)


def test_uncached_turn_uses_elevenlabs_without_falling_back_to_local_voice(tmp_path):
    class NoFallback(Local):
        def speak(self, text): raise AssertionError('The chosen speaker must be retained')
    app = create_app(settings(tmp_path), Brain(), NoFallback())
    selected = app.state.voice.elevenlabs
    selected.client.close()
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=PCM, headers={'content-type':'audio/pcm'})
    selected.client = httpx.Client(base_url='https://api.elevenlabs.io', transport=httpx.MockTransport(handler))
    with TestClient(app) as client:
        for _ in range(2):
            response = client.post('/v1/turn', content=b'\0\0'*3200, headers={**HEADERS,
                'Content-Type':'application/octet-stream', 'X-Mochi-Audio-Cache':'bypass'})
            assert response.status_code == 200
            assert response.content == PCM
        assert len(requests) == 2
        assert app.state.voice.cache.stats()['clips'] == 0
