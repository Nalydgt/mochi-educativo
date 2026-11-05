"""Persistent admission limits for task-scoped voice, with no conversation storage."""
import hashlib
import os
from pathlib import Path
import sqlite3
import time

from fastapi import HTTPException


def claim_turn(token: str, turn_id: str, *, path: Path | None = None, now: int | None = None):
    """Authorize one processing attempt, before recognition, inference or paid voice.

    A duplicate is rejected instead of generating more audio. Receipts contain a
    credential hash and opaque turn id, never the bearer, text, audio or learner.
    The device remains usable for downloaded exercises when a limit is reached.
    """
    instant = int(time.time()) if now is None else now
    database = path or Path(os.environ.get("PELUQO_TURN_DB", "/runtime/education-turns.sqlite3"))
    identity = hashlib.sha256(token.encode()).hexdigest()
    try:
        with sqlite3.connect(database, timeout=5) as connection:
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("CREATE TABLE IF NOT EXISTS turns(device TEXT NOT NULL, turn TEXT NOT NULL, at INTEGER NOT NULL, PRIMARY KEY(device,turn))")
            connection.execute("CREATE INDEX IF NOT EXISTS turns_by_time ON turns(device,at)")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM turns WHERE at<?", (instant - 86400,))
            if connection.execute("SELECT 1 FROM turns WHERE device=? AND turn=?", (identity, turn_id)).fetchone():
                raise HTTPException(409, "turn_already_processed")
            minute, day = connection.execute("SELECT coalesce(sum(at>=?),0),count(*) FROM turns WHERE device=?", (instant - 60, identity)).fetchone()
            total = connection.execute("SELECT count(*) FROM turns").fetchone()[0]
            if minute >= 10 or day >= 120 or total >= 10000:
                raise HTTPException(429, "education_voice_limit_reached")
            connection.execute("INSERT INTO turns(device,turn,at) VALUES(?,?,?)", (identity, turn_id, instant))
    except sqlite3.Error as error:
        raise HTTPException(503, "education_voice_admission_unavailable") from error
