"""Step 2 of the offline pipeline: train and compare four models.

    python -m securelytics.train                       # all available models
    python -m securelytics.train --models xgboost catboost

Models: HistGradientBoosting (scikit-learn), XGBoost, LightGBM, CatBoost.
A logistic regression is also trained as a simple reference baseline.

* Split: out-of-time. The first 80% of the training period fits the models, the
  last 20% is used for early stopping and threshold tuning, and fraudTest.csv
  (a later, unseen period) is the final test set. Every model sees exactly the
  same data, so the comparison is fair.
* Each model gets its own thresholds (score scales differ between libraries):
    BLOCK  >= lowest score with >= 95% precision on validation
    REVIEW >= score that maximises (fraud $ caught - $10 x false alerts)
* Outputs: models/<name>.joblib, models/registry.json,
  reports/model_comparison.{json,md}, reports/*.png
"""
from __future__ import annotations

import argparse
import json
import logging
import time
import traceback
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, precision_recall_curve, roc_auc_score,
                             roc_curve)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import config
from .features import FEATURE_NAMES
from .model import FraudModel, model_frame
from .registry import MODEL_CATALOG, read_registry, write_registry

log = logging.getLogger("train")

FALSE_ALERT_COST = 10.0      # analyst time + customer friction per false alarm ($)
BLOCK_MIN_PRECISION = 0.95
FRAUD_WEIGHT = 5             # same class weighting for every model
MAX_TREES = 1500
EARLY_STOP = 50
SEED = 42


# --------------------------------------------------------------------------- #
# Model builders: each returns a fitted estimator with predict_proba
# --------------------------------------------------------------------------- #
def fit_hist_gb(Xf, yf, Xv, yv):
    clf = HistGradientBoostingClassifier(
        learning_rate=0.05, max_leaf_nodes=63, min_samples_leaf=50, l2_regularization=1.0,
        max_iter=MAX_TREES, early_stopping=True, n_iter_no_change=30, scoring="loss",
        class_weight={0: 1, 1: FRAUD_WEIGHT}, categorical_features="from_dtype", random_state=SEED,
    )
    clf.fit(Xf, yf, X_val=Xv, y_val=yv)
    return clf, int(clf.n_iter_)


def fit_xgboost(Xf, yf, Xv, yv):
    from xgboost import XGBClassifier
    clf = XGBClassifier(
        n_estimators=MAX_TREES, learning_rate=0.05, tree_method="hist", grow_policy="lossguide",
        max_leaves=63, max_depth=0, min_child_weight=1, reg_lambda=1.0, subsample=0.9,
        colsample_bytree=0.9, scale_pos_weight=FRAUD_WEIGHT, enable_categorical=True,
        eval_metric="aucpr", early_stopping_rounds=EARLY_STOP, n_jobs=-1, random_state=SEED,
    )
    clf.fit(Xf, yf, eval_set=[(Xv, yv)], verbose=False)
    return clf, int(clf.best_iteration) + 1


def fit_lightgbm(Xf, yf, Xv, yv):
    import lightgbm as lgb
    clf = lgb.LGBMClassifier(
        n_estimators=MAX_TREES, learning_rate=0.05, num_leaves=63, min_child_samples=50,
        reg_lambda=1.0, subsample=0.9, subsample_freq=1, colsample_bytree=0.9,
        scale_pos_weight=FRAUD_WEIGHT, metric="average_precision", random_state=SEED, verbose=-1,
    )
    clf.fit(Xf, yf, eval_set=[(Xv, yv)],
            callbacks=[lgb.early_stopping(EARLY_STOP, verbose=False)])
    return clf, int(clf.best_iteration_ or MAX_TREES)


def fit_catboost(Xf, yf, Xv, yv):
    from catboost import CatBoostClassifier
    clf = CatBoostClassifier(
        iterations=MAX_TREES, learning_rate=0.08, depth=7, l2_leaf_reg=3.0,
        scale_pos_weight=FRAUD_WEIGHT, eval_metric="PRAUC", od_type="Iter", od_wait=EARLY_STOP,
        use_best_model=True, cat_features=["category_code"], random_seed=SEED,
        thread_count=-1, verbose=False, allow_writing_files=False,
    )
    clf.fit(Xf, yf, eval_set=(Xv, yv))
    return clf, int(clf.get_best_iteration()) + 1


BUILDERS = {"hist_gb": fit_hist_gb, "xgboost": fit_xgboost,
            "lightgbm": fit_lightgbm, "catboost": fit_catboost}


