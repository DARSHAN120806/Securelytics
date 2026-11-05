"""Central configuration. Every value can be overridden with an environment variable."""
import os
from pathlib import Path

ROOT = Path(os.getenv("SECURELYTICS_ROOT", Path(__file__).resolve().parents[2]))
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
MODELS_DIR = ROOT / "models"
REPORTS_DIR = ROOT / "reports"

def _find_csv(name: str) -> Path:
    """data/raw/<name> is the standard place; also accept Kaggle's unzip layout <root>/<name>/<name>."""
    if os.getenv(name.split(".")[0].upper() + "_CSV"):
        return Path(os.environ[name.split(".")[0].upper() + "_CSV"])
    # Kaggle zips unpack as a *folder* named fraudTrain.csv containing fraudTrain.csv, so check inside those too
    for candidate in (DATA_RAW / name, DATA_RAW / name / name, ROOT / name / name, ROOT / name):
        if candidate.is_file():
            return candidate
    return DATA_RAW / name


TRAIN_CSV = _find_csv("fraudTrain.csv")   # override with FRAUDTRAIN_CSV
TEST_CSV = _find_csv("fraudTest.csv")     # override with FRAUDTEST_CSV

# Infrastructure
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC_TRANSACTIONS = os.getenv("TOPIC_TRANSACTIONS", "transactions")
TOPIC_ALERTS = os.getenv("TOPIC_ALERTS", "fraud-alerts")
TOPIC_DLQ = os.getenv("TOPIC_DLQ", "transactions-dlq")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
POSTGRES_DSN = os.getenv(
    "POSTGRES_DSN", "postgresql://fraud:fraud@localhost:5432/securelytics"
)

# Producer
EVENTS_PER_SEC = float(os.getenv("EVENTS_PER_SEC", "50"))

# Feature windows (seconds)
WINDOW_1H = 3600
WINDOW_24H = 86400
WINDOW_7D = 7 * 86400
