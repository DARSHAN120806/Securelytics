"""Payment simulator: turns a payment made in the /pay app into a raw card event, exactly
like the ones the producer replays from fraudTest.csv, so it flows through Kafka and the
normal pipeline. Nothing here decides fraud: the trained model in the processor does.

Cardholders come from the dataset itself (loaded at runtime from fraudTest.csv, never
committed). The payment clock follows the replayed 2020 timeline, because each card's
history in the feature store is from that period.
"""
from __future__ import annotations

import datetime as dt
import random
import secrets
from functools import lru_cache

import pandas as pd

from . import config
from .cleaning import CATEGORIES, TS_FORMAT
from .scoring import card_ref

N_CARDS = 8
MAX_AMOUNT = 25_000.0
MAX_DAYS_AHEAD = 7  # payments far past the card's last activity would look unlike any training data

CATEGORY_LABELS = {
    "grocery_pos": "Groceries (in store)", "grocery_net": "Groceries (online)",
    "shopping_pos": "Shopping (in store)", "shopping_net": "Shopping (online)",
    "gas_transport": "Fuel & transport", "food_dining": "Food & dining", "entertainment": "Entertainment",
    "health_fitness": "Health & fitness", "home": "Home", "kids_pets": "Kids & pets",
    "personal_care": "Personal care", "travel": "Travel", "misc_pos": "Other (in store)", "misc_net": "Other (online)",
}

CITIES = {
    "New York, NY": (40.7128, -74.0060), "Los Angeles, CA": (34.0522, -118.2437),
    "Chicago, IL": (41.8781, -87.6298), "Houston, TX": (29.7604, -95.3698),
    "Miami, FL": (25.7617, -80.1918), "Seattle, WA": (47.6062, -122.3321),
    "Las Vegas, NV": (36.1699, -115.1398), "Denver, CO": (39.7392, -104.9903),
    "Boston, MA": (42.3601, -71.0589), "Atlanta, GA": (33.7490, -84.3880),
    "San Francisco, CA": (37.7749, -122.4194), "Dallas, TX": (32.7767, -96.7970),
    "Phoenix, AZ": (33.4484, -112.0740), "New Orleans, LA": (29.9511, -90.0715),
    "Anchorage, AK": (61.2181, -149.9003), "Honolulu, HI": (21.3069, -157.8583),
}

PROFILE_COLS = ["cc_num", "first", "last", "gender", "street", "city", "state", "zip", "lat", "long",
                "city_pop", "job", "dob", "is_fraud"]


class PaymentError(ValueError):
    """Invalid payment request (shown to the user)."""


@lru_cache(maxsize=1)
def load_cards() -> dict[str, dict]:
    """Pick N_CARDS everyday cardholders from the replayed test data (busy cards, no fraud, different states)."""
    df = pd.read_csv(config.TEST_CSV, usecols=PROFILE_COLS, dtype={"cc_num": str, "zip": str})
    fraud_cards = set(df.loc[df["is_fraud"] == 1, "cc_num"])
    counts = df["cc_num"].value_counts()
    profiles = df.drop_duplicates("cc_num").set_index("cc_num")
    cards, states = {}, set()
    for cc in counts.index:
        if cc in fraud_cards:
            continue
        p = profiles.loc[cc]
        if p["state"] in states:
            continue
        states.add(p["state"])
        ref = card_ref(cc)
        cards[ref] = {
            "id": ref, "cc_num": cc, "last4": cc[-4:], "holder": f"{p['first']} {p['last']}",
            "gender": p["gender"], "street": p["street"], "city": p["city"], "state": p["state"], "zip": p["zip"],
            "lat": float(p["lat"]), "long": float(p["long"]), "city_pop": int(p["city_pop"]),
            "job": p["job"], "dob": str(p["dob"])[:10], "color": len(cards) % 5,
        }
        if len(cards) >= N_CARDS:
            break
    return cards


