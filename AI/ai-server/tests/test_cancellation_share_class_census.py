from app.replay.cancellation_share_class_census import (
    date_comparison,
    kosdaq_lines,
    kospi_lines,
    reconcile,
    unchanged_instruments,
    unresolved_status,
)


def kospi_notice(label, symbol, isin):
    return (f"◎ 변경상장 ① 상장종목 표본 ② 주식의 종류와 수(변경전 → 변경후) "
            f"▶ 기명식 {label} 1,000주 (제 1 회) → 900 (제1회) ▶ 변경주식수 : -100주 "
            "③ 1주의 금액 : 500원 ④ 발행일(소각일) : 2026년1월5일 ⑤ 배당기산일 : 2026년1월1일 "
            f"⑦ 변경상장일 : 2026년1월9일 ⑧ 변경사유 : 이익소각 ⑨ 코드 ▶ 표준코드 : {isin} (단축코드 : A{symbol})")


def detail(**updates):
    return {"listingDate": "2026-01-09", "reportedIssueDate": "2026-01-05", "signedShareChange": -100,
            "reason": "주식소각", "stockIssueReportedOutstanding": 900} | updates


def test_separate_krx_sections_preserve_security_identity():
    common = kospi_notice("보통주", "000880", "KR7000880005")
    preferred = kospi_notice("종류주식1(3우선주)", "00088K", "KR700088K015")
    lines = kospi_lines(common + " " + preferred)
    assert [(line["symbol"], line["isin"], line["shareClass"]) for line in lines] == [
        ("000880", "KR7000880005", "COMMON"), ("00088K", "KR700088K015", "PREFERRED")]
    assert reconcile(detail(), lines)[0] == "NOTICE_DETAIL_CONFLICT"
    assert reconcile(detail(), lines[:1])[0] == "COMMON"
    conflicting_date = detail(reportedIssueDate="2026-01-04")
    assert reconcile(conflicting_date, lines[:1])[0] == "COMMON"
    assert date_comparison(conflicting_date, lines[:1]) == "ISSUE_DATE_DISAGREES"
    assert reconcile(detail(stockIssueReportedOutstanding=899), lines[:1])[0] == "NOTICE_DETAIL_CONFLICT"
    assert kospi_lines(common.replace("900 (제1회)", "901 (제1회)")) == []


def test_kosdaq_links_change_outstanding_and_explicit_preferred_ticker():
    body = ("2. 변경주식의 종류와 수 상환전환우선주 A00088K -100 3. 1주당 액면가 500 "
            "4. 변경상장 후 상장주식총수 상환전환우선주 900 2026-01-01 5. 상장일 2026-01-09 "
            "발행회수(발행일) 상환전환우선주 주식소각 - -100 - ('26.01.05)")
    lines = kosdaq_lines(body)
    assert len(lines) == 1
    assert (lines[0]["shareClassLabel"], lines[0]["symbol"], lines[0]["isin"]) == ("상환전환우선주", "00088K", None)
    assert reconcile(detail(), lines)[0] == "PREFERRED"
    assert kosdaq_lines(body.replace("- -100 -", "- -99 -")) == []
    assert kosdaq_lines(body.replace("('26.01.05)", "('26.01.10)")) == []
    assert kosdaq_lines(body.replace("상환전환우선주", "미확인우선주")) == []


def test_unresolved_sources_remain_distinguishable():
    assert unresolved_status(set()) == "NO_NOTICE_CANDIDATE"
    assert unresolved_status({"VIEWER_UNAVAILABLE"}) == "SOURCE_UNAVAILABLE"
    assert unresolved_status({"NOTICE_INVALID_DATE"}) == "NOTICE_INSTRUMENT_FIELDS_UNCONFIRMED"
    assert unresolved_status({"NOTICE_VERSION_REVIEW"}) == "NOTICE_VERSION_REVIEW"
    assert unresolved_status({"NOTICE_PARSED"}) == "NO_MATCHING_INSTRUMENT"


def test_correction_of_a_date_preserves_only_the_unchanged_instrument():
    first, = kospi_lines(kospi_notice("보통주", "000880", "KR7000880005"))
    corrected = first | {"reportedIssueDates": ["2025-01-05"]}
    stable = unchanged_instruments([[first], [corrected]])
    assert reconcile(detail(), stable)[0] == "COMMON"
    assert date_comparison(detail(), stable) == "NOTICE_VERSION_DATES_DIFFER"
    assert unchanged_instruments([[first], [corrected | {"outstanding": 899}]]) == []