def logistic_baseline() -> Pipeline:
    numeric = [f for f in FEATURE_NAMES if f != "category_code"]
    pre = ColumnTransformer([
        ("num", Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)),
                          ("scale", StandardScaler())]), numeric),
        ("cat", OneHotEncoder(handle_unknown="ignore"), ["category_code"]),
    ])
    return Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=2000, class_weight="balanced"))])


# --------------------------------------------------------------------------- #
# Thresholds & metrics
# --------------------------------------------------------------------------- #
def choose_thresholds(y: np.ndarray, score: np.ndarray, amt: np.ndarray) -> dict:
    grid = np.unique(np.round(np.quantile(score, np.linspace(0.9, 1, 2001)), 6))
    best_net, review_t = -np.inf, 0.5
    block_t = None
    for t in grid:
        flag = score >= t
        tp, fp = (flag & (y == 1)).sum(), (flag & (y == 0)).sum()
        net = amt[flag & (y == 1)].sum() - FALSE_ALERT_COST * fp
        if net > best_net:
            best_net, review_t = net, float(t)
        if block_t is None and tp + fp > 0 and tp / (tp + fp) >= BLOCK_MIN_PRECISION:
            block_t = float(t)
    block_t = max(block_t if block_t is not None else 0.99, review_t)
    return {"review": review_t, "block": block_t}


def evaluate(y, score, amt, card, thresholds) -> dict:
    out = {
        "pr_auc": round(float(average_precision_score(y, score)), 4),
        "roc_auc": round(float(roc_auc_score(y, score)), 4),
        "fraud_rate": round(float(y.mean()), 5),
        "n": int(len(y)),
        "n_fraud": int(y.sum()),
    }
    fraud_cards = set(card[y == 1])
    for name, t in thresholds.items():
        flag = score >= t
        tp = int((flag & (y == 1)).sum()); fp = int((flag & (y == 0)).sum())
        fn = int((~flag & (y == 1)).sum()); tn = int((~flag & (y == 0)).sum())
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        caught_amt = float(amt[flag & (y == 1)].sum())
        out[f"at_{name}"] = {
            "threshold": round(t, 6),
            "accuracy": round((tp + tn) / len(y), 6),
            "precision": round(p, 4), "recall": round(r, 4),
            "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "alerts_per_10k_txns": round(10000 * (tp + fp) / len(y), 2),
            "fraud_amount_caught": round(caught_amt, 2),
            "fraud_amount_total": round(float(amt[y == 1].sum()), 2),
            "net_savings": round(caught_amt - FALSE_ALERT_COST * fp, 2),
            "fraud_cards_detected": f"{len(set(card[flag & (y == 1)]))}/{len(fraud_cards)}",
        }
    return out


def permutation_importance_ap(est, X: pd.DataFrame, y: np.ndarray, repeats: int = 2) -> pd.Series:
    """Drop in PR-AUC when each feature is shuffled. Library-agnostic (works for any predict_proba)."""
    rng = np.random.default_rng(SEED)
    base = average_precision_score(y, np.asarray(est.predict_proba(X))[:, 1])
    drops = {}
    for col in X.columns:
        vals = []
        for _ in range(repeats):
            Xp = X.copy()
            Xp[col] = Xp[col].sample(frac=1.0, random_state=int(rng.integers(1e9))).values
            vals.append(base - average_precision_score(y, np.asarray(est.predict_proba(Xp))[:, 1]))
        drops[col] = float(np.mean(vals))
    return pd.Series(drops)


