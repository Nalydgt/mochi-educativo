"""Accessible dialogue: same permissions and consent without microphone or TTS."""
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


@pytest.fixture
def chat(monkeypatch):
    spec = importlib.util.spec_from_file_location("text_connector", Path(__file__).with_name("app.py"))
    service = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(service)
    state = {"deviceId": "fictional-paired-device", "deviceSettings": {
        "voiceEnabled": False, "startTime": "00:00", "endTime": "00:00", "language": "es",
        "revision": 1, "familySupportAlertsEnabled": True,
    }}
    calls = []
    async def web(action, **kwargs):
        calls.append((action, kwargs))
        return {"accepted": True, "visibleToFamily": True} if action == "support-signal" else state
    monkeypatch.setattr(service, "web", web)
    monkeypatch.setattr(service, "claim_turn", lambda *args: calls.append(("admitted", args)))
    monkeypatch.setattr(service, "daily_reply", lambda *args: {"text": "Podemos formar grupos juntos.", "emotion": "think"})
    monkeypatch.setattr(service, "speak", lambda *args: pytest.fail("Text must not synthesize audio"))
    monkeypatch.setattr(service, "transcribe", lambda *args: pytest.fail("Text must not load ASR"))
    return service, state, calls


def post(client, question, **extra):
    return client.post("/v1/education/text", headers={"Authorization": "Bearer fictional-text-device"},
        json={"requestId": str(uuid4()), "question": question, **extra})


def test_text_works_with_voice_disabled_and_keeps_ephemeral_follow_up(chat, monkeypatch):
    service, state, calls = chat
    history = []
    def daily(question, state, previous, generate):
        history.append(previous)
        assert any(action == "admitted" for action, _ in calls)
        return {"text": "Podemos formar grupos juntos.", "emotion": "think"}
    monkeypatch.setattr(service, "daily_reply", daily)
    with TestClient(service.app) as client:
        for _ in range(2):
            reply = post(client, "Hoy aprendí a sumar")
            assert reply.status_code == 200
            assert reply.json()["channel"] == "text"
            assert reply.headers["cache-control"] == "no-store"
    assert len(history[0]) == 0 and len(history[1]) == 2


@pytest.mark.parametrize("change", ["unpair", "policy"])
def test_revalidate_before_return_or_remember(chat, monkeypatch, change):
    service, state, calls = chat
    async def web(action, **kwargs):
        if calls:
            return {**state, "deviceId": None} if change == "unpair" else {**state, "deviceSettings": {**state["deviceSettings"], "revision": 2}}
        calls.append((action, kwargs))
        return state
    monkeypatch.setattr(service, "web", web)
    with TestClient(service.app) as client:
        assert post(client, "Hoy aprendí a sumar").status_code == 409
    assert service.CONVERSATIONS.get("fictional-text-device", "daily") == []


def test_confirmation_creates_only_minimal_text_signal_and_forgets_dialogue(chat):
    service, _, calls = chat
    with TestClient(service.app) as client:
        first = post(client, "En el colegio mis compañeros me insultan.")
        assert first.status_code == 200 and "¿Quieres" in first.json()["text"]
        assert all(action != "support-signal" for action, _ in calls)
        assert "He dejado un aviso" in post(client, "Sí, avisa a mi familia.").json()["text"]
    receipts = [payload for action, payload in calls if action == "support-signal"]
    assert len(receipts) == 1
    assert receipts[0]["source"] == "daily_text"
    assert set(receipts[0]) == {"token", "signalId", "source", "category", "schoolPeerContext", "childConfirmed"}
    assert service.CONVERSATIONS.get("fictional-text-device", "daily") == []


@pytest.mark.parametrize("question,extra,code", [(" ", {}, 400), ("a\x00b", {}, 400),
    ("x" * 501, {}, 422), ("hola", {"transcript": "unexpected"}, 422),
    ("seis", {"step": 0}, 400), ("seis", {"step": 0, "lessonId": str(uuid4())}, 409)])
def test_reject_invalid_inputs_before_inference(chat, monkeypatch, question, extra, code):
    service, _, _ = chat
    monkeypatch.setattr(service, "daily_reply", lambda *args: pytest.fail("No inference for invalid input"))
    with TestClient(service.app) as client:
        assert post(client, question, **extra).status_code == code


def test_valid_typed_number_is_bound_to_approved_question(chat):
    service, state, _ = chat
    identity = str(uuid4())
    state["localLesson"] = {"id": identity, "kind": "multiplication", "factors": [[3, 2]]}
    with TestClient(service.app) as client:
        reply = post(client, "seis", lessonId=identity, step=0)
    assert reply.status_code == 200
    assert {key: reply.json()[key] for key in ("answer", "lessonId", "step")} == {"answer": 6, "lessonId": identity, "step": 0}


def test_schedule_denial_happens_before_admission(chat, monkeypatch):
    service, _, calls = chat
    monkeypatch.setattr(service, "assert_text_allowed", lambda *args: (_ for _ in ()).throw(HTTPException(403, "outside_authorized_schedule")))
    with TestClient(service.app) as client:
        assert post(client, "Hola").status_code == 403
    assert all(action != "admitted" for action, _ in calls)
