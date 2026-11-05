"""Transaction producer: replays fraudTest.csv into Kafka as a live stream.

    python services/producer.py --rate 50 --inject-attacks 30

Each CSV row becomes one JSON event on the ``transactions`` topic, keyed by
card number so every card's events land on the same partition (in order).
``--inject-attacks N`` adds a synthetic "card-testing" attack every N seconds:
a burst of tiny charges followed by large online purchases on one card.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import signal
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from confluent_kafka import Producer  # noqa: E402

from securelytics import config  # noqa: E402
from securelytics.cleaning import TS_FORMAT  # noqa: E402

log = logging.getLogger("producer")
running = True


def stop(*_):
    global running
    running = False


def attack_burst(row: dict) -> list[dict]:
    """Card-testing then cash-out, on the card from ``row`` at its event time."""
    base = datetime.strptime(row["trans_date_trans_time"], TS_FORMAT)
    events = []
    plan = [(random.uniform(1, 3), "misc_net", 20) for _ in range(4)] + \
           [(random.uniform(700, 1300), "shopping_net", 90) for _ in range(3)]
    for i, (amt, cat, gap) in enumerate(plan):
        base += timedelta(seconds=gap + random.randint(0, 30))
        e = dict(row)
        e.update({
            "trans_num": f"atk-{uuid.uuid4().hex[:24]}",
            "trans_date_trans_time": base.strftime(TS_FORMAT),
            "amt": f"{amt:.2f}",
            "category": cat,
            "merchant": f"fraud_Injected Store {random.randint(1, 5)}",
            "is_fraud": "1",
            "injected": True,
        })
        events.append(e)
    return events


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(config.TEST_CSV))
    ap.add_argument("--rate", type=float, default=config.EVENTS_PER_SEC, help="events per second (0 = max)")
    ap.add_argument("--limit", type=int, default=0, help="stop after N rows (0 = all)")
    ap.add_argument("--inject-attacks", type=float, default=0, help="inject an attack every N seconds")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    signal.signal(signal.SIGINT, stop); signal.signal(signal.SIGTERM, stop)

    producer = Producer({"bootstrap.servers": config.KAFKA_BOOTSTRAP, "linger.ms": 5,
                         "enable.idempotence": True, "compression.type": "lz4"})
    delivered = {"ok": 0, "err": 0}

    def on_delivery(err, _msg):
        delivered["err" if err else "ok"] += 1
        if err:
            log.error("delivery failed: %s", err)

    def send(event: dict) -> None:
        event["sent_at_ms"] = int(time.time() * 1000)
        producer.produce(config.TOPIC_TRANSACTIONS, key=str(event["cc_num"]),
                         value=json.dumps(event), on_delivery=on_delivery)
        producer.poll(0)

    interval = 1.0 / args.rate if args.rate > 0 else 0
    next_attack = time.time() + args.inject_attacks if args.inject_attacks else float("inf")
    sent, t_start = 0, time.time()
    with open(args.csv, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if not running or (args.limit and sent >= args.limit):
                break
            row.pop("", None)  # pandas index column
            send(row)
            sent += 1
            if time.time() >= next_attack:
                burst = attack_burst(row)
                for e in burst:
                    send(e)
                log.info("injected attack on card ****%s (%d events)", row["cc_num"][-4:], len(burst))
                next_attack = time.time() + args.inject_attacks
            if sent % 1000 == 0:
                log.info("sent %d events (%.0f/s)", sent, sent / (time.time() - t_start))
            if interval:
                time.sleep(max(0.0, t_start + sent * interval - time.time()))
    producer.flush(10)
    log.info("done: sent %d, delivered %s", sent, delivered)


if __name__ == "__main__":
    main()
