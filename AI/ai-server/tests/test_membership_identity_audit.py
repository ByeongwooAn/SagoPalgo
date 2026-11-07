"""Check that issuer, issue, exchange, and publication evidence stay separate."""
from zipfile import ZipFile

import pytest

from app.replay import membership_identity_audit as audit
from app.replay.dataset import canonical, digest
from app.replay.models import ResearchError


EARLY = "2026-11-04T00:00:00Z"
LATER = "2026-11-07T00:00:00Z"


def notices():
    return {
        "half-year-report": "주식회사 컴투스엔은 주식회사 위지윅스튜디오와의 합병계약을 승인하였으며, "
                            "2026년 7월 15일부로 합병(합병효력발생일)을 완료하였습니다. "
                            "합병등기일인 2026년 7월 15일에 반영되었습니다.",
        "delisting": "상장폐지 (주)위지윅스튜디오 보통주 A299900 피흡수합병 7.상장폐지일 2026-08-14 "
                     "(주)컴투스엔으로 흡수되며 별도의 정리매매는 없으며 합병신주로 상장됨",
        "new-shares": "(주)엔피 보통주 A291230 타법인흡수합병 5.상장일 2026-08-14",
        "rename": "(주)엔피 상호변경 (주)컴투스엔 4.상장일 2026-08-14",
        "issuance-report": "합병기일 2026-07-14 합병종료보고",
    }


def test_issuer_reported_effective_date_is_separate_from_exchange_delisting():
    result = audit.case_facts(notices())
    assert result["disclosedMergerReferenceDate"] == "2026-07-14"
    assert result["issuerReportedMergerEffectiveDate"] == "2026-07-15"
    assert result["exchangeAnnouncedDelistingDate"] == "2026-08-14"
    assert result["successorNewSharesListingDate"] == result["successorExchangeRenameDate"] == "2026-08-14"


def test_a_planned_registration_date_alone_does_not_confirm_merger_effect():
    texts = notices()
    texts["half-year-report"] = "주식회사 컴투스엔과 주식회사 위지윅스튜디오의 합병등기 신청일(예정) 2026-07-15"
    with pytest.raises(ResearchError, match="MEMBERSHIP_CASE_FILING_FACTS"):
        audit.case_facts(texts)


def test_different_dates_in_related_exchange_notices_are_rejected():
    texts = notices()
    texts["new-shares"] = texts["new-shares"].replace("2026-08-14", "2026-08-18")
    with pytest.raises(ResearchError, match="MEMBERSHIP_CASE_DATE_CONFLICT"):
        audit.case_facts(texts)


def test_equal_trading_totals_do_not_hide_replaced_codes():
    proof = {"knownAt": LATER}
    basic = [{"symbol": "299900", "classification": "COMMON_SHARE"},
             {"symbol": "291230", "classification": "COMMON_SHARE"}]
    trades = [{"symbol": "299900", "volume": "0"}, {"symbol": "290000", "volume": "100"}]
    result = audit.trade_comparison(basic, trades, proof)
    assert result["tradingIssueRows"] == len(basic) == 2
    assert result["status"] == "CONFLICT"
    assert result["targetVolume"] == {"299900": 0, "291230": None}
    assert result["basicOnlySymbols"] == ["291230"] and result["tradingOnlySymbols"] == ["290000"]


def test_observed_spans_preserve_gaps_and_market_moves_for_the_same_issue():
    row = {"symbol": "1234A0", "market": "KOSDAQ", "name": "First"}
    spans = []
    audit.observed_span(spans, row, "2026-01-01", EARLY)
    audit.observed_span(spans, row, "2026-01-02", LATER)
    audit.observed_span(spans, row, "2026-01-04", EARLY)
    audit.observed_span(spans, {**row, "market": "KOSPI"}, "2026-01-05", LATER)
    assert [(s["market"], s["firstObserved"], s["lastObserved"]) for s in spans] == [
        ("KOSDAQ", "2026-01-01", "2026-01-02"), ("KOSDAQ", "2026-01-04", "2026-01-04"),
        ("KOSPI", "2026-01-05", "2026-01-05"),
    ]
    assert spans[0]["knownAt"] == LATER


