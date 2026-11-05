"""Family support is opt-in, child-confirmed, minimal and never a teacher message."""
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


def load(name):
    spec = importlib.util.spec_from_file_location("family_support_test_" + name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


support = load("family_support")


@pytest.mark.parametrize("text", ["Hay unos niños que me pegan en el recreo", "En el colegio se burlan de mí", "Mis compañeros me insultan en clase", "Kids bully me at school", "Na escola batem em mim"])
def test_explicit_peer_school_statements_offer_help(text):
    assert support.explicit_peer_disclosure(text)


@pytest.mark.parametrize("text", ["Estoy triste", "¿Qué es el bullying?", "En el colegio no me pegan", "Mi padre me pega en casa", "Los niños del colegio me pegan y no quiero que se entere mi familia", "En un cuento hay niños que me pegan en el recreo", "A mi amigo le pegan en el colegio", "¿Me pegan en el colegio?"])
def test_no_family_notice_from_tone_household_fiction_questions_or_refusal(text):
    assert not support.explicit_peer_disclosure(text)


def test_confirmation_is_isolated_single_use_and_only_immediately_next_utterance():
    pending = support.SupportConsent(ttl=10, capacity=2)
    episode = str(uuid4())
    pending.offer("private-token", episode, "daily_voice", now=1)
    assert pending.take("other-token", "sí", now=2) == (None, None)
    assert "private-token" not in pending._entries
    assert pending.take("private-token", "sí", now=2) == ("confirm", {"signalId": episode, "source": "daily_voice"})
    assert pending.take("private-token", "sí", now=2) == (None, None)
    pending.offer("private-token", episode, "daily_voice", now=3)
    assert pending.take("private-token", "Vamos a multiplicar", now=4) == (None, None)
    assert pending.take("private-token", "sí", now=4) == (None, None)
    pending.offer("private-token", episode, "daily_voice", now=5)
    assert pending.take("private-token", "sí", now=15) == (None, None)


def connector(monkeypatch, phrases, *, enabled=True, denied=False):
    module = load("app")
    state = {"deviceId": "paired", "localLesson": {"id": str(uuid4()), "kind": "multiplication", "factors": [[3, 4]]},
             "deviceSettings": {"voiceEnabled": True, "language": "es", "revision": 1, "familySupportAlertsEnabled": enabled}}
    seen = []
    spoken = []
    async def web(action, **kwargs):
        if action == "events":
            return state
        assert action == "support-signal"
        seen.append(kwargs)
        if denied:
            raise HTTPException(403, "denied")
        return {"accepted": True, "visibleToFamily": True}
    inputs = iter(phrases)
    monkeypatch.setattr(module, "web", web)
    monkeypatch.setattr(module, "claim_turn", lambda *args: None)
    monkeypatch.setattr(module, "transcribe", lambda pcm: next(inputs))
    monkeypatch.setattr(module, "speak", lambda text: spoken.append(text) or bytes(6400))
    monkeypatch.setattr(module, "daily_reply", lambda *args: {"text": "Podemos contar juntos.", "emotion": "think"})
    return module, seen, spoken


def turn(client, identity=None):
    return client.post("/v1/education/turn", headers={"Authorization": "Bearer fictional-support-token", "X-Mochi-Turn-ID": identity or str(uuid4())}, content=bytes(3200))


def test_notice_is_not_sent_until_child_confirms_and_never_contains_conversation(monkeypatch):
    module, seen, spoken = connector(monkeypatch, ["En el colegio se burlan de mí", "Sí, avisa a mi familia."])
    first = str(uuid4())
    with TestClient(module.app) as client:
        response = turn(client, first)
        assert response.status_code == 200 and response.headers["x-mochi-education-reply"] == "support"
        assert seen == []
        assert "¿Quieres" in spoken[0]
        assert turn(client).status_code == 200
    assert seen == [{"token": "fictional-support-token", "signalId": first, "source": "daily_voice", "category": "possible_peer_bullying", "schoolPeerContext": True, "childConfirmed": True}]
    assert "He dejado un aviso" in spoken[-1]
    assert module.CONVERSATIONS.get("fictional-support-token", "daily") == []


@pytest.mark.parametrize("phrases,enabled", [(["sí"], True), (["En el colegio me insultan", "no"], True), (["En el colegio me insultan", "Contemos", "sí"], True), (["En el colegio me insultan", "sí"], False), (["Mi padre me pega en casa", "sí"], True)])
def test_no_notice_without_both_consents_or_after_unrelated_speech(monkeypatch, phrases, enabled):
    module, seen, spoken = connector(monkeypatch, phrases, enabled=enabled)
    with TestClient(module.app) as client:
        for _ in phrases:
            assert turn(client).status_code == 200
    assert seen == []
    assert all("He dejado un aviso" not in text for text in spoken)


def test_backend_denial_never_claims_a_family_was_notified(monkeypatch):
    module, seen, spoken = connector(monkeypatch, ["En el colegio me insultan", "sí"], denied=True)
    with TestClient(module.app) as client:
        assert turn(client).status_code == 200
        assert turn(client).status_code == 200
    assert len(seen) == 1
    assert "no he podido confirmar" in spoken[-1]
