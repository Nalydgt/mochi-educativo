"""Short ASR must preserve complete captures, lazy execution and worker ownership."""
from pathlib import Path
import sys
import threading
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from speech import LocalSpeech, RATE


def transcriber(monkeypatch, frames=800, synchronize=None):
    seen=[]
    class Model:
        def __init__(self,*args,**kwargs):pass
        def encode(self,features):
            seen.append((threading.current_thread().name,features.shape[-1]))
        def transcribe(self,audio,**options):
            def segments():
                if synchronize:synchronize.wait(timeout=3)
                self.encode(np.zeros((80,3000),dtype=np.float32))
                yield SimpleNamespace(text=' Palabras completas. ')
            return segments(),None
    module=ModuleType('faster_whisper');module.WhisperModel=Model
    monkeypatch.setitem(sys.modules,'faster_whisper',module)
    return LocalSpeech(Path('unused'),encoder_frames=frames),seen


@pytest.mark.parametrize('frames',[800,1600])
def test_eight_second_capture_uses_window_but_one_extra_sample_preserves_full_encoder(monkeypatch,frames):
    speech,seen=transcriber(monkeypatch,frames)
    assert speech.transcribe(b'\0\0'*(RATE*8))=='Palabras completas.'
    assert speech.transcribe(b'\0\0'*(RATE*8+1))=='Palabras completas.'
    assert speech.transcribe(b'\0\0'*RATE)=='Palabras completas.'
    assert [length for _,length in seen]==[frames,3000,frames]


def test_default_preserves_full_encoder_and_startup_warms_selected_path(monkeypatch):
    speech,seen=transcriber(monkeypatch,0)
    speech.transcribe(b'\0\0'*RATE)
    assert [length for _,length in seen]==[3000]
    speech,seen=transcriber(monkeypatch,1600)
    speech.warmup_transcriber()
    assert [length for _,length in seen]==[1600,1600]


def test_short_and_legacy_workers_cannot_change_each_others_encoder_window(monkeypatch):
    speech,seen=transcriber(monkeypatch,synchronize=threading.Barrier(2))
    speech._load_transcriber()
    results=[]
    def run(samples):results.append(speech.transcribe(b'\0\0'*samples))
    short=threading.Thread(target=run,args=(RATE,),name='short-capture')
    legacy=threading.Thread(target=run,args=(RATE*8+1,),name='legacy-capture')
    short.start();legacy.start();short.join(timeout=4);legacy.join(timeout=4)
    assert not short.is_alive() and not legacy.is_alive()
    assert results==['Palabras completas.']*2
    assert dict(seen)=={'short-capture':800,'legacy-capture':3000}


@pytest.mark.parametrize('invalid',[True,'800',900,1600.0,-1])
def test_unvalidated_encoder_windows_are_rejected(invalid):
    with pytest.raises(ValueError,match='Encoder window'):
        LocalSpeech(Path('unused'),encoder_frames=invalid)
