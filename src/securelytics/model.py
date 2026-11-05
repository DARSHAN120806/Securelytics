"""Model wrapper used by both training and the live stream processor.

Holds the trained classifier, the decision thresholds chosen during training,
and the "typical legitimate" baseline used to explain each alert.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .cleaning import CATEGORIES
from .features import FEATURE_NAMES

APPROVE, REVIEW, BLOCK = "APPROVE", "REVIEW", "BLOCK"

# Features that only make sense together are explained as a group.
_EXPLAIN_GROUPS = {
    "amount": ["amt", "log_amt", "amt_to_card_mean", "amt_zscore", "amt_to_7d_mean"],
    "time": ["hour", "is_night"],
    "velocity": ["txn_count_1h", "txn_count_24h", "amt_sum_24h"],
    "history": ["card_txn_count", "card_amt_mean", "txn_count_7d", "log_secs_since_last"],
    "category": ["category_code"],
    "merchant": ["is_new_merchant"],
    "distance": ["dist_km"],
    "customer": ["age", "log_city_pop", "gender_m"],
    "calendar": ["day_of_week", "is_weekend"],
}


def model_frame(rows, kind: str = "hist_gb") -> pd.DataFrame:
    """Feature rows -> the exact input format each library expects."""
    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows, columns=FEATURE_NAMES)
    df = df[FEATURE_NAMES].astype("float64")
    if kind == "catboost":
        df["category_code"] = df["category_code"].astype("int64")  # CatBoost wants int/str categories
    else:
        df["category_code"] = pd.Categorical(df["category_code"], categories=range(len(CATEGORIES)))
    return df


@dataclass
class FraudModel:
    estimator: object
    review_threshold: float
    block_threshold: float
    baseline: dict          # typical legitimate value of every feature
    metadata: dict          # includes "kind": hist_gb | xgboost | lightgbm | catboost

    @property
    def kind(self) -> str:
        return self.metadata.get("kind", "hist_gb")

    @property
    def name(self) -> str:
        return self.metadata.get("name", self.kind)

    # ------------------------------------------------------------------ io --
    def save(self, path: Path) -> None:
        joblib.dump(self, path)

    @staticmethod
    def load(path: Path) -> "FraudModel":
        return joblib.load(path)

    # ------------------------------------------------------------- scoring --
    def score_many(self, rows) -> np.ndarray:
        return np.asarray(self.estimator.predict_proba(model_frame(rows, self.kind)))[:, 1]

    def score(self, features: dict) -> float:
        return float(self.score_many([features])[0])

    def decide(self, score: float) -> str:
        if score >= self.block_threshold:
            return BLOCK
        if score >= self.review_threshold:
            return REVIEW
        return APPROVE

    # ------------------------------------------------------- explanations --
    def explain(self, features: dict, top_k: int = 3) -> list[dict]:
        """Occlusion-based reason codes.

        For each feature group, replace its values with the typical legitimate
        value and measure how much the fraud score drops. The groups with the
        biggest drop are the reasons this transaction looked suspicious.
        """
        base_score = self.score(features)
        variants = []
        for group, cols in _EXPLAIN_GROUPS.items():
            v = dict(features)
            for c in cols:
                v[c] = self.baseline[c]
            variants.append(v)
        scores = self.score_many(variants)
        impacts = sorted(
            ((g, base_score - s) for g, s in zip(_EXPLAIN_GROUPS, scores)),
            key=lambda x: x[1], reverse=True,
        )
        return [
            {"factor": g, "impact": round(float(d), 4), "text": describe(g, features)}
            for g, d in impacts[:top_k] if d > 0.01
        ]


def describe(group: str, f: dict) -> str:
    """Human-readable sentence for one reason group."""
    def fmt(x, nd=1):
        return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{nd}f}"

    if group == "amount":
        return (f"Amount ${f['amt']:.2f} is {fmt(f['amt_to_card_mean'])}x this card's average "
                f"(${fmt(f['card_amt_mean'], 2)})")
    if group == "time":
        return f"Made at {int(f['hour']):02d}:00" + (" (night-time)" if f["is_night"] else "")
    if group == "velocity":
        return (f"{int(f['txn_count_1h'])} card transactions in the previous hour, "
                f"{int(f['txn_count_24h'])} in 24h (${f['amt_sum_24h']:.2f})")
    if group == "history":
        return f"Card has {int(f['card_txn_count'])} prior transactions"
    if group == "category":
        return f"High-risk category: {CATEGORIES[int(f['category_code'])]}"
    if group == "merchant":
        return "First time this card used this merchant" if f["is_new_merchant"] else "Known merchant"
    if group == "distance":
        return f"Merchant is {f['dist_km']:.0f} km from the cardholder"
    if group == "customer":
        return f"Cardholder profile (age {f['age']:.0f})"
    if group == "calendar":
        return "Day-of-week pattern"
    return group
