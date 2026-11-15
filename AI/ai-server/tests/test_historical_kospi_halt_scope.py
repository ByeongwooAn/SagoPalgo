from app.replay.historical_kospi_halt_scope import (
    changed_listing_release,
    classify,
    daily_query_outcomes,
    krx_daily_rows,
    preferred_candidates,
)


def test_explicit_old_preferred_name_does_not_select_viewer_common_code():
    issues = {
        "000880": {"symbol": "000880", "name": "한화보통주", "abbreviatedName": "한화", "shareType": "보통주"},
        "000885": {"symbol": "000885", "name": "한화1우선주", "abbreviatedName": "한화우", "shareType": "구형우선주"},
        "00088K": {"symbol": "00088K", "name": "한화3우선주(신형)", "abbreviatedName": "한화3우B", "shareType": "신형우선주"},
    }
    assert preferred_candidates("한화1우선주", "000880", issues) == [issues["000885"]]


def test_one_listed_common_share_keeps_candidate_status_until_dated_evidence():
    points = {"halt": {"status": "DATED_KRX_NAME_MATCH", "candidateIssues": [
        {"symbol": "000880", "dailyHaltEvidence": None},
    ]}}
    notice = {"publishedTarget": "(주)한화 주권"}
    assert classify(notice, points) == "SINGLE_COMMON_SHARE_CANDIDATE"

    points["halt"]["candidateIssues"][0]["dailyHaltEvidence"] = {"haltFlag": "Y"}
    assert classify(notice, points) == "CODE_LEVEL_HALT_DAY_EVIDENCE_AVAILABLE"


def test_daily_history_records_keep_date_without_inventing_time():
    raw = ("번호,일자,종목코드,종목명,시장구분,정지여부\r\n"
           '"1","2023/12/22","336370","솔루스첨단소재","KOSPI","N"\r\n').encode("cp949")
    row = krx_daily_rows(raw)["336370", "2023-12-22"]
    assert row["haltFlag"] == "N"
    assert "haltTimeKst" not in row
    assert "reopeningTimeKst" not in row


def test_changed_listing_requires_explicit_release_clause_agreeing_with_listing_date():
    body = ("◎ 예시 변경상장(액면분할) ⑤ 변경상장일 : 2024년04월17일 "
            "▶ 보통주 표준코드 : KR7001460005 (단축코드:A001460) "
            "▶ 1우선주 표준코드 : KR7001461003 (단축코드:A001465) "
            "※ 변경상장일(2024년04월17일)에 매매거래정지 해제됨")
    assert changed_listing_release(body) == {
        "reopeningDate": "2024-04-17",
        "symbols": {"001460": "KR7001460005", "001465": "KR7001461003"},
    }
    assert changed_listing_release(body.replace("(2024년04월17일)", "(2024년04월18일)")) is None
    assert changed_listing_release(body.split("※")[0]) is None


def test_daily_outcomes_keep_unreturned_dates_separate_from_reported_n():
    planned = [
        {"symbol": "000040", "date": "2024-02-23", "notices": [{"receipt": "test", "phase": "halt"}]},
        {"symbol": "000040", "date": "2024-02-24", "notices": [{"receipt": "test", "phase": "reopening"}]},
        {"symbol": "000075", "date": "2024-07-01", "notices": [{"receipt": "other", "phase": "halt"}]},
    ]
    daily = {("000040", "2024-02-23"): {"haltFlag": "N"}}
    sources = [{"symbol": "000040", "from": "2024-02-23", "through": "2024-02-24"}]
    unavailable = [{"symbol": "000075", "from": "2024-07-01", "through": "2025-07-02",
                    "reason": "STOCK_FINDER_NO_RESULT"}]

    returned, missing = daily_query_outcomes(planned, daily, sources, unavailable)

    assert returned == [planned[0] | {"evidence": {"haltFlag": "N"}}]
    assert missing == [
        planned[1] | {"unavailableReason": "DATE_NOT_RETURNED_IN_KRX_CSV"},
        planned[2] | {"unavailableReason": "STOCK_FINDER_NO_RESULT"},
    ]
