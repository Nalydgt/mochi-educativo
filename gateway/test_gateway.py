from pathlib import Path
import io
import wave

from fastapi.testclient import TestClient
import numpy as np
import pytest

from app import Settings, create_app
from hermes_bridge import HermesUnavailable
from speech import wav_to_pcm16

TOKEN = "a" * 40
HEADERS = {"Authorization": "Bearer " + TOKEN}


class Brain:
    def __init__(self):
        self.calls = []
        self.fail = False

    def ready(self):
        return True

    def reply(self, messages):
        self.calls.append(messages)
        if self.fail:
            raise HermesUnavailable("private upstream diagnostic")
        return {"text": "Hola, me alegra verte.", "emotion": "happy"}


class Speech:
    def transcribe(self, pcm):
        return "Hola Mochi"

    def speak(self, text):
        return b"\x00\x01" * 1600


@pytest.fixture
def setup(tmp_path):
    brain = Brain()
    app = create_app(Settings(TOKEN, tmp_path, tmp_path / "voice.onnx"), brain, Speech())
    return TestClient(app), brain, app


def test_requires_auth_before_processing_audio(setup):
    client, brain, _ = setup
    assert client.get("/health").status_code == 401
    assert client.post("/v1/turn", content=b"x" * 5000).status_code == 401
    assert not brain.calls


def test_failed_model_prewarm_keeps_recovery_http_available_without_faking_answers(tmp_path):
    class UnavailableBrain(Brain):
        def ready(self):return False
        def warmup(self):raise HermesUnavailable('private model diagnostic')
    class Local(Speech):
        def warmup(self):pass
    brain=UnavailableBrain();brain.fail=True
    app=create_app(Settings(TOKEN,tmp_path,tmp_path/'voice.onnx',hermes_warmup=True),brain,Local())
    with TestClient(app) as client:
        health=client.get('/health',headers=HEADERS)
        assert health.status_code==200
        assert health.json()['speech_loaded'] is True
        assert health.json()['profile_ready'] is False
        response=client.post('/v1/chat',headers=HEADERS,json={'text':'Hola'})
        assert response.status_code==503
        assert 'private model diagnostic' not in response.text
        assert app.state.memory.history('mochi')==[]


def test_history_survives_new_app_and_is_separate_per_device(setup, tmp_path):
    client, brain, _ = setup
    assert client.post("/v1/chat", headers=HEADERS, json={"text": "Me llamo Dylan", "device_id": "a"}).status_code == 200
    app = create_app(Settings(TOKEN, tmp_path, tmp_path / "voice.onnx"), brain, Speech())
    client = TestClient(app)
    client.post("/v1/chat", headers=HEADERS, json={"text": "Recuerdas mi nombre?", "device_id": "a"})
    assert brain.calls[-1][0]["content"] == "Me llamo Dylan"
    client.post("/v1/chat", headers=HEADERS, json={"text": "Hola", "device_id": "b"})
    assert len(brain.calls[-1]) == 1


def test_upstream_failure_does_not_store_an_unanswered_turn(setup):
    client, brain, app = setup
    brain.fail = True
    response = client.post("/v1/chat", headers=HEADERS, json={"text": "Hola"})
    assert response.status_code == 503
    assert "private upstream" not in response.text
    assert app.state.memory.history("mochi") == []


def test_voice_contract_and_input_limits(setup):
    client, _, _ = setup
    headers = {**HEADERS, "Content-Type": "application/octet-stream", "X-Device-ID": "mochi-1"}
    response = client.post("/v1/turn", headers=headers, content=b"\x00\x00" * 16000)
    assert response.status_code == 200
    assert response.headers["x-mochi-emotion"] == "happy"
    assert response.headers["x-mochi-sample-rate"] == "16000"
    assert len(response.content) == 3200
    assert client.post("/v1/turn", headers=headers, content=b"x" * 256002).status_code == 413
    assert client.post("/v1/turn", headers=headers, content=b"x" * 5001).status_code == 422


def test_resampling_converts_stereo_to_mono_and_preserves_duration():
    buffer = io.BytesIO()
    samples = np.column_stack((np.full(24000, 1000, dtype="<i2"), np.full(24000, 3000, dtype="<i2")))
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(samples.tobytes())
    pcm = np.frombuffer(wav_to_pcm16(buffer.getvalue()), dtype="<i2")
    assert len(pcm) == 16000
    assert np.all(pcm == 2000)


def test_fails_closed_without_a_device_secret(tmp_path):
    with pytest.raises(RuntimeError, match="MOCHI_TOKEN"):
        create_app(Settings("", tmp_path, Path("missing")))


def test_voice_preview_requires_auth_and_does_not_change_memory(setup):
    client, brain, app = setup
    assert client.post("/v1/say", json={"text": "Hola"}).status_code == 401
    response = client.post("/v1/say", headers=HEADERS, json={"text": "Hola, soy Mochi"})
    assert response.status_code == 200
    assert response.headers["x-mochi-sample-rate"] == "16000"
    assert app.state.memory.history("mochi") == []
    assert not brain.calls


def test_cute_pitch_preserves_device_sample_rate():
    rate = 22050
    buffer = io.BytesIO()
    samples = (np.sin(np.arange(rate) * 2 * np.pi * 440 / rate) * 10000).astype("<i2")
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(samples.tobytes())
    pcm = np.frombuffer(wav_to_pcm16(buffer.getvalue(), pitch_semitones=3), dtype="<i2")
    frequencies = np.fft.rfftfreq(len(pcm), d=1/16000)
    peak = frequencies[np.abs(np.fft.rfft(pcm)).argmax()]
    assert abs(peak - 440 * 2 ** .25) < 3
    assert len(pcm) == round(16000 / 2 ** .25)
