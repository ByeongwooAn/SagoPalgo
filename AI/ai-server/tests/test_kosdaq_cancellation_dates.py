import pytest

from app.replay.kosdaq_cancellation_dates import actual_note_dates, actual_table_dates, outcome, planned_date
from app.replay.models import ResearchError


def test_report_table_binds_date_code_quantity_and_common_share_class():
    row = """
    <TR>
      <TU AUNIT="BRN_DT" AUNITVALUE="20260331">2026년 3월 31일</TU>
      <TU AUNIT="BRN_MTD" AUNITVALUE="1">이익소각</TU>
      <TE ACODE="SHR_KND">보통주</TE>
      <TE ACODE="BRN_QTY">600,000</TE>
    </TR>
    """
    (value, basis, sha), = list(actual_table_dates(row, 600000))
    assert (value, basis, len(sha)) == ("2026-03-31", "ISSUER_RETIREMENT_TABLE", 64)
    assert list(actual_table_dates(row.replace("보통주", "우선주"), 600000)) == []
    assert list(actual_table_dates(row, 600001)) == []
    with pytest.raises(ResearchError, match="ISSUER_ACTUAL_DATE_DISPLAY_CONFLICT"):
        list(actual_table_dates(row.replace("20260331", "20260330"), 600000))


def test_completion_note_preserves_its_actual_date_with_the_exact_common_share_count():
    body = ("<P>2026년 7월 8일 이사회결의. 2026년 8월 3일 회사가 당반기 취득한 "
            "자기주식(보통주 2,034,824주, 취득금액 2,997,418,817원)을 소각하였습니다.</P>")
    (value, basis, _), = list(actual_note_dates(body, 2034824))
    assert (value, basis) == ("2026-08-03", "ISSUER_REPORTED_COMPLETION_NOTE")
    assert list(actual_note_dates(body.replace("소각하였습니다", "소각할 예정입니다"), 2034824)) == []


def test_scheduled_date_requires_the_same_post_cancellation_share_count():
    body = ("<P>1. 소각할 주식의 종류와 수 보통주식(주) 600,000 종류주식(주) - "
            "2. 발행주식총수 보통주식(주) 15,800,000 종류주식(주) - "
            "7. 소각 예정일 2026-04-07</P>")
    assert planned_date(body, 600000, 15200000) == "2026-04-07"
    assert planned_date(body, 600000, 15200001) is None
    assert outcome([], [{"date": "2026-04-07"}]) == ("SCHEDULED_DATE_ONLY", None)


def test_depository_and_issuer_completion_are_distinct_and_conflicts_are_not_promoted():
    known = {"date": "2026-09-11"}
    other = {"date": "2026-09-12"}
    assert outcome([], [known], known) == ("KSD_REPORTED_CANCELLATION_DATE", known["date"])
    assert outcome([known], [other], known) == ("ISSUER_REPORTED_CANCELLATION_DATE", known["date"])
    assert outcome([other], [known], known) == ("CONFLICTING_COMPLETION_DATES", None)
