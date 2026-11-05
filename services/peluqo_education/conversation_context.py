"""Short-lived conversational context, held only in process memory.

No raw audio, database, full identity, guardian access or protection disclosure
storage. Learning evidence belongs to the separate, authorized school records.
"""
from collections import OrderedDict
import hashlib
import threading
import time


class ConversationContext:
    def __init__(self, *, ttl=600, capacity=128):
        self.ttl, self.capacity = ttl, capacity
        self._entries = OrderedDict()
        self._lock = threading.Lock()

    def _key(self, token):
        return hashlib.sha256(token.encode()).hexdigest()

    def _expire(self, instant):
        for key in list(self._entries):
            if instant - self._entries[key][0] >= self.ttl:
                del self._entries[key]

    def get(self, token, topic, *, now=None):
        instant = time.monotonic() if now is None else now
        with self._lock:
            self._expire(instant)
            item = self._entries.get(self._key(token))
            return [dict(turn) for turn in item[2]] if item and item[1] == topic else []

    def remember(self, token, topic, question, answer, *, now=None):
        instant = time.monotonic() if now is None else now
        with self._lock:
            self._expire(instant)
            key = self._key(token)
            old = self._entries.pop(key, None)
            turns = list(old[2]) if old and old[1] == topic else []
            turns.extend([{"role": "user", "content": question[:1000]}, {"role": "assistant", "content": answer[:700]}])
            self._entries[key] = (instant, topic, turns[-6:])
            while len(self._entries) > self.capacity:
                self._entries.popitem(last=False)

    def forget(self, token):
        with self._lock:
            self._entries.pop(self._key(token), None)

    def expire(self):
        with self._lock:
            self._expire(time.monotonic())
