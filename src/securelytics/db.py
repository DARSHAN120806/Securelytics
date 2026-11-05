"""Postgres access for the processor, API and dashboard."""
from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime, timezone

import psycopg

from . import config
from .cleaning import redact_payload

log = logging.getLogger(__name__)

TXN_SQL = """
INSERT INTO transactions (trans_id, event_ts, card_ref, card_last4, merchant, category, amt,
                          model_name, score, decision, shadow_scores, is_fraud, scoring_ms, e2e_ms)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (trans_id) DO NOTHING
"""
ALERT_SQL = """
INSERT INTO alerts (trans_id, event_ts, card_ref, card_last4, merchant, category, amt,
                    model_name, score, decision, reasons, features, is_fraud)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (trans_id) DO NOTHING
"""


def connect(dsn: str = config.POSTGRES_DSN, retries: int = 30) -> psycopg.Connection:
    for attempt in range(1, retries + 1):
        try:
            return psycopg.connect(dsn, autocommit=False)
        except psycopg.OperationalError as exc:
            log.warning("postgres not ready (%s/%s): %s", attempt, retries, exc)
            time.sleep(2)
    raise RuntimeError("could not connect to Postgres")


def _ts(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def _sanitize(obj):
    """NaN/inf are not valid JSON for Postgres: store them as null."""
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


def _clean_json(obj) -> str:
    return json.dumps(_sanitize(obj), default=float)


def write_results(conn: psycopg.Connection, results: list[dict]) -> None:
    if not results:
        return
    txn_rows = [(r["trans_id"], _ts(r["event_ts"]), r["card_ref"], r["card_last4"], r["merchant"],
                 r["category"], r["amt"], r["model_name"], r["score"], r["decision"],
                 _clean_json(r.get("shadow_scores", {})), r["is_fraud"],
                 r["scoring_ms"], r.get("e2e_ms")) for r in results]
    alert_rows = [(r["trans_id"], _ts(r["event_ts"]), r["card_ref"], r["card_last4"], r["merchant"],
                   r["category"], r["amt"], r["model_name"], r["score"], r["decision"], _clean_json(r["reasons"]),
                   _clean_json(r["features"]), r["is_fraud"]) for r in results if r["decision"] != "APPROVE"]
    with conn.cursor() as cur:
        cur.executemany(TXN_SQL, txn_rows)
        if alert_rows:
            cur.executemany(ALERT_SQL, alert_rows)
    conn.commit()


def write_dead_letter(conn: psycopg.Connection, payload: str, error: str) -> None:
    payload = redact_payload(payload)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO dead_letters (payload, error) VALUES (%s, %s)", (payload[:10000], error[:1000]))
    conn.commit()


def log_model_switch(conn: psycopg.Connection, from_model: str | None, to_model: str,
                     switched_by: str, note: str = "") -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO model_switches (from_model, to_model, switched_by, note) VALUES (%s, %s, %s, %s)",
                    (from_model, to_model, switched_by, note))
    conn.commit()
