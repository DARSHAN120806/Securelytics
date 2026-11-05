"""Multi-model registry, live switching, shadow scoring and live metrics."""
import json

import numpy as np
import pandas as pd
import pytest
from fake_redis import FakeRedis

from securelytics import config
from securelytics.live_metrics import per_model_metrics
from securelytics.model import FraudModel
from securelytics.registry import ACTIVE_KEY, MODEL_CATALOG, get_active, read_registry, set_active
from securelytics.scoring import Scorer
from securelytics.store import RedisStore


class AlwaysScore:
    """Stand-in estimator returning a fixed probability."""
    def __init__(self, p): self.p = p
    def predict_proba(self, X): return np.column_stack([1 - np.full(len(X), self.p), np.full(len(X), self.p)])


def stub_model(name, p, baseline):
    return FraudModel(AlwaysScore(p), review_threshold=0.5, block_threshold=0.9, baseline=baseline,
                      metadata={"name": name, "kind": "hist_gb"})


def test_registry_lists_trained_models_with_metrics():
    reg = read_registry()
    assert reg["default"] in reg["models"]
    for name, entry in reg["models"].items():
        assert name in MODEL_CATALOG
        assert (config.MODELS_DIR / entry["file"]).is_file()
        t = entry["test"]
        for key in ("pr_auc", "roc_auc", "accuracy_block", "precision_block", "recall_block", "f1_block"):
            assert 0 <= t[key] <= 1
        assert entry["thresholds"]["review"] <= entry["thresholds"]["block"]


def test_active_model_follows_redis_and_falls_back_to_default(models):
    r = FakeRedis()
    default = read_registry()["default"]
    expected = default if default in models else next(iter(models))  # default's library may be missing
    assert get_active(r, models, default) == expected
    r.set(ACTIVE_KEY, "does-not-exist")
    assert get_active(r, models, default) == expected
    other = next(n for n in models if n != expected) if len(models) > 1 else expected
    set_active(r, other)
    assert get_active(r, models, default) == other
    with pytest.raises(ValueError):
        set_active(r, "not-a-model")


def test_switching_changes_decision_and_shadow_scores_cover_all_models(model, raw_test_sample):
    models = {"real": model, "always_fraud": stub_model("always_fraud", 0.95, model.baseline)}
    scorer = Scorer(RedisStore(FakeRedis()), models, active="real", shadow=True)
    raw = raw_test_sample.iloc[0].to_dict()
    res = scorer.process(raw, commit=False)
    assert res["model_name"] == "real" and res["decision"] == "APPROVE"
    assert set(res["shadow_scores"]) == {"real", "always_fraud"}
    assert res["shadow_scores"]["always_fraud"] == pytest.approx(0.95)

    scorer.set_active("always_fraud")
    res2 = scorer.process(raw, commit=False)
    assert res2["model_name"] == "always_fraud" and res2["decision"] == "BLOCK"
    assert res2["shadow_scores"]["real"] == pytest.approx(res["score"])
    json.dumps(res2["shadow_scores"])


def test_shadow_off_scores_only_active_model(model, raw_test_sample):
    models = {"real": model, "other": stub_model("other", 0.1, model.baseline)}
    res = Scorer(RedisStore(FakeRedis()), models, active="real", shadow=False).process(
        raw_test_sample.iloc[0].to_dict(), commit=False)
    assert list(res["shadow_scores"]) == ["real"]


def test_live_metrics_per_model():
    reg = {"models": {"a": {"label": "A", "thresholds": {"review": 0.5, "block": 0.8}},
                      "b": {"label": "B", "thresholds": {"review": 0.5, "block": 0.8}}}}
    df = pd.DataFrame({
        "shadow_scores": [json.dumps({"a": 0.9, "b": 0.1}), {"a": 0.1, "b": 0.9}, {"a": 0.9, "b": 0.9}, {"a": 0.0, "b": 0.0}],
        "is_fraud": [1, 0, 1, 0], "amt": [100, 10, 50, 5]})
    m = per_model_metrics(df, reg).set_index("model")
    assert m.loc["a", "recall_block"] == 1.0 and m.loc["a", "precision_block"] == 1.0
    assert m.loc["a", "accuracy_block"] == 1.0 and m.loc["a", "fraud_amt_caught_block"] == 150
    assert m.loc["b", "recall_block"] == 0.5 and m.loc["b", "false_alerts_block"] == 1
    assert m.loc["b", "accuracy_block"] == 0.5
