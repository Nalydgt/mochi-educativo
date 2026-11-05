"""Persistent audio, keyed by voice settings and exact normalized text."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import unicodedata

from speech import RATE, MAX_SECONDS


def clean_text(text: str) -> str:
    text = " ".join(unicodedata.normalize("NFC", text).split())
    if not text or len(text) > 2000:
        raise ValueError("Invalid speech text")
    return text


def voice_key(settings: dict) -> str:
    return hashlib.sha256(json.dumps(settings, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def valid_pcm(pcm: bytes) -> bool:
    return 0 < len(pcm) <= RATE * 2 * MAX_SECONDS and len(pcm) % 2 == 0


class AudioCache:
    def __init__(self, path: Path, max_bytes: int = 256 * 1024 * 1024):
        self.path, self.max_bytes = path, max_bytes
        self.render_lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS clips (
                voice TEXT NOT NULL, text TEXT NOT NULL, pcm BLOB NOT NULL,
                pinned INTEGER NOT NULL DEFAULT 0, used REAL NOT NULL,
                hits INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (voice,text))""")
            db.commit()

    def get(self, voice: str, text: str) -> bytes | None:
        text = clean_text(text)
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT pcm FROM clips WHERE voice=? AND text=?", (voice, text)).fetchone()
            if not row:
                return None
            pcm = row[0]
            if not valid_pcm(pcm):
                raise ValueError("Stored audio is invalid")
            db.execute("UPDATE clips SET used=julianday('now'),hits=hits+1 WHERE voice=? AND text=?", (voice, text))
            db.commit()
            return pcm

    def contains(self, voice: str, text: str) -> bool:
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute("SELECT 1 FROM clips WHERE voice=? AND text=?", (voice, clean_text(text))).fetchone() is not None

    def put(self, voice: str, text: str, pcm: bytes, pinned: bool = False):
        if not valid_pcm(pcm) or len(pcm) > self.max_bytes:
            raise ValueError("Invalid audio or cache capacity")
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            text = clean_text(text)
            old = db.execute("SELECT length(pcm) FROM clips WHERE voice=? AND text=?", (voice, text)).fetchone()
            size = db.execute("SELECT COALESCE(SUM(length(pcm)),0) FROM clips").fetchone()[0] - (old[0] if old else 0)
            while size + len(pcm) > self.max_bytes:
                victim = db.execute("SELECT voice,text,length(pcm) FROM clips WHERE pinned=0 AND NOT(voice=? AND text=?) ORDER BY used LIMIT 1", (voice, text)).fetchone()
                if victim is None:
                    raise ValueError("Cache is full of saved phrases")
                db.execute("DELETE FROM clips WHERE voice=? AND text=?", victim[:2])
                size -= victim[2]
            db.execute("""INSERT INTO clips(voice,text,pcm,pinned,used) VALUES(?,?,?,?,julianday('now'))
                ON CONFLICT(voice,text) DO UPDATE SET pcm=excluded.pcm,
                pinned=MAX(clips.pinned,excluded.pinned),used=excluded.used""", (voice, text, pcm, int(pinned)))
            db.commit()

    def render(self, voice: str, text: str, generate, pinned: bool = False) -> bytes:
        text = clean_text(text)
        # Cached phrases do not use the synthesizer and must not wait for it.
        pcm = self.get(voice, text)
        if pcm is not None:
            return pcm
        # One worker per service; concurrent identical requests cannot spend twice.
        with self.render_lock:
            pcm = self.get(voice, text)
            if pcm is None:
                pcm = generate(text)
                self.put(voice, text, pcm, pinned)
            return pcm

    def stats(self) -> dict:
        with closing(sqlite3.connect(self.path)) as db:
            clips, size, hits = db.execute("SELECT COUNT(*),COALESCE(SUM(length(pcm)),0),COALESCE(SUM(hits),0) FROM clips").fetchone()
            return {"clips": clips, "bytes": size, "reuses": hits}
