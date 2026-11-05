"""Expert rules that run next to the ML model.

The model only knows fraud patterns present in its training data. Rules cover
known attack patterns the data lacks (e.g. card testing). Rules can only
*escalate* a decision (APPROVE -> REVIEW -> BLOCK), never relax it.
"""
from __future__ import annotations

from .features import CardSnapshot
from .model import APPROVE, BLOCK, REVIEW

_RANK = {APPROVE: 0, REVIEW: 1, BLOCK: 2}

SMALL_TEST_AMOUNT = 5.0
CARD_TESTING_MIN_TESTS = 3
CARD_TESTING_WINDOW = 3600
VELOCITY_1H_LIMIT = 8
CASHOUT_MIN_AMOUNT = 300.0


def apply_rules(txn: dict, snap: CardSnapshot, features: dict) -> list[dict]:
    """Return the rules that fired, each with the decision it demands."""
    hits = []
    ts = txn["event_ts"]
    tests = sum(1 for t, a in snap.window if ts - t < CARD_TESTING_WINDOW and a <= SMALL_TEST_AMOUNT)
    if tests >= CARD_TESTING_MIN_TESTS and txn["amt"] >= CASHOUT_MIN_AMOUNT:
        hits.append({"rule": "card_testing", "decision": BLOCK,
                     "text": f"{tests} tiny 'test' charges (<= ${SMALL_TEST_AMOUNT:.0f}) in the last hour, "
                             f"then ${txn['amt']:.2f}"})
    elif tests >= CARD_TESTING_MIN_TESTS:
        hits.append({"rule": "card_testing_probe", "decision": REVIEW,
                     "text": f"{tests + 1} tiny charges in the last hour (possible card testing)"})
    if features["txn_count_1h"] >= VELOCITY_1H_LIMIT:
        hits.append({"rule": "velocity_1h", "decision": REVIEW,
                     "text": f"{features['txn_count_1h']} transactions in the previous hour"})
    return hits


def combine(model_decision: str, hits: list[dict]) -> str:
    return max([model_decision] + [h["decision"] for h in hits], key=_RANK.__getitem__)
