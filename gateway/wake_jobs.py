"""Persistent, restartable name preparation queue shared with the isolated CPU worker."""
from contextlib import closing, contextmanager
from pathlib import Path
import re
import sqlite3
import time
import uuid

from device_context import pet_name

STAGES = {'queued', 'preparing', 'training', 'checking', 'ready', 'failed'}


class WakeJobs:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'jobs.sqlite3'
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, device TEXT NOT NULL, name TEXT NOT NULL,
                stage TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
                error TEXT, created REAL NOT NULL, updated REAL NOT NULL,
                worker TEXT, lease_until REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS activity (id TEXT PRIMARY KEY, until REAL NOT NULL);
            ''')

    def connect(self):
        return closing(sqlite3.connect(self.path, timeout=10, isolation_level=None))

    def create(self, name, device):
        name = pet_name(name)
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,48}', device):
            raise ValueError('Invalid device')
        now = time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT id FROM jobs WHERE device=? AND stage NOT IN ('ready','failed')", (device,)).fetchone()
            if row:
                db.rollback()
                raise RuntimeError('A name is already being prepared for this device')
            if db.execute("SELECT COUNT(*) FROM jobs WHERE stage NOT IN ('ready','failed')").fetchone()[0] >= 8:
                db.rollback()
                raise RuntimeError('Preparation queue is full')
            identifier = uuid.uuid4().hex
            db.execute('INSERT INTO jobs(id,device,name,stage,created,updated) VALUES(?,?,?,?,?,?)',
                       (identifier,device,name,'queued',now,now))
            db.commit()
        return self.get(identifier)

    def get(self, identifier):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT id,device,name,stage,progress,error,created,updated FROM jobs WHERE id=?',
                             (identifier,)).fetchone()
        return dict(row) if row else None

    def claim(self, worker):
        now = time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            # A live lease is exclusive across worker restarts/accidental replicas.
            if db.execute("SELECT 1 FROM jobs WHERE stage IN ('preparing','training','checking') AND lease_until>?", (now,)).fetchone():
                db.rollback(); return None
            row = db.execute("SELECT id FROM jobs WHERE stage='queued' OR (stage IN ('preparing','training','checking') AND lease_until<?) ORDER BY created LIMIT 1", (now,)).fetchone()
            if not row:
                db.rollback(); return None
            db.execute("UPDATE jobs SET stage='preparing',worker=?,lease_until=?,updated=?,error=NULL WHERE id=?", (worker,now+60,now,row[0]))
            db.commit()
        return self.get(row[0])

    def update(self, identifier, worker, stage, progress, error=None):
        if stage not in STAGES or not 0 <= progress <= 100:
            raise ValueError('Invalid job state')
        with self.connect() as db:
            count = db.execute('UPDATE jobs SET stage=?,progress=?,error=?,updated=?,lease_until=? WHERE id=? AND worker=?',
                         (stage,progress,error,time.time(),time.time()+60,identifier,worker)).rowcount
        if not count:
            raise RuntimeError('Job lease lost')

    @contextmanager
    def foreground(self):
        identifier = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO activity VALUES(?,?)', (identifier,time.time()+240))
        try:
            yield
        finally:
            with self.connect() as db:
                db.execute('DELETE FROM activity WHERE id=?', (identifier,))

    def conversation_active(self):
        with self.connect() as db:
            return bool(db.execute('SELECT 1 FROM activity WHERE until>? LIMIT 1', (time.time(),)).fetchone())

    def directory(self, identifier):
        from artifacts import checked_id
        return self.root / checked_id(identifier)
