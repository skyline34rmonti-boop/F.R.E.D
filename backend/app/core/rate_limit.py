"""Single-process sliding window limiter. Use a shared store before scaling out."""
from collections import deque
from threading import Lock
from time import monotonic


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = {}
        self._lock = Lock()

    def allow(self, key: str, limit: int) -> bool:
        current = monotonic()
        with self._lock:
            for old_key in list(self._buckets):
                if not self._buckets[old_key] or self._buckets[old_key][-1] < current - 60:
                    del self._buckets[old_key]
            bucket = self._buckets.setdefault(key, deque())
            while bucket and bucket[0] <= current - 60:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(current)
            return True
