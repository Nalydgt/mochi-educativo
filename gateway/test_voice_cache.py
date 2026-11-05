from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from app import Settings
from voice_cache import AudioCache
from voice_service import VoiceService

PCM = b"\x01\x02" * 1600


def test_replacing_local_weights_or_configuration_never_reuses_old_voice(tmp_path):
    class Local:
        def __init__(self,pcm):self.pcm=pcm
        def speak(self,text):return self.pcm
    path=tmp_path/'voice.onnx';path.write_bytes(b'old weights')
    config=path.with_suffix('.onnx.json');config.write_text('{"phonemes":"old"}')
    settings=Settings('a'*40,tmp_path,path)
    old=VoiceService(settings,Local(PCM))
    assert old.speak('Hola')==PCM
    path.write_bytes(b'replacement weights')
    new_pcm=b'\x03\x04'*1600
    replacement=VoiceService(settings,Local(new_pcm))
    assert replacement.local_id!=old.local_id
    assert replacement.speak('Hola')==new_pcm
    config.write_text('{"phonemes":"new"}')
    reconfigured=VoiceService(settings,Local(new_pcm))
    assert reconfigured.local_id!=replacement.local_id
    assert old.cache.get(old.local_id,'Hola')==PCM
    assert replacement.cache.get(replacement.local_id,'Hola')==new_pcm


def test_reuse_survives_restart_and_preserves_voice_and_punctuation(tmp_path):
    cache = AudioCache(tmp_path / "cache.db")
    calls = []
    def generate(text):
        calls.append(text)
        return PCM
    assert cache.render("voice-a", "  ¡Hola!\n", generate) == PCM
    cache = AudioCache(tmp_path / "cache.db")
    assert cache.render("voice-a", "¡Hola!", generate) == PCM
    assert len(calls) == 1
    cache.render("voice-b", "¡Hola!", generate)
    cache.render("voice-a", "¡Hola?", generate)
    assert len(calls) == 3


def test_concurrent_requests_generate_only_once(tmp_path):
    cache = AudioCache(tmp_path / "cache.db")
    calls = []
    def generate(text):
        calls.append(text)
        return PCM
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(pcm == PCM for pcm in pool.map(lambda _: cache.render("v", "Hola", generate), range(8)))
    assert calls == ["Hola"]


def test_cached_phrase_does_not_wait_for_another_synthesis(tmp_path):
    cache = AudioCache(tmp_path / 'cache.db')
    cache.put('v', 'Guardada', PCM)
    started, finish = threading.Event(), threading.Event()
    def generate(text):
        started.set()
        assert finish.wait(3)
        return PCM
    with ThreadPoolExecutor(max_workers=2) as pool:
        generating = pool.submit(cache.render, 'v', 'Nueva', generate)
        try:
            assert started.wait(2)
            cached = pool.submit(cache.render, 'v', 'Guardada', generate)
            assert cached.result(timeout=1) == PCM
            assert not generating.done()
        finally:
            finish.set()
        assert generating.result(timeout=2) == PCM


def test_saved_phrases_are_not_evicted(tmp_path):
    cache = AudioCache(tmp_path / "cache.db", max_bytes=8)
    cache.put("v", "Favorita", b"\x01\x02", pinned=True)
    cache.put("v", "Antigua", b"\x01\x02" * 3)
    cache.put("v", "Nueva", b"\x03\x04" * 3)
    assert cache.contains("v", "Favorita") and cache.contains("v", "Nueva")
    assert not cache.contains("v", "Antigua")


def test_invalid_generation_is_never_cached(tmp_path):
    cache = AudioCache(tmp_path / "cache.db")
    with pytest.raises(ValueError):
        cache.render("v", "Hola", lambda text: b"x")
    assert cache.stats()["clips"] == 0
