import json

import numpy as np
import pandas as pd
import pytest
from fake_redis import FakeRedis

from securelytics import config
from securelytics.model import APPROVE, BLOCK, REVIEW
from securelytics.scoring import DuplicateEvent, Scorer, ValidationError
from securelytics.store import RedisStore


@pytest.fixture()
def live_scorer(model):
    """Scorer exactly as the processor builds it: Redis warmed from the training snapshot."""
    snap = config.MODELS_DIR / "card_state_snapshot.json"
    if not snap.is_file() or not (config.DATA_PROCESSED / "test_features.pkl").is_file():
        pytest.skip("needs prepared data (run python -m securelytics.prepare)")
    r = FakeRedis()
    store = RedisStore(r)
    store.import_snapshot(snap)
    first = lambda tid: bool(r.set(f"seen:{tid}", 1, nx=True))  # noqa: E731
    return Scorer(store, model, dedupe=first)


def test_decisions_follow_thresholds(model):
    assert model.decide(0.0) == APPROVE
    assert model.decide(model.review_threshold) == REVIEW
    assert model.decide(model.block_threshold) == BLOCK


def test_live_path_reproduces_offline_scores(live_scorer, model, raw_test_sample):
    """Streaming the raw CSV rows through clean -> Redis -> model gives the offline test scores."""
    offline = pd.read_pickle(config.DATA_PROCESSED / "test_features.pkl").head(5000).set_index("trans_id")
    offline_scores = pd.Series(model.score_many(offline.reset_index()), index=offline.index)
    for raw in raw_test_sample.head(5000).to_dict("records"):
        res = live_scorer.process(raw)
        assert np.isclose(res["score"], offline_scores[res["trans_id"]], atol=1e-6)


def test_alerts_have_reasons_and_output_is_json_safe(live_scorer, raw_test_sample):
    frauds = raw_test_sample[raw_test_sample["is_fraud"] == "1"]
    caught = 0
    for raw in raw_test_sample.head(int(frauds.index[20]) + 1).to_dict("records"):
        res = live_scorer.process(raw)
        if res["decision"] != APPROVE:
            assert res["reasons"], res
            caught += res["is_fraud"] == 1
        assert "cc_num" not in res and len(res["card_last4"]) == 4
        json.dumps({k: v for k, v in res.items() if k != "features"})
    assert caught >= 15


def test_duplicates_and_invalid_events(live_scorer, raw_test_sample):
    raw = raw_test_sample.iloc[0].to_dict()
    live_scorer.process(raw)
    with pytest.raises(DuplicateEvent):
        live_scorer.process(raw)
    with pytest.raises(ValidationError):
        live_scorer.process({**raw, "trans_num": "x1", "amt": "-3"})


def test_rules_catch_card_testing_the_model_misses(model):
    from fake_redis import FakeRedis
    from test_cleaning import GOOD

    scorer = Scorer(RedisStore(FakeRedis()), model)
    base = {**GOOD, "trans_date_trans_time": "2020-07-01 14:00:00", "category": "misc_net"}
    for i in range(3):
        res = scorer.process({**base, "trans_num": f"probe{i}", "amt": "1.50",
                              "trans_date_trans_time": f"2020-07-01 14:0{i}:00"})
    assert "card_testing_probe" not in res["rules_fired"]  # only 2 prior tests at the 3rd probe
    res = scorer.process({**base, "trans_num": "cashout", "amt": "900.00", "category": "shopping_net",
                          "trans_date_trans_time": "2020-07-01 14:10:00"})
    assert res["decision"] == BLOCK and "card_testing" in res["rules_fired"]
    assert res["reasons"][0]["factor"] == "rule:card_testing"
