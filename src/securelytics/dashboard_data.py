"""SQL queries behind the web dashboard. Every function takes an open psycopg connection."""
from __future__ import annotations

import json

import pandas as pd
from psycopg.rows import dict_row

from .live_metrics import per_model_metrics

SCORE_BUCKETS = [0, 0.001, 0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0001]
SCORE_LABELS = ["<0.001", "0.001-0.01", "0.01-0.05", "0.05-0.1", "0.1-0.2", "0.2-0.3", "0.3-0.5",
                "0.5-0.7", "0.7-0.9", "0.9-1"]


def rows(conn, sql: str, params=None) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def one(conn, sql: str, params=None) -> dict:
    r = rows(conn, sql, params)
    return r[0] if r else {}


def _scope(model: str | None, alias: str = "") -> tuple[str, tuple]:
    col = f"{alias}model_name" if alias else "model_name"
    return (f"WHERE {col} = %s", (model,)) if model else ("WHERE TRUE", ())


# --------------------------------------------------------------------- overview --
def overview(conn, model: str | None, minutes: int = 60) -> dict:
    where, p = _scope(model)
    kpi = one(conn, f"""
        SELECT count(*)                                                        AS processed,
               count(*) FILTER (WHERE decision <> 'APPROVE')                   AS alerts,
               count(*) FILTER (WHERE decision = 'REVIEW')                     AS review,
               count(*) FILTER (WHERE decision = 'BLOCK')                      AS blocked,
               coalesce(sum(amt), 0)                                           AS volume_amt,
               coalesce(sum(amt) FILTER (WHERE decision = 'BLOCK' AND is_fraud = 1), 0)    AS fraud_blocked_amt,
               coalesce(sum(amt) FILTER (WHERE decision <> 'APPROVE' AND is_fraud = 1), 0) AS fraud_flagged_amt,
               coalesce(sum(amt) FILTER (WHERE is_fraud = 1), 0)               AS fraud_total_amt,
               count(*) FILTER (WHERE is_fraud = 1)                            AS fraud_total,
               count(*) FILTER (WHERE is_fraud = 1 AND decision <> 'APPROVE')  AS fraud_flagged,
               count(*) FILTER (WHERE is_fraud = 0 AND decision = 'APPROVE')   AS true_neg,
               count(*) FILTER (WHERE is_fraud = 0 AND decision = 'BLOCK')     AS good_blocked,
               count(*) FILTER (WHERE processed_at > now() - interval '60 seconds') / 60.0 AS tps,
               percentile_cont(0.5)  WITHIN GROUP (ORDER BY scoring_ms)        AS p50_ms,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY scoring_ms)        AS p95_ms,
               percentile_cont(0.5)  WITHIN GROUP (ORDER BY e2e_ms)            AS e2e_p50_ms,
               max(processed_at)                                               AS last_processed_at
        FROM transactions {where}""", p)
    n = kpi.get("processed") or 0
    alerts = kpi.get("alerts") or 0
    kpi["precision"] = kpi["fraud_flagged"] / alerts if alerts else None
    kpi["recall"] = kpi["fraud_flagged"] / kpi["fraud_total"] if kpi.get("fraud_total") else None
    kpi["accuracy"] = (kpi["fraud_flagged"] + kpi["true_neg"]) / n if n else None
    kpi["alert_rate"] = alerts / n if n else None

    series = rows(conn, f"""
        SELECT m AS minute, coalesce(t.txns, 0) AS txns, coalesce(t.alerts, 0) AS alerts,
               coalesce(t.blocked, 0) AS blocked
        FROM generate_series(date_trunc('minute', now()) - (%s - 1) * interval '1 minute',
                             date_trunc('minute', now()), interval '1 minute') AS m
        LEFT JOIN (
            SELECT date_trunc('minute', processed_at) AS mm, count(*) AS txns,
                   count(*) FILTER (WHERE decision <> 'APPROVE') AS alerts,
                   count(*) FILTER (WHERE decision = 'BLOCK') AS blocked
            FROM transactions {where} AND processed_at > now() - %s * interval '1 minute'
            GROUP BY 1) t ON t.mm = m
        ORDER BY m""", (minutes, *p, minutes))

    decisions = rows(conn, f"SELECT decision, count(*) AS n FROM transactions {where} GROUP BY 1", p)
    categories = rows(conn, f"""
        SELECT category, count(*) AS alerts,
               count(*) FILTER (WHERE is_fraud = 1) AS confirmed_fraud,
               coalesce(sum(amt), 0) AS amount
        FROM alerts {where} GROUP BY 1 ORDER BY 2 DESC LIMIT 10""", p)
    buckets = rows(conn, f"""
        SELECT width_bucket(score, ARRAY{SCORE_BUCKETS}::float8[]) AS b, count(*) AS n
        FROM transactions {where} GROUP BY 1 ORDER BY 1""", p)
    hist = {int(b["b"]): b["n"] for b in buckets}
    score_hist = [{"bucket": lab, "n": hist.get(i + 1, 0)} for i, lab in enumerate(SCORE_LABELS)]
    recent = rows(conn, f"""
        SELECT trans_id, created_at, decision, score, card_last4, merchant, category, amt, model_name, reasons, is_fraud
        FROM alerts {where} ORDER BY created_at DESC LIMIT 6""", p)
    return {"kpi": kpi, "series": series, "decisions": decisions, "categories": categories,
            "score_hist": score_hist, "recent_alerts": recent}


