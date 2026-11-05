"""Real-time feature engineering.

Every feature is computed from (a) the transaction itself and (b) the card's
history *before* this transaction. The history lives in a ``FeatureStore``:
an in-memory one for offline training and Redis in production. Because both
paths call the same ``compute_features`` function, the features the model is
trained on are exactly the features it sees live (no training/serving skew).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .cleaning import CATEGORY_CODE
from .config import WINDOW_1H, WINDOW_24H, WINDOW_7D

FEATURE_NAMES = [
    # transaction
    "amt", "log_amt", "category_code", "hour", "day_of_week", "is_night", "is_weekend",
    # customer / merchant
    "age", "log_city_pop", "gender_m", "dist_km",
    # card history (behavioural)
    "card_txn_count", "card_amt_mean", "amt_to_card_mean", "amt_zscore", "log_secs_since_last",
    # velocity windows
    "txn_count_1h", "txn_count_24h", "txn_count_7d", "amt_sum_24h", "amt_to_7d_mean",
    "is_new_merchant",
]
CATEGORICAL_FEATURES = ["category_code"]
NAN = float("nan")


@dataclass
class CardSnapshot:
    """What the store returns for a card *before* the current transaction."""
    count: int = 0
    amt_sum: float = 0.0
    amt_sumsq: float = 0.0
    last_ts: int | None = None
    window: list = field(default_factory=list)  # [(ts, amt)] within the last 7 days
    merchant_seen: bool = False


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def compute_features(txn: dict, snap: CardSnapshot) -> dict:
    """Build the model's feature vector for one cleaned transaction."""
    ts = txn["event_ts"]
    amt = txn["amt"]
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    dob = datetime.strptime(txn["dob"], "%Y-%m-%d").date()

    in_1h = [a for t, a in snap.window if ts - t < WINDOW_1H]
    in_24h = [a for t, a in snap.window if ts - t < WINDOW_24H]
    in_7d = [a for t, a in snap.window if ts - t < WINDOW_7D]

    if snap.count:
        mean = snap.amt_sum / snap.count
        var = max(snap.amt_sumsq / snap.count - mean * mean, 0.0)
        std = math.sqrt(var)
        card_mean, amt_ratio = mean, amt / mean
        zscore = (amt - mean) / std if snap.count >= 2 and std > 0 else NAN
        secs = max(ts - snap.last_ts, 0)
        log_secs = math.log1p(secs)
    else:
        card_mean = amt_ratio = zscore = log_secs = NAN

    return {
        "amt": amt,
        "log_amt": math.log1p(amt),
        "category_code": CATEGORY_CODE[txn["category"]],
        "hour": dt.hour,
        "day_of_week": dt.weekday(),
        "is_night": int(dt.hour >= 22 or dt.hour < 4),
        "is_weekend": int(dt.weekday() >= 5),
        "age": (dt.date() - dob).days / 365.25,
        "log_city_pop": math.log1p(txn["city_pop"]),
        "gender_m": txn["gender_m"],
        "dist_km": haversine_km(txn["lat"], txn["long"], txn["merch_lat"], txn["merch_long"]),
        "card_txn_count": snap.count,
        "card_amt_mean": card_mean,
        "amt_to_card_mean": amt_ratio,
        "amt_zscore": zscore,
        "log_secs_since_last": log_secs,
        "txn_count_1h": len(in_1h),
        "txn_count_24h": len(in_24h),
        "txn_count_7d": len(in_7d),
        "amt_sum_24h": sum(in_24h),
        "amt_to_7d_mean": amt / (sum(in_7d) / len(in_7d)) if in_7d else NAN,
        "is_new_merchant": int(not snap.merchant_seen),
    }


def to_vector(features: dict) -> list[float]:
    return [features[name] for name in FEATURE_NAMES]
