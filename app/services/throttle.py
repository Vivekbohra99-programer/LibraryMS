"""Slows down password guessing. Nothing is written to disk.

Failed sign-ins are counted per (client address, username) and, with a higher limit, per client address
alone, so one machine cannot walk through many usernames either. When a counter reaches its limit that
sign-in is locked for a while. The table is a bounded LRU, so spraying thousands of made-up usernames
cannot grow the server's memory without limit (this is the Q17 goal applied to security code)."""
import threading
import time
from collections import OrderedDict


class LoginThrottle:
    def __init__(self, max_failures=5, lock_seconds=900, window_seconds=900, address_factor=4, max_entries=2048):
        self.max_failures = max(1, int(max_failures))
        self.lock_seconds = lock_seconds
        self.window = window_seconds
        self.address_limit = self.max_failures * address_factor
        self.max_entries = max_entries
        self._rows = OrderedDict()          # key -> [failures, window_start, locked_until]
        self._mutex = threading.Lock()

    @staticmethod
    def _keys(address, username):
        address = address or '?'
        return ('user', address, (username or '').strip().lower()[:80]), ('address', address)

    def _limit(self, key):
        return self.max_failures if key[0] == 'user' else self.address_limit

    def locked_for(self, address, username, now=None):
        """Seconds left before this address/username may try again, or 0 if it may try now."""
        now = time.monotonic() if now is None else now
        left = 0
        with self._mutex:
            for key in self._keys(address, username):
                row = self._rows.get(key)
                if row and row[2] > now:
                    left = max(left, int(row[2] - now) + 1)
        return left

    def record_failure(self, address, username, now=None):
        """Count one wrong password. Returns True when this failure is the one that locked the sign-in."""
        now = time.monotonic() if now is None else now
        just_locked = False
        with self._mutex:
            for key in self._keys(address, username):
                row = self._rows.pop(key, None)
                if row is None or (row[2] and row[2] <= now) or now - row[1] > self.window:
                    row = [0, now, 0.0]       # first failure, or the last lock/window has run out
                row[0] += 1
                if row[0] >= self._limit(key) and not row[2]:
                    row[2] = now + self.lock_seconds
                    just_locked = True
                self._rows[key] = row         # re-inserted last = most recently used
            while len(self._rows) > self.max_entries:
                self._rows.popitem(last=False)
        return just_locked

    def reset(self, address, username):
        """A correct password clears that user's counter. The per-address counter keeps running."""
        with self._mutex:
            self._rows.pop(self._keys(address, username)[0], None)

    def __len__(self):
        return len(self._rows)
