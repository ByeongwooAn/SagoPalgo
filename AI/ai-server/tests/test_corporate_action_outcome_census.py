import pytest

from app.replay.cancellation_evidence import detail_fields, kosdaq_common_notice, kospi_common_notice, notice_links
from app.replay.corporate_action_outcome_census import kospi_halt_dates, notice_role
from app.replay.ksd_dividend_evidence import cross_check, parse_count, parse_rows
from app.replay.models import ResearchError

SCOPE = ("2023-11-01", "2026-11-02")


def test_stock_issue_detail_binds_listing_and_preserves_missing_date():
    raw = """<table><tr><th>회사명</th><td><img alt="유가증권" />알파</td>
      <th>상장일</th><td>2025-01-08</td><th>상장방식</th><td>변경상장</td></tr></table>
      <table><tr><th>발행사유</th><td>주식소각</td><th>발행일</th><td>2025-01-03</td></tr>
      <tr><th>발행주식수</th><td>-10,000</td><th>누적발행주식수</th><td>100,000</td></tr></table>""".encode()
    listing = {"market": "KOSPI", "issuer": "알파", "listingDate": "2025-01-08", "listingType": "변경상장",
               "reason": "주식소각", "signedShareChange": -10000}
    fields = detail_fields(raw, listing, SCOPE)
    assert fields["reportedIssueDate"] == "2025-01-03"
    assert fields["status"] == "CANCELLATION_DATE_UNVERIFIED_SHARE_CLASS"
    assert detail_fields(raw, listing | {"signedShareChange": -1}, SCOPE)["status"] == "STOCK_LISTING_DETAIL_CONFLICT"
    assert detail_fields(raw.replace(b"2025-01-03", b""), listing, SCOPE)["status"] == "STOCK_ISSUE_DATE_MISSING"


def test_common_notice_checks_count_and_keeps_share_class_boundary():
    body = ("기명식 보통주 : 110,000주 → 100,000주 - 변경주식수 : -10,000주 "
            "기명식 우선주 : 30,000주 → 25,000주 - 변경주식수 : -5,000주 "
            "④ 발행일(소각일) : 2025년01월03일 ⑦ 변경상장일 : 2025년01월08일 ⑧ 변경사유 : 주식소각 ⑨ 코드 "
            "▶ 보통주 표준코드 : KR7000000001 (단축코드:A000001) "
            "▶ 우선주 표준코드 : KR7000001000 (단축코드:A000002)")
    common = kospi_common_notice(body)
    assert common["symbol"] == "000001"
    assert common["signedShareChange"] == -10000
    assert kospi_common_notice(body.replace("110,000", "115,000")) is None
    kosdaq = ("2.변경주식의 종류와 수 보통주 A067990 -1,000,000 4.변경상장 후 상장주식총수 "
              "보통주 31,181,550 2023-01-01 5.상장일 2023-12-08 〖발행내역〗 발행회수(발행일) "
              "보통주 주식소각 - -1,000,000 - ('23.11.29)")
    assert kosdaq_common_notice(kosdaq, "067990")["cancellationDate"] == "2023-11-29"
    assert kosdaq_common_notice(kosdaq.replace("'23.", "'21."), "067990") is None
    assert kosdaq_common_notice(kosdaq.replace("('23.11.29)", "-"), "067990")["cancellationDate"] is None


