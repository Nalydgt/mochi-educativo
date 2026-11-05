"""Speech scoring is deterministic and tied to the device's current task/step."""
import base64
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


def load(name):
    spec = importlib.util.spec_from_file_location("spoken_test_" + name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


numbers = load("spoken_numbers")


@pytest.mark.parametrize("text,answer", [("seis", 6), ("Son seis.", 6), ("Creo que es veintidós", 22), ("ciento cuarenta y cuatro", 144), ("The answer is six", 6), ("vinte e dois", 22), ("0", 0),
    ("Hay seis peces", 6), ("La respuesta seis", 6), ("Respuesta es seis.", 6), ("Respuesta seis", 6), ("El resultado es seis", 6), ("Son seis manzanas en total", 6),
    ("twenty-two", 22), ("one hundred six", 106), ("dezesseis", 16), ("A resposta é seis", 6)])
def test_explicit_numeric_answers(text, answer):
    assert numbers.spoken_answer(text) == answer


@pytest.mark.parametrize("text", ["¿Son seis?", "Me pegan seis veces", "Tengo tres amigos", "seis o siete", "145", "no sé", "dame la respuesta", "me gustan seis", "me gustan seis manzanas", "seis o siete peces", "-6", "menos seis", "Hay seis peces?"])
def test_mentions_questions_and_disclosures_are_not_scored(text):
    assert numbers.spoken_answer(text) is None


def test_answer_diagnostics_never_include_words_or_number_values():
    shape = numbers.speech_shape("La respuesta es seis")
    assert shape == {"characters": 20, "words": 4, "question": False, "answer_prefix": True, "number_word": True, "numeric_match": True}
    assert all(type(value) in {bool, int} for value in shape.values())


def service(monkeypatch, question="seis"):
    module = load("app")
    monkeypatch.setattr(module, "claim_turn", lambda *args: None)
    lesson = {"id": str(uuid4()), "assignmentId": str(uuid4()), "kind": "multiplication", "factors": [[2, 3]], "instructions": "Enséñame a contar grupos."}
    async def web(action, **kwargs):
        assert action == "events"
        return {"deviceId": "paired", "localLesson": lesson}
    monkeypatch.setattr(module, "web", web)
    monkeypatch.setattr(module, "transcribe", lambda pcm: question)
    monkeypatch.setattr(module, "model_answer", lambda *args: pytest.fail("Arithmetic correction must not depend on a model"))
    monkeypatch.setattr(module, "speak", lambda text: bytes(6400))
    return module, lesson


def test_spoken_answer_echoes_bound_step_and_full_caption(monkeypatch):
    module, lesson = service(monkeypatch)
    with TestClient(module.app) as client:
        reply = client.post("/v1/education/turn", headers={"X-Mochi-Turn-ID": str(uuid4()), "X-Mochi-Lesson-ID": lesson["id"], "X-Mochi-Lesson-Step": "0"}, content=bytes(3200))
    assert reply.status_code == 200
    assert reply.headers["x-mochi-education-reply"] == "spoken-answer"
    assert reply.headers["x-mochi-lesson-answer"] == "6"
    assert reply.headers["x-mochi-lesson-id"] == lesson["id"]
    caption = base64.b64decode(reply.headers["x-mochi-caption-1"]).decode("utf-8")
    assert "Lo he entendido" in caption


def test_stale_spoken_context_is_rejected_before_recognition(monkeypatch):
    module, lesson = service(monkeypatch)
    monkeypatch.setattr(module, "transcribe", lambda pcm: pytest.fail("Stale task must not reach ASR"))
    with TestClient(module.app) as client:
        reply = client.post("/v1/education/turn", headers={"X-Mochi-Turn-ID": str(uuid4()), "X-Mochi-Lesson-ID": str(uuid4()), "X-Mochi-Lesson-Step": "0"}, content=bytes(3200))
    assert reply.status_code == 409


def test_question_speech_contains_teacher_instructions_and_no_child_audio_capture(monkeypatch):
    module, lesson = service(monkeypatch)
    spoken = []
    monkeypatch.setattr(module, "speak", lambda text: spoken.append(text) or bytes(6400))
    with TestClient(module.app) as client:
        reply = client.post("/v1/education/say", json={"cue": "question", "requestId": str(uuid4()), "lessonId": lesson["id"], "step": 0})
    assert reply.status_code == 200
    assert lesson["instructions"] in spoken[0]
    assert "2 cestas" in spoken[0] and "3 manzanas" in spoken[0]


@pytest.mark.parametrize("step,groups,items", [(0, "2 cestas", "3 manzanas"), (1, "3 estanques", "2 peces"), (2, "2 cajas", "4 coches de juguete")])
def test_question_voice_matches_each_illustrated_scene(monkeypatch, step, groups, items):
    module, lesson = service(monkeypatch)
    lesson["factors"] = [[2, 3], [3, 2], [2, 4]]
    spoken = []
    monkeypatch.setattr(module, "speak", lambda text: spoken.append(text) or bytes(6400))
    with TestClient(module.app) as client:
        reply = client.post("/v1/education/say", json={"cue": "question", "requestId": str(uuid4()), "lessonId": lesson["id"], "step": step})
    assert reply.status_code == 200
    assert groups in spoken[0] and items in spoken[0]
    assert (lesson["instructions"] in spoken[0]) == (step == 0)


def test_long_unicode_captions_are_complete_and_each_header_is_bounded():
    module = load("app")
    text = "🌿" * 700
    headers = module.caption_headers(text)
    assert max(map(len, headers.values())) <= 960
    encoded = "".join(headers.values())
    assert base64.b64decode(encoded).decode("utf-8") == text


@pytest.mark.parametrize("language,question,expected", [("en", "six", "I understand"), ("pt", "seis", "Já percebi")])
def test_spoken_feedback_and_synthesis_follow_adult_language(monkeypatch, language, question, expected):
    module, lesson = service(monkeypatch, question)
    async def web(action, **kwargs):
        return {"deviceId": "paired", "localLesson": lesson, "deviceSettings": {"language": language, "voiceEnabled": True}}
    monkeypatch.setattr(module, "web", web)
    monkeypatch.setattr(module, "transcribe", lambda pcm, actual: question if actual == language else pytest.fail("ASR language"))
    spoken = []
    def synthesize(text, actual):
        assert actual == language
        spoken.append(text)
        return bytes(6400)
    monkeypatch.setattr(module, "speak", synthesize)
    with TestClient(module.app) as client:
        reply = client.post("/v1/education/turn", headers={"X-Mochi-Turn-ID": str(uuid4()), "X-Mochi-Lesson-ID": lesson["id"], "X-Mochi-Lesson-Step": "0"}, content=bytes(3200))
    assert reply.status_code == 200
    assert expected in spoken[0]


def test_minimal_completion_does_not_transmit_answers(monkeypatch):
    module = load("app")
    seen = []
    async def web(action, **kwargs):
        seen.append((action, kwargs))
        return {"accepted": True, "resultId": kwargs["resultId"]}
    monkeypatch.setattr(module, "web", web)
    body = {"resultId": str(uuid4()), "lessonId": str(uuid4()), "assignmentId": str(uuid4()), "completed": True,
            "attempts": 4, "hints": 1, "elapsedSeconds": 20, "detailsShared": False, "completedCount": 3, "answers": []}
    with TestClient(module.app) as client:
        assert client.post("/v1/education/result", json=body).status_code == 200
        assert client.post("/v1/education/result", json={**body, "answers": [{"a": 1, "b": 1, "choice": 1, "correct": True}]}).status_code == 400
    assert len(seen) == 1
    assert seen[0][1]["answers"] == []
