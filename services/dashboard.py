"""Live fraud monitoring dashboard (main page). The admin panel is in pages/.

    streamlit run services/dashboard.py      (http://localhost:8501)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import streamlit as st  # noqa: E402
from ui_common import active_model, execute, label, q  # noqa: E402

st.set_page_config(page_title="Securelytics - live fraud monitor", layout="wide")
st.title("Securelytics: real-time fraud detection")
st.caption("Kafka -> stream processor (Redis features + ML model + rules) -> Postgres. Refreshes every 3 seconds. "
           "Switch models in the Admin panel (sidebar).")

scope = st.radio("Show metrics for", ["Live model only", "All models"], horizontal=True)


@st.fragment(run_every="3s")
def live():
    current = active_model()
    where, params = ("WHERE model_name = %s", (current,)) if scope == "Live model only" else ("", None)
    st.markdown(f"**Live model:** {label(current)}" +
                ("  ·  metrics below cover only transactions decided by this model" if where else ""))
    k = q(f"""
        SELECT count(*)                                              AS processed,
               count(*) FILTER (WHERE decision <> 'APPROVE')          AS alerts,
               count(*) FILTER (WHERE decision = 'BLOCK')             AS blocked,
               coalesce(sum(amt) FILTER (WHERE decision = 'BLOCK' AND is_fraud = 1), 0) AS fraud_blocked_amt,
               count(*) FILTER (WHERE processed_at > now() - interval '10 seconds') / 10.0 AS tps,
               percentile_cont(0.5)  WITHIN GROUP (ORDER BY scoring_ms) AS p50_ms,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY scoring_ms) AS p95_ms,
               count(*) FILTER (WHERE is_fraud = 1)                   AS fraud_total,
               count(*) FILTER (WHERE is_fraud = 1 AND decision <> 'APPROVE') AS fraud_flagged,
               count(*) FILTER (WHERE is_fraud = 0 AND decision = 'APPROVE')  AS true_neg
        FROM transactions {where}""", params).iloc[0]
    if not k["processed"]:
        st.info("Waiting for transactions... (start the producer, or this model has not decided any yet)")
        return
    precision = k["fraud_flagged"] / k["alerts"] if k["alerts"] else 0
    recall = k["fraud_flagged"] / k["fraud_total"] if k["fraud_total"] else 0
    accuracy = (k["fraud_flagged"] + k["true_neg"]) / k["processed"]

    c = st.columns(7)
    c[0].metric("Transactions scored", f"{int(k['processed']):,}")
    c[1].metric("Throughput", f"{float(k['tps']):.0f} /s")
    c[2].metric("Alerts (review + block)", f"{int(k['alerts']):,}")
    c[3].metric("Fraud $ blocked", f"${float(k['fraud_blocked_amt']):,.0f}")
    c[4].metric("Accuracy", f"{accuracy:.2%}")
    c[5].metric("Precision / recall", f"{precision:.0%} / {recall:.0%}")
    c[6].metric("Latency p50 / p95", f"{float(k['p50_ms']):.1f} / {float(k['p95_ms']):.1f} ms")

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Volume per minute")
        ts = q(f"""SELECT date_trunc('minute', processed_at) AS minute,
                          count(*) AS transactions,
                          count(*) FILTER (WHERE decision <> 'APPROVE') AS alerts
                   FROM transactions {where + ' AND' if where else 'WHERE'} processed_at > now() - interval '30 minutes'
                   GROUP BY 1 ORDER BY 1""", params)
        if not ts.empty:
            st.line_chart(ts.set_index("minute"))
    with right:
        st.subheader("Alerts by category")
        cat = q(f"SELECT category, count(*) AS alerts FROM alerts {where} GROUP BY 1 ORDER BY 2 DESC", params)
        if not cat.empty:
            st.bar_chart(cat.set_index("category"), horizontal=True)

    st.subheader("Latest alerts")
    a = q(f"""SELECT created_at, model_name, decision, round(score::numeric, 3) AS score,
                     '****' || card_last4 AS card, merchant, category, amt, reasons, is_fraud
              FROM alerts {where} ORDER BY created_at DESC LIMIT 25""", params)
    if not a.empty:
        a["model"] = a["model_name"].map(label)
        a["why"] = a["reasons"].apply(lambda rs: " | ".join(r["text"] for r in (rs if isinstance(rs, list) else json.loads(rs))))
        a["truth"] = a["is_fraud"].map({1: "fraud", 0: "legit"}).fillna("?")
        st.dataframe(a[["created_at", "model", "decision", "score", "card", "merchant", "category", "amt", "why", "truth"]],
                     width="stretch", hide_index=True)


live()

with st.expander("Analyst review (feedback loop)"):
    st.write("Label an alert. Labels are stored in `alerts.analyst_label` and can be used to retrain the models.")
    pending = q("SELECT trans_id, decision, amt, merchant FROM alerts WHERE analyst_label IS NULL "
                "ORDER BY created_at DESC LIMIT 50")
    if pending.empty:
        st.write("No unreviewed alerts.")
    else:
        choice = st.selectbox("Alert", pending["trans_id"],
                              format_func=lambda t: "{decision}  ${amt}  {merchant}".format(
                                  **pending.set_index("trans_id").loc[t].to_dict()))
        col1, col2 = st.columns(2)
        for col, lbl, text in [(col1, 1, "Confirm fraud"), (col2, 0, "Mark legitimate")]:
            if col.button(text):
                execute("UPDATE alerts SET analyst_label = %s, reviewed_at = now() WHERE trans_id = %s", (lbl, choice))
                st.success("Saved.")
