"""
Q17 Feature 4: Query Caching – bounded LRU with TTL.
Preserved from original cache.py with thread-safety added.
"""
import time
import threading
from collections import OrderedDict


class LRUCache:
    def __init__(self, maxsize: int = 64, ttl_seconds: int = 120):
        self.maxsize = maxsize
        self.ttl = ttl_seconds
        self._store = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def get(self, key):
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            value, inserted_at = entry
            if (time.time() - inserted_at) > self.ttl:
                del self._store[key]
                self.misses += 1
                return None
            self._store.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key, value):
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (value, time.time())
            if len(self._store) > self.maxsize:
                self._store.popitem(last=False)
                self.evictions += 1

    def invalidate_all(self):
        with self._lock:
            self._store.clear()

    def invalidate(self, key):
        with self._lock:
            self._store.pop(key, None)

    def stats(self) -> dict:
        total = self.hits + self.misses
        hit_rate = round((self.hits / total) * 100, 1) if total else 0.0
        return {
            'entries': len(self._store),
            'max_entries': self.maxsize,
            'hits': self.hits,
            'misses': self.misses,
            'evictions': self.evictions,
            'hit_rate_pct': hit_rate,
            'ttl': self.ttl,
        }

    def reconfigure(self, maxsize=None, ttl=None):
        with self._lock:
            if maxsize is not None:
                self.maxsize = maxsize
                while len(self._store) > self.maxsize:
                    self._store.popitem(last=False)
                    self.evictions += 1
            if ttl is not None:
                self.ttl = ttl


# Shared cache instance
search_cache = LRUCache(maxsize=64, ttl_seconds=120)
