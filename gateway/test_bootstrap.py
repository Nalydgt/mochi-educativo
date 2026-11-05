from pathlib import Path
import runpy
import sys
from types import ModuleType

from app import Settings


def test_preinstalled_fast_spanish_voice_can_boot_without_downloading(monkeypatch,tmp_path):
    voice=tmp_path/'voices'/'es_ES-carlfm-x_low.onnx'
    voice.parent.mkdir()
    for name in (voice.name,voice.name+'.json',voice.stem+'-MODEL_CARD'):
        (voice.parent/name).write_bytes(b'installed asset')
    model_dir=tmp_path/'asr';model_dir.mkdir()
    settings=Settings('s'*40,tmp_path,voice,whisper_model=str(model_dir),voice_pitch=0,voice_speaker=0)
    monkeypatch.setattr(Settings,'from_env',lambda:settings)
    package=ModuleType('faster_whisper');package.__path__=[]
    utils=ModuleType('faster_whisper.utils')
    def unexpected(*args,**kwargs):raise AssertionError('Installed assets must not be downloaded at startup')
    utils.download_model=unexpected
    monkeypatch.setitem(sys.modules,'faster_whisper',package)
    monkeypatch.setitem(sys.modules,'faster_whisper.utils',utils)
    monkeypatch.setattr('urllib.request.urlopen',unexpected)
    runpy.run_path(str(Path(__file__).with_name('bootstrap.py')))


def test_native_voice_boot_does_not_validate_or_prepare_unused_piper_assets(monkeypatch, tmp_path):
    model_dir = tmp_path / 'asr'
    model_dir.mkdir()
    voice = tmp_path / 'unused' / 'private-speaker.onnx'
    settings = Settings('s'*40, tmp_path, voice, whisper_model=str(model_dir), voice_provider='native')
    monkeypatch.setattr(Settings, 'from_env', lambda: settings)
    package = ModuleType('faster_whisper')
    package.__path__ = []
    utils = ModuleType('faster_whisper.utils')
    def unexpected(*args, **kwargs):
        raise AssertionError('Native voice must not download Piper assets')
    utils.download_model = unexpected
    monkeypatch.setitem(sys.modules, 'faster_whisper', package)
    monkeypatch.setitem(sys.modules, 'faster_whisper.utils', utils)
    monkeypatch.setattr('urllib.request.urlopen', unexpected)
    runpy.run_path(str(Path(__file__).with_name('bootstrap.py')))
    assert not voice.parent.exists()
