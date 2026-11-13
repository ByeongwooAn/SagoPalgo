from copy import deepcopy

import pytest

from app.replay.historical_actions_followup import SCHEMA, action_sample
from app.replay.historical_market_action_expansion import extra_fields, select_rows
from app.replay.models import ResearchError


def candidate(receipt, day, *, correction=False):
    return {"receipt": receipt, "listedMinuteKst": f"{day}T09:00", "market": "KOSDAQ", "title": "권리락",
            "routes": ["category/rights"], "titleCorrectionFlag": correction,
            "membership": {"status": "SAME_DATE_NAME_MATCH"}}


def test_selects_every_unreviewed_candidate_in_window():
    rows = [candidate("before", "2023-11-30"), candidate("first", "2023-12-01"),
            candidate("second", "2023-12-04"), candidate("correction", "2023-12-05", correction=True),
            candidate("last", "2023-12-31"), candidate("after", "2024-01-02")]
    inventory = {"candidateRows": rows}
    candidates, prior = action_sample(inventory)
    sample = {"schemaVersion": SCHEMA, "actionCandidates": len(candidates),
              "actionSample": [{"receipt": receipt} for receipt in sorted(prior)]}

    assert select_rows(inventory, sample, "2023-12-01", "2023-12-31") == rows[3:5]

    altered = deepcopy(sample)
    altered["actionSample"][0]["receipt"] = "correction"
    with pytest.raises(ResearchError, match="EXPANSION_SAMPLE_BINDING"):
        select_rows(inventory, altered, "2023-12-01", "2023-12-31")


def test_combined_rights_requires_explicit_common_share_and_matching_symbol():
    body = ("1. 권배락 실시일 2023-12-27 2. 권배락 사유 무상증자 및 배당 3. 권배락 내역 "
            "회사명 주권종류 단축코드 기준가(원) 예시 보통주식 A123450 2,425 4. 기타 -")
    form = ("KOSDAQ", "DIVIDEND_OR_COMBINED", "70768.htm")

    assert extra_fields(*form, body, "예시", "123450") == {
        "appliedDate": "2023-12-27", "referencePriceKrw": 2425, "publishedCause": "무상증자 및 배당"}
    assert extra_fields(*form, body, "예시", "123455") is None
    assert extra_fields(*form, body.replace("보통주식", "우선주"), "예시", "123450") is None


def test_halt_times_preserve_unconfirmed_share_class_and_reject_reversed_boundary():
    body = "3. 매매거래정지 일시 2023-12-21 16:14 4. 매매거래정지 해제일시 2023-12-22 09:00 5. 사유"
    form = ("KOSPI", "HALT_BOUNDARY_REVIEW", "99808.htm")

    assert extra_fields(*form, body, "예시", "123450") == {
        "status": "HALT_TIMES_SHARE_CLASS_UNCONFIRMED", "haltTimeKst": "2023-12-21T16:14:00+09:00",
        "reopeningTimeKst": "2023-12-22T09:00:00+09:00", "actualFirstTradeAt": None}
    assert extra_fields(*form, body.replace("2023-12-22", "2023-12-21"), "예시", "123450") is None
