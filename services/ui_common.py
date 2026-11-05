"""Helpers shared by the dashboard and the admin panel."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pandas as pd  # noqa: E402
import psycopg  # noqa: E402
import redis  # noqa: E402
import streamlit as st  # noqa: E402

from securelytics import config  # noqa: E402
from securelytics.registry import ACTIVE_KEY, MODEL_CATALOG, read_registry  # noqa: E402


@st.cache_resource
def pg():
    return psycopg.connect(config.POSTGRES_DSN, autocommit=True)


@st.cache_resource
def rds():
    return redis.Redis.from_url(config.REDIS_URL, decode_responses=True)


def q(sql: str, params=None) -> pd.DataFrame:
    with pg().cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def execute(sql: str, params=None) -> None:
    with pg().cursor() as cur:
        cur.execute(sql, params)


def active_model() -> str | None:
    reg = read_registry()
    name = rds().get(ACTIVE_KEY)
    if name in reg.get("models", {}):
        return name
    return reg.get("default")


def label(name: str | None) -> str:
    return MODEL_CATALOG.get(name, name or "-")