# ----------------------------------------------------------------------- alerts --
def _filters(args: dict, alias: str = "") -> tuple[str, list]:
    cond, p = [], []
    if args.get("decision"):
        cond.append(f"{alias}decision = %s"); p.append(args["decision"].upper())
    if args.get("category"):
        cond.append(f"{alias}category = %s"); p.append(args["category"])
    if args.get("model"):
        cond.append(f"{alias}model_name = %s"); p.append(args["model"])
    if args.get("q"):
        cond.append(f"({alias}merchant ILIKE %s OR {alias}card_last4 = %s OR {alias}trans_id = %s)")
        p += [f"%{args['q']}%", args["q"], args["q"]]
    if args.get("truth") == "fraud":
        cond.append(f"{alias}is_fraud = 1")
    elif args.get("truth") == "legit":
        cond.append(f"{alias}is_fraud = 0")
    if args.get("review") == "pending":
        cond.append(f"{alias}analyst_label IS NULL")
    elif args.get("review") == "done":
        cond.append(f"{alias}analyst_label IS NOT NULL")
    return ("WHERE " + " AND ".join(cond)) if cond else "", p


def list_alerts(conn, args: dict, limit: int, offset: int) -> dict:
    where, p = _filters(args)
    total = one(conn, f"SELECT count(*) AS n FROM alerts {where}", p).get("n", 0)
    items = rows(conn, f"""
        SELECT trans_id, created_at, event_ts, decision, score, card_last4, merchant, category, amt,
               model_name, reasons, is_fraud, analyst_label
        FROM alerts {where} ORDER BY created_at DESC LIMIT %s OFFSET %s""", (*p, limit, offset))
    return {"total": total, "items": items}


def alert_detail(conn, trans_id: str) -> dict | None:
    r = rows(conn, """
        SELECT a.*, t.shadow_scores, t.scoring_ms, t.e2e_ms, t.processed_at
        FROM alerts a JOIN transactions t USING (trans_id) WHERE a.trans_id = %s""", (trans_id,))
    return r[0] if r else None


def label_alert(conn, trans_id: str, label: int | None) -> bool:
    with conn.cursor() as cur:
        if label is None:
            cur.execute("UPDATE alerts SET analyst_label = NULL, reviewed_at = NULL WHERE trans_id = %s", (trans_id,))
        else:
            cur.execute("UPDATE alerts SET analyst_label = %s, reviewed_at = now() WHERE trans_id = %s",
                        (int(label), trans_id))
    conn.commit()
    return True


