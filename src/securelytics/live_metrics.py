"""Live, per-model performance computed from stored transactions.

Every transaction stores the score of *every* loaded model (shadow scores), so
all models can be compared on exactly the same live traffic, each using its
own thresholds from the registry. Labels (is_fraud) exist because this is a
replay of a labelled dataset; in production they arrive later (chargebacks,
analyst reviews).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score


def _as_dict(v):
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        return json.loads(v)
    return {}


def per_model_metrics(df: pd.DataFrame, registry: dict) -> pd.DataFrame:
    """df needs columns: shadow_scores (dict/json), is_fraud, amt."""
    if df.empty:
        return pd.DataFrame()
    scores = pd.DataFrame([_as_dict(v) for v in df["shadow_scores"]], index=df.index)
    y = pd.to_numeric(df["is_fraud"], errors="coerce")
    rows = []
    for name, entry in registry.get("models", {}).items():
        if name not in scores:
            continue
        s = scores[name].astype(float)
        mask = s.notna() & y.notna()
        if not mask.any():
            continue
        yy, ss, amt = y[mask].astype(int).values, s[mask].values, df.loc[mask, "amt"].astype(float).values
        row = {"model": name, "label": entry.get("label", name), "transactions": int(mask.sum()),
               "fraud_in_window": int(yy.sum())}
        for level in ("block", "review"):
            flag = ss >= entry["thresholds"][level]
            tp = int((flag & (yy == 1)).sum()); fp = int((flag & (yy == 0)).sum())
            fn = int((~flag & (yy == 1)).sum()); tn = int((~flag & (yy == 0)).sum())
            p = tp / (tp + fp) if tp + fp else np.nan
            r = tp / (tp + fn) if tp + fn else np.nan
            row[f"accuracy_{level}"] = (tp + tn) / len(yy)
            row[f"precision_{level}"] = p
            row[f"recall_{level}"] = r
            row[f"f1_{level}"] = 2 * p * r / (p + r) if p and r and (p + r) else np.nan
            row[f"alerts_{level}"] = tp + fp
            row[f"false_alerts_{level}"] = fp
            row[f"missed_fraud_{level}"] = fn
            row[f"fraud_amt_caught_{level}"] = float(amt[flag & (yy == 1)].sum())
        both = len(set(yy)) == 2
        row["roc_auc"] = roc_auc_score(yy, ss) if both else np.nan
        row["pr_auc"] = average_precision_score(yy, ss) if both else np.nan
        rows.append(row)
    return pd.DataFrame(rows)
