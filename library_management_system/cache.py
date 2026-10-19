"""
cache.py
--------
FEATURE 4: Query Caching  (Quality Goal Q17 - Reduce Memory Usage)

A naive cache that only ever grows will *increase* memory usage over
time, which would work against the whole point of Q17. So this is a
bounded LRU (Least-Recently-Used) cache: once it hits `maxsize` entries,
the least-recently-used result is evicted to make room for a new one.

This means:
  - Repeated/common queries (e.g. "search by category = Fiction") don't
    have to re-hit SQLite and re-materialise result rows every time.
  - The cache can never grow unbounded, so it has a small, fixed memory
    ceiling instead of silently eating more RAM the longer the app runs.
  - Any write (add/update/delete/issue/return) invalidates the cache, so
    stale data is never served.
"""

import time
from collections import OrderedDict


class LRUCache:
    def __init__(self, maxsize: int = 64, ttl_seconds: int = 120):
        self.maxsize = maxsize
        self.ttl = ttl_seconds
        self._store = OrderedDict()  # key -> (value, inserted_at)
        self.hits = 0
        self.misses = 0

    def get(self, key):
        entry = self._store.get(key)
        if entry is None:
            self.misses += 1
            return None

        value, inserted_at = entry
        if (time.time() - inserted_at) > self.ttl:
            # Expired -- drop it rather than serve stale data.
            del self._store[key]
            self.misses += 1
            return None

        # Mark as recently used.
        self._store.move_to_end(key)
        self.hits += 1
        return value

    def set(self, key, value):
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (value, time.time())
        if len(self._store) > self.maxsize:
            # Evict the least-recently-used entry -- this is what keeps
            # the cache's memory footprint bounded no matter how many
            # distinct queries get run over the app's lifetime.
            self._store.popitem(last=False)

    def invalidate_all(self):
        """Call this after any write so stale results are never returned."""
        self._store.clear()

    def stats(self) -> dict:
        total = self.hits + self.misses
        hit_rate = round((self.hits / total) * 100, 1) if total else 0.0
        return {
            "entries": len(self._store),
            "max_entries": self.maxsize,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_pct": hit_rate,
        }


# One shared cache instance for search/lookup queries across the app.
search_cache = LRUCache(maxsize=32, ttl_seconds=120)