def single_row_latency_ms(model: FraudModel, rows: pd.DataFrame, n: int = 300) -> dict:
    records = rows[FEATURE_NAMES].head(n).to_dict("records")
    model.score(records[0])  # warm-up
    times = []
    for r in records:
        t0 = time.perf_counter(); model.score(r); times.append((time.perf_counter() - t0) * 1000)
    return {"p50_ms": round(float(np.percentile(times, 50)), 3), "p95_ms": round(float(np.percentile(times, 95)), 3)}


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=list(MODEL_CATALOG), choices=list(MODEL_CATALOG))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    t_start = time.time()
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    train = pd.read_pickle(config.DATA_PROCESSED / "train_features.pkl")
    test = pd.read_pickle(config.DATA_PROCESSED / "test_features.pkl")
    cut = train["event_ts"].quantile(0.8)
    fit_df, val_df = train[train["event_ts"] <= cut], train[train["event_ts"] > cut]
    y_fit, y_val, y_test = fit_df["is_fraud"].values, val_df["is_fraud"].values, test["is_fraud"].values
    log.info("fit %s | val %s | test %s rows", f"{len(fit_df):,}", f"{len(val_df):,}", f"{len(test):,}")

    legit = fit_df[fit_df["is_fraud"] == 0]
    baseline = {f: float(np.nanmedian(legit[f].values)) for f in FEATURE_NAMES}
    baseline["category_code"] = float(legit["category_code"].mode()[0])
    trained_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ---- reference baseline ----
    lr = logistic_baseline().fit(fit_df[FEATURE_NAMES], y_fit)
    lr_val = lr.predict_proba(val_df[FEATURE_NAMES])[:, 1]
    lr_test = lr.predict_proba(test[FEATURE_NAMES])[:, 1]
    lr_thr = choose_thresholds(y_val, lr_val, val_df["amt"].values)
    results = {"logistic_baseline": {
        "label": "Logistic regression (baseline)",
        "test": evaluate(y_test, lr_test, test["amt"].values, test["cc_num"].values, lr_thr)}}
    curves = {"Logistic regression": lr_test}

    rng = np.random.default_rng(SEED)
    pi_idx = np.concatenate([np.where(y_test == 1)[0], rng.choice(np.where(y_test == 0)[0], 30000, replace=False)])

    # ---- the four candidate models ----
    reg = read_registry()
    reg.setdefault("models", {})
    failures = {}
    for name in args.models:
        label = MODEL_CATALOG[name]
        t0 = time.time()
        try:
            Xf, Xv, Xt = (model_frame(d, name) for d in (fit_df, val_df, test))
            est, n_trees = BUILDERS[name](Xf, y_fit, Xv, y_val)
        except ImportError as exc:
            failures[name] = f"library not installed: {exc}"
            log.warning("skipping %s: %s", name, failures[name]); continue
        except Exception as exc:  # noqa: BLE001 - one model failing must not stop the others
            failures[name] = f"{type(exc).__name__}: {exc}"
            log.error("training %s failed:\n%s", name, traceback.format_exc()); continue
        fit_secs = time.time() - t0

        val_score = np.asarray(est.predict_proba(Xv))[:, 1]
        test_score = np.asarray(est.predict_proba(Xt))[:, 1]
        thr = choose_thresholds(y_val, val_score, val_df["amt"].values)
        model = FraudModel(estimator=est, review_threshold=thr["review"], block_threshold=thr["block"],
                           baseline=baseline,
                           metadata={"name": name, "kind": name, "label": label, "features": FEATURE_NAMES,
                                     "trained_at": trained_at, "n_trees": n_trees})
        importance = permutation_importance_ap(est, Xt.iloc[pi_idx], y_test[pi_idx])
        res = {
            "label": label,
            "n_trees": n_trees,
            "train_seconds": round(fit_secs, 1),
            "thresholds": thr,
            "validation": evaluate(y_val, val_score, val_df["amt"].values, val_df["cc_num"].values, thr),
            "test": evaluate(y_test, test_score, test["amt"].values, test["cc_num"].values, thr),
            "latency": single_row_latency_ms(model, test),
            "top_features": {k: round(float(v), 4) for k, v in importance.nlargest(8).items()},
        }
        model.metadata["test_pr_auc"] = res["test"]["pr_auc"]
        model.save(config.MODELS_DIR / f"{name}.joblib")
        results[name] = res
        curves[label] = test_score
        reg["models"][name] = {"label": label, "file": f"{name}.joblib", "trained_at": trained_at,
                               "thresholds": thr, "n_trees": n_trees,
                               "validation_pr_auc": res["validation"]["pr_auc"],
                               "test": _summary(res)}
        log.info("%-9s val PR-AUC %.4f | test PR-AUC %.4f ROC-AUC %.4f | %d trees | %.0fs",
                 name, res["validation"]["pr_auc"], res["test"]["pr_auc"], res["test"]["roc_auc"], n_trees, fit_secs)

    trained = {n: r for n, r in results.items() if n in MODEL_CATALOG}
    if not trained:
        raise SystemExit(f"no model trained: {failures}")
    # Default = best on VALIDATION (never pick by test score: that would leak the test set)
    reg["default"] = max((n for n in reg["models"]), key=lambda n: reg["models"][n]["validation_pr_auc"])
    reg["updated_at"] = trained_at
    write_registry(reg)

    report = {"trained_at": trained_at, "default_model": reg["default"], "failures": failures,
              "split": {"fit_rows": len(fit_df), "val_rows": len(val_df), "test_rows": len(test)},
              "false_alert_cost": FALSE_ALERT_COST, "models": results}
    (config.REPORTS_DIR / "model_comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (config.REPORTS_DIR / "model_comparison.md").write_text(comparison_markdown(results, reg["default"], failures),
                                                            encoding="utf-8")
    make_plots(y_test, curves, results)
    print(comparison_markdown(results, reg["default"], failures))
    log.info("done in %.0fs", time.time() - t_start)


