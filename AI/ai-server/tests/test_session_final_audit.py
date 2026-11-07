from types import SimpleNamespace

import pytest

from app.replay.models import ResearchError, utc
from app.replay.session_final_audit import as_of, candidates, kind_publication, minute_relation, pinned, scheduled_date


DAY = "2024-08-05"
AUDIT = "2026-11-07T11:27:00Z"


@pytest.mark.parametrize(("instant", "expected"), [
    ("2024-08-05T05:14:59.999999Z", "EFFECT_BEFORE_LISTED_MINUTE"),
    ("2024-08-05T05:15:00Z", "SAME_MINUTE_ORDER_UNPROVEN"),
    ("2024-08-05T05:15:59.999999Z", "SAME_MINUTE_ORDER_UNPROVEN"),
    ("2024-08-05T05:16:00Z", "EFFECT_AFTER_LISTED_MINUTE"),
])
def test_kind_minute_comparison_is_interval_based(instant, expected):
    assert minute_relation("2024-08-05 14:15", utc(instant)) == expected
    assert minute_relation(None, utc(instant)) == "UNATTRIBUTED"


def test_each_viewer_version_requires_its_own_market_receipt():
    def version(suffix, number, corrected):
        return {"document": f"202408050000{number}", "bodySha256": str(number) * 32,
                "correctionMarked": corrected, "sourceKnownAt": AUDIT,
                "url": f"https://kind.krx.co.kr/external/2024/08/05/{suffix}/202408050000{number}/99303.htm"}

    versions = [version("000001", 11, False), version("000002", 22, True)]
    original = {"receipt": "20240805000001", "market": "KOSPI",
                "reportedAtKstText": "2024-08-05 12:12", "versions": versions}
    corrected = original | {"receipt": "20240805000002", "reportedAtKstText": "2024-08-05 13:50"}
    original_review, corrected_review = [
        {"market": "KOSPI", "knownAt": AUDIT, "classification": "ISSUER_SPECIFIC_HALT",
         "subjectIssuer": "sample", "document": v["document"], "bodySha256": v["bodySha256"]}
        for v in versions
    ]
    archive = {"knownAt": AUDIT, "rows": [corrected, original | {"market": "KOSDAQ", "versions": []}]}
    _, [group] = kind_publication([archive], [], utc(AUDIT))
    assert [v["listedMinuteKst"] for v in group["versions"]] == [None, "2024-08-05 13:50"]
    assert group["publicationOrder"] == "ORDER_UNCONFIRMED"
    assert group["scope"] == "UNREVIEWED"

    archive["rows"].append(original)
    _, [group] = kind_publication([archive], [original_review, corrected_review], utc(AUDIT))
    assert [v["listedMinuteKst"] for v in group["versions"]] == ["2024-08-05 12:12", "2024-08-05 13:50"]
    assert group["publicationOrder"] == "ORDERED_BY_DISTINCT_LISTED_MINUTES"
    assert group["scope"] == "ISSUER_ONLY"


def test_scheduled_titles_distinguish_posted_year_from_effective_year():
    assert scheduled_date("2025년 연말 시장운영 일정 및 2026년 연초 개장일(1.2) 매매거래시간 안내",
                          "2025-12-18") == "2026-01-02"
    assert scheduled_date("대학수학능력시험일(11.19) 증권시장 등 거래시간 임시 변경", "2026-11-05") == "2026-11-19"
    assert scheduled_date("파생상품 야간거래 휴장 안내", "2025-09-10") is None


def candidate_sources():
    decisions = []
    markets = {}
    trade = {"candidate": {"value": True}, "value": None}
    for market in ("KOSPI", "KOSDAQ"):
        decisions.append({"market": market, "businessDate": DAY, "decision": "DEFERRED", "actualSessionConfirmed": False,
                          "includedInReferencePack": False, "nominalOpen": "09:00", "nominalClose": "15:30",
                          "ruleBookIds": ["1"], "knownAt": AUDIT, "blockers": ["NOTICE_SCOPE_NOT_EXHAUSTIVE"]})
        markets[market] = {"candidates": [{"businessDate": DAY, "ordinaryRuleConfirmed": True, "knownAt": AUDIT,
                                          "open": "09:00", "close": "15:30"}],
                           "rulePeriods": [{"startDate": DAY, "endDate": DAY, "continuityConfirmed": True,
                                            "bookIds": ["1"], "nominalOpen": "09:00", "nominalClose": "15:30"}]}
    calendar = {"markets": {market: {"rows": [{"businessDate": DAY, "krxTradingSchedule": trade.copy()}]}
                            for market in markets}}
    return {"promotionDecisions": decisions}, {"markets": markets}, calendar


def test_partial_program_and_market_evidence_do_not_confirm_whole_day():
    decisions, rules, calendar = candidate_sources()
    timeline = SimpleNamespace(phases=[
        SimpleNamespace(market="KOSPI", businessDate=DAY, kind="PROGRAM_BUY_PAUSE", phaseId="program"),
        SimpleNamespace(market="KOSDAQ", businessDate=DAY, kind="HALT", phaseId="halt"),
    ])
    decisions["promotionDecisions"][1]["blockers"].append("MARKET_WIDE_INTRADAY_HALT_REQUIRES_INTERVAL_MODEL")
    rows = candidates(decisions, rules, calendar, timeline, [], utc(AUDIT))
    assert [r["coverage"] for r in rows] == ["PARTIAL_PROGRAM_RESTRICTION", "PARTIAL_MARKET_RESTRICTION"]
    assert all(not r["wholeSessionConfirmed"] and not r["actualSessionConfirmed"] for r in rows)
    assert all(r["actualOpenAt"] is None and r["actualCloseAt"] is None for r in rows)
    assert all(r["blockers"] == ["NOTICE_SCOPE_NOT_EXHAUSTIVE"] for r in rows)
    report = {"knownAt": AUDIT, "candidateDecisions": rows, "scheduledExceptions": [], "circuitBreakerComparisons": []}
    assert as_of(report, "KOSPI", DAY, "2026-11-07T11:26:59.999999Z")["candidateDecisions"] == []
    assert as_of(report, "KOSPI", DAY, AUDIT)["candidateDecisions"] == [rows[0]]


def test_actual_closure_or_special_schedule_cannot_be_an_ordinary_candidate():
    decisions, rules, calendar = candidate_sources()
    timeline = SimpleNamespace(phases=[])
    with pytest.raises(ResearchError, match="H03_CANDIDATE_SCOPE_COLLISION"):
        candidates(decisions, rules, calendar, timeline, [{"market": "KOSPI", "businessDate": DAY}], utc(AUDIT))
    calendar["markets"]["KOSPI"]["rows"][0]["krxTradingSchedule"]["value"] = False
    with pytest.raises(ResearchError, match="H03_RULE_OR_CALENDAR_CONFLICT"):
        candidates(decisions, rules, calendar, timeline, [], utc(AUDIT))


def test_tampered_raw_attachment_is_rejected(tmp_path):
    source = tmp_path / "attachment.pdf"
    source.write_bytes(b"%PDF-replaced")
    with pytest.raises(ResearchError, match="H03_INPUT_HASH"):
        pinned(source, "0" * 64)
