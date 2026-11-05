"""Contracts for the educational connector; all external calls are mocked."""
import importlib.util
from pathlib import Path
from uuid import uuid4
import pytest, httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient


@pytest.fixture
def service(monkeypatch):
    path = Path(__file__).with_name("app.py")
    spec = importlib.util.spec_from_file_location("educational_connector_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "INTEGRATION", "i" * 64)
    monkeypatch.setattr(module, "PROVISION", "p" * 64)
    monkeypatch.setattr(module, "claim_turn", lambda *args: None)
    return module


def test_usage_quota_is_reported_without_returning_provider_text(service, monkeypatch):
    def route(request):
        return httpx.Response(200, json={
            "choices": [{
                "finish_reason": "error",
                "message": {"role": "assistant", "content": "The AI model service's usage limit is reached"},
            }],
        })

    original = httpx.Client
    monkeypatch.setattr(
        service.httpx, "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(route), **kwargs),
    )
    monkeypatch.setattr(service, "MODEL", "http://educational-model.test/v1")
    monkeypatch.setattr(service, "MODEL_KEY", "m" * 64)
    with pytest.raises(HTTPException) as rejected:
        service.model_answer("JSON", {"question": "Pregunta de prueba"}, 200)
    assert rejected.value.status_code == 503
    assert rejected.value.detail == "education_ai_usage_limit"


def test_pair_bootstrap_is_private_and_does_not_send_an_empty_bearer(
    service, monkeypatch
):
    seen = []

    def route(request):
        seen.append(request)
        return httpx.Response(200, json={"code": "ABCDEFGH"})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        service.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(route), **kw),
    )
    with TestClient(service.app) as client:
        assert client.post("/v1/education/pair/start").status_code == 401
        assert (
            client.post(
                "/v1/education/pair/start",
                headers={"Authorization": "Bearer " + "p" * 64},
            ).status_code
            == 200
        )
    assert len(seen) == 1
    assert "authorization" not in seen[0].headers
    assert seen[0].headers["x-integration-key"] == "i" * 64


def test_denied_device_never_reaches_recognition(service, monkeypatch):
    async def denied(*args, **kwargs):
        raise HTTPException(401, "denied")

    def forbidden(*args):
        raise AssertionError("Unauthorized ASR")

    monkeypatch.setattr(service, "web", denied)
    monkeypatch.setattr(service, "transcribe", forbidden)
    with TestClient(service.app) as client:
        response = client.post(
            "/v1/education/turn",
            headers={"X-Mochi-Turn-ID": str(uuid4())},
            content=bytes(3200),
        )
    assert response.status_code == 401


def test_firmware_compact_turn_id_is_normalized_for_the_web_contract(
    service, monkeypatch
):
    identity = uuid4()
    seen = []

    async def web(action, **kwargs):
        if action == "events":
            return {
                "sessionId": "session",
                "phase": "practice",
                "activeActivity": "fish",
            }
        assert action == "turn"
        seen.append(kwargs["requestId"])
        return {"text": "Respuesta", "emotion": "happy"}

    monkeypatch.setattr(service, "web", web)
    monkeypatch.setattr(service, "transcribe", lambda pcm: "Pregunta del alumno")
    monkeypatch.setattr(service, "speak", lambda text: bytes(3200))
    with TestClient(service.app) as client:
        response = client.post(
            "/v1/education/turn",
            headers={"X-Mochi-Turn-ID": identity.hex},
            content=bytes(3200),
        )
    assert response.status_code == 200
    assert seen == [str(identity)]


@pytest.mark.parametrize("session_changed", [False, True])
def test_unavailable_tutor_speaks_service_status_and_revalidates_binding(
    service, monkeypatch, session_changed
):
    checks = iter(["session-a", "session-b" if session_changed else "session-a"])
    turns = []

    async def web(action, **kwargs):
        if action == "events":
            return {"sessionId": next(checks), "phase": "practice", "activeActivity": "fish"}
        assert action == "turn"
        turns.append(kwargs["requestId"])
        raise HTTPException(503, "education_request_denied")

    def speak(text):
        assert text == service.UNAVAILABLE_SPEECH
        return bytes(3200)

    monkeypatch.setattr(service, "web", web)
    monkeypatch.setattr(service, "transcribe", lambda pcm: "Pregunta de prueba")
    monkeypatch.setattr(service, "speak", speak)
    identity = uuid4()
    with TestClient(service.app) as client:
        response = client.post(
            "/v1/education/turn",
            headers={"X-Mochi-Turn-ID": identity.hex},
            content=bytes(3200),
        )
    assert turns == [str(identity)]
    assert response.status_code == (409 if session_changed else 200)


@pytest.mark.parametrize("session_changed", [False, True])
def test_quiet_recording_gets_spoken_retry_without_a_tutor_turn(
    service, monkeypatch, session_changed
):
    checks = iter(["session-a", "session-b" if session_changed else "session-a"])

    async def web(action, **kwargs):
        assert action == "events"
        return {"sessionId": next(checks), "phase": "practice", "activeActivity": "fish"}

    def speak(text):
        assert text == service.RETRY_SPEECH
        return bytes(3200)

    monkeypatch.setattr(service, "web", web)
    monkeypatch.setattr(service, "speak", speak)
    with TestClient(service.app) as client:
        response = client.post(
            "/v1/education/turn",
            headers={"X-Mochi-Turn-ID": uuid4().hex, "X-Mochi-Stream": "pcm16"},
            content=bytes(3200),
        )
    assert response.status_code == (409 if session_changed else 200)
    if not session_changed:
        assert response.headers["x-mochi-stream"] == "pcm16"
        assert response.content == bytes(3200)


