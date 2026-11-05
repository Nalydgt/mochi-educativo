import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import py_compile
import sys
from types import SimpleNamespace

import pytest

spec=importlib.util.spec_from_file_location('mochi_hermes_runtime_hook',Path(__file__).with_name('runtime_hook.py'))
hook=importlib.util.module_from_spec(spec);spec.loader.exec_module(hook)


def recipe(monkeypatch):
    original=b'VALUE="original"\n'
    patched=b'VALUE="guarded"\n'
    monkeypatch.setattr(hook,'PATCHED_SHA256',hashlib.sha256(patched).hexdigest())
    monkeypatch.setattr(hook,'_recipe',lambda:SimpleNamespace(
        SUPPORTED_SOURCE_SHA256=hashlib.sha256(original).hexdigest(),patched_source=lambda raw:patched))
    return original,patched


def test_real_import_loader_ignores_old_bytecode_and_never_changes_image_source(tmp_path,monkeypatch):
    original,patched=recipe(monkeypatch)
    name='synthetic_reviewed_hermes_module'
    path=tmp_path/(name+'.py');path.write_bytes(original)
    py_compile.compile(str(path),doraise=True)
    monkeypatch.setattr(hook,'TARGET_MODULE',name)
    monkeypatch.setattr(hook,'LOADED_DIR',tmp_path/'loaded')
    process_stat=tmp_path/'stat'
    process_stat.write_text('123 (python with spaces) '+' '.join(['0']*19+['123456']))
    monkeypatch.setattr(hook,'PROCESS_STAT',process_stat)
    monkeypatch.syspath_prepend(str(tmp_path))
    finder=hook.ReviewedSourceFinder();sys.meta_path.insert(0,finder)
    try:
        module=importlib.import_module(name)
        assert module.VALUE=='guarded'
        assert path.read_bytes()==original
        markers=list((tmp_path/'loaded').glob('*.json'))
        assert len(markers)==1
        marker=json.loads(markers[0].read_text())
        assert marker['pid']>0 and marker['process_start_ticks']=='123456'
        assert marker['effective_sha256']==hashlib.sha256(patched).hexdigest()
        assert marker['source_sha256']==hashlib.sha256(original).hexdigest()
    finally:
        sys.meta_path.remove(finder);sys.modules.pop(name,None)


def test_unknown_image_source_stops_target_import_instead_of_serving_without_guard(tmp_path,monkeypatch):
    recipe(monkeypatch)
    path=tmp_path/'api.py';path.write_text('VALUE="future image"\n')
    loader=hook.ReviewedSourceLoader('synthetic_future_image',str(path))
    with pytest.raises(ImportError,match='unreviewed API source'):
        loader.get_code('synthetic_future_image')


def test_already_patched_image_is_not_patched_twice(monkeypatch):
    original,patched=recipe(monkeypatch)
    result,source_digest=hook.runtime_source(patched)
    assert result==patched and source_digest==hashlib.sha256(patched).hexdigest()


def test_recipe_drift_is_rejected_before_execution(monkeypatch):
    original,patched=recipe(monkeypatch)
    monkeypatch.setattr(hook,'PATCHED_SHA256','f'*64)
    with pytest.raises(ImportError,match='recipe integrity mismatch'):
        hook.runtime_source(original)


def test_other_modules_are_not_intercepted():
    assert hook.ReviewedSourceFinder().find_spec('unrelated_user_module') is None
