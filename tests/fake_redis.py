"""Minimal in-memory Redis stand-in (only the commands RedisStore uses).

Returns bytes like redis-py does without decode_responses, so the decoding
paths in RedisStore are exercised too. Use a real Redis for integration tests.
"""
from __future__ import annotations


def _b(v) -> bytes:
    return v if isinstance(v, bytes) else str(v).encode()


def _score(v) -> float:
    return float(v) if not isinstance(v, str) or v not in ("-inf", "+inf", "inf") else float(v.replace("+", ""))


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict = {}

    # strings
    def ping(self): return True
    def get(self, k): return self.data.get(k)

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.data:
            return None
        self.data[k] = _b(v)
        return True

    def delete(self, *keys):
        return sum(self.data.pop(k, None) is not None for k in keys)

    def expire(self, k, s): return k in self.data

    # hashes
    def hgetall(self, k): return {_b(f): v for f, v in self.data.get(k, {}).items()}
    def hget(self, k, f): return self.data.get(k, {}).get(f)

    def hset(self, k, field=None, value=None, mapping=None):
        h = self.data.setdefault(k, {})
        items = dict(mapping or {})
        if field is not None:
            items[field] = value
        for f, v in items.items():
            h[f] = _b(v)
        return len(items)

    def hincrby(self, k, f, n):
        h = self.data.setdefault(k, {})
        h[f] = _b(int(h.get(f, b"0")) + n)
        return int(h[f])

    def hincrbyfloat(self, k, f, n):
        h = self.data.setdefault(k, {})
        h[f] = _b(repr(float(h.get(f, b"0")) + n))
        return float(h[f])

    # sorted sets
    def zadd(self, k, mapping):
        z = self.data.setdefault(k, {})
        z.update({_b(m): float(s) for m, s in mapping.items()})
        return len(mapping)

    def zrangebyscore(self, k, lo, hi, withscores=False):
        lo, hi = _score(lo), _score(hi)
        items = sorted((s, m) for m, s in self.data.get(k, {}).items() if lo <= s <= hi)
        return [(m, s) for s, m in items] if withscores else [m for _, m in items]

    def zremrangebyscore(self, k, lo, hi):
        lo, hi = _score(lo), _score(hi)
        z = self.data.get(k, {})
        drop = [m for m, s in z.items() if lo <= s <= hi]
        for m in drop:
            del z[m]
        return len(drop)

    # sets
    def sadd(self, k, *vals):
        s = self.data.setdefault(k, set())
        before = len(s); s.update(_b(v) for v in vals)
        return len(s) - before

    def sismember(self, k, v): return int(_b(v) in self.data.get(k, set()))

    def pipeline(self, transaction=True):
        return _Pipeline(self)


class _Pipeline:
    def __init__(self, r: FakeRedis) -> None:
        self.r, self.calls = r, []

    def __getattr__(self, name):
        def queue(*a, **kw):
            self.calls.append((name, a, kw))
            return self
        return queue

    def execute(self):
        out = [getattr(self.r, n)(*a, **kw) for n, a, kw in self.calls]
        self.calls = []
        return out
