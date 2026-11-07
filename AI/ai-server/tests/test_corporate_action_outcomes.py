import pytest

from app.replay.corporate_action_outcomes import as_of, halt_period, list_page, payment
from app.replay.models import ResearchError


PLAN = ("이사회결의일(결정일) 2025-02-27 배당금지급 예정일자 2025-04-24 배당기준일 2024-12-31 "
        "1주당 배당금(원) 보통주식 100 배당금총액(원) 2,628,800,000")
VOTE = "주주총회일자 2025-03-25 보통주식 기말배당금 100 중간 배당금총액(원) 2,628,800,000"
PAID = ("회 사 명 : 주식회사 원익큐엔씨 2025년 3월 25일 개최된 당사의 주주총회에서 승인된 배당금은 "
        "2,628,800천원으로, 2025년 4월 24일에 지급되었습니다")
HALT = "동양철관 종목에 대해 금일 12시05분부터 시장관리상 사유로 매매거래정지 조치"
RESUME = "동양철관(008970) 종목의 거래를 15:00:00부터 재개 10분간(15:00~15:10) 호가접수를 거쳐 단일가매매"


def test_payment_needs_explicit_reported_payment_and_preserves_date_roles():
    row = payment(PLAN, VOTE, PAID)
    assert row["recordDate"] < row["decisionDate"] < row["approvedDate"]
    assert row["reportedTotalPaidKrw"] == 2_628_800_000
    assert row["paymentDate"] == "2025-04-24"
    assert row["exDividendDate"] is None
    with pytest.raises(ResearchError, match="BODY_FIELD_MISSING"):
        payment(PLAN, VOTE, PAID.replace("지급되었습니다", "지급될 예정입니다"))


def test_payment_fails_when_approved_and_paid_amounts_conflict():
    with pytest.raises(ResearchError, match="DIVIDEND_PAYMENT_CONFLICT"):
        payment(PLAN, VOTE, PAID.replace("2,628,800천원", "2,628,801천원"))


def test_halt_preserves_minute_precision_and_distinguishes_reopening_phases():
    row = halt_period(HALT, RESUME, "2025-03-18")
    assert row["haltLocalMinute"] == "2025-03-18T12:05+09:00"
    assert row["quoteAcceptanceResumesAt"] == "2025-03-18T15:00:00+09:00"
    assert row["continuousTradingReferenceAt"] == "2025-03-18T15:10:00+09:00"
    assert row["actualFirstTradeAt"] is None
    with pytest.raises(ResearchError, match="HALT_REOPENING_INTERVAL"):
        halt_period(HALT, RESUME.replace("15:10", "15:09"), "2025-03-18")


def test_list_page_detects_missing_rows_even_when_provider_total_is_stable():
    raw = '<div class="info type-00">전체 1건 : 1/1</div><table></table>'.encode()
    with pytest.raises(ResearchError, match="LIST_RANK"):
        list_page(raw, {"market": "KOSPI", "fromDate": "2025-01-01", "toDate": "2025-12-31"}, 1)


def test_as_of_releases_review_facts_only_after_local_knowledge_boundary():
    report = {"knownAt": "2026-11-08T01:00:00+09:00", "cases": [{"appliedDate": "2026-10-20"}]}
    assert as_of(report, "2026-10-20T20:00:00+09:00") == []
    assert as_of(report, "2026-11-08T01:00:00+09:00") == report["cases"]
