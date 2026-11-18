import pytest

from app.replay.hynix_daily_training import frozen_hynix_dates, merge_rows
from app.replay.models import ResearchError


def test_capture_overlap_retains_first_observation_and_rejects_mismatch():
    first = {"businessDate": "2024-05-31", "close": "100", "retrievedAt": "first"}
    repeated = {**first, "retrievedAt": "later"}
    next_day = {"businessDate": "2024-06-03", "close": "103"}
    rows, overlaps = merge_rows([[first], [repeated, next_day]])
    assert rows == [first, next_day] and overlaps == 1
    with pytest.raises(ResearchError, match="HYNIX_DAILY_CROSS_JOB_CONFLICT"):
        merge_rows([[first], [{**repeated, "close": "101"}]])


def test_common_dates_keep_samsung_purge_and_use_hynix_price_reviews():
    samsung = [
        {"businessDate": "2025-08-27", "targetDate": "2025-08-28", "sampleUse": "TRAIN", "priceReview": ["SAMSUNG_NOTE"]},
        {"businessDate": "2025-08-28", "targetDate": "2025-08-29", "sampleUse": "EXCLUDED_TARGET_CROSSES_SPLIT", "priceReview": []},
    ]
    result = frozen_hynix_dates(samsung, {"2025-08-28": ["HYNIX_NOTE"]})
    assert [row["targetDate"] for row in result] == ["2025-08-28", "2025-08-29"]
    assert [row["commonSample"] for row in result] == [True, False]
    assert [row["priceReview"] for row in result] == [[], ["HYNIX_NOTE"]]
    assert samsung[0]["priceReview"] == ["SAMSUNG_NOTE"]
