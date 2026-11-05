"""REST API for on-demand scoring, alerts and model management.

    uvicorn services.api:app --port 8000      (docs at http://localhost:8000/docs)

POST /score is read-only: it scores a transaction against the card's live
history in Redis without adding it to that history.
PUT /models/active switches the live model (needs the X-Admin-Token header).
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import redis  # noqa: E402
from fastapi import FastAPI, Header, HTTPException  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from securelytics import config, db  # noqa: E402
from securelytics.registry import (MODEL_CATALOG, get_active, load_models, read_registry,  # noqa: E402
                                   registry_path, set_active)
from securelytics.scoring import Scorer, ValidationError  # noqa: E402
from securelytics.store import RedisStore  # noqa: E402

ADMIN_TOKEN = os.getenv("ADMIN_PASSWORD", "")

app = FastAPI(title="Securelytics fraud API", version="2.0.0")
r = redis.Redis.from_url(config.REDIS_URL)
_state = {"mtime": None, "scorer": None}


def scorer() -> Scorer:
    """Scorer using the admin's active model; reloads models when they are retrained."""
    mtime = registry_path().stat().st_mtime
    if _state["mtime"] != mtime:
        _state["scorer"] = Scorer(RedisStore(r), load_models(), shadow=True)
        _state["mtime"] = mtime
    s = _state["scorer"]
    s.set_active(get_active(r, s.models, read_registry().get("default")))
    return s


class Transaction(BaseModel):
    trans_num: str
    trans_date_trans_time: str           # "2020-12-31 23:59:00"
    cc_num: str
    merchant: str
    category: str
    amt: float
    gender: str
    lat: float
    long: float
    city_pop: int
    dob: str                             # "1985-04-12"
    merch_lat: float
    merch_long: float

    model_config = {"json_schema_extra": {"example": {
        "trans_num": "demo-001", "trans_date_trans_time": "2020-12-31 23:10:00",
        "cc_num": "2291163933867244", "merchant": "fraud_Kirlin and Sons", "category": "shopping_net",
        "amt": 1049.99, "gender": "M", "lat": 33.9659, "long": -80.9355, "city_pop": 333497,
        "dob": "1968-03-19", "merch_lat": 33.986391, "merch_long": -81.200714}}}


class ActiveModel(BaseModel):
    name: str
    switched_by: str = "api"


def _finite(d: dict) -> dict:
    return {k: (None if isinstance(v, float) and not math.isfinite(v) else v) for k, v in d.items()}


@app.get("/health")
def health():
    s = scorer()
    return {"status": "ok", "active_model": s.active, "loaded_models": list(s.models)}


@app.post("/score")
def score(txn: Transaction):
    try:
        res = scorer().process(txn.model_dump(), commit=False)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    res["features"] = _finite(res["features"])
    return res


@app.get("/models")
def models():
    reg = read_registry()
    s = scorer()
    return {"active": s.active, "default": reg.get("default"),
            "models": [{"name": n, "label": label, "trained": n in reg.get("models", {}),
                        "loaded": n in s.models, **reg.get("models", {}).get(n, {})}
                       for n, label in MODEL_CATALOG.items()]}


@app.put("/models/active")
def switch_model(body: ActiveModel, x_admin_token: str = Header(default="")):
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="invalid admin token")
    s = scorer()
    if body.name not in s.models:
        raise HTTPException(status_code=400, detail=f"model {body.name!r} is not trained/loaded")
    previous = s.active
    set_active(r, body.name)
    with db.connect(retries=1) as conn:
        db.log_model_switch(conn, previous, body.name, body.switched_by, "via API")
    return {"active": body.name, "previous": previous}


@app.get("/alerts")
def alerts(limit: int = 50, decision: str | None = None):
    sql = "SELECT trans_id, event_ts, card_last4, merchant, category, amt, model_name, score, decision, " \
          "reasons, is_fraud FROM alerts " + ("WHERE decision = %s " if decision else "") + \
          "ORDER BY created_at DESC LIMIT %s"
    params = (decision.upper(), limit) if decision else (limit,)
    with db.connect(retries=1) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchall()
