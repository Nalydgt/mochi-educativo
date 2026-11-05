"""One local, durable journal for the gateway and the Mochi Hermes provider.

Connections are short lived: SQLite WAL coordinates the two processes. Public
history contains delivered answers only; the journal retains every attempt.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
import time
import unicodedata
import uuid


class ExchangeConflict(ValueError):
    pass


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFD',text.lower()) if not unicodedata.combining(c))


class Memory:
    def __init__(self, path: Path, *, recover=False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY, device TEXT NOT NULL,
                    role TEXT NOT NULL, content TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS exchanges (
                    id TEXT PRIMARY KEY, device TEXT NOT NULL, question TEXT NOT NULL,
                    answer TEXT, emotion TEXT, route TEXT, request_hash TEXT,
                    delivery TEXT NOT NULL DEFAULT 'received',
                    reviewed INTEGER NOT NULL DEFAULT 0, review_attempts INTEGER NOT NULL DEFAULT 0,
                    created REAL NOT NULL, updated REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS exchanges_device ON exchanges(device, created);
                CREATE INDEX IF NOT EXISTS exchanges_pending ON exchanges(reviewed, delivery, created);
                CREATE TABLE IF NOT EXISTS facts (
                    device TEXT NOT NULL, key TEXT NOT NULL, content TEXT NOT NULL,
                    source TEXT NOT NULL, updated REAL NOT NULL,
                    PRIMARY KEY(device, key));
                CREATE TABLE IF NOT EXISTS migrations (name TEXT PRIMARY KEY);
            ''')
            if not db.execute("SELECT 1 FROM migrations WHERE name='messages-v1'").fetchone():
                # Retain the old table as evidence. Migration identities refer to
                # row IDs, so a restart can never import an old answer twice.
                rows = db.execute('SELECT id,device,role,content FROM messages ORDER BY id').fetchall()
                pending = {}
                for row in rows:
                    rid, device, role, content = row
                    if role == 'user':
                        pending[device] = (rid, content)
                        db.execute('INSERT OR IGNORE INTO exchanges(id,device,question,delivery,created,updated) VALUES(?,?,?,?,?,?)',
                                   (f'legacy-{rid}', device, content, 'incomplete', rid / 1e6, rid / 1e6))
                    elif role == 'assistant' and device in pending:
                        uid, question = pending.pop(device)
                        db.execute("UPDATE exchanges SET answer=?,emotion='idle',route='hermes',delivery='delivered' WHERE id=?",
                                   (content, f'legacy-{uid}'))
                db.execute("INSERT INTO migrations VALUES('messages-v1')")
            if recover:
                # Called by the sole gateway owner at startup, never by Hermes.
                db.execute("UPDATE exchanges SET delivery='incomplete',updated=? WHERE delivery IN ('received','answered')", (time.time(),))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.create_function('mochi_normalize',1,normalized,deterministic=True)
        try:
            db.execute('PRAGMA busy_timeout=5000')
            db.execute('PRAGMA synchronous=FULL')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def checked_id(value=None):
        value = value or str(uuid.uuid4())
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,96}', value):
            raise ValueError('invalid_exchange_id')
        return value

    def get(self, exchange_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM exchanges WHERE id=?', (exchange_id,)).fetchone()
        return dict(row) if row else None

    def begin(self, device, question, exchange_id=None, request_hash=None):
        exchange_id = self.checked_id(exchange_id)
        now = time.time()
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO exchanges(id,device,question,request_hash,created,updated) VALUES(?,?,?,?,?,?)',
                       (exchange_id, device, question, request_hash, now, now))
            row = dict(db.execute('SELECT * FROM exchanges WHERE id=?', (exchange_id,)).fetchone())
            if row['device'] != device or row['question'] != question or (request_hash and row['request_hash'] != request_hash):
                raise ExchangeConflict('exchange_id_reused')
        return row

    def answered(self, exchange_id, answer, route):
        with self.connect() as db:
            db.execute("UPDATE exchanges SET answer=?,emotion=?,route=?,delivery='answered',updated=? WHERE id=? AND delivery='received'",
                       (answer['text'], answer['emotion'], route, time.time(), exchange_id))

    def delivered(self, exchange_id):
        with self.connect() as db:
            db.execute("UPDATE exchanges SET delivery='delivered',updated=? WHERE id=? AND answer IS NOT NULL", (time.time(), exchange_id))

    def interrupt(self, exchange_id):
        with self.connect() as db:
            db.execute("UPDATE exchanges SET delivery='incomplete',updated=? WHERE id=? AND delivery!='delivered'", (time.time(), exchange_id))

    def history(self, device, limit=24):
        with self.connect() as db:
            rows = db.execute("SELECT question,answer FROM exchanges WHERE device=? AND delivery='delivered' ORDER BY created DESC,id DESC LIMIT ?",
                              (device, limit // 2)).fetchall()
        return [message for row in reversed(rows) for message in (
            {'role': 'user', 'content': row['question']}, {'role': 'assistant', 'content': row['answer']})]

    def latest_device_history(self):
        with self.connect() as db:
            row = db.execute("SELECT device FROM exchanges WHERE device NOT LIKE 'mochi-diagnostics%' AND delivery='delivered' ORDER BY created DESC LIMIT 1").fetchone()
        return self.history(row[0]) if row else []

    def append_turn(self, device, text, answer, exchange_id=None):
        row = self.begin(device, text, exchange_id)
        self.answered(row['id'], {'text': answer, 'emotion': 'idle'}, 'hermes')
        self.delivered(row['id'])
        return row['id']

    def search(self, device, query, limit=8):
        stopwords={'que','qué','como','cómo','por','para','con','una','uno','las','los','del','mis','tus','tiene',
                   'tengo','dime','cuál','cual','cuándo','cuando','dónde','donde','eres','soy','puedes','sobre','hace','más','mas'}
        terms = list(dict.fromkeys(normalized(t) for t in re.findall(r'\w{3,}', query.lower()) if t not in stopwords))[:10]
        if not terms:
            return []
        where = ' OR '.join('(mochi_normalize(question) LIKE ? OR mochi_normalize(coalesce(answer,\'\')) LIKE ?)' for _ in terms)
        params = [value for term in terms for value in (f'%{term}%', f'%{term}%')]
        with self.connect() as db:
            rows = db.execute(f'SELECT id,question,answer,delivery FROM exchanges WHERE device=? AND ({where}) ORDER BY created DESC LIMIT ?',
                              [device, *params, min(limit, 20)]).fetchall()
        return [dict(row) for row in rows]

    def pending(self, device=None, limit=16, *, recent=False):
        with self.connect() as db:
            sql = "SELECT * FROM exchanges WHERE reviewed=0 AND delivery IN ('delivered','incomplete') AND device NOT LIKE 'mochi-diagnostics%'"
            params = []
            if device is not None:
                sql += ' AND device=?'; params.append(device)
            sql += ' ORDER BY created DESC,id DESC LIMIT ?' if recent else ' ORDER BY created,id LIMIT ?'
            params.append(limit)
            rows=[dict(r) for r in db.execute(sql, params).fetchall()]
            return rows[::-1] if recent else rows

    def facts(self, device):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT key,content,source FROM facts WHERE device=? ORDER BY updated DESC', (device,)).fetchall()]

    def context(self, device, query, max_chars=6500):
        # Facts, pending evidence and older matching exchanges share one bounded
        # budget. Pending questions are included even when their audio failed.
        items = {'facts': self.facts(device), 'pending': [
            {k:r[k] for k in ('id','question','answer','delivery')} for r in self.pending(device, 32,recent=True)],
            'older_matches': self.search(device, query, 4)}
        # Trim whole records, never cut JSON or individual words.
        def encoded(value):
            return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        size = len(encoded(items))
        while size > max_chars:
            key = next((k for k in ('older_matches','pending','facts') if items[k]), None)
            if key is None: break
            removed = items[key].pop(0 if key == 'pending' else -1)
            size -= len(encoded(removed)) + bool(items[key])
        return encoded(items)

    def review_commit(self, rows, updates):
        allowed = {r['id']:r for r in rows}
        if len(updates) > 32: raise ValueError('Too many facts')
        checked = []
        for item in updates:
            if set(item) != {'key','content','source'} or item['source'] not in allowed:
                raise ValueError('Unknown review evidence')
            if not isinstance(item['key'], str) or not re.fullmatch(r'[a-z0-9_.-]{1,80}', item['key']):
                raise ValueError('Invalid fact key')
            if not isinstance(item['content'], str) or len(item['content']) > 600:
                raise ValueError('Invalid fact text')
            if item['content']:
                generic={'usuario','user','nombre','name','tiene','tener','dice','gustan','gusta','favorito','favorita','prefiere',
                         'para','como','esta','está','del','que','una','con','por','los','las','sus','mis'}
                words=lambda text:{w for w in re.findall(r'\w+',normalized(text)) if (len(w)>=3 or w.isdigit()) and w not in generic}
                if not words(item['content']) & words(allowed[item['source']]['question']):
                    raise ValueError('Fact lacks direct evidence')
            checked.append(item)
        with self.connect() as db:
            for item in checked:
                source = allowed[item['source']]
                # Tombstones (empty content) keep correction provenance.
                db.execute('''INSERT INTO facts VALUES(?,?,?,?,?) ON CONFLICT(device,key)
                    DO UPDATE SET content=excluded.content,source=excluded.source,updated=excluded.updated
                    WHERE excluded.updated >= facts.updated''',
                    (source['device'], item['key'], item['content'], item['source'], source['created']))
            db.executemany('UPDATE exchanges SET reviewed=1,review_attempts=review_attempts+1 WHERE id=?', [(r['id'],) for r in rows])

    def review_failed(self, rows):
        with self.connect() as db:
            db.executemany('UPDATE exchanges SET review_attempts=review_attempts+1 WHERE id=?', [(r['id'],) for r in rows])

    def invalidate_native(self, previous_content):
        # A confirmed native replace/remove wins immediately over extracted
        # copies. Tombstone instead of deleting so an older pending review
        # cannot reintroduce a forgotten fact.
        with self.connect() as db:
            rows=db.execute('SELECT device,key,content FROM facts WHERE content!=\'\'').fetchall()
            for row in rows:
                if row['content'] in previous_content or previous_content in row['content']:
                    db.execute("UPDATE facts SET content='',source='native-correction',updated=? WHERE device=? AND key=?",
                               (time.time(),row['device'],row['key']))


def profile_context(directory):
    """Read the same personal files as Hermes; paths are deployment settings."""
    root = Path(directory) if directory else None
    if not root: return ''
    pieces = []
    soul = 'SOUL-VOICE.md' if (root/'SOUL-VOICE.md').is_file() else 'SOUL.md'
    for name in (soul, 'memories/MEMORY.md', 'memories/USER.md'):
        path = root / name
        if path.is_file():
            pieces.append(f'{name}:\n{path.read_text(encoding="utf-8")[:14000]}')
    return '\n\n'.join(pieces)
