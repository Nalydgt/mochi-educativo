"""Local lifecycle and cancellation checks; no models, NAS or hardware needed."""
import asyncio
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from app import Settings, create_app
from test_gateway import Brain, Speech, HEADERS, TOKEN


@pytest.mark.parametrize('failed_start', [False, True])
def test_http_clients_close_on_shutdown_and_failed_start(tmp_path, failed_start):
    closed = []
    class Local(Speech):
        def warmup(self):
            if failed_start:
                raise RuntimeError('warmup failed')
    class Model(Brain):
        def close(self):
            closed.append('brain')
    class Weather:
        def close(self):
            closed.append('weather')
    class Nav:
        def close(self):
            closed.append('navigation')
    app = create_app(Settings(TOKEN, tmp_path, tmp_path/'voice', navigation_enabled=True,
                             voice_provider='native', native_voice_url='http://localhost:8775',
                             native_voice_token='v'*40, native_voice_profile='a'*64),
                     Model(), Local(), Weather(), navigation=Nav())
    if failed_start:
        with pytest.raises(RuntimeError, match='warmup failed'):
            with TestClient(app):
                pass
    else:
        with TestClient(app):
            assert app.state.speech_ready
    assert set(closed) == {'brain', 'weather', 'navigation'}
    assert app.state.voice.native.client.is_closed
    assert not app.state.speech_ready


def test_non_ascii_authorization_reaches_normal_auth_rejection(tmp_path):
    app = create_app(Settings(TOKEN, tmp_path, tmp_path/'voice', memory_review_enabled=True), Brain(), Speech())
    response = TestClient(app).post('/v1/chat', headers={b'Authorization': b'Bearer \xff'}, json={'text': 'Hola'})
    assert response.status_code == 401


def test_memory_extraction_can_use_separate_model_without_touching_fast_slot(tmp_path, monkeypatch):
    destinations = []
    class Reviewer:
        def __init__(self, memory, url, key):
            destinations.append(url)
    monkeypatch.setattr('app.MemoryReviewer', Reviewer)
    create_app(Settings(TOKEN, tmp_path, tmp_path/'voice', memory_review_enabled=True,
                        fast_url='http://localhost:8776', memory_review_url='http://localhost:8769'),
               Brain(), Speech())
    assert destinations == ['http://localhost:8769']


def test_cancelled_legacy_preview_keeps_speaker_until_synthesis_finishes(tmp_path):
    async def check():
        started, finish = threading.Event(), threading.Event()
        class Slow(Speech):
            def speak(self, text):
                started.set()
                assert finish.wait(3)
                return b'\x01\x02'*1600
        app = create_app(Settings(TOKEN, tmp_path, tmp_path/'voice'), Brain(), Slow())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            task = asyncio.create_task(client.post('/v1/say', headers=HEADERS, json={'text': 'Hola'}))
            try:
                assert await asyncio.to_thread(started.wait, 2)
                task.cancel()
                await asyncio.sleep(.02)
                assert not task.done()
                assert app.state.jobs.conversation_active()
                busy = await client.post('/v1/say', headers=HEADERS, json={'text': 'Otra frase'})
                assert busy.status_code == 429
            finally:
                finish.set()
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert not app.state.jobs.conversation_active()
    asyncio.run(check())
