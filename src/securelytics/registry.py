"""Model registry: which models exist, how good they are, and which one is live.

    models/registry.json        written by train.py (metrics, thresholds, files)
    models/<name>.joblib        one FraudModel per algorithm
    Redis securelytics:active_model   the model the admin switched to (shared by all services)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from . import config
from .model import FraudModel

log = logging.getLogger(__name__)

# The four algorithms the admin can choose from, in display order.
MODEL_CATALOG = {
    "hist_gb": "HistGradientBoosting (scikit-learn)",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "catboost": "CatBoost",
}
ACTIVE_KEY = "securelytics:active_model"
REGISTRY_FILE = "registry.json"


def registry_path(models_dir: Path = config.MODELS_DIR) -> Path:
    return Path(models_dir) / REGISTRY_FILE


def read_registry(models_dir: Path = config.MODELS_DIR) -> dict:
    path = registry_path(models_dir)
    if not path.is_file():
        return {"default": None, "models": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def write_registry(reg: dict, models_dir: Path = config.MODELS_DIR) -> None:
    registry_path(models_dir).write_text(json.dumps(reg, indent=2), encoding="utf-8")


def load_models(models_dir: Path = config.MODELS_DIR) -> dict[str, FraudModel]:
    """Load every registered model. A model whose library is missing is skipped, not fatal."""
    reg = read_registry(models_dir)
    loaded = {}
    for name, entry in reg.get("models", {}).items():
        try:
            loaded[name] = FraudModel.load(Path(models_dir) / entry["file"])
        except Exception as exc:  # noqa: BLE001 - e.g. ImportError for a missing library
            log.warning("could not load model %s: %s", name, exc)
    if not loaded:
        raise RuntimeError(f"no models could be loaded from {models_dir}; run the trainer first")
    return loaded


def get_active(redis_client, models: dict[str, FraudModel], default: str | None) -> str:
    """Active model chosen by the admin, falling back to the registry default."""
    name = None
    if redis_client is not None:
        raw = redis_client.get(ACTIVE_KEY)
        name = raw.decode() if isinstance(raw, bytes) else raw
    if name in models:
        return name
    if default in models:
        return default
    return next(iter(models))


def set_active(redis_client, name: str, models_dir: Path = config.MODELS_DIR) -> None:
    reg = read_registry(models_dir)
    if name not in reg.get("models", {}):
        raise ValueError(f"model {name!r} is not trained/registered")
    redis_client.set(ACTIVE_KEY, name)