def alert_filters(conn) -> dict:
    return {"categories": [r["category"] for r in rows(conn, "SELECT DISTINCT category FROM transactions ORDER BY 1")],
            "models": [r["model_name"] for r in rows(conn, "SELECT DISTINCT model_name FROM transactions ORDER BY 1")]}


# ----------------------------------------------------------------- transactions --
def list_transactions(conn, args: dict, limit: int, offset: int) -> dict:
    args = {k: v for k, v in args.items() if k not in ("review",)}
    where, p = _filters(args)
    total = one(conn, f"SELECT count(*) AS n FROM transactions {where}", p).get("n", 0)
    items = rows(conn, f"""
        SELECT trans_id, processed_at, event_ts, decision, score, card_last4, merchant, category, amt,
               model_name, is_fraud, scoring_ms
        FROM transactions {where} ORDER BY processed_at DESC LIMIT %s OFFSET %s""", (*p, limit, offset))
    return {"total": total, "items": items}


# ----------------------------------------------------------------------- models --
def live_model_metrics(conn, registry: dict, window: int) -> list[dict]:
    data = rows(conn, "SELECT shadow_scores, is_fraud, amt FROM transactions ORDER BY processed_at DESC LIMIT %s",
                (window,))
    df = pd.DataFrame(data, columns=["shadow_scores", "is_fraud", "amt"])
    if df.empty:
        return []
    df["shadow_scores"] = df["shadow_scores"].apply(lambda v: v if isinstance(v, dict) else json.loads(v or "{}"))
    m = per_model_metrics(df, registry)
    return [] if m.empty else m.to_dict("records")


def decisions_by_model(conn) -> list[dict]:
    return rows(conn, """
        SELECT model_name, count(*) AS txns,
               count(*) FILTER (WHERE decision = 'BLOCK') AS blocked,
               count(*) FILTER (WHERE decision = 'REVIEW') AS review,
               count(*) FILTER (WHERE is_fraud = 1 AND decision <> 'APPROVE') AS fraud_flagged,
               count(*) FILTER (WHERE is_fraud = 1) AS fraud_total,
               count(*) FILTER (WHERE is_fraud = 0 AND decision = 'BLOCK') AS good_blocked,
               min(processed_at) AS first_used, max(processed_at) AS last_used
        FROM transactions GROUP BY model_name ORDER BY last_used DESC""")


def switches(conn, limit: int = 20) -> list[dict]:
    return rows(conn, "SELECT switched_at, from_model, to_model, switched_by, note FROM model_switches "
                      "ORDER BY switched_at DESC LIMIT %s", (limit,))


def log_switch(conn, from_model, to_model, by, note) -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO model_switches (from_model, to_model, switched_by, note) VALUES (%s, %s, %s, %s)",
                    (from_model, to_model, by, note))
    conn.commit()


# ----------------------------------------------------------------------- system --
def dead_letters(conn, limit: int = 50) -> dict:
    total = one(conn, "SELECT count(*) AS n FROM dead_letters").get("n", 0)
    items = rows(conn, "SELECT id, created_at, error, payload FROM dead_letters ORDER BY created_at DESC LIMIT %s",
                 (limit,))
    return {"total": total, "items": items}


def db_stats(conn) -> dict:
    return one(conn, """
        SELECT (SELECT count(*) FROM transactions) AS transactions,
               (SELECT count(*) FROM alerts) AS alerts,
               (SELECT count(*) FROM alerts WHERE analyst_label IS NULL) AS alerts_pending_review,
               (SELECT count(*) FROM dead_letters) AS dead_letters,
               (SELECT count(*) FROM model_switches) AS model_switches,
               (SELECT max(processed_at) FROM transactions) AS last_processed_at""")
