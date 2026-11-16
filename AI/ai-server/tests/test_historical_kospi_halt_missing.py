from app.replay.historical_kospi_halt_missing import delisting_fields, match_scope


def test_delisting_reads_both_preferred_codes_from_the_same_notice():
    raw = """<table>
      <tr><td>1.상장폐지 대상 주권 및 주식수</td><td>주권종류</td><td>주식수</td><td>단축코드</td></tr>
      <tr><td>진흥기업1우선주(신형)</td><td>85,721</td><td>A002785</td></tr>
      <tr><td>진흥기업2우선주(신형)</td><td>29,480</td><td>A002787</td></tr>
      <tr><td>3.상장폐지일</td><td>2026-11-10</td></tr>
    </table>""".encode()

    assert delisting_fields(raw) == {
        "issuer": None, "date": "2026-11-10",
        "stockCodes": {"002785": "진흥기업1우선주(신형)", "002787": "진흥기업2우선주(신형)"},
    }


def test_named_halt_remarks_apply_only_to_the_listed_issues_on_that_date():
    first = {"name": "진흥기업1우선주(신형)", "shareType": "신형우선주"}
    second = {"name": "진흥기업2우선주(신형)", "shareType": "신형우선주"}
    boundary = {"status": "DATED_KRX_NAME_MATCH", "candidateIssues": [first, second]}
    body = "동 매매거래정지로 보통주 및 진흥기업 1우선주, 진흥기업 2우선주는 2026년 8월 14일부터 매매거래정지됨"

    assert match_scope({}, boundary, second, body, [], [], "halt", "2026-08-14")[0] == "KIND_NAMES_SHARE_IN_HALT_REMARKS"
    assert match_scope({}, boundary, second, body, [], [], "halt", "2026-08-15")[0] == "KIND_ISSUE_SCOPE_UNCONFIRMED"


def test_later_delisting_does_not_assign_an_issuer_wide_notice_to_a_preferred_share():
    common = {"name": "삼양홀딩스보통주", "shareType": "보통주"}
    preferred = {"name": "삼양홀딩스1우선주", "shareType": "구형우선주"}
    boundary = {"status": "DATED_KRX_NAME_MATCH", "candidateIssues": [common, preferred]}
    delisting = {"issuer": "삼양홀딩스1우선주", "shareClass": "우선주", "date": "2025-08-20"}

    result = match_scope({}, boundary, preferred, "(주)삼양홀딩스 주권", [delisting], [], "halt", "2025-05-30")

    assert result == ("KIND_ISSUE_SCOPE_UNCONFIRMED", [])


def test_matching_changed_listing_requires_the_original_notice_to_link_the_release():
    common = {"name": "서울식품공업보통주", "shareType": "보통주"}
    preferred = {"name": "서울식품공업1우선주", "shareType": "구형우선주"}
    boundary = {"status": "DATED_KRX_NAME_MATCH", "candidateIssues": [common, preferred]}
    release = [{"reopeningDate": "2026-05-21"}]

    result = match_scope({}, boundary, preferred, "매매거래정지해제일 변경상장일", [], release, "halt", "2026-04-27")

    assert result == ("MATCHING_CHANGED_LISTING_IDENTIFIES_HALTED_SHARE", release)
    assert match_scope({}, boundary, preferred, "해제일 별도 안내", [], release, "halt", "2026-04-27")[0] == "KIND_ISSUE_SCOPE_UNCONFIRMED"