def test_issuer_name_link_requires_full_code_and_observed_market():
    issue = {"symbol": "0126Z0", "market": "KOSPI", "isin": "KR70126Z0005"}
    observation = {"isin": issue["isin"], "before": None, "after": issue}
    fact = {"issuerName": "Issuer", "stockCode": issue["symbol"], "market": "KOSPI",
            "historyIsin": issue["isin"], "knownAt": EARLY, "sourceUrl": audit.KIND + "/external/source"}
    evidence = [fact, {**fact, "stockCode": "0126Z"}, {**fact, "market": "KOSDAQ"},
                {**fact, "sourceIsin": "KR7000000000"}]
    links = audit.issuer_edges([{"observationId": "one", "observation": observation, "evidence": evidence}])
    edge, = links[issue["isin"]].values()
    assert edge["symbol"] == issue["symbol"] and edge["sourceIsin"] is None
    assert "legalIssuerId" not in edge


def test_current_dart_snapshot_requires_an_exact_single_code_and_name():
    issue = {"symbol": "0126Z0", "name": "표본보통주"}
    issuer = {"dartCorpCode": "00123456", "issuerName": "주식회사 표본"}
    assert audit.endpoint_issuer_check(issue, {"0126Z0": [issuer]}) == {"status": "MATCH", **issuer}
    assert audit.endpoint_issuer_check(issue, {"0126Z0": [issuer, issuer]}) == {"status": "AMBIGUOUS_CODE"}
    assert audit.endpoint_issuer_check({**issue, "name": "다른회사"}, {"0126Z0": [issuer]}) == {"status": "NAME_MISMATCH"}
    assert audit.endpoint_issuer_check(issue, {"0126Z": [issuer]}) == {"status": "NOT_FOUND"}


def test_dart_snapshot_does_not_assign_blank_stock_codes(tmp_path):
    raw_path = tmp_path / "body.zip"
    with ZipFile(raw_path, "w") as archive:
        archive.writestr("CORPCODE.xml", "<result><list><stock_code>0126Z0</stock_code><corp_code>00123456</corp_code>"
                        "<corp_name>표본</corp_name></list><list><stock_code> </stock_code><corp_code>00123457</corp_code>"
                        "<corp_name>비상장</corp_name></list></result>")
    receipt = canonical({"schemaVersion": "SAGOPALGO_H01_DART_REGISTRY_CAPTURE_V1", "url": audit.DART_REGISTRY,
                         "startedAt": EARLY, "capturedAt": LATER, "status": "COMPLETE", "sha256": digest(raw_path.read_bytes())})
    (tmp_path / "receipt.json").write_bytes(receipt)
    listed, proof = audit.dart_registry(tmp_path, digest(receipt))
    assert list(listed) == ["0126Z0"]
    assert proof["knownAt"] == LATER


def write_kosis(folder, periods=("202311", "202402")):
    table = audit.TABLES["KOSPI"]
    html = ("<table><tr><th>주식지표별</th><th>2024.02</th><th>2023.11</th></tr>"
            "<tr><td>회사수 (개)</td><td>801</td><td>800</td></tr>"
            "<tr><td>종목수 (개)</td><td>1,102</td><td>1,101</td></tr></table>")
    body = canonical({"ParamInfo": {"orgId": "343", "tblId": table}, "result": [html]})
    (folder / "body.json").write_bytes(body)
    receipt = canonical({"orgId": "343", "market": "KOSPI", "tableId": table, "startedAt": EARLY, "capturedAt": LATER,
                         "periods": list(periods), "queryUrl": audit.KOSIS + "/statHtml/html.do",
                         "sourceUrl": audit.KOSIS + f"/statHtml/statHtml.do?orgId=343&tblId={table}", "sha256": digest(body)})
    (folder / "receipt.json").write_bytes(receipt)
    return digest(receipt)


def test_publication_retains_company_total_and_uses_only_the_exact_month_end(tmp_path):
    result = audit.kosis_months(tmp_path, "KOSPI", write_kosis(tmp_path))
    assert set(result) == {"2023-11-30", "2024-02-29"}
    assert result["2024-02-29"]["publishedCompanies"] == 801
    assert result["2024-02-29"]["publishedIssues"] == 1102


def test_publication_wrong_period_and_tampered_raw_are_rejected(tmp_path):
    expected = write_kosis(tmp_path, periods=("202311", "202403"))
    with pytest.raises(ResearchError, match="MEMBERSHIP_KOSIS_PERIOD"):
        audit.kosis_months(tmp_path, "KOSPI", expected)
    (tmp_path / "body.json").write_bytes(b"{}")
    with pytest.raises(ResearchError, match="MEMBERSHIP_IDENTITY_INPUT_HASH"):
        audit.kosis_months(tmp_path, "KOSPI", expected)
