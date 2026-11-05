"""Step 1 of the offline pipeline: clean raw CSVs and build features.

    python -m securelytics.prepare

Outputs
    data/processed/train_features.pkl, test_features.pkl
    models/card_state_snapshot.json   (card history at the end of the training period,
                                       loaded into Redis so live features start warm)
    reports/data_quality.json
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from . import config
from .cleaning import CLEAN_COLUMNS, clean_dataframe
from .features import FEATURE_NAMES, compute_features
from .store import InMemoryStore


def _records(clean: pd.DataFrame):
    """Yield one plain-Python dict per row without materialising them all (keeps memory low)."""
    for tup in clean[CLEAN_COLUMNS].itertuples(index=False, name=None):
        txn = dict(zip(CLEAN_COLUMNS, tup))
        for k in ("event_ts", "gender_m", "city_pop"):
            txn[k] = int(txn[k])
        for k in ("amt", "lat", "long", "merch_lat", "merch_long"):
            txn[k] = float(txn[k])
        yield txn


def build_feature_frame(clean: pd.DataFrame, store: InMemoryStore) -> pd.DataFrame:
    """Replay transactions in event-time order, exactly like the live stream."""
    out = np.empty((len(clean), len(FEATURE_NAMES)), dtype="float64")
    for i, txn in enumerate(_records(clean)):
        f = compute_features(txn, store.load(txn))
        out[i] = [f[name] for name in FEATURE_NAMES]
        store.commit(txn)
    feats = pd.DataFrame(out, columns=FEATURE_NAMES)
    feats["trans_id"] = clean["trans_id"].values
    feats["event_ts"] = clean["event_ts"].values
    feats["cc_num"] = clean["cc_num"].values
    feats["is_fraud"] = clean["is_fraud"].astype(int).values
    return feats


def profile(df: pd.DataFrame) -> dict:
    return {
        "rows": len(df),
        "cards": int(df["cc_num"].nunique()),
        "merchants": int(df["merchant"].nunique()),
        "fraud_count": int(df["is_fraud"].sum()),
        "fraud_rate": round(float(df["is_fraud"].mean()), 6),
        "period": [pd.to_datetime(df["event_ts"].min(), unit="s").isoformat(),
                   pd.to_datetime(df["event_ts"].max(), unit="s").isoformat()],
        "amount": {k: round(float(v), 2) for k, v in df["amt"].describe().items()},
    }


def main() -> None:
    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    quality = {}
    cleaned = {}
    for name, path in [("train", config.TRAIN_CSV), ("test", config.TEST_CSV)]:
        t0 = time.time()
        raw = pd.read_csv(path)
        quality[name] = {"raw_shape": list(raw.shape),
                         "raw_null_counts": {k: int(v) for k, v in raw.isna().sum().items() if v}}
        clean, rep = clean_dataframe(raw)
        quality[name]["cleaning"] = rep.as_dict()
        quality[name]["profile"] = profile(clean)
        cleaned[name] = clean
        print(f"[{name}] cleaned {rep.rows_in:,} -> {rep.rows_out:,} rows in {time.time() - t0:.1f}s")

    overlap = set(cleaned["train"]["trans_id"]) & set(cleaned["test"]["trans_id"])
    quality["train_test_trans_id_overlap"] = len(overlap)
    quality["test_cards_unseen_in_train"] = len(set(cleaned["test"]["cc_num"]) - set(cleaned["train"]["cc_num"]))
    quality["time_split_ok"] = bool(cleaned["train"]["event_ts"].max() <= cleaned["test"]["event_ts"].min())
    if overlap:
        cleaned["test"] = cleaned["test"][~cleaned["test"]["trans_id"].isin(overlap)]

    store = InMemoryStore()
    t0 = time.time()
    train_feats = build_feature_frame(cleaned["train"], store)
    store.export_snapshot(config.MODELS_DIR / "card_state_snapshot.json")
    test_feats = build_feature_frame(cleaned["test"], store)  # history carries over, as in production
    print(f"features built in {time.time() - t0:.1f}s")

    train_feats.to_pickle(config.DATA_PROCESSED / "train_features.pkl")
    test_feats.to_pickle(config.DATA_PROCESSED / "test_features.pkl")
    (config.REPORTS_DIR / "data_quality.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
    print(json.dumps({k: v["cleaning"] for k, v in quality.items() if isinstance(v, dict) and "cleaning" in v}, indent=2))


if __name__ == "__main__":
    main()
