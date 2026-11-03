"""Synthetic case studies exercise membership boundaries and audited source links."""
import copy
import io
import json

import pytest
from pydantic import ValidationError

from app.replay.dataset import canonical, digest
from app.replay.kind_cases import (Case, CaseScope, LAYOUTS, as_of, audit_report, audit_source,
                                   build_report, capture_source, case_fact, main)
from app.replay.models import ResearchError
from app.replay.session_evidence import LIMIT

CAPTURED = "2026-11-03T12:00:00Z"


def case(kind):
    number = {"IPO": "000002", "DELISTING": "000003"}.get(kind, "000001")
    return Case.model_validate({"caseId": "test-" + kind.lower(), "stockCode": number,
                               "issuerName": "가상회사" + number, "market": "KOSDAQ", "kind": kind,
                               "url": "https://kind.krx.co.kr/external/2024/01/01/000001/20240101000001/" + LAYOUTS[kind][0] + ".htm"})


def body(kind):
    item = case(kind)
    common = [["1.회사명", item.issuerName], ["보통주", "A" + item.stockCode]]
    rows = {
        "IPO": [["1.회사명", "정식명", "한글", item.issuerName], ["보통주", "KR7000002000", "A000002", "100"],
                ["10.상장일(매매개시일)", "2024년 01월 03일"]],
        "DELISTING": [["1.회사명", item.issuerName], ["보통주", "A000003", "100", "2020-01-02"], ["7.상장폐지일", "2024-01-05"]],
        "SPLIT": [*common, ["3.변경상장사유", "액면분할"], ["4.액면변경내역", "변경전액면가(원)", "500", "변경후액면가(원)", "100"],
                  ["6.상장일", "2024-01-04"]],
        "SUSPENSION": [["1.대상종목", item.issuerName, "보통주"], ["3.정지기간", "가.정지일시", "2024-01-02", "-"],
                       ["나.만료일시", "신주권 변경상장일 전일까지"], ["4.근거규정", "코스닥시장 테스트 규정"]],
        "RESUMPTION": [["1.대상종목", item.issuerName, "보통주"], ["3.해제일시", "2024-01-04", "-"], ["4.근거규정", "코스닥시장 테스트 규정"]],
    }[kind]
    table = "<table>" + "".join("<tr>" + "".join("<td>" + v + "</td>" for v in row) + "</tr>" for row in rows) + "</table>"
    return ('<html><head><style>2020-01-01</style></head><body><a name="#2">' + LAYOUTS[kind][1] + "</a>" + table + "</body></html>").encode()


class Opener:
    def __init__(self, value, fail=False):
        self.value, self.fail, self.calls = value, fail, []

    def open(self, req, timeout):
        self.calls.append(req)
        if self.fail:
            raise OSError("private transport detail")
        return io.BytesIO(self.value)


def setup_cases(tmp_path):
    scope = CaseScope.model_validate({"schemaVersion": "SAGOPALGO_KIND_CASE_SCOPE_V1", "startDate": "2024-01-01",
                                      "endDate": "2024-01-10", "purpose": "PERSONAL_LOCAL_REFERENCE_RESEARCH",
                                      "cases": [case(kind).model_dump() for kind in LAYOUTS]})
    cache = tmp_path / "cache"
    for item in scope.cases:
        _, folder, _ = capture_source(item.url, cache, Opener(body(item.kind)))
        receipt = json.loads((folder / "receipt.json").read_bytes())
        receipt.update(startedAt=CAPTURED, capturedAt=CAPTURED)
        (folder / "receipt.json").write_bytes(canonical(receipt))
    return scope, cache


@pytest.mark.parametrize("kind", list(LAYOUTS))
def test_reviewed_forms_preserve_dates_identity_and_current_knowledge(kind):
    fact = case_fact(body(kind), case(kind), CAPTURED)
    assert fact["kind"] == kind and fact["knownAt"] == CAPTURED and fact["precision"] == "DATE_ONLY"
    assert fact["knowledgeBasis"] == "FETCH_TIME_ONLY" and fact["sourceSha256"] == digest(body(kind))
    if kind == "SPLIT":
        assert fact["details"]["ratio"] == "5" and fact["dateBasis"] == "CHANGED_LISTING_DATE_NOT_LEGAL_EFFECTIVE_DATE"
    if kind in {"SUSPENSION", "RESUMPTION"}:
        assert fact["identityBasis"] == "REVIEWED_ISSUER_MAPPING"


