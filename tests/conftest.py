import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from securelytics import config  # noqa: E402


@pytest.fixture(scope="session")
def raw_test_sample() -> pd.DataFrame:
    """First 20k rows of fraudTest.csv, read as strings like the producer sends them."""
    if not config.TEST_CSV.is_file():
        pytest.skip("fraudTest.csv not found")
    return pd.read_csv(config.TEST_CSV, nrows=20000, dtype=str, keep_default_na=False)


@pytest.fixture(scope="session")
def models():
    from securelytics.registry import load_models
    try:
        return load_models()
    except RuntimeError:
        pytest.skip("no trained models yet")


@pytest.fixture(scope="session")
def model(models):
    from securelytics.registry import read_registry
    default = read_registry()["default"]
    return models[default] if default in models else next(iter(models.values()))
