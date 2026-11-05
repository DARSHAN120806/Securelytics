"""Data cleaning and validation.

The same rules are implemented twice on purpose:

* ``clean_dataframe`` is vectorised and used offline (EDA, training).
* ``clean_record`` works on one raw event and is used by the stream processor.

``tests/test_cleaning.py`` checks that both produce identical output, so the
model never sees data in production that was cleaned differently from the data
it was trained on.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

TS_FORMAT = "%Y-%m-%d %H:%M:%S"
MERCHANT_PREFIX = "fraud_"  # artefact of the Sparkov generator, present on every merchant

CATEGORIES = [
    "entertainment", "food_dining", "gas_transport", "grocery_net", "grocery_pos",
    "health_fitness", "home", "kids_pets", "misc_net", "misc_pos",
    "personal_care", "shopping_net", "shopping_pos", "travel",
]
CATEGORY_CODE = {c: i for i, c in enumerate(CATEGORIES)}

REQUIRED_COLUMNS = [
    "trans_date_trans_time", "cc_num", "merchant", "category", "amt", "gender",
    "lat", "long", "city_pop", "dob", "trans_num", "merch_lat", "merch_long",
]
# Personal data that the model does not need. Dropped as early as possible.
PII_COLUMNS = ["first", "last", "street", "city", "state", "zip", "job"]
# Inconsistent with trans_date_trans_time in this dataset (offset varies per row),
# so event time is derived from the timestamp string instead.
UNRELIABLE_COLUMNS = ["unix_time"]

CLEAN_COLUMNS = [
    "trans_id", "event_ts", "cc_num", "merchant", "category", "amt", "gender_m",
    "lat", "long", "city_pop", "dob", "merch_lat", "merch_long", "is_fraud",
]

MIN_AGE, MAX_AGE = 10, 110


class ValidationError(ValueError):
    """Raised when a single streamed record cannot be cleaned."""


@dataclass
class CleaningReport:
    rows_in: int = 0
    rows_out: int = 0
    dropped: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    def drop(self, reason: str, n: int) -> None:
        if n:
            self.dropped[reason] = self.dropped.get(reason, 0) + int(n)

    def as_dict(self) -> dict:
        return {
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "rows_dropped": self.rows_in - self.rows_out,
            "dropped_by_reason": self.dropped,
            "notes": self.notes,
        }


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def _clean_merchant(name: str) -> str:
    name = name.strip()
    if name.startswith(MERCHANT_PREFIX):
        name = name[len(MERCHANT_PREFIX):]
    return name


def _age_years(dob: date, event_ts: int) -> float:
    event_day = datetime.fromtimestamp(event_ts, tz=timezone.utc).date()
    return (event_day - dob).days / 365.25


# --------------------------------------------------------------------------- #
# Streaming: one record at a time
# --------------------------------------------------------------------------- #
def clean_record(raw: dict) -> dict:
    """Validate and normalise one raw transaction. Raises ValidationError."""
    missing = [c for c in REQUIRED_COLUMNS if raw.get(c) in (None, "")]
    if missing:
        raise ValidationError(f"missing fields: {missing}")
    try:
        event_dt = datetime.strptime(str(raw["trans_date_trans_time"]), TS_FORMAT)
        event_ts = int(event_dt.replace(tzinfo=timezone.utc).timestamp())
        dob = datetime.strptime(str(raw["dob"])[:10], "%Y-%m-%d").date()
        amt = float(raw["amt"])
        lat, lon = float(raw["lat"]), float(raw["long"])
        mlat, mlon = float(raw["merch_lat"]), float(raw["merch_long"])
        city_pop = int(float(raw["city_pop"]))
        cc_num = str(int(float(raw["cc_num"]))) if not isinstance(raw["cc_num"], str) else raw["cc_num"].strip()
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"bad type: {exc}") from exc

    if any(math.isnan(v) for v in (amt, lat, lon, mlat, mlon)):
        raise ValidationError("NaN in numeric field")
    if amt <= 0:
        raise ValidationError("non-positive amount")
    if not (-90 <= lat <= 90 and -90 <= mlat <= 90 and -180 <= lon <= 180 and -180 <= mlon <= 180):
        raise ValidationError("coordinates out of range")
    if city_pop <= 0:
        raise ValidationError("non-positive city_pop")
    category = str(raw["category"]).strip().lower()
    if category not in CATEGORY_CODE:
        raise ValidationError(f"unknown category {category!r}")
    gender = str(raw["gender"]).strip().upper()
    if gender not in ("M", "F"):
        raise ValidationError(f"unknown gender {gender!r}")
    age = _age_years(dob, event_ts)
    if not (MIN_AGE <= age <= MAX_AGE):
        raise ValidationError(f"implausible age {age:.1f}")

    label = raw.get("is_fraud")
    return {
        "trans_id": str(raw["trans_num"]).strip(),
        "event_ts": event_ts,
        "cc_num": cc_num,
        "merchant": _clean_merchant(str(raw["merchant"])),
        "category": category,
        "amt": round(amt, 2),
        "gender_m": 1 if gender == "M" else 0,
        "lat": round(lat, 6),
        "long": round(lon, 6),
        "city_pop": city_pop,
        "dob": dob.isoformat(),
        "merch_lat": round(mlat, 6),
        "merch_long": round(mlon, 6),
        "is_fraud": None if label in (None, "") else int(label),
    }


# --------------------------------------------------------------------------- #
# Offline: whole DataFrame
# --------------------------------------------------------------------------- #
def clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    """Vectorised version of ``clean_record`` with a report of what was removed."""
    rep = CleaningReport(rows_in=len(df))
    df = df.copy()

    # 1. Structure: drop the CSV index column, PII and unreliable columns.
    index_cols = [c for c in df.columns if c.startswith("Unnamed")]
    df = df.drop(columns=index_cols + [c for c in PII_COLUMNS + UNRELIABLE_COLUMNS if c in df.columns])
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"input is missing required columns: {missing_cols}")
    rep.notes.append(f"dropped columns: {index_cols + PII_COLUMNS + UNRELIABLE_COLUMNS}")

    # 2. Missing values in required fields.
    for c in REQUIRED_COLUMNS:
        df[c] = df[c].replace("", np.nan)
    na = df[REQUIRED_COLUMNS].isna().any(axis=1)
    rep.drop("missing_required_field", na.sum())
    df = df[~na]

    # 3. Type coercion. Anything that fails to parse becomes NaN and is dropped.
    event_dt = pd.to_datetime(df["trans_date_trans_time"], format=TS_FORMAT, errors="coerce")
    dob = pd.to_datetime(df["dob"].astype(str).str[:10], format="%Y-%m-%d", errors="coerce")
    num = {c: pd.to_numeric(df[c], errors="coerce") for c in ["amt", "lat", "long", "merch_lat", "merch_long", "city_pop", "cc_num"]}
    bad_type = event_dt.isna() | dob.isna() | pd.concat(num, axis=1).isna().any(axis=1)
    rep.drop("unparseable_value", bad_type.sum())
    keep = ~bad_type
    df, event_dt, dob = df[keep], event_dt[keep], dob[keep]
    num = {k: v[keep] for k, v in num.items()}

    out = pd.DataFrame(index=df.index)
    out["trans_id"] = df["trans_num"].astype(str).str.strip()
    out["event_ts"] = ((event_dt - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).astype("int64")
    out["cc_num"] = num["cc_num"].astype("int64").astype(str)
    out["merchant"] = df["merchant"].astype(str).str.strip().str.removeprefix(MERCHANT_PREFIX)
    out["category"] = df["category"].astype(str).str.strip().str.lower()
    out["amt"] = num["amt"].round(2)
    gender = df["gender"].astype(str).str.strip().str.upper()
    out["gender_m"] = (gender == "M").astype("int8")
    # coordinates rounded to 6 dp (~0.1 m) so batch and stream parsing give identical floats
    out["lat"], out["long"] = num["lat"].round(6), num["long"].round(6)
    out["city_pop"] = num["city_pop"].astype("int64")
    out["dob"] = dob.dt.strftime("%Y-%m-%d")
    out["merch_lat"], out["merch_long"] = num["merch_lat"].round(6), num["merch_long"].round(6)
    out["is_fraud"] = pd.to_numeric(df["is_fraud"], errors="coerce").astype("Int8") if "is_fraud" in df else pd.NA

    # 4. Business-rule validation (same rules as clean_record).
    age = (event_dt.dt.normalize() - dob).dt.days / 365.25
    rules = {
        "non_positive_amount": out["amt"] <= 0,
        "coordinates_out_of_range": ~(out["lat"].between(-90, 90) & out["merch_lat"].between(-90, 90)
                                      & out["long"].between(-180, 180) & out["merch_long"].between(-180, 180)),
        "non_positive_city_pop": out["city_pop"] <= 0,
        "unknown_category": ~out["category"].isin(CATEGORIES),
        "unknown_gender": ~gender.isin(["M", "F"]),
        "implausible_age": ~age.between(MIN_AGE, MAX_AGE),
    }
    invalid = pd.Series(False, index=out.index)
    for reason, mask in rules.items():
        rep.drop(reason, (mask & ~invalid).sum())
        invalid |= mask
    out = out[~invalid]

    # 5. Duplicates: the same transaction id must only be processed once.
    dup = out["trans_id"].duplicated(keep="first")
    rep.drop("duplicate_trans_id", dup.sum())
    out = out[~dup]

    # 6. Order by event time: stateful features depend on it.
    out = out.sort_values(["event_ts", "trans_id"], kind="stable").reset_index(drop=True)

    # 7. Outliers are flagged, NOT removed: very large amounts are a fraud signal.
    p999 = out["amt"].quantile(0.999)
    rep.notes.append(
        f"amount outliers kept on purpose: {(out['amt'] > p999).sum()} rows above p99.9 ({p999:.2f}); "
        "handled with log-scaling and per-card ratios instead of deletion"
    )
    rep.rows_out = len(out)
    return out[CLEAN_COLUMNS], rep
