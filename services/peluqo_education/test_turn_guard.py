import importlib.util
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest
from fastapi import HTTPException

spec = importlib.util.spec_from_file_location("education_turn_guard", Path(__file__).with_name("turn_guard.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def test_receipt_survives_new_connection_and_rejects_duplicate_without_credentials(tmp_path):
    path = tmp_path / "turns.db"
    identity = str(uuid4())
    guard.claim_turn("fictional-device-token", identity, path=path, now=100000)
    with pytest.raises(HTTPException) as duplicate:
        guard.claim_turn("fictional-device-token", identity, path=path, now=100001)
    assert duplicate.value.status_code == 409
    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT device,turn,at FROM turns").fetchall()
    assert len(rows) == 1
    assert rows[0][0] != "fictional-device-token"
    assert len(rows[0][0]) == 64
    guard.claim_turn("other-fictional-device", identity, path=path, now=100001)


def test_limits_expire_and_each_device_has_its_own_allowance(tmp_path):
    path = tmp_path / "turns.db"
    for _ in range(10):
        guard.claim_turn("device-a", str(uuid4()), path=path, now=100000)
    with pytest.raises(HTTPException) as limit:
        guard.claim_turn("device-a", str(uuid4()), path=path, now=100001)
    assert limit.value.status_code == 429
    guard.claim_turn("device-b", str(uuid4()), path=path, now=100001)
    guard.claim_turn("device-a", str(uuid4()), path=path, now=100061)


def test_missing_storage_fails_before_generating_or_speaking(tmp_path):
    with pytest.raises(HTTPException) as failure:
        guard.claim_turn("device", str(uuid4()), path=tmp_path / "missing" / "turns.db", now=100000)
    assert failure.value.status_code == 503