def _summary(res: dict) -> dict:
    t = res["test"]
    return {"pr_auc": t["pr_auc"], "roc_auc": t["roc_auc"],
            **{f"{k}_{lvl}": t[f"at_{lvl}"][k] for lvl in ("block", "review")
               for k in ("accuracy", "precision", "recall", "f1", "fp", "fn")},
            "fraud_amount_caught_review": t["at_review"]["fraud_amount_caught"],
            "latency_p50_ms": res.get("latency", {}).get("p50_ms")}


def comparison_markdown(results: dict, default: str, failures: dict) -> str:
    lines = ["# Model comparison (unseen test period, 555,719 transactions)", "",
             "| Model | PR-AUC | ROC-AUC | Accuracy | Precision | Recall | F1 | False blocks | Missed fraud | Latency p50 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for name, r in sorted(results.items(), key=lambda kv: -kv[1]["test"]["pr_auc"]):
        b = r["test"]["at_block"]
        star = " **(default)**" if name == default else ""
        lat = f"{r['latency']['p50_ms']:.2f} ms" if "latency" in r else "-"
        lines.append(f"| {r['label']}{star} | {r['test']['pr_auc']:.4f} | {r['test']['roc_auc']:.4f} | "
                     f"{b['accuracy']:.4%} | {b['precision']:.2%} | {b['recall']:.2%} | {b['f1']:.4f} | "
                     f"{b['fp']} | {b['fn']} | {lat} |")
    lines += ["", "Accuracy, precision, recall and F1 are at each model's BLOCK threshold.",
              "Accuracy is shown for completeness but is misleading here: predicting 'legit' for everything "
              "already scores 99.6%. Compare models on PR-AUC, recall and false blocks."]
    if failures:
        lines += ["", "Not trained: " + "; ".join(f"{k} ({v})" for k, v in failures.items())]
    return "\n".join(lines) + "\n"


def make_plots(y, curves: dict, results: dict) -> None:
    out = config.REPORTS_DIR
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for label, s in curves.items():
        p, r, _ = precision_recall_curve(y, s)
        axes[0].plot(r, p, label=f"{label} ({average_precision_score(y, s):.3f})")
        fpr, tpr, _ = roc_curve(y, s)
        axes[1].plot(fpr, tpr, label=f"{label} ({roc_auc_score(y, s):.4f})")
    axes[0].set(xlabel="Recall", ylabel="Precision", title="Precision-recall (PR-AUC)")
    axes[1].set(xlabel="False positive rate", ylabel="True positive rate", title="ROC (ROC-AUC)", xscale="log")
    for ax in axes:
        ax.legend(fontsize=8, loc="lower left" if ax is axes[0] else "lower right"); ax.grid(alpha=0.3)
    fig.suptitle("Model comparison on unseen test period")
    fig.tight_layout(); fig.savefig(out / "model_comparison_curves.png", dpi=130); plt.close(fig)

    models = [n for n in results if n in MODEL_CATALOG]
    metrics = ["precision", "recall", "f1"]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    w = 0.8 / len(models)
    for i, n in enumerate(models):
        vals = [results[n]["test"]["at_block"][m] for m in metrics] + [results[n]["test"]["pr_auc"]]
        ax.bar(np.arange(4) + i * w, vals, w, label=results[n]["label"])
    ax.set_xticks(np.arange(4) + w * (len(models) - 1) / 2, ["Precision", "Recall", "F1", "PR-AUC"])
    lowest = min(min(results[n]["test"]["at_block"][m] for m in metrics) for n in models)
    ax.set_ylim(max(0.0, lowest - 0.05), 1.0); ax.set_title("Test metrics at BLOCK threshold"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(out / "model_comparison_bars.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    main()