def test_complete_selected_cases_never_assert_complete_market_or_training(tmp_path):
    scope, cache = setup_cases(tmp_path)
    report = build_report(scope, cache)
    assert report["verifiedCaseCount"] == report["targetCaseCount"] == 5
    assert report["verifiedCompanyCount"] == 3 and report["caseStudyComplete"]
    assert report["verifiedMarkets"] == ["KOSDAQ"]
    assert not any(report[key] for key in ["marketUniverseComplete", "corporateActionsComplete", "calendarComplete",
                                          "usableForTraining", "usableForTrading", "priceAdjustmentApplied"])
    pack = report["referencePack"]
    assert len(pack["listings"]) == 2 and len(pack["actions"]) == 3
    assert not pack["calendar"] and not pack["sessions"] and not pack["coverage"]


def test_cutoff_and_effective_date_both_gate_membership_and_stop_restart(tmp_path):
    scope, cache = setup_cases(tmp_path)
    report = build_report(scope, cache)
    for stock in ["000001", "000002", "000003"]:
        old = as_of(report, stock, "2024-01-10T18:00:00Z", "2024-01-05")
        assert old["membership"] is None and not old["actions"] and not old["visibleFacts"]
    assert as_of(report, "000002", CAPTURED, "2024-01-02")["membership"] is None
    assert as_of(report, "000002", CAPTURED, "2024-01-03")["membership"]["eligible"] is True
    assert as_of(report, "000003", CAPTURED, "2024-01-04")["membership"] is None
    assert as_of(report, "000003", CAPTURED, "2024-01-05")["membership"]["eligible"] is False
    assert as_of(report, "000001", CAPTURED, "2024-01-01")["lastAnnouncedRestriction"] is None
    assert as_of(report, "000001", CAPTURED, "2024-01-02")["lastAnnouncedRestriction"]["kind"] == "SUSPENSION"
    result = as_of(report, "000001", CAPTURED, "2024-01-04")
    assert result["lastAnnouncedRestriction"]["kind"] == "RESUMPTION"
    assert not result["actualTradabilityConfirmed"] and not result["priceAdjustmentApplied"]
    # A source captured after the cutoff cannot release a restriction early.
    later = copy.deepcopy(report)
    later["facts"][-1]["knownAt"] = "2026-11-04T00:00:00Z"
    assert as_of(later, "000001", CAPTURED, "2024-01-04")["lastAnnouncedRestriction"]["kind"] == "SUSPENSION"


@pytest.mark.parametrize("change", ["issuer", "code", "class", "duplicate-date", "title", "nested-table", "invalid-date", "doctype", "ratio", "reason", "ambiguous-date", "correction", "number-format"])
def test_ambiguous_or_changed_forms_cannot_become_reference_events(change):
    text = body("SPLIT").decode()
    text = {
        "issuer": text.replace("가상회사000001", "다른회사"),
        "code": text.replace("A000001", "A999999"),
        "class": text.replace("보통주", "우선주"),
        "duplicate-date": text.replace("</table>", "<tr><td>6.상장일</td><td>2024-01-05</td></tr></table>"),
        "title": text.replace("변경상장(액면변경)", "회사분할결정"),
        "nested-table": text.replace("500</td>", "<table><tr><td>500</td></tr></table></td>"),
        "invalid-date": text.replace("2024-01-04", "2024-02-31"),
        "doctype": "<!DOCTYPE html SYSTEM 'https://invalid.example/private'>" + text,
        "ratio": text.replace("500</td>", "50</td>"),
        "reason": text.replace("액면분할</td>", "액면병합</td>"),
        "ambiguous-date": text.replace("2024-01-04</td>", "2024-01-04</td><td>2024-01-05</td>"),
        "correction": text.replace("<body>", "<body><p>정 정 신 고</p>"),
        "number-format": text.replace("500</td>", "5,0,0</td>"),
    }[change]
    with pytest.raises((ResearchError, ValueError)):
        case_fact(text.encode(), case("SPLIT"), CAPTURED)


def test_time_of_day_is_not_silently_dropped():
    text = body("SUSPENSION").decode().replace("2024-01-02</td><td>-", "2024-01-02</td><td>14:00:00")
    with pytest.raises(ResearchError, match="INTRADAY"):
        case_fact(text.encode(), case("SUSPENSION"), CAPTURED)


def test_unverified_symbol_mapping_and_scope_dates_fail(tmp_path):
    scope, cache = setup_cases(tmp_path)
    data = scope.model_dump()
    data["cases"] = [case("SUSPENSION").model_dump()]
    with pytest.raises(ResearchError, match="CODE_ANCHOR_MISSING"):
        build_report(CaseScope.model_validate(data), cache)
    data = scope.model_dump()
    data["endDate"] = "2024-01-02"
    with pytest.raises(ResearchError, match="OUTSIDE_SCOPE"):
        build_report(CaseScope.model_validate(data), cache)
    data = scope.model_dump()
    data["cases"].append(data["cases"][0])
    with pytest.raises(ValidationError):
        CaseScope.model_validate(data)


