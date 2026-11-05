"""Rebuild the comparison table and charts from already-trained models (no retraining).

    python -m securelytics.report

Reads reports/model_comparison.json and models/registry.json written by train.py,
re-scores the test set with each saved model and redraws the charts.
"""
from __future__ import annotations

import json

import pandas as pd

from . import config
from .registry import load_models, read_registry
from .train import comparison_markdown, make_plots


def main() -> None:
    report = json.loads((config.REPORTS_DIR / "model_comparison.json").read_text(encoding="utf-8"))
    reg = read_registry()
    results = report["models"]

    md = comparison_markdown(results, reg.get("default"), report.get("failures", {}))
    (config.REPORTS_DIR / "model_comparison.md").write_text(md, encoding="utf-8")

    test = pd.read_pickle(config.DATA_PROCESSED / "test_features.pkl")
    y = test["is_fraud"].values
    curves = {}
    for name, model in load_models().items():
        if name in results:
            curves[results[name]["label"]] = model.score_many(test)
    make_plots(y, curves, results)
    print(md)
    print(f"charts written to {config.REPORTS_DIR}")


if __name__ == "__main__":
    main()
