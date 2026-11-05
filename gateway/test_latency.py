import logging
import time

from fastapi.testclient import TestClient
import pytest

from app import Settings, create_app

TOKEN = "latency-private-token-" + "x" * 32
AUTH = {"Authorization": "Bearer " + TOKEN}


class Brain:
    def ready(self):
        return True

    def reply(self, messages):
        time.sleep(.025)
        return {"text": "respuesta privada", "emotion": "happy"}


class Speech:
    def __init__(self):
        self.loads = 0

    def warmup(self):
        self.loads += 1

    def transcribe(self, pcm):
        assert self.loads == 1
        time.sleep(.015)
        return "transcripción privada"

    def speak(self, text):
        assert self.loads == 1
        time.sleep(.015)
        return b"\x01\x02" * 1600


def test_models_are_loaded_once_before_the_first_turn(tmp_path):
    speech = Speech()
    application = create_app(Settings(TOKEN, tmp_path, tmp_path / "voice.onnx"), Brain(), speech)
    assert speech.loads == 0 and not application.state.speech_ready
    with TestClient(application) as client:
        assert client.get("/health", headers=AUTH).json()["speech_loaded"]
        headers = {**AUTH, "Content-Type": "application/octet-stream"}
        for _ in range(2):
            assert client.post("/v1/turn", headers=headers, content=b"\0\0" * 16000).status_code == 200
        assert speech.loads == 1


def test_failed_model_preload_does_not_advertise_readiness(tmp_path):
    class BrokenSpeech(Speech):
        def warmup(self):
            raise RuntimeError("model unavailable")

    application = create_app(Settings(TOKEN, tmp_path, tmp_path / "voice.onnx"), Brain(), BrokenSpeech())
    with pytest.raises(RuntimeError, match="model unavailable"):
        with TestClient(application):
            pytest.fail("The service must not serve before its speech models are loaded")
    assert not application.state.speech_ready


def test_turn_timings_distinguish_slow_stages_without_logging_private_content(tmp_path, caplog):
    application = create_app(Settings(TOKEN, tmp_path, tmp_path / "voice.onnx"), Brain(), Speech())
    headers = {**AUTH, "Content-Type": "application/octet-stream", "X-Device-ID": "private-device",
               "X-Mochi-Latitude": "40.1234", "X-Mochi-Longitude": "-3.4321"}
    with caplog.at_level(logging.INFO, logger="uvicorn.error"), TestClient(application) as client:
        response = client.post("/v1/turn", headers=headers, content=b"\0\0" * 16000)
    assert response.status_code == 200
    timings = {name: float(duration.removeprefix("dur="))
               for name, duration in (entry.split(";") for entry in response.headers["Server-Timing"].split(", "))}
    assert {"upload", "asr", "context", "hermes", "tts", "memory", "total"} == set(timings)
    assert timings["asr"] >= 10 and timings["hermes"] >= 20 and timings["tts"] >= 10
    assert timings["total"] >= sum(value for name, value in timings.items() if name != "total") - .1
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "asr_ms=" in messages and "hermes_ms=" in messages and "tts_ms=" in messages
    for private in (TOKEN, "private-device", "40.1234", "-3.4321", "transcripción privada", "respuesta privada"):
        assert private not in messages and private not in response.headers["Server-Timing"]


def test_latency_diagnostics_are_private_bounded_and_contain_no_conversation(tmp_path):
    from test_gateway import Brain as FastBrain
    application = create_app(Settings(TOKEN, tmp_path, tmp_path / "voice.onnx"), FastBrain(), Speech())
    with TestClient(application) as client:
        assert client.get('/v1/diagnostics/latency').status_code == 401
        response = client.post('/v1/chat', headers=AUTH,
            json={'text':'un texto privado','device_id':'private-device'})
        assert response.status_code == 200
        report = client.get('/v1/diagnostics/latency', headers=AUTH).json()
        sample = report['samples'][0]
        assert sample['phase'] == 'reply_ready' and sample['status'] == 200
        assert sample['stages_ms']['hermes'] >= 0
        for private in ('un texto privado','private-device',TOKEN,'Hola, me alegra verte.'):
            assert private not in str(report)
        for _ in range(70):client.post('/v1/chat',json={'text':'no autorizado'})
        report = client.get('/v1/diagnostics/latency',headers=AUTH).json()
        assert len(report['samples']) == report['capacity'] == 64


def test_hermes_prefix_is_warmed_once_before_readiness_without_device_history(tmp_path):
    import sqlite3
    class WarmBrain(Brain):
        warmed = 0
        def warmup(self):self.warmed += 1
    brain=WarmBrain()
    application=create_app(Settings(TOKEN,tmp_path,tmp_path/'voice.onnx',hermes_warmup=True),brain,Speech())
    with TestClient(application) as client:
        assert brain.warmed == 1
        assert client.get('/health',headers=AUTH).status_code == 200
        with sqlite3.connect(tmp_path/'memory.sqlite3') as db:
            assert db.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 0
        client.post('/v1/chat',headers=AUTH,json={'text':'Hola'})
        assert brain.warmed == 1


def test_startup_does_not_replay_real_conversations_to_the_agent(tmp_path):
    from app import Memory
    memory=Memory(tmp_path/'memory.sqlite3')
    memory.append_turn('mochi','Mi color favorito es azul.','El azul es bonito.')
    memory.append_turn('mochi-diagnostics-new','Pregunta sintetica.','Respuesta sintetica.')
    class WarmBrain(Brain):
        def __init__(self):self.calls=[]
        def warmup(self):pass
        def reply(self,messages):
            self.calls.append(messages)
            return super().reply(messages)
    brain=WarmBrain()
    application=create_app(Settings(TOKEN,tmp_path,tmp_path/'voice.onnx',hermes_warmup=True),brain,Speech())
    before=memory.history('mochi')
    with TestClient(application):
        assert brain.calls==[]
        assert memory.history('mochi')==before
        assert len(memory.history('mochi-diagnostics-new'))==2
