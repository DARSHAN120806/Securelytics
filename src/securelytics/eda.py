"""Exploratory data analysis: saves charts to reports/eda/.

    python -m securelytics.eda
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from . import config
from .cleaning import clean_dataframe

FRAUD, LEGIT = "#D85A30", "#888780"


def main() -> None:
    out = config.REPORTS_DIR / "eda"
    out.mkdir(parents=True, exist_ok=True)
    df, _ = clean_dataframe(pd.read_csv(config.TRAIN_CSV))
    dt = pd.to_datetime(df["event_ts"], unit="s")
    df["hour"] = dt.dt.hour
    f, l = df[df.is_fraud == 1], df[df.is_fraud == 0]

    # 1. Fraud rate by hour
    fig, ax = plt.subplots(figsize=(7, 3.8))
    df.groupby("hour")["is_fraud"].mean().mul(100).plot.bar(ax=ax, color=FRAUD)
    ax.set_ylabel("Fraud rate (%)"); ax.set_title("Fraud concentrates at night (22:00-03:59)")
    fig.tight_layout(); fig.savefig(out / "fraud_rate_by_hour.png", dpi=130); plt.close(fig)

    # 2. Amount distribution
    fig, ax = plt.subplots(figsize=(7, 3.8))
    bins = [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2000, 30000]
    for d, lab, c in [(l, "Legitimate", LEGIT), (f, "Fraud", FRAUD)]:
        ax.hist(d["amt"], bins=bins, density=True, alpha=0.6, label=lab, color=c)
    ax.set_xscale("log"); ax.set_xlabel("Amount ($, log scale)"); ax.set_ylabel("Density")
    ax.set_title("Fraud amounts are much larger than typical spend"); ax.legend()
    fig.tight_layout(); fig.savefig(out / "amount_distribution.png", dpi=130); plt.close(fig)

    # 3. Fraud rate by category
    fig, ax = plt.subplots(figsize=(7, 4.2))
    df.groupby("category")["is_fraud"].mean().mul(100).sort_values().plot.barh(ax=ax, color=FRAUD)
    ax.set_xlabel("Fraud rate (%)"); ax.set_title("Online shopping and grocery are most targeted")
    fig.tight_layout(); fig.savefig(out / "fraud_rate_by_category.png", dpi=130); plt.close(fig)

    # 4. Fraud is bursty per card
    fig, ax = plt.subplots(figsize=(7, 3.8))
    f.groupby("cc_num").size().plot.hist(bins=30, ax=ax, color=FRAUD)
    ax.set_xlabel("Fraudulent transactions per compromised card")
    ax.set_title("Compromised cards are hit repeatedly (velocity features matter)")
    fig.tight_layout(); fig.savefig(out / "fraud_burst_per_card.png", dpi=130); plt.close(fig)
    print(f"saved charts to {out}")


if __name__ == "__main__":
    main()
