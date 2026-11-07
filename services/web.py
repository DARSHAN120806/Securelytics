"""Securelytics web dashboard: JSON API + single-page frontend (services/static).

    uvicorn services.web:app --port 8501      ->  http://localhost:8501

Built on Starlette (already installed as part of FastAPI). Every endpoint
returns a clear JSON error instead of crashing when Postgres or Redis is down,
so the UI can show what is wrong.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import decimal
import hmac
import json
import logging
import math
import os
import secrets
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import psycopg  # noqa: E402
import redis  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import FileResponse, Response  # noqa: E402
from starlette.routing import Mount, Route  # noqa: E402
from starlette.staticfiles import StaticFiles  # noqa: E402

from securelytics import config  # noqa: E402
from securelytics import dashboard_data as dd  # noqa: E402
from securelytics import db as dbmod  # noqa: E402
from securelytics import payments  # noqa: E402
from securelytics.registry import (ACTIVE_KEY, MODEL_CATALOG, get_active, load_models,  # noqa: E402
                                   read_registry, registry_path)
from securelytics.scoring import Scorer, ValidationError  # noqa: E402
from securelytics.store import RedisStore  # noqa: E402

log = logging.getLogger("web")
STATIC = Path(__file__).resolve().parent / "static"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SESSION_TTL = 12 * 3600
HEARTBEAT_KEY = "securelytics:processor:heartbeat"
_sessions: dict[str, tuple[str, float]] = {}
_state: dict = {"mtime": None, "models": {}}


# ------------------------------------------------------------------ helpers --
def _clean(o):
    if isinstance(o, float):
        return None if not math.isfinite(o) else o
    if isinstance(o, decimal.Decimal):
        return float(o)
    if isinstance(o, (dt.datetime, dt.date)):
        return o.isoformat()
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if hasattr(o, "item"):  # numpy scalars
        return _clean(o.item())
    return o


def J(data, status: int = 200) -> Response:
    return Response(json.dumps(_clean(data)), status_code=status, media_type="application/json")


def err(code: str, message: str, status: int) -> Response:
    return J({"error": code, "message": message}, status)


def db_conn():
    return psycopg.connect(config.POSTGRES_DSN, autocommit=False, connect_timeout=3)


def rds():
    return redis.Redis.from_url(config.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)


def with_db(fn):
    """Run fn(conn, request); turn infrastructure failures into friendly JSON errors."""
    async def endpoint(request: Request):
        try:
            try:
                with db_conn() as conn:
                    return await fn(conn, request)
            except psycopg.errors.UndefinedTable:
                # database exists but its tables were never created: create them and retry once
                log.warning("tables missing; creating schema")
                with db_conn() as conn:
                    dbmod.ensure_schema(conn)
                with db_conn() as conn:
                    return await fn(conn, request)
        except psycopg.OperationalError as exc:
            log.warning("database unavailable: %s", exc)
            return err("database_unavailable",
                       "Cannot reach the Postgres database. Check that the 'postgres' container is running "
                       "(docker compose ps) and see its logs (docker compose logs postgres).", 503)
        except redis.ConnectionError:
            return err("redis_unavailable", "Cannot reach Redis. Check the 'redis' container.", 503)
    return endpoint


def models():
    """Models from the registry, reloaded automatically after retraining."""
    path = registry_path()
    mtime = path.stat().st_mtime if path.is_file() else None
    if mtime != _state["mtime"]:
        try:
            _state["models"] = load_models() if mtime else {}
        except RuntimeError:
            _state["models"] = {}
        _state["mtime"] = mtime
    return _state["models"]


def active_model(r=None) -> str | None:
    reg = read_registry()
    loaded = models() or {n: None for n in reg.get("models", {})}
    if not loaded:
        return None
    try:
        return get_active(r or rds(), loaded, reg.get("default"))
    except Exception:  # noqa: BLE001 - redis down: fall back to the registry default
        return reg.get("default")


def admin_user(request: Request) -> str | None:
    token = request.headers.get("x-admin-token", "")
    entry = _sessions.get(token)
    if not entry or entry[1] < time.time():
        _sessions.pop(token, None)
        return None
    return entry[0]


def _int(v, default, lo=0, hi=10_000):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------- endpoints --
async def status(request: Request):
    out = {"time": dt.datetime.now(dt.timezone.utc), "db": {"ok": False}, "redis": {"ok": False},
           "processor": {"ok": False}, "models": {}}
    try:
        with db_conn() as conn:
            try:
                stats = dd.db_stats(conn)
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                dbmod.ensure_schema(conn)
                stats = dd.db_stats(conn)
            out["db"] = {"ok": True, **stats}
    except Exception as exc:  # noqa: BLE001
        out["db"]["error"] = str(exc).splitlines()[0][:200]
    try:
        r = rds()
        r.ping()
        out["redis"] = {"ok": True}
        hb = r.get(HEARTBEAT_KEY)
        if hb:
            hb = json.loads(hb)
            age = time.time() - hb.get("ts", 0)
            out["processor"] = {"ok": age < 30, "age_s": round(age, 1), **hb}
        else:
            out["processor"]["error"] = "no heartbeat yet (processor not started, or no messages)"
    except Exception as exc:  # noqa: BLE001
        out["redis"]["error"] = str(exc).splitlines()[0][:200]
    reg = read_registry()
    out["models"] = {"active": active_model(), "default": reg.get("default"),
                     "trained": list(reg.get("models", {})), "loaded": list(models())}
    out["admin_enabled"] = bool(ADMIN_PASSWORD)
    return J(out)


@with_db
async def overview(conn, request: Request):
    scope = request.query_params.get("scope", "live")
    model = active_model() if scope == "live" else None
    minutes = _int(request.query_params.get("minutes"), 60, 5, 1440)
    data = dd.overview(conn, model, minutes)
    data["scope_model"] = model
    data["model_labels"] = MODEL_CATALOG
    return J(data)


@with_db
async def alerts(conn, request: Request):
    q = dict(request.query_params)
    return J(dd.list_alerts(conn, q, _int(q.get("limit"), 25, 1, 200), _int(q.get("offset"), 0, 0, 10**7)))


@with_db
async def alert(conn, request: Request):
    item = dd.alert_detail(conn, request.path_params["trans_id"])
    return J(item) if item else err("not_found", "Alert not found", 404)


@with_db
async def label(conn, request: Request):
    body = await request.json()
    lab = body.get("label")
    if lab not in (0, 1, None):
        return err("bad_request", "label must be 1 (fraud), 0 (legitimate) or null", 400)
    dd.label_alert(conn, request.path_params["trans_id"], lab)
    return J({"ok": True})


@with_db
async def filters(conn, request: Request):
    return J(dd.alert_filters(conn))


@with_db
async def transactions(conn, request: Request):
    q = dict(request.query_params)
    return J(dd.list_transactions(conn, q, _int(q.get("limit"), 25, 1, 200), _int(q.get("offset"), 0, 0, 10**7)))


@with_db
async def model_info(conn, request: Request):
    reg = read_registry()
    window = _int(request.query_params.get("window"), 20000, 100, 500_000)
    catalog = []
    for name, lab in MODEL_CATALOG.items():
        entry = reg.get("models", {}).get(name)
        catalog.append({"name": name, "label": lab, "trained": bool(entry), "loaded": name in models(),
                        **({"thresholds": entry["thresholds"], "n_trees": entry.get("n_trees"),
                            "trained_at": entry.get("trained_at"), "test": entry.get("test"),
                            "validation_pr_auc": entry.get("validation_pr_auc")} if entry else {})})
    return J({"active": active_model(), "default": reg.get("default"), "catalog": catalog,
              "live": dd.live_model_metrics(conn, reg, window), "by_model": dd.decisions_by_model(conn),
              "switches": dd.switches(conn), "window": window})


async def login(request: Request):
    if not ADMIN_PASSWORD:
        return err("admin_disabled", "Set ADMIN_PASSWORD in .env and restart to enable admin features.", 403)
    body = await request.json()
    name = (body.get("name") or "").strip()[:40]
    if not name or not hmac.compare_digest(str(body.get("password", "")), ADMIN_PASSWORD):
        time.sleep(0.5)
        return err("bad_credentials", "Wrong password (or missing name).", 401)
    token = secrets.token_urlsafe(32)
    _sessions[token] = (name, time.time() + SESSION_TTL)
    return J({"token": token, "name": name, "expires_in": SESSION_TTL})


async def logout(request: Request):
    _sessions.pop(request.headers.get("x-admin-token", ""), None)
    return J({"ok": True})


async def whoami(request: Request):
    user = admin_user(request)
    return J({"admin": bool(user), "name": user, "admin_enabled": bool(ADMIN_PASSWORD)})


@with_db
async def switch_model(conn, request: Request):
    user = admin_user(request)
    if not user:
        return err("unauthorized", "Admin login required.", 401)
    body = await request.json()
    name = body.get("name")
    if name not in models():
        return err("bad_request", f"Model {name!r} is not trained/loaded.", 400)
    r = rds()
    previous = active_model(r)
    r.set(ACTIVE_KEY, name)
    dd.log_switch(conn, previous, name, user, (body.get("note") or "")[:200])
    return J({"active": name, "previous": previous})


async def score(request: Request):
    body = await request.json()
    loaded = models()
    if not loaded:
        return err("no_models", "No trained models found in models/.", 503)
    try:
        r = rds()
        scorer = Scorer(RedisStore(r), loaded, active=active_model(r), shadow=True)
        res = scorer.process(body, commit=False)
    except ValidationError as exc:
        return err("invalid_transaction", str(exc), 422)
    except redis.ConnectionError:
        return err("redis_unavailable", "Cannot reach Redis (feature store).", 503)
    return J(res)


@with_db
async def dead_letters(conn, request: Request):
    return J(dd.dead_letters(conn, _int(request.query_params.get("limit"), 50, 1, 500)))


# ------------------------------------------------------------ payment app --
_kafka: dict = {}


def kafka_producer():
    if "p" not in _kafka:
        from confluent_kafka import Producer
        _kafka["p"] = Producer({"bootstrap.servers": config.KAFKA_BOOTSTRAP, "linger.ms": 0,
                                "message.timeout.ms": 8000, "enable.idempotence": True})
    return _kafka["p"]


def card_last_ts(r, cc_num: str) -> int | None:
    raw = r.hget(f"card:{cc_num}:stats", "last_ts")
    if raw is None:
        return None
    return int(float(raw.decode() if isinstance(raw, bytes) else raw))


async def pay_cards(request: Request):
    try:
        cards = payments.load_cards()
    except FileNotFoundError:
        return err("dataset_missing", "fraudTest.csv was not found in data/raw, so there are no cardholders to load.", 503)
    try:
        r = rds()
        out = [payments.public_card(c, card_last_ts(r, c["cc_num"])) for c in cards.values()]
    except redis.ConnectionError:
        return err("redis_unavailable", "The bank's systems are offline (Redis). Try again shortly.", 503)
    return J({"cards": out, "categories": payments.CATEGORY_LABELS, "cities": list(payments.CITIES)})


async def pay(request: Request):
    body = await request.json()
    try:
        cards = payments.load_cards()
    except FileNotFoundError:
        return err("dataset_missing", "fraudTest.csv was not found in data/raw.", 503)
    card = cards.get(body.get("card_id"))
    if not card:
        return err("bad_request", "Unknown card.", 400)
    try:
        r = rds()
        event, receipt = payments.build_event(card, body, card_last_ts(r, card["cc_num"]))
    except payments.PaymentError as exc:
        return err("invalid_payment", str(exc), 422)
    except redis.ConnectionError:
        return err("redis_unavailable", "The bank's systems are offline (Redis). Try again shortly.", 503)
    event["sent_at_ms"] = int(time.time() * 1000)
    delivered: dict = {}
    try:
        p = kafka_producer()
        p.produce(config.TOPIC_TRANSACTIONS, key=card["cc_num"], value=json.dumps(event),
                  on_delivery=lambda e, m: delivered.update(error=e))
        p.flush(8)
    except Exception as exc:  # noqa: BLE001
        log.warning("kafka publish failed: %s", exc)
        delivered["error"] = exc
    if "error" not in delivered or delivered["error"] is not None:
        return err("network_unavailable", "The payment network is unavailable (Kafka). Please try again.", 503)
    return J(receipt)


async def pay_page(request: Request):
    return FileResponse(STATIC / "pay.html", headers={"Cache-Control": "no-cache"})


async def index(request: Request):
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


routes = [
    Route("/", index),
    Route("/pay", pay_page),
    Route("/api/pay/cards", pay_cards),
    Route("/api/pay", pay, methods=["POST"]),
    Route("/api/status", status),
    Route("/api/overview", overview),
    Route("/api/alerts", alerts),
    Route("/api/alerts/{trans_id}", alert),
    Route("/api/alerts/{trans_id}/label", label, methods=["POST"]),
    Route("/api/filters", filters),
    Route("/api/transactions", transactions),
    Route("/api/models", model_info),
    Route("/api/models/active", switch_model, methods=["POST"]),
    Route("/api/admin/login", login, methods=["POST"]),
    Route("/api/admin/logout", logout, methods=["POST"]),
    Route("/api/admin/me", whoami),
    Route("/api/score", score, methods=["POST"]),
    Route("/api/dead-letters", dead_letters),
    Mount("/static", StaticFiles(directory=STATIC), name="static"),
]
def _startup() -> None:
    import threading
    threading.Thread(target=_warm_cards, daemon=True).start()  # payment app: load cardholders in the background
    try:
        with db_conn() as conn:
            dbmod.ensure_schema(conn)
    except Exception as exc:  # noqa: BLE001 - the UI shows a clear message if the DB is down
        log.warning("could not check database schema at startup: %s", exc)


def _warm_cards() -> None:
    try:
        payments.load_cards()
    except Exception as exc:  # noqa: BLE001
        log.warning("payment app: could not load cardholders: %s", exc)


@contextlib.asynccontextmanager
async def lifespan(app):
    _startup()
    yield


app = Starlette(routes=routes, lifespan=lifespan)
