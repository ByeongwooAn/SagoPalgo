from app.replay.historical_market_action_monthly import compare_versions, review_body


def test_historical_name_mismatch_keeps_published_fields_without_resolving_code():
    notice = {"market": "KOSDAQ", "role": "HALT", "membership": {"candidates": []}}
    body = ("주권매매거래정지 1.대상종목 (주)옛이름 보통주 2.정지사유 감자 "
            "3.정지기간 가.정지일시 2024-01-29 - 나.만료일시 변경상장일 전일까지 4.근거규정 예시")

    result = review_body(notice, ("새이름", "123450"), "70797.htm", body)

    assert result["status"] == "BODY_TARGET_IDENTITY_UNCONFIRMED"
    assert (result["publishedIssuer"], result["shareClass"], result["appliedDate"]) == (
        "(주)옛이름", "COMMON", "2024-01-29")
    assert result["viewerSymbol"] == "123450"
    assert "symbol" not in result
    assert result["noticeTimeKst"] is None


def test_revision_compares_application_field_without_using_correction_table_as_body():
    notice = {"market": "KOSDAQ", "role": "HALT", "membership": {"candidates": []}}
    original = ("주권매매거래정지 1.대상종목 예시 보통주 2.정지사유 감자 "
                "3.정지기간 가.정지일시 2024-01-29 - 나.만료일시 변경상장일 전일까지 4.근거규정 예시")
    corrected = "정정 전후 정지일시 2024-01-29 - " + original.replace("2024-01-29", "2024-01-30")
    versions = [
        {"document": "original", "correctionMarked": False, "contentSha256": "x",
         "review": review_body(notice, ("예시", "123450"), "70797.htm", original)},
        {"document": "corrected", "correctionMarked": True, "contentSha256": "y",
         "review": review_body(notice, ("예시", "123450"), "70797.htm", corrected)},
    ]

    assert compare_versions(versions)["verifiedFieldChanges"] == {
        "appliedDate": {"before": "2024-01-29", "after": "2024-01-30"}}
    assert compare_versions(versions[1:])["status"] == "CORRECTION_ORIGINAL_UNAVAILABLE"


def test_kospi_halt_time_does_not_prove_common_share_coverage():
    notice = {"market": "KOSPI", "role": "HALT_BOUNDARY_REVIEW", "membership": {"candidates": []}}
    body = ("1.종목명 예시 주권 2.매매거래정지일 2024년01월26일 15:47 부터 "
            "3.매매거래정지해제일 상장폐지 사유 해소시")

    result = review_body(notice, ("예시", "123450"), "68054.htm", body)

    assert result["status"] == "HALT_TIMES_SHARE_CLASS_UNCONFIRMED"
    assert result["haltTimeKst"] == "2024-01-26T15:47:00+09:00"
    assert "shareClass" not in result


def test_kospi_market_dividend_list_does_not_assign_share_class_from_name():
    notice = {"market": "KOSPI", "role": "DIVIDEND_OR_COMBINED", "membership": {"candidates": []}}
    body = ("1. 결산법인의 배당락 종목(1개사 2종목) - 예시, 예시우 "
            "2. 기준가격 : 배당부 종가 3. 적용일 : 2024.3.28(목) 4. 근거규정 : 예시")

    result = review_body(notice, None, "99342.htm", body)

    assert result["status"] == "MARKET_DIVIDEND_LIST_VERIFIED"
    assert result["appliedDate"] == "2024-03-28"
    assert result["publishedTargets"] == ["예시", "예시우"]
    assert "shareClass" not in result
