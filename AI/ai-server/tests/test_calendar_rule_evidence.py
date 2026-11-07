"""Check rule binding, conditional T+2 calculation, and knowledge boundaries."""
import pytest

from app.replay import calendar_rule_evidence as audit
from app.replay.models import ResearchError


EARLY = "2026-11-05T00:00:00Z"
LATER = "2026-11-07T06:00:00Z"


def raw_clause(book, anchor, text):
    return (f'<div class="lawbon"><img onclick="printJo(\'{book}\',\'123\',\'bon{anchor}\');">'
            f'<a name="bon{anchor}"><strong>{text}</strong></a><a name="bon999">end</a></div>').encode()


def test_holiday_clause_must_bind_to_the_expected_market_and_body():
    raw = raw_clause("123456", "5", "제5조(휴장) 매매거래를 하지 아니한다. 공휴일, 근로자의 날, 토요일, "
                     "12월 31일, 시장관리상 필요")
    assert len(audit.holiday_clause(raw, "123456", "KOSPI")) == 64
    with pytest.raises(ResearchError, match="CALENDAR_RULE_CLAUSE_IDENTITY"):
        audit.holiday_clause(raw, "987654", "KOSPI")
    with pytest.raises(ResearchError, match="CALENDAR_HOLIDAY_RULE_REVIEW"):
        audit.holiday_clause(raw, "123456", "KOSDAQ")


def test_settlement_clause_requires_holiday_exclusion_and_exception_provision():
    raw = raw_clause("123456", "6", "제6조(대상 매매거래) 보통거래: 체결한 날을 포함하여 3일째 되는 날에 결제한다. "
                     "세칙으로 정하는 경우, 휴장일을 제외하고 계산한다. 결제일을 변경할 수 있다.")
    assert len(audit.settlement_clause(raw, "123456", "6")) == 64
    with pytest.raises(ResearchError, match="CALENDAR_SETTLEMENT_RULE_REVIEW"):
        audit.settlement_clause(raw.replace("제외".encode(), "포함".encode()), "123456", "6")


def calendar_row(date, opened, settlement=None, open_status="RECONSTRUCTED"):
    return {"businessDate": date, "fields": {
        "openDay": {"status": open_status, "value": opened,
                    "claims": [] if opened is None else [{"sourceId": "calendar"}]},
        "settlementDay": {"status": "UNKNOWN" if settlement is None else "EXPLICIT_SCHEDULE", "value": settlement,
                          "claims": [] if settlement is None else [{"sourceId": "notice"}]},
    }}


def rule_fixture():
    periods = [
        {"startDate": "2025-02-28", "endDate": "2025-03-03", "continuityConfirmed": True, "bookIds": ["old"]},
        {"startDate": "2025-03-04", "endDate": "2025-03-05", "continuityConfirmed": True, "bookIds": ["new"]},
    ]
    facts = {"old": {"effectiveDate": "2023-01-01", "knownAt": EARLY, "settlementClauseSha256": "proof"},
             "new": {"effectiveDate": "2025-03-04", "knownAt": EARLY}}
    clearing = {"clearing": {"bookId": "clearing", "effectiveDate": "2025-03-04", "knownAt": LATER}}
    return periods, facts, clearing, {"calendar": {"knownAt": EARLY}, "notice": {"knownAt": LATER}}


def dates():
    return [calendar_row(date, opened) for date, opened in (
        ("2025-02-28", True), ("2025-03-01", False), ("2025-03-02", False), ("2025-03-03", False),
        ("2025-03-04", True), ("2025-03-05", True),
    )]


def test_t_plus_two_crosses_holiday_and_regulation_boundary_and_preserves_provenance():
    rows = audit.date_rows(dates(), *rule_fixture())
    audit.attach_trade_dates(rows)
    assert rows[1]["standardSettlementCalendar"]["status"] == "RULE_EXCLUDED"
    assert rows[1]["standardSettlementForTrade"]["status"] == "NO_SCHEDULED_TRADE"
    assert rows[0]["standardSettlementForTrade"] == {
        "status": "T_PLUS_TWO_CANDIDATE", "value": "2025-03-05", "knownAt": LATER,
        "bookIds": ["clearing", "new", "old"],
    }
    assert rows[-2]["standardSettlementForTrade"]["status"] == "AFTER_SCOPE"
    report = {"markets": {"KOSPI": {"rows": rows}}}
    assert audit.as_of(report, "KOSPI", "2025-02-28", EARLY)["standardSettlementForTrade"]["value"] is None
    assert audit.as_of(report, "KOSPI", "2025-02-28", LATER)["standardSettlementForTrade"]["value"] == "2025-03-05"


def test_conflicting_settlement_evidence_is_not_overridden_or_exposed_early():
    calendar = dates()
    calendar[3] = calendar_row("2025-03-03", False, settlement=True)
    rows = audit.date_rows(calendar, *rule_fixture())
    audit.attach_trade_dates(rows)
    assert rows[0]["standardSettlementForTrade"]["status"] == "UNCONFIRMED_CALENDAR"
    report = {"markets": {"KOSDAQ": {"rows": rows}}}
    assert audit.as_of(report, "KOSDAQ", "2025-03-03", EARLY)["standardSettlementCalendar"]["status"] == "UNKNOWN"
    assert audit.as_of(report, "KOSDAQ", "2025-03-03", LATER)["standardSettlementCalendar"]["status"] == "CONFLICT"


def test_gaps_in_dates_or_market_edition_periods_stop_the_report():
    with pytest.raises(ResearchError, match="CALENDAR_RULE_DATE_GAP"):
        audit.date_rows([dates()[0], *dates()[2:]], *rule_fixture())
    periods, facts, clearing, evidence = rule_fixture()
    with pytest.raises(ResearchError, match="CALENDAR_MARKET_RULE_PERIOD_GAP"):
        audit.date_rows(dates(), periods[:1], facts, clearing, evidence)