def test_notice_detail_date_conflict_is_never_promoted():
    notice = {"market": "KOSPI", "noticeIssuer": "알파", "listingDate": "2025-01-08", "signedShareChange": -10000,
              "status": "COMMON_SHARE_NOTICE_FIELDS", "cancellationDate": "2025-01-03", "after": 100000,
              "symbol": "000001", "isin": "KR7000000001"}
    row = {"market": "KOSPI", "issuer": "알파", "listingDate": "2025-01-08", "signedShareChange": -10000,
           "stockIssueReportedOutstanding": 100000, "processId": "20250105000001", "shareClass": None,
           "actualCancellationDate": None, "reportedIssueDate": "2025-01-04"}
    conflict = dict(notice)
    notice_links([conflict], [row], SCOPE)
    assert conflict["status"] == "CANCELLATION_NOTICE_DETAIL_CONFLICT"
    assert row["actualCancellationDate"] is None
    row["reportedIssueDate"] = "2025-01-03"
    other = notice | {"symbol": "000002", "isin": "KR7000002000"}
    notice_links([dict(notice), other], [row], SCOPE)
    assert row["status"] == "CANCELLATION_NOTICE_SECURITY_CONFLICT"
    assert row["actualCancellationDate"] is None
    notice_links([notice], [row], SCOPE)
    assert (row["symbol"], row["actualCancellationDate"]) == ("000001", "2025-01-03")
    missing = row | {"reportedIssueDate": None, "actualCancellationDate": None, "shareClass": None}
    notice_links([notice | {"status": "COMMON_SHARE_NOTICE_FIELDS"}], [missing], SCOPE)
    assert missing["status"] == "COMMON_SHARE_CANCELLATION_DATE_FROM_NOTICE"
    assert missing["actualCancellationDate"] == "2025-01-03"
    missing_both = missing | {"actualCancellationDate": None, "shareClass": None}
    notice_links([notice | {"status": "COMMON_SHARE_NOTICE_FIELDS", "cancellationDate": None}], [missing_both], SCOPE)
    assert missing_both["status"] == "COMMON_SHARE_CANCELLATION_DATE_MISSING"
    assert missing_both["actualCancellationDate"] is None


def test_ksd_display_agreement_never_creates_actual_payment():
    row = {"market": "KOSPI", "symbol": "000001", "displayedPaymentDate": "2025-04-21", "recordDate": "2024-12-31"}
    schedule = {k: v for k, v in row.items() if k != "recordDate"}
    normal = cross_check([row], [schedule])["dividendRows"][0]
    assert normal["status"] == "DISPLAYED_DATE_AGREES"
    assert normal["actualPaymentDate"] is None
    ambiguous = cross_check([row, row | {"recordDate": "2025-01-08"}], [schedule])
    assert ambiguous["dividendCounts"] == {"AMBIGUOUS_SCHEDULE_LINK": 2}
    mismatch = cross_check([row], [schedule | {"market": "KOSDAQ"}])
    assert mismatch["dividendCounts"] == {"PAYMENT_SCHEDULE_LINK_MISSING": 1}
    assert len(mismatch["unmatchedScheduleRows"]) == 1


def test_ksd_count_and_result_envelopes_remain_distinct():
    assert parse_count(b'<result result="1"><LIST_CNT value="24"/></result>') == 24
    assert list(parse_rows(b'<vector result="1"><data vectorkey="0"><result><A value="x"/></result></data></vector>')) == [{"A": "x"}]
    with pytest.raises(ResearchError, match="KSD_ROWS_LAYOUT"):
        list(parse_rows(b'<vector result="2"><data vectorkey="0"><result/></data></vector>'))


def test_notice_roles_include_revisions_and_keep_the_selected_partition():
    windows = {"cancellation": {"from": "2023-11-01", "through": "2023-12-31"},
               "marketActions": {"from": "2023-11-01", "through": "2023-11-30"}}
    row = {"title": "[정정] 주권매매거래정지기간변경", "routes": {"category/halt": []},
           "listedMinuteKst": "2023-11-02 12:00"}
    assert notice_role(row, windows) == "HALT_BOUNDARY_REVIEW"
    assert notice_role(row | {"listedMinuteKst": "2023-12-02 12:00"}, windows) is None
    assert notice_role(row | {"title": "ETF 분배락"}, windows) is None
    assert notice_role(row | {"title": "변경상장(주식소각)", "listedMinuteKst": "2023-12-02 12:00"}, windows) == "CANCEL"
    body = "2.매매거래정지일 - 3.매매거래정지해제일 2023년11월09일 부터"
    assert kospi_halt_dates("68054.htm", body, SCOPE) == {"reopeningDate": "2023-11-09"}
