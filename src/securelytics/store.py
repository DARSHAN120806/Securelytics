"""Feature stores holding each card's history.

``InMemoryStore`` is used for offline training and tests. ``RedisStore`` is the
production store shared by all stream-processor instances. Both expose the
same two methods:

* ``load(txn)``   -> CardSnapshot of the card's history before ``txn``
* ``commit(txn)`` -> add ``txn`` to the card's history

Redis layout per card ``c``:
    card:{c}:stats      HASH  count, amt_sum, amt_sumsq, last_ts
    card:{c}:win        ZSET  member "<trans_id>|<amt>" scored by event_ts (7-day window)
    card:{c}:merchants  SET   merchants this card has used
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from .config import WINDOW_7D
from .features import CardSnapshot

STATE_TTL_SECONDS = 400 * 86400  # forget cards inactive for > ~13 months


class InMemoryStore:
    def __init__(self) -> None:
        self.cards: dict[str, dict] = {}

    def _card(self, cc: str) -> dict:
        card = self.cards.get(cc)
        if card is None:
            card = {"count": 0, "amt_sum": 0.0, "amt_sumsq": 0.0, "last_ts": None,
                    "window": deque(), "merchants": set()}
            self.cards[cc] = card
        return card

    def load(self, txn: dict) -> CardSnapshot:
        card = self.cards.get(txn["cc_num"])
        if card is None:
            return CardSnapshot()
        ts = txn["event_ts"]
        return CardSnapshot(
            count=card["count"], amt_sum=card["amt_sum"], amt_sumsq=card["amt_sumsq"],
            last_ts=card["last_ts"],
            window=[(t, a) for t, a in card["window"] if 0 <= ts - t < WINDOW_7D],
            merchant_seen=txn["merchant"] in card["merchants"],
        )

    def commit(self, txn: dict) -> None:
        card = self._card(txn["cc_num"])
        ts, amt = txn["event_ts"], txn["amt"]
        card["count"] += 1
        card["amt_sum"] += amt
        card["amt_sumsq"] += amt * amt
        card["last_ts"] = ts if card["last_ts"] is None else max(card["last_ts"], ts)
        card["window"].append((ts, amt))
        while card["window"] and card["window"][0][0] <= card["last_ts"] - WINDOW_7D:
            card["window"].popleft()
        card["merchants"].add(txn["merchant"])

    # ---- snapshot: lets production Redis start from the training history ---- #
    def export_snapshot(self, path: Path) -> None:
        data = {
            cc: {"count": c["count"], "amt_sum": c["amt_sum"], "amt_sumsq": c["amt_sumsq"],
                 "last_ts": c["last_ts"], "window": list(c["window"]),
                 "merchants": sorted(c["merchants"])}
            for cc, c in self.cards.items()
        }
        Path(path).write_text(json.dumps(data), encoding="utf-8")


class RedisStore:
    def __init__(self, client) -> None:
        self.r = client

    @staticmethod
    def _keys(cc: str) -> tuple[str, str, str]:
        return f"card:{cc}:stats", f"card:{cc}:win", f"card:{cc}:merchants"

    def load(self, txn: dict) -> CardSnapshot:
        stats_k, win_k, merch_k = self._keys(txn["cc_num"])
        ts = txn["event_ts"]
        pipe = self.r.pipeline(transaction=False)
        pipe.hgetall(stats_k)
        pipe.zrangebyscore(win_k, ts - WINDOW_7D + 1, ts, withscores=True)
        pipe.sismember(merch_k, txn["merchant"])
        stats, win, seen = pipe.execute()
        if not stats:
            return CardSnapshot()
        stats = {_s(k): _s(v) for k, v in stats.items()}
        return CardSnapshot(
            count=int(stats["count"]),
            amt_sum=float(stats["amt_sum"]),
            amt_sumsq=float(stats["amt_sumsq"]),
            last_ts=int(stats["last_ts"]),
            window=[(int(score), float(_s(member).rsplit("|", 1)[1])) for member, score in win],
            merchant_seen=bool(seen),
        )

    def commit(self, txn: dict) -> None:
        stats_k, win_k, merch_k = self._keys(txn["cc_num"])
        ts, amt = txn["event_ts"], txn["amt"]
        pipe = self.r.pipeline(transaction=True)
        pipe.hincrby(stats_k, "count", 1)
        pipe.hincrbyfloat(stats_k, "amt_sum", amt)
        pipe.hincrbyfloat(stats_k, "amt_sumsq", amt * amt)
        pipe.execute()
        # last_ts only moves forward
        last = self.r.hget(stats_k, "last_ts")
        pipe = self.r.pipeline(transaction=True)
        if last is None or int(_s(last)) < ts:
            pipe.hset(stats_k, "last_ts", ts)
        pipe.zadd(win_k, {f"{txn['trans_id']}|{amt}": ts})
        pipe.zremrangebyscore(win_k, "-inf", ts - WINDOW_7D)
        pipe.sadd(merch_k, txn["merchant"])
        for k in (stats_k, win_k, merch_k):
            pipe.expire(k, STATE_TTL_SECONDS)
        pipe.execute()

    def is_empty(self) -> bool:
        return self.r.get("securelytics:bootstrapped") is None

    def import_snapshot(self, path: Path, batch: int = 200) -> int:
        """Load a snapshot produced by ``InMemoryStore.export_snapshot``."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        pipe = self.r.pipeline(transaction=False)
        for i, (cc, c) in enumerate(data.items(), 1):
            stats_k, win_k, merch_k = self._keys(cc)
            pipe.delete(stats_k, win_k, merch_k)
            pipe.hset(stats_k, mapping={"count": c["count"], "amt_sum": c["amt_sum"],
                                        "amt_sumsq": c["amt_sumsq"], "last_ts": c["last_ts"]})
            if c["window"]:
                pipe.zadd(win_k, {f"snap{j}|{a}": t for j, (t, a) in enumerate(c["window"])})
            if c["merchants"]:
                pipe.sadd(merch_k, *c["merchants"])
            for k in (stats_k, win_k, merch_k):
                pipe.expire(k, STATE_TTL_SECONDS)
            if i % batch == 0:
                pipe.execute()
        pipe.set("securelytics:bootstrapped", "1")
        pipe.execute()
        return len(data)


def _s(v):
    return v.decode() if isinstance(v, bytes) else v
