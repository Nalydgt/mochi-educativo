"""Product behavior: everyday dialogue, private context, schedules and teacher drafts."""
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


def module(name):
    spec = importlib.util.spec_from_file_location("product_" + name, Path(__file__).with_name(name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


policy, context, dialogue = module("voice_policy"), module("conversation_context"), module("lesson_dialogue")


def test_midnight_schedule_and_time_zone_are_checked_on_server():
    state = {"deviceSettings": {"voiceEnabled": True, "startTime": "22:00", "endTime": "06:00", "timezone": "Europe/Madrid", "language": "es"}}
    policy.assert_voice_allowed(state, now=datetime(2026, 11, 5, 22, 0, tzinfo=timezone.utc))
    with pytest.raises(HTTPException) as closed:
        policy.assert_voice_allowed(state, now=datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc))
    assert closed.value.status_code == 403
    with pytest.raises(HTTPException):
        policy.assert_voice_allowed({"deviceSettings": {**state["deviceSettings"], "voiceEnabled": False}})


def test_context_is_private_bounded_expiring_and_not_shared_across_topics():
    cache = context.ConversationContext(ttl=10, capacity=2)
    cache.remember("a-secret-token", "daily", "Tengo tres grupos", "¿Cuántos en cada uno?", now=1)
    assert cache.get("a-secret-token", "daily", now=2)[0]["content"] == "Tengo tres grupos"
    assert cache.get("other-token", "daily", now=2) == []
    assert cache.get("a-secret-token", "different-task", now=2) == []
    assert "a-secret-token" not in cache._entries
    assert cache.get("a-secret-token", "daily", now=11) == []
    cache.remember("a", "daily", "a", "a", now=20)
    cache.remember("b", "daily", "b", "b", now=20)
    cache.remember("c", "daily", "c", "c", now=20)
    assert cache.get("a", "daily", now=20) == []
    cache.forget("b")
    assert cache.get("b", "daily", now=20) == []


def test_daily_tutor_uses_only_academic_summary_and_short_context():
    seen = []
    def generate(instructions, content, tokens):
        seen.append(content)
        return {"text": "¿Me enseñas con un grupo distinto?", "emotion": "think"}
    state = {"educationalProfile": {"ageBand": "6–8", "privateConversation": "must not be used"}, "learningSummary": {"lastConcepts": ["Grupos iguales"], "privateNotes": "must not be used"}}
    dialogue.daily_reply("Hoy aprendí multiplicaciones", state, [{"role": "user", "content": "Tengo tres grupos"}], generate)
    assert seen[0]["learningSummary"] == {"lastConcepts": ["Grupos iguales"]}
    assert seen[0]["profile"]["ageBand"] == "6–8"
    assert "privateConversation" not in str(seen)
    assert "privateNotes" not in str(seen)


def test_assignment_proposal_is_validated_and_never_publishes():
    proposal = {"title": "Grupos de plantas", "goal": "Comprender los grupos iguales", "instructions": "Enséñame a contar los grupos.", "factors": [[2, 3], [3, 2]]}
    result = dialogue.lesson_proposal("Jardín de grupos", 2, [], lambda *args: proposal)
    assert result["suggested"] is True
    assert "assignmentId" not in result
    with pytest.raises(HTTPException) as invalid:
        dialogue.lesson_proposal("Jardín de grupos", 2, [], lambda *args: {**proposal, "factors": [[99, 2], [1, 1]]})
    assert invalid.value.status_code == 502


def connector(monkeypatch):
    service = module("app")
    monkeypatch.setattr(service, "claim_turn", lambda *args: None)
    return service


@pytest.mark.parametrize("pending_homework", [False, True])
def test_daily_dialogue_without_homework_or_web_login(monkeypatch, pending_homework):
    service = connector(monkeypatch)
    async def web(action, **kwargs):
        assert action == "events"
        return {"deviceId": "paired-device", "sessionId": None,
                "localLesson": {"id": str(UUID(int=1)), "kind": "multiplication", "factors": [[3, 4]]} if pending_homework else None}
    seen = []
    def daily(question, state, history, model):
        seen.append(history)
        return {"text": "Cuéntame cómo haces los grupos.", "emotion": "think"}
    monkeypatch.setattr(service, "web", web)
    monkeypatch.setattr(service, "daily_reply", daily)
    monkeypatch.setattr(service, "transcribe", lambda pcm: "Hoy aprendí a multiplicar")
    monkeypatch.setattr(service, "speak", lambda text: bytes(6400))
    with TestClient(service.app) as client:
        for _ in range(2):
            reply = client.post("/v1/education/turn", headers={"Authorization": "Bearer fictional-device", "X-Mochi-Turn-ID": str(uuid4())}, content=bytes(3200))
            assert reply.status_code == 200
            assert reply.headers["x-mochi-education-reply"] == "daily"
    assert seen[0] == []
    assert len(seen[1]) == 2


def test_disabled_voice_is_denied_before_asr_or_inference(monkeypatch):
    service = connector(monkeypatch)
    async def web(action, **kwargs):
        return {"deviceId": "paired-device", "deviceSettings": {"voiceEnabled": False}}
    monkeypatch.setattr(service, "web", web)
    monkeypatch.setattr(service, "transcribe", lambda pcm: pytest.fail("ASR must not run"))
    with TestClient(service.app) as client:
        reply = client.post("/v1/education/turn", headers={"X-Mochi-Turn-ID": str(uuid4())}, content=bytes(3200))
    assert reply.status_code == 403


def test_voice_permission_is_checked_again_after_synthesis(monkeypatch):
    service = connector(monkeypatch)
    states = iter([{"deviceId": "paired", "deviceSettings": {"voiceEnabled": True, "revision": 1}}, {"deviceId": "paired", "deviceSettings": {"voiceEnabled": False, "revision": 2}}])
    async def web(action, **kwargs):
        return next(states)
    monkeypatch.setattr(service, "web", web)
    monkeypatch.setattr(service, "daily_reply", lambda *args: {"text": "Probemos juntos.", "emotion": "happy"})
    monkeypatch.setattr(service, "transcribe", lambda pcm: "Dos grupos")
    monkeypatch.setattr(service, "speak", lambda text: bytes(6400))
    with TestClient(service.app) as client:
        reply = client.post("/v1/education/turn", headers={"X-Mochi-Turn-ID": str(uuid4())}, content=bytes(3200))
    assert reply.status_code == 403
    assert reply.headers.get("x-mochi-sample-rate") is None
