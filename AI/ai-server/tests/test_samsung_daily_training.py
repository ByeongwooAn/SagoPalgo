from datetime import date, timedelta

import pytest

from app.replay.dataset import canonical, digest
from app.replay.models import ResearchError
from app.replay.samsung_daily_training import audit_boundaries, freeze_dates, read_pinned, validate_trading_dates


@pytest.fixture
def observations():
    calendar = []
    for offset in range(70):
        day = date(2024, 1, 1) + timedelta(days=offset)
        opened = day.weekday() < 5
        calendar.append({"businessDate": day.isoformat(), "openDay": opened, "holidayReason": None,
                         "basis": "WEEKDAY_OPEN_RECONSTRUCTION" if opened else "WEEKEND_RULE"})
    rows = [{"businessDate": day["businessDate"], "status": "OBSERVED_PRICE", "volume": "1"}
            for day in calendar if day["openDay"]]
    return calendar, rows


def test_next_open_day_lookback_and_split_boundaries(observations):
    calendar, rows = observations
    trading_dates = validate_trading_dates(calendar, rows)
    manifest = freeze_dates(calendar, trading_dates, {})
    by_date = {row["businessDate"]: row for row in manifest}
    assert by_date["2024-01-06"]["sampleUse"] == "EXCLUDED_MARKET_CLOSED"
    assert by_date["2024-01-26"]["sampleUse"] == "EXCLUDED_INSUFFICIENT_LOOKBACK"
    assert by_date["2024-01-26"]["targetDate"] == "2024-01-29"
    assert by_date["2024-01-29"]["oldestFeatureDate"] == "2024-01-01"
    assert by_date["2024-03-08"]["sampleUse"] == "EXCLUDED_TARGET_OUTSIDE_SNAPSHOT"
    assert by_date["2024-03-08"]["targetDate"] is None

    for earlier, later in (("TRAIN", "VALIDATION"), ("VALIDATION", "FINAL_EVALUATION")):
        last_target = max(row["targetDate"] for row in manifest if row["sampleUse"] == earlier)
        first_signal = min(row["businessDate"] for row in manifest if row["sampleUse"] == later)
        assert last_target < first_signal
        assert by_date[last_target]["sampleUse"] == "EXCLUDED_TARGET_CROSSES_SPLIT"
        assert by_date[last_target]["targetDate"] == first_signal


@pytest.mark.parametrize("change", ["missing", "duplicate", "closed"])
def test_calendar_mismatch_cannot_shift_the_target(observations, change):
    calendar, rows = observations
    if change == "missing":
        rows.pop(22)
    elif change == "duplicate":
        rows.insert(22, rows[22])
    else:
        rows[4]["businessDate"] = "2024-01-06"
    with pytest.raises(ResearchError, match="SAMSUNG_DAILY_CALENDAR_MISMATCH"):
        validate_trading_dates(calendar, rows)


def test_nontraded_open_day_blocks_freeze(observations):
    calendar, rows = observations
    rows[3]["volume"] = "0"
    with pytest.raises(ResearchError, match="SAMSUNG_DAILY_NOT_TRADED"):
        validate_trading_dates(calendar, rows)


@pytest.mark.parametrize("delta, error", [("1", "PREVIOUS_CLOSE_CONFLICT"), ("20", "UNREVIEWED_PRICE_BOUNDARY")])
def test_unreviewed_gap_or_inconsistent_prior_close_blocks_freeze(tmp_path, delta, error):
    provider_rows = [
        {"stck_bsop_date": stamp, "prdy_vrss": value, "flng_cls_code": "00", "prtt_rate": "0.00",
         "mod_yn": "N", "revl_issu_reas": ""}
        for stamp, value in (("20240102", "0"), ("20240103", delta))
    ]
    raw = canonical({"output2": provider_rows})
    (tmp_path / "response.json").write_bytes(raw)
    rows = [{"businessDate": "2024-01-02", "open": "100", "close": "100"},
            {"businessDate": "2024-01-03", "open": "110", "close": "120"}]
    with pytest.raises(ResearchError, match=f"SAMSUNG_DAILY_{error}"):
        audit_boundaries(tmp_path, [{"file": "response.json", "sha256": digest(raw)}], rows)


def test_changed_calendar_rejects_even_valid_json(tmp_path):
    calendar = tmp_path / "calendar.json"
    calendar.write_bytes(b"{}")
    with pytest.raises(ResearchError, match="SAMSUNG_DAILY_SNAPSHOT_CHANGED"):
        read_pinned(calendar, "calendar")
