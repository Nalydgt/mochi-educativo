import importlib.util
from pathlib import Path
import sys

import pytest


spec=importlib.util.spec_from_file_location('mochi_wake_worker',Path(__file__).with_name('worker.py'))
worker=importlib.util.module_from_spec(spec)
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'gateway'))
try:spec.loader.exec_module(worker)
finally:sys.path.pop(0)


@pytest.mark.parametrize('content',[b'',b'TFL3',b'\0'*4+b'BAD3',b'\0'*4+b'TFL3'+b'\0'*2097152],
    ids=['empty','truncated','wrong_header','oversized'])
def test_corrupt_or_oversized_reused_model_is_rejected(tmp_path,content):
    model=tmp_path/'model.tflite'
    model.write_bytes(content)
    assert not worker.valid_model(model)


def test_valid_tflite_and_missing_model(tmp_path):
    model=tmp_path/'model.tflite'
    assert not worker.valid_model(model)
    model.write_bytes(b'\x18\0\0\0TFL3'+b'\0'*16)
    assert worker.valid_model(model)
