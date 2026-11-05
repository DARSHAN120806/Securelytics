import math

from fake_redis import FakeRedis

from securelytics.cleaning import clean_record
from securelytics.features import FEATURE_NAMES, CardSnapshot, compute_features, haversine_km
from securelytics.store import InMemoryStore, RedisStore

BASE = {"trans_id": "t0", "event_ts": 1_600_000_000, "cc_num": "42", "merchant": "m1",
        "category": "shopping_net", "amt": 100.0, "gender_m": 1, "lat": 40.0, "long": -74.0,
        "city_pop": 1000, "dob": "1980-01-01", "merch_lat": 40.0, "merch_long": -74.0, "is_fraud": 0}


def txn(i, dt, amt, merchant="m1"):
    return {**BASE, "trans_id": f"t{i}", "event_ts": BASE["event_ts"] + dt, "amt": amt, "merchant": merchant}


def test_first_transaction_has_no_history():
    f = compute_features(BASE, CardSnapshot())
    assert f["card_txn_count"] == 0 and f["is_new_merchant"] == 1
    assert math.isnan(f["amt_to_card_mean"]) and f["txn_count_24h"] == 0
    assert set(f) == set(FEATURE_NAMES)


def test_velocity_windows_and_ratios():
    s = InMemoryStore()
    history = [txn(1, 0, 10), txn(2, 1800, 20), txn(3, 7200, 30), txn(4, 86400 * 3, 40)]
    for t in history:
        s.commit(t)
    now = txn(5, 86400 * 3 + 600, 500, merchant="new-shop")
    f = compute_features(now, s.load(now))
    assert f["card_txn_count"] == 4
    assert f["txn_count_1h"] == 1 and f["txn_count_24h"] == 1 and f["txn_count_7d"] == 4
    assert f["amt_sum_24h"] == 40
    assert f["amt_to_card_mean"] == 500 / 25
    assert f["is_new_merchant"] == 1
    assert f["log_secs_since_last"] == math.log1p(600)


def test_window_excludes_events_older_than_7_days():
    s = InMemoryStore()
    s.commit(txn(1, 0, 10))
    later = txn(2, 7 * 86400, 10)
    assert compute_features(later, s.load(later))["txn_count_7d"] == 0


def test_haversine():
    assert abs(haversine_km(0, 0, 0, 1) - 111.19) < 0.1


def test_redis_store_matches_in_memory_store(raw_test_sample):
    """Same events through both stores must give the same features (no train/serve skew)."""
    mem, red = InMemoryStore(), RedisStore(FakeRedis())
    txns = [clean_record(r) for r in raw_test_sample.head(4000).to_dict("records")]
    for t in txns:
        fm, fr = compute_features(t, mem.load(t)), compute_features(t, red.load(t))
        for k in FEATURE_NAMES:
            a, b = fm[k], fr[k]
            assert (math.isnan(a) and math.isnan(b)) or math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9), (k, a, b)
        mem.commit(t); red.commit(t)


def test_snapshot_round_trip(tmp_path, raw_test_sample):
    mem = InMemoryStore()
    txns = [clean_record(r) for r in raw_test_sample.head(2000).to_dict("records")]
    for t in txns[:1500]:
        mem.commit(t)
    mem.export_snapshot(tmp_path / "snap.json")
    red = RedisStore(FakeRedis())
    assert red.is_empty()
    red.import_snapshot(tmp_path / "snap.json")
    assert not red.is_empty()
    for t in txns[1500:]:
        fm, fr = compute_features(t, mem.load(t)), compute_features(t, red.load(t))
        assert all((math.isnan(fm[k]) and math.isnan(fr[k])) or math.isclose(fm[k], fr[k], rel_tol=1e-9)
                   for k in FEATURE_NAMES)
        mem.commit(t); red.commit(t)