def public_card(c: dict, last_ts: int | None) -> dict:
    """What the browser may see: no full card number."""
    return {"id": c["id"], "last4": c["last4"], "holder": c["holder"], "home": f"{c['city']}, {c['state']}",
            "lat": c["lat"], "long": c["long"], "color": c["color"],
            "last_activity": dt.datetime.fromtimestamp(last_ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M") if last_ts else None}


def new_txn_id(when: dt.datetime) -> str:
    return f"TXN-{when:%Y%m%d}-{secrets.token_hex(4).upper()}"


def build_event(card: dict, req: dict, last_ts: int | None, rng: random.Random | None = None) -> tuple[dict, dict]:
    """Validate a payment request and build (raw_event, receipt)."""
    rng = rng or random.Random()
    try:
        amount = round(float(req.get("amount")), 2)
    except (TypeError, ValueError):
        raise PaymentError("Enter a valid amount.")
    if not 0.01 <= amount <= MAX_AMOUNT:
        raise PaymentError(f"Amount must be between $0.01 and ${MAX_AMOUNT:,.0f}.")
    category = req.get("category")
    if category not in CATEGORIES:
        raise PaymentError("Choose a category.")
    merchant = str(req.get("merchant") or "").strip()
    if not 1 <= len(merchant) <= 60:
        raise PaymentError("Enter the merchant name (up to 60 characters).")
    try:
        when = dt.datetime.strptime(str(req.get("when")), "%Y-%m-%dT%H:%M")
    except ValueError:
        raise PaymentError("Choose a date and time.")
    if last_ts:
        last = dt.datetime.fromtimestamp(last_ts, dt.timezone.utc).replace(tzinfo=None)
        if when <= last:
            raise PaymentError(f"Pick a time after this card's last transaction ({last:%b %d, %Y %H:%M}).")
        if when > last + dt.timedelta(days=MAX_DAYS_AHEAD):
            raise PaymentError(f"Pick a time within {MAX_DAYS_AHEAD} days of the card's last transaction "
                               f"({last:%b %d, %Y %H:%M}); the simulation follows the replayed 2020 timeline.")

    location = req.get("location") or "home"
    if location == "home":
        base_lat, base_long, place = card["lat"], card["long"], f"{card['city']}, {card['state']}"
        spread = 0.5  # like the dataset: merchants are scattered around the cardholder's home
    elif location in CITIES:
        (base_lat, base_long), place, spread = CITIES[location], location, 0.05
    else:
        raise PaymentError("Choose a location.")
    merch_lat = round(base_lat + rng.uniform(-spread, spread), 6)
    merch_long = round(base_long + rng.uniform(-spread, spread), 6)

    txn_id = str(req.get("txn_id") or "").strip() or new_txn_id(when)
    if not txn_id.replace("-", "").replace("_", "").isalnum() or len(txn_id) > 40:
        raise PaymentError("Transaction ID may only contain letters, digits, '-' and '_' (max 40).")

    event = {
        "trans_date_trans_time": when.strftime(TS_FORMAT), "cc_num": card["cc_num"], "merchant": merchant,
        "category": category, "amt": f"{amount:.2f}", "first": card["holder"].split(" ")[0],
        "last": card["holder"].split(" ", 1)[-1], "gender": card["gender"], "street": card["street"],
        "city": card["city"], "state": card["state"], "zip": card["zip"], "lat": card["lat"], "long": card["long"],
        "city_pop": card["city_pop"], "job": card["job"], "dob": card["dob"], "trans_num": txn_id,
        "merch_lat": merch_lat, "merch_long": merch_long,
        "is_fraud": "",          # unknown: a real payment has no label
        "source": "payment-app",
    }
    receipt = {"txn_id": txn_id, "status": "COMPLETED", "amount": amount, "merchant": merchant,
               "category": category, "category_label": CATEGORY_LABELS[category], "location": place,
               "when": when.strftime("%Y-%m-%dT%H:%M"), "card_last4": card["last4"], "holder": card["holder"]}
    return event, receipt
