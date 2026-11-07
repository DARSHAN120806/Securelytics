"""Payment simulator: a payment becomes a raw event the normal pipeline understands."""
import datetime as dt
import random

import pytest

from securelytics.cleaning import clean_record
from securelytics.payments import CITIES, PaymentError, build_event

CARD = {"id": "abc", "cc_num": "2291163933867244", "last4": "7244", "holder": "Jeff Elliott", "gender": "M",
        "street": "351 Darlene Green", "city": "Columbia", "state": "SC", "zip": "29209", "lat": 33.9659,
        "long": -80.9355, "city_pop": 333497, "job": "Engineer", "dob": "1968-03-19", "color": 0}
LAST = int(dt.datetime(2020, 6, 21, 12, 0, tzinfo=dt.timezone.utc).timestamp())


def req(**kw):
    return {"amount": 42.5, "category": "grocery_pos", "merchant": "FreshMart", "location": "home",
            "when": "2020-06-21T18:30", **kw}


def test_payment_becomes_a_valid_pipeline_event():
    event, receipt = build_event(CARD, req(), LAST, random.Random(1))
    txn = clean_record(event)  # exactly what the processor does with it
    assert txn["amt"] == 42.5 and txn["category"] == "grocery_pos" and txn["cc_num"] == CARD["cc_num"]
    assert txn["is_fraud"] is None  # a real payment has no label
    assert abs(txn["merch_lat"] - CARD["lat"]) <= 0.5
    assert receipt["status"] == "COMPLETED" and receipt["txn_id"].startswith("TXN-20200621-")


def test_other_city_location_and_custom_txn_id():
    event, receipt = build_event(CARD, req(location="Miami, FL", txn_id="MY-ID_1"), LAST, random.Random(1))
    lat, lon = CITIES["Miami, FL"]
    assert abs(event["merch_lat"] - lat) <= 0.05 and abs(event["merch_long"] - lon) <= 0.05
    assert event["trans_num"] == "MY-ID_1" and receipt["location"] == "Miami, FL"


@pytest.mark.parametrize("bad, msg", [
    ({"amount": 0}, "between"), ({"amount": "x"}, "valid amount"), ({"category": "crypto"}, "category"),
    ({"merchant": ""}, "merchant"), ({"location": "Mars"}, "location"), ({"when": "2020-06-20T10:00"}, "after"),
    ({"when": "2020-07-30T10:00"}, "within"), ({"txn_id": "bad id!"}, "Transaction ID"),
])
def test_invalid_payments_are_rejected_with_a_clear_message(bad, msg):
    with pytest.raises(PaymentError, match=msg):
        build_event(CARD, req(**bad), LAST)
