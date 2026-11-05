import pandas as pd
import pytest

from securelytics.cleaning import ValidationError, clean_dataframe, clean_record

GOOD = {
    "trans_date_trans_time": "2020-06-21 12:14:25", "cc_num": "2291163933867244",
    "merchant": "fraud_Kirlin and Sons", "category": "personal_care", "amt": "2.86",
    "first": "Jeff", "last": "Elliott", "gender": "M", "street": "351 Darlene Green",
    "city": "Columbia", "state": "SC", "zip": "29209", "lat": "33.9659", "long": "-80.9355",
    "city_pop": "333497", "job": "Mechanical engineer", "dob": "1968-03-19",
    "trans_num": "2da90c7d74bd46a0caf3777415b3ebd3", "unix_time": "1371816865",
    "merch_lat": "33.986391", "merch_long": "-81.200714", "is_fraud": "0",
}


def test_clean_record_normalises_and_drops_pii():
    out = clean_record(GOOD)
    assert out["merchant"] == "Kirlin and Sons"          # generator prefix stripped
    assert out["event_ts"] == 1592741665                 # from the timestamp string, not unix_time
    assert out["gender_m"] == 1 and out["amt"] == 2.86
    assert not {"first", "last", "street", "job"} & out.keys()


@pytest.mark.parametrize("field,value", [
    ("amt", "-5"), ("amt", "abc"), ("amt", ""), ("category", "crypto"), ("gender", "X"),
    ("lat", "123"), ("dob", "2019-01-01"), ("trans_date_trans_time", "yesterday"), ("cc_num", None),
])
def test_clean_record_rejects_bad_values(field, value):
    with pytest.raises(ValidationError):
        clean_record({**GOOD, field: value})


def test_clean_dataframe_report_counts_each_problem():
    rows = [GOOD, {**GOOD, "trans_num": "b", "amt": "-1"}, {**GOOD, "trans_num": "c", "category": "crypto"},
            dict(GOOD), {**GOOD, "trans_num": "d", "lat": ""}]
    df, rep = clean_dataframe(pd.DataFrame(rows))
    assert len(df) == 1
    assert rep.dropped == {"non_positive_amount": 1, "unknown_category": 1,
                           "duplicate_trans_id": 1, "missing_required_field": 1}


def test_batch_and_stream_cleaning_are_identical(raw_test_sample):
    batch, _ = clean_dataframe(raw_test_sample)
    batch = batch.set_index("trans_id")
    for raw in raw_test_sample.head(3000).to_dict("records"):
        rec = clean_record(raw)
        row = batch.loc[rec["trans_id"]]
        for k, v in rec.items():
            if k != "trans_id":
                assert row[k] == v, (k, row[k], v)