@pytest.mark.parametrize("changed_key", ["sessionId", "phase", "activeActivity"])
def test_event_speech_uses_server_text_and_rejects_a_changed_binding(
    service, monkeypatch, changed_key
):
    before = {"sessionId": "session-a", "phase": "practice", "activeActivity": "fish"}
    after = {**before, changed_key: "changed"}
    calls = []
    checks = iter([before, after])

    async def web(action, **kwargs):
        if action == "events":
            return next(checks)
        assert action == "say-text"
        return {"text": "Pista autorizada", "mood": "think"}

    monkeypatch.setattr(service, "web", web)
    monkeypatch.setattr(
        service, "speak", lambda text: (calls.append(text) or bytes(3200))
    )
    with TestClient(service.app) as client:
        result = client.post(
            "/v1/education/say",
            json={"eventId": str(uuid4()), "text": "Texto introducido por el cliente"},
        )
    assert result.status_code == 409
    assert calls == ["Pista autorizada"]


def test_hermes_uses_only_the_restricted_endpoint_and_fresh_sessions(
    service, monkeypatch
):
    requests = []

    def route(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"text":"con fuentes"}'},
                    }
                ]
            },
        )

    original = httpx.Client
    monkeypatch.setattr(service, "MODEL", "http://hermes/p/peluqo/v1")
    monkeypatch.setattr(service, "MODEL_KEY", "h" * 64)
    monkeypatch.setattr(
        service.httpx,
        "Client",
        lambda **kw: original(transport=httpx.MockTransport(route), **kw),
    )
    service.model_answer("Instrucciones autorizadas", {"sources": []}, 400)
    service.model_answer("Instrucciones autorizadas", {"sources": []}, 400)
    import json

    assert all(
        str(r.url) == "http://hermes/p/peluqo/v1/chat/completions" for r in requests
    )
    assert all(
        json.loads(r.content)["tools"] == []
        and json.loads(r.content)["tool_choice"] == "none"
        for r in requests
    )
    assert (
        requests[0].headers["x-hermes-session-id"]
        != requests[1].headers["x-hermes-session-id"]
    )


def test_provider_audio_must_be_pcm_and_have_bounded_even_length(
    service, monkeypatch, tmp_path
):
    key = tmp_path / "voice-key"
    key.write_text("private-test-key" * 4)
    monkeypatch.setattr(service, "VOICE_KEY_FILE", str(key))
    monkeypatch.setattr(service, "VOICE_ID", "educational-voice")
    original = httpx.Client

    def route(request):
        assert request.headers["xi-api-key"] == "private-test-key" * 4
        assert request.url.params["output_format"] == "pcm_16000"
        return httpx.Response(
            200, headers={"content-type": "audio/mpeg"}, content=b"ID3untrusted"
        )

    monkeypatch.setattr(
        service.httpx,
        "Client",
        lambda **kw: original(transport=httpx.MockTransport(route), **kw),
    )
    with pytest.raises(HTTPException) as error:
        service.speak("Hola")
    assert error.value.status_code == 502


def test_local_result_forwards_device_token_and_bounded_evidence(service, monkeypatch):
    identity = str(uuid4())
    seen = []

    async def web(action, **kwargs):
        seen.append((action, kwargs))
        return {"accepted": True, "resultId": identity}

    monkeypatch.setattr(service, "web", web)
    body = {"resultId": identity, "lessonId": str(uuid4()), "assignmentId": str(uuid4()),
            "completed": True, "attempts": 1, "hints": 0, "elapsedSeconds": 20,
            "answers": [{"a": 3, "b": 4, "choice": 12, "correct": True}]}
    with TestClient(service.app) as client:
        reply = client.post("/v1/education/result", headers={"Authorization": "Bearer device-test"}, json=body)
        assert reply.status_code == 200
        assert reply.json() == {"accepted": True, "resultId": identity}
        assert client.post("/v1/education/result", json={**body, "attempts": 2}).status_code == 400
        assert client.post("/v1/education/result", json={**body, "answers": body["answers"] * 41}).status_code == 422
    assert len(seen) == 1
    assert seen[0][0] == "lesson-result"
    assert seen[0][1]["token"] == "device-test"
    assert seen[0][1]["assignmentId"] == body["assignmentId"]


@pytest.mark.parametrize("lesson_changed", [False, True])
def test_local_lesson_voice_does_not_need_a_web_session_and_revalidates(service, monkeypatch, lesson_changed):
    first = {"id": str(uuid4()), "assignmentId": str(uuid4()), "kind": "multiplication", "factors": [[3, 4]]}
    last = {**first, "id": str(uuid4())} if lesson_changed else first
    states = iter([first, last])
    seen = []

    async def web(action, **kwargs):
        assert action == "events"
        return {"sessionId": None, "localLesson": next(states)}

    def dialogue(question, lesson, model, language="es"):
        assert language == "es"
        seen.append((question, lesson))
        return {"text": "¿Me enseñas a formar tres grupos?", "emotion": "think"}

    monkeypatch.setattr(service, "web", web)
    monkeypatch.setattr(service, "dialogue_reply", dialogue)
    monkeypatch.setattr(service, "transcribe", lambda pcm: "Hoy hemos aprendido a multiplicar")
    monkeypatch.setattr(service, "speak", lambda text: bytes(3200))
    with TestClient(service.app) as client:
        response = client.post("/v1/education/turn", headers={"X-Mochi-Turn-ID": str(uuid4()),
            "X-Mochi-Lesson-Id": first["id"], "X-Mochi-Lesson-Step": "0"}, content=bytes(3200))
    assert len(seen) == 1
    assert seen[0][1] == first
    assert response.status_code == (409 if lesson_changed else 200)
