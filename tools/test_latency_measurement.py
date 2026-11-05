"""The latency report must never accept cached, malformed or failed delivery."""
import importlib.util
import hashlib
import io
from pathlib import Path
import wave

import pytest

spec = importlib.util.spec_from_file_location('latency_measurement', Path(__file__).with_name('Measure-MochiLatency.py'))
measurement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measurement)


@pytest.mark.parametrize('audio,cache,accepted', [(b'\x01\x02'*100, 'bypass', True),
                                               (b'\x01', 'bypass', False),
                                               (b'\x01\x02'*100, 'use', False)])
def test_goal_latency_gate_requires_complete_valid_uncached_response(tmp_path, monkeypatch, audio, cache, accepted):
    class Response(io.BytesIO):
        status = 200
        headers = {'X-Mochi-Sample-Rate': '16000', 'X-Mochi-Stream': 'pcm16',
                   'X-Mochi-Audio-Cache': cache}
    monkeypatch.setattr(measurement, 'urlopen', lambda *a, **kw: Response(audio))
    # The delivery gate needs valid PCM, not a stored speech corpus. Generate
    # its input locally so a clean source checkout contains no recordings.
    fixture = tmp_path / 'input'
    fixture.mkdir()
    source_pcm = b'\x01\x02' * 1600
    path = fixture / 'synthetic.wav'
    with wave.open(str(path), 'wb') as recording:
        recording.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        recording.writeframes(source_pcm)
    inputs = [{'index': 0, 'question': 'Synthetic delivery probe', 'file': path.name,
               'wav_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
               'pcm_sha256': hashlib.sha256(source_pcm).hexdigest()}]
    result = measurement.measure('http://test', 'unused', inputs, fixture, tmp_path/'report.json', target=2)
    assert result['near_immediate_verified'] is accepted
    assert result['all_responses_valid'] is accepted
    assert result['physical_first_sound_measured'] is False
