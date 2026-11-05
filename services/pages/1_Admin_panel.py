"""Admin panel: compare the four models and switch the live one."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from ui_common import active_model, execute, label, q, rds  # noqa: E402

from securelytics import config  # noqa: E402
from securelytics.live_metrics import per_model_metrics  # noqa: E402
from securelytics.registry import MODEL_CATALOG, read_registry, set_active  # noqa: E402

st.set_page_config(page_title="Securelytics - admin", layout="wide")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# ------------------------------------------------------------------ login --
if not ADMIN_PASSWORD:
    st.title("Admin panel")
    st.error("Admin panel is disabled: set ADMIN_PASSWORD in your .env file and restart (docker compose up).")
    st.stop()
if not st.session_state.get("is_admin"):
    st.title("Admin panel")
    with st.form("login"):
        user = st.text_input("Admin name")
        pwd = st.text_input("Password", type="password")
        if st.form_submit_button("Log in"):
            if pwd == ADMIN_PASSWORD and user.strip():
                st.session_state.update(is_admin=True, admin_name=user.strip())
                st.rerun()
            else:
                st.error("Wrong password, or admin name missing.")
    st.caption("Password is set with ADMIN_PASSWORD in your .env file.")
    st.stop()

reg = read_registry()
trained = reg.get("models", {})
current = active_model()

st.title("Admin panel: model management")
st.caption(f"Logged in as **{st.session_state['admin_name']}**")

# -------------------------------------------------------- 1. switch model --
st.subheader("1. Live model")
c1, c2 = st.columns([2, 3])
with c1:
    st.metric("Currently deciding on live traffic", label(current))
    options = list(MODEL_CATALOG)
    choice = st.radio(
        "Choose the model that makes live decisions",
        options, index=options.index(current) if current in options else 0,
        format_func=lambda n: f"{MODEL_CATALOG[n]}" + ("" if n in trained else "  (not trained yet)"),
    )
    note = st.text_input("Reason for switch (optional)")
    can_switch = choice in trained and choice != current
    if choice not in trained:
        st.warning("This model has not been trained yet. Run: docker compose run --rm trainer")
    if st.button("Activate model", type="primary", disabled=not can_switch):
        set_active(rds(), choice)
        execute("INSERT INTO model_switches (from_model, to_model, switched_by, note) VALUES (%s, %s, %s, %s)",
                (current, choice, st.session_state["admin_name"], note))
        st.success(f"{label(choice)} is now live. The stream processor switches within about 1 second.")
        st.rerun()
with c2:
    if current in trained:
        t = trained[current]
        st.markdown(f"**{label(current)}** thresholds: REVIEW ≥ `{t['thresholds']['review']:.4f}`, "
                    f"BLOCK ≥ `{t['thresholds']['block']:.4f}` · {t.get('n_trees', '?')} trees · "
                    f"trained {t.get('trained_at', '?')}")
    hist = q("SELECT switched_at, from_model, to_model, switched_by, note FROM model_switches "
             "ORDER BY switched_at DESC LIMIT 10")
    st.markdown("**Switch history**")
    if hist.empty:
        st.caption("No switches yet.")
    else:
        st.dataframe(hist, hide_index=True, width="stretch")

# ------------------------------------------------- 2. offline comparison --
st.subheader("2. Offline comparison (unseen test period, 555,719 transactions)")
rows = []
for name, lab in MODEL_CATALOG.items():
    t = trained.get(name, {}).get("test")
    if not t:
        rows.append({"Model": lab, "Status": "not trained"})
        continue
    rows.append({
        "Model": lab + (" (live)" if name == current else ""),
        "Status": "trained",
        "PR-AUC": t["pr_auc"], "ROC-AUC": t["roc_auc"],
        "Accuracy": t["accuracy_block"], "Precision": t["precision_block"],
        "Recall": t["recall_block"], "F1": t["f1_block"],
        "False blocks": t["fp_block"], "Missed fraud": t["fn_block"],
        "Recall @ review": t["recall_review"],
        "Latency p50 (ms)": t.get("latency_p50_ms"),
    })
offline = pd.DataFrame(rows)
fmt = {c: "{:.4f}" for c in ["PR-AUC", "ROC-AUC", "F1"]}
fmt.update({c: "{:.2%}" for c in ["Accuracy", "Precision", "Recall", "Recall @ review"]})
fmt["Latency p50 (ms)"] = "{:.2f}"
st.dataframe(offline.style.format(fmt, na_rep="-"), hide_index=True, width="stretch")
st.caption("Accuracy/precision/recall/F1 at each model's BLOCK threshold. Accuracy is ~99.6% even for a model "
           "that never flags fraud, so judge models on PR-AUC, recall and false blocks.")
for img in ["model_comparison_curves.png", "model_comparison_bars.png"]:
    p = config.REPORTS_DIR / img
    if p.is_file():
        st.image(str(p))

# ----------------------------------------------------- 3. live comparison --
st.subheader("3. Live comparison on the same traffic (shadow scoring)")
window = st.select_slider("Window (most recent transactions)", [1000, 5000, 20000, 50000, 100000], value=20000)
live = q("SELECT shadow_scores, is_fraud, amt FROM transactions ORDER BY processed_at DESC LIMIT %s", (window,))
lm = per_model_metrics(live, reg)
if lm.empty:
    st.info("No live transactions yet. Start the producer.")
else:
    show = lm[["label", "transactions", "fraud_in_window", "pr_auc", "roc_auc", "accuracy_block",
               "precision_block", "recall_block", "f1_block", "false_alerts_block", "missed_fraud_block",
               "fraud_amt_caught_review"]].rename(columns={
        "label": "Model", "transactions": "Txns", "fraud_in_window": "Fraud", "pr_auc": "PR-AUC",
        "roc_auc": "ROC-AUC", "accuracy_block": "Accuracy", "precision_block": "Precision",
        "recall_block": "Recall", "f1_block": "F1", "false_alerts_block": "False blocks",
        "missed_fraud_block": "Missed fraud", "fraud_amt_caught_review": "Fraud $ caught (review)"})
    st.dataframe(show.style.format({"PR-AUC": "{:.4f}", "ROC-AUC": "{:.4f}", "Accuracy": "{:.3%}",
                                    "Precision": "{:.2%}", "Recall": "{:.2%}", "F1": "{:.4f}",
                                    "Fraud $ caught (review)": "${:,.0f}"}, na_rep="-"),
                 hide_index=True, width="stretch")
    st.caption("Every model scores every transaction; only the live model's decision is applied.")

# ------------------------------------------- 4. actual decisions by model --
st.subheader("4. Actual decisions, by the model that made them")
act = q("""SELECT model_name, count(*) AS txns,
                  count(*) FILTER (WHERE decision = 'BLOCK') AS blocked,
                  count(*) FILTER (WHERE decision = 'REVIEW') AS review,
                  count(*) FILTER (WHERE is_fraud = 1 AND decision <> 'APPROVE') AS fraud_flagged,
                  count(*) FILTER (WHERE is_fraud = 1) AS fraud_total,
                  count(*) FILTER (WHERE is_fraud = 0 AND decision = 'BLOCK') AS good_customers_blocked,
                  min(processed_at) AS first_used, max(processed_at) AS last_used
           FROM transactions GROUP BY model_name ORDER BY last_used DESC""")
if not act.empty:
    act["model_name"] = act["model_name"].map(label)
    act["recall"] = (act["fraud_flagged"] / act["fraud_total"].where(act["fraud_total"] > 0)).map(
        lambda v: "-" if pd.isna(v) else f"{v:.1%}")
    st.dataframe(act, hide_index=True, width="stretch")

if st.button("Log out"):
    st.session_state.clear(); st.rerun()
