"""Educational/safety boundaries, using fictional text and mocked inference."""
import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException

spec = importlib.util.spec_from_file_location("lesson_dialogue", Path(__file__).with_name("lesson_dialogue.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

LESSON = {"kind": "multiplication", "title": "Construimos una casa", "instructions": "Explica tus agrupaciones", "factors": [[3, 4], [4, 3], [2, 6]]}


def test_teacher_task_is_context_not_automatic_grading_or_history():
    seen = []
    def generate(instructions, content, tokens):
        seen.append((instructions, content, tokens))
        return {"text": "¿Cómo harías grupos iguales para enseñármelo?", "emotion": "think", "grade": 10}
    result = module.dialogue_reply("Hoy aprendí a multiplicar", LESSON, generate)
    assert result == {"text": "¿Cómo harías grupos iguales para enseñármelo?", "emotion": "think"}
    assert set(seen[0][1]) == {"question", "task"}
    assert seen[0][1]["task"]["factors"] == LESSON["factors"]


def test_explicit_harm_gets_safe_reply_without_inference_or_automatic_sharing():
    def forbidden(*args):
        raise AssertionError("An explicit disclosure must not depend on inference")
    result = module.dialogue_reply("Hay unos niños que me pegan en el recreo", LESSON, forbidden)
    assert "No es culpa tuya" in result["text"]
    assert "adulto de confianza" in result["text"]
    assert "padres" not in result["text"]
    demo = module.safeguarding_demo()
    assert demo["simulation"]
    assert not demo["automaticNotificationSent"]
    assert not demo["fullConversationShared"]


@pytest.mark.parametrize("question", ["Estoy triste", "No sé multiplicar", "¿Qué significa bullying?", "Me gusta el recreo"])
def test_feeling_or_school_topic_does_not_trigger_explicit_harm_route(question):
    assert module.explicit_support(question) is None


@pytest.mark.parametrize("factors", [[], [[0, 3]], [[3, True]], [[13, 2]], [[2]], [[2, 3]] * 6])
def test_rejects_unbounded_or_invalid_task_before_model(factors):
    with pytest.raises(HTTPException) as error:
        module.dialogue_reply("Ayúdame", {**LESSON, "factors": factors}, lambda *args: pytest.fail("model called"))
    assert error.value.status_code == 400


@pytest.mark.parametrize("result", [{"text": "", "emotion": "happy"}, {"text": "x" * 701, "emotion": "happy"}, {"text": "Respuesta", "emotion": "angry"}, []])
def test_model_output_is_validated(result):
    with pytest.raises(HTTPException) as error:
        module.dialogue_reply("¿Cómo hago grupos?", LESSON, lambda *args: result)
    assert error.value.status_code == 502
