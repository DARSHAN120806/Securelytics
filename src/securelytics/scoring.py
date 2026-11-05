"""The real-time scoring engine: raw event in, decision out.

Kept free of Kafka/Postgres code so it can be unit-tested and reused by the
stream processor and the REST API.

Several models can be loaded at once. The *active* model (chosen by the admin)
makes the decision; with shadow scoring on, every other model also scores the
transaction so the admin panel can compare all models on the same live traffic.
"""
from __future__ import annotations

import hashlib
import time

from .cleaning import ValidationError, clean_record
from .features import compute_features
from .model import APPROVE, FraudModel
from .rules import apply_rules, combine


class DuplicateEvent(Exception):
    """The transaction was already processed (e.g. Kafka redelivery)."""


def card_ref(cc_num: str) -> str:
    """Pseudonymous card id for storage/display; the raw number never leaves the processor."""
    return hashlib.sha256(cc_num.encode()).hexdigest()[:16]


class Scorer:
    def __init__(self, store, models: dict[str, FraudModel] | FraudModel, active: str | None = None,
                 dedupe=None, shadow: bool = True) -> None:
        if isinstance(models, FraudModel):
            models = {models.name: models}
        self.store = store
        self.models = models
        self.active = active if active in models else next(iter(models))
        self.dedupe = dedupe  # callable(trans_id) -> True if first time seen
        self.shadow = shadow

    @property
    def model(self) -> FraudModel:
        return self.models[self.active]

    def set_active(self, name: str) -> None:
        if name not in self.models:
            raise KeyError(f"model {name!r} not loaded")
        self.active = name

    def process(self, raw: dict, commit: bool = True) -> dict:
        t0 = time.perf_counter()
        txn = clean_record(raw)  # raises ValidationError
        if commit and self.dedupe is not None and not self.dedupe(txn["trans_id"]):
            raise DuplicateEvent(txn["trans_id"])

        snap = self.store.load(txn)
        features = compute_features(txn, snap)
        model = self.model
        score = model.score(features)
        model_decision = model.decide(score)
        rule_hits = apply_rules(txn, snap, features)
        decision = combine(model_decision, rule_hits)
        reasons = [{"factor": f"rule:{h['rule']}", "impact": None, "text": h["text"]} for h in rule_hits]
        if decision != APPROVE:
            reasons += model.explain(features)
        scoring_ms = (time.perf_counter() - t0) * 1000  # latency of the decision path only

        shadow_scores = {self.active: round(score, 6)}
        if self.shadow:
            for name, m in self.models.items():
                if name != self.active:
                    shadow_scores[name] = round(m.score(features), 6)
        if commit:
            self.store.commit(txn)

        return {
            "trans_id": txn["trans_id"],
            "event_ts": txn["event_ts"],
            "card_ref": card_ref(txn["cc_num"]),
            "card_last4": txn["cc_num"][-4:],
            "merchant": txn["merchant"],
            "category": txn["category"],
            "amt": txn["amt"],
            "model_name": self.active,
            "score": round(score, 6),
            "decision": decision,
            "model_decision": model_decision,
            "rules_fired": [h["rule"] for h in rule_hits],
            "reasons": reasons,
            "shadow_scores": shadow_scores,
            "is_fraud": txn["is_fraud"],
            "features": features,
            "scoring_ms": round(scoring_ms, 3),
        }


__all__ = ["Scorer", "ValidationError", "DuplicateEvent", "card_ref"]