def test_absent_sources_remain_missing_without_inferred_market_coverage(tmp_path):
    scope, _ = setup_cases(tmp_path)
    report = build_report(scope, tmp_path / "empty")
    assert report["verifiedCaseCount"] == 0 and len(report["missingCaseIds"]) == 5
    assert not report["caseStudyComplete"] and report["referencePack"] is None


def test_capture_and_cache_reuse_audit_without_second_request(tmp_path):
    opener = Opener(body("IPO"))
    receipt, folder, cached = capture_source(case("IPO").url, tmp_path, opener)
    assert not cached and receipt["maxGetRequests"] == 1
    assert opener.calls[0].method == "GET" and not opener.calls[0].has_header("Authorization")
    assert capture_source(case("IPO").url, tmp_path, opener)[2]
    assert len(opener.calls) == 1
    (folder / "body.html").write_bytes(b"tampered")
    with pytest.raises(ResearchError, match="CACHE_TAMPERED"):
        capture_source(case("IPO").url, tmp_path, opener)
    assert len(opener.calls) == 1


@pytest.mark.parametrize("value,fail,code", [(b"", True, "CAPTURE_FAILED"), (b"x" * (LIMIT + 1), False, "RESPONSE_LIMIT")],
                         ids=["transport-failure", "oversized-response"])
def test_failed_capture_reserves_budget_and_redacts_error(tmp_path, value, fail, code):
    opener = Opener(value, fail)
    with pytest.raises(ResearchError, match=code):
        capture_source(case("IPO").url, tmp_path, opener)
    with pytest.raises(ResearchError, match="CAPTURE_RESERVED"):
        capture_source(case("IPO").url, tmp_path, opener)
    assert len(opener.calls) == 1


def test_untrusted_urls_fail_before_files_or_network(tmp_path):
    opener = Opener(b"")
    with pytest.raises(ResearchError, match="URL_INVALID"):
        capture_source("https://kind.krx.co.kr.invalid.example/private", tmp_path / "cache", opener)
    assert not opener.calls and not (tmp_path / "cache").exists()


def test_scope_and_cached_report_changes_are_detected(tmp_path):
    scope, cache = setup_cases(tmp_path)
    path = tmp_path / "report.json"
    report = build_report(scope, cache)
    path.write_bytes(canonical(report))
    assert audit_report(scope, cache, path) == report
    report["marketUniverseComplete"] = True
    path.write_bytes(canonical(report))
    with pytest.raises(ResearchError, match="REPORT_TAMPERED"):
        audit_report(scope, cache, path)


@pytest.mark.parametrize("field,value", [("url", "https://invalid.example"), ("knowledgeBasis", "PUBLICATION_ASSUMED"),
                                        ("maxGetRequests", True), ("capturedAt", "2024-01-01T00:00:00Z")])
def test_receipt_metadata_cannot_change_identity_budget_or_knowledge(tmp_path, field, value):
    item = case("IPO")
    _, folder, _ = capture_source(item.url, tmp_path, Opener(body("IPO")))
    receipt = json.loads((folder / "receipt.json").read_bytes())
    receipt[field] = value
    (folder / "receipt.json").write_bytes(canonical(receipt))
    with pytest.raises(ResearchError, match="CACHE_TAMPERED"):
        audit_source(folder, item.url)


def test_cli_build_audit_asof_are_offline_and_budget_preflight_is_before_network(tmp_path, monkeypatch, capsys):
    scope, cache = setup_cases(tmp_path)
    scope_path = tmp_path / "scope.json"
    scope_path.write_bytes(canonical(scope.model_dump()))
    monkeypatch.setattr("app.replay.kind_cases.request.build_opener", lambda *_: pytest.fail("network forbidden"))
    args = ["--scope", str(scope_path), "--cache", str(cache)]
    path = tmp_path / "output" / "report.json"
    for cmd in ["build", "audit", "build"]:
        assert main([cmd, *args, "--report", str(path)]) == 0
        assert json.loads(capsys.readouterr().out)["verifiedCaseCount"] == 5
    assert main(["as-of", *args, "--report", str(path), "--stock", "000003", "--at", CAPTURED, "--date", "2024-01-05"]) == 0
    assert json.loads(capsys.readouterr().out)["membership"]["eligible"] is False
    assert main(["capture", *args, "--max-new-requests", "0"]) == 0
    assert json.loads(capsys.readouterr().out)["reusedSources"] == 5
    assert main(["capture", "--scope", str(scope_path), "--cache", str(tmp_path / "empty"), "--max-new-requests", "4"]) == 2
    assert json.loads(capsys.readouterr().out)["diagnostic"] == "KIND_CASE_REQUEST_BUDGET_EXCEEDED"
    assert not (tmp_path / "empty").exists()
