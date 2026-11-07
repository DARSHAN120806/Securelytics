"""Stream processor: consume transactions, score them, store and publish alerts.

    python services/processor.py

Flow per batch of Kafka messages:
    check which model the admin selected (Redis) -> reload models if retrained
    validate/clean -> dedupe -> Redis features -> active model score + rules -> decision
    -> shadow scores from every other model (for live comparison in the admin panel)
    -> explanations (alerts only) -> Postgres + `fraud-alerts` topic
    -> commit Kafka offsets (at-least-once; Redis dedupe makes replays harmless)
Invalid events go to the `transactions-dlq` topic and the dead_letters table.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import psycopg  # noqa: E402
import redis  # noqa: E402
from confluent_kafka import Consumer, KafkaError, Producer  # noqa: E402

from securelytics import config, db  # noqa: E402
from securelytics.registry import get_active, load_models, read_registry, registry_path  # noqa: E402
from securelytics.scoring import DuplicateEvent, Scorer, ValidationError  # noqa: E402
from securelytics.store import RedisStore  # noqa: E402

log = logging.getLogger("processor")
running = True
BATCH_SIZE = 500
DEDUPE_TTL = 3 * 86400
SHADOW = os.getenv("SHADOW_SCORING", "true").lower() == "true"
HEARTBEAT_KEY = "securelytics:processor:heartbeat"


def stop(*_):
    global running
    running = False


def make_dedupe(r: redis.Redis):
    def first_time(trans_id: str) -> bool:
        return bool(r.set(f"seen:{trans_id}", 1, nx=True, ex=DEDUPE_TTL))
    return first_time


def wait_for_redis(r: redis.Redis) -> None:
    for _ in range(30):
        try:
            r.ping(); return
        except redis.ConnectionError:
            log.warning("waiting for redis..."); time.sleep(2)
    raise RuntimeError("redis not reachable")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    signal.signal(signal.SIGINT, stop); signal.signal(signal.SIGTERM, stop)

    r = redis.Redis.from_url(config.REDIS_URL)
    wait_for_redis(r)
    models = load_models()
    reg_mtime = registry_path().stat().st_mtime
    default = read_registry().get("default")
    active = get_active(r, models, default)
    for name, m in models.items():
        log.info("model %-9s loaded | review>=%.4f block>=%.4f%s", name, m.review_threshold,
                 m.block_threshold, "  <- ACTIVE" if name == active else "")
    store = RedisStore(r)
    snap = config.MODELS_DIR / "card_state_snapshot.json"
    if store.is_empty() and snap.is_file():
        t0 = time.time()
        n = store.import_snapshot(snap)
        log.info("bootstrapped Redis feature store with %d cards from %s (%.1fs)", n, snap.name, time.time() - t0)
    elif store.is_empty():
        log.warning("no %s found: starting with empty card history (run the trainer to create it; "
                    "live scores will be less accurate until cards build up history)", snap.name)

    scorer = Scorer(store, models, active=active, dedupe=make_dedupe(r), shadow=SHADOW)
    conn = db.connect()
    db.ensure_schema(conn)
    consumer = Consumer({
        "bootstrap.servers": config.KAFKA_BOOTSTRAP,
        "group.id": "fraud-scorer",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })
    consumer.subscribe([config.TOPIC_TRANSACTIONS])
    producer = Producer({"bootstrap.servers": config.KAFKA_BOOTSTRAP, "linger.ms": 5})

    stats = {"processed": 0, "alerts": 0, "invalid": 0, "duplicates": 0}
    latencies: list[float] = []
    last_log = last_beat = time.time()
    started = time.time()
    log.info("consuming from %s", config.TOPIC_TRANSACTIONS)

    while running:
        # 1. pick up retrained models (registry.json changed on disk)
        mtime = registry_path().stat().st_mtime
        if mtime != reg_mtime:
            try:
                scorer.models = load_models(); default = read_registry().get("default")
                reg_mtime = mtime
                log.info("models reloaded: %s", list(scorer.models))
            except Exception as exc:  # noqa: BLE001 - keep serving with the old models
                log.error("model reload failed, keeping current models: %s", exc)
        # 2. follow the admin's model choice
        wanted = get_active(r, scorer.models, default)
        if wanted != scorer.active:
            log.info("switching active model %s -> %s", scorer.active, wanted)
            scorer.set_active(wanted)

        msgs = consumer.consume(num_messages=BATCH_SIZE, timeout=1.0)
        results = []
        for msg in msgs:
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    log.error("kafka error: %s", msg.error())
                continue
            payload = msg.value().decode("utf-8", errors="replace")
            try:
                raw = json.loads(payload)
                res = scorer.process(raw)
            except (ValidationError, json.JSONDecodeError) as exc:
                stats["invalid"] += 1
                producer.produce(config.TOPIC_DLQ, value=json.dumps({"error": str(exc), "payload": payload}))
                db.write_dead_letter(conn, payload, str(exc))
                continue
            except DuplicateEvent:
                stats["duplicates"] += 1
                continue
            if "sent_at_ms" in raw:
                res["e2e_ms"] = time.time() * 1000 - float(raw["sent_at_ms"])
            results.append(res)
            latencies.append(res["scoring_ms"])

        if results:
            # Card history and dedupe markers are already saved, so the write must not be lost:
            # keep retrying (offsets are not committed until it succeeds).
            while True:
                try:
                    db.write_results(conn, results)
                    break
                except psycopg.Error as exc:
                    log.error("database write failed (%s); retrying in 3s", str(exc).splitlines()[0])
                    time.sleep(3)
                    try:
                        conn.close()
                    except Exception:  # noqa: BLE001
                        pass
                    conn = db.connect()
            for res in results:
                if res["decision"] != "APPROVE":
                    stats["alerts"] += 1
                    alert = {k: v for k, v in res.items() if k != "features"}
                    producer.produce(config.TOPIC_ALERTS, key=res["card_ref"], value=json.dumps(alert))
            producer.poll(0)
            stats["processed"] += len(results)
        if msgs:
            consumer.commit(asynchronous=False)  # only after results are safely stored

        if time.time() - last_beat >= 2:  # heartbeat for the dashboard's System page
            try:
                r.set(HEARTBEAT_KEY, json.dumps({"ts": time.time(), "started": started, "active_model": scorer.active,
                                                 "models": list(scorer.models), "shadow": SHADOW, **stats}), ex=60)
            except redis.RedisError as exc:
                log.warning("heartbeat failed: %s", exc)
            last_beat = time.time()

        if time.time() - last_log >= 10 and latencies:
            q = statistics.quantiles(latencies, n=100)
            log.info("%s | active=%s | scoring latency p50=%.2fms p95=%.2fms p99=%.2fms",
                     stats, scorer.active, q[49], q[94], q[98])
            latencies.clear(); last_log = time.time()

    log.info("shutting down: %s", stats)
    producer.flush(5)
    consumer.close()
    conn.close()


if __name__ == "__main__":
    main()
