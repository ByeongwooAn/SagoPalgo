"""Synthetic paired evidence tests; actual issuer data stays outside Git."""
import copy
import json

import pytest
from pydantic import ValidationError

from app.replay.dataset import canonical, digest
from app.replay.kind_cases import capture_source
from app.replay.models import ResearchError
from app.replay.universe_events import (Scope, as_of, audit_report, build_report, main, merger_fact, transfer_fact)
from test_kind_cases import CAPTURED, Opener, body

ROOT_URL = "https://kind.krx.co.kr/external/2024/01/01/000001/"
EXIT_URL = ROOT_URL + "20240101000011/70769.htm"
ENTRY_URL = ROOT_URL + "20240101000012/99343.htm"
MERGER_URL = ROOT_URL + "20240101000013/70769.htm"
ENTRY = """<html><head><title>reviewed synthetic form</title></head><body>
<div class="xforms_title">주권 등 신규상장 기준가격 안내 (이전상장)</div>
<table id="XFormD1_Form0_RepeatTable1"><tr><td>1. 회사명</td><td>가상회사000003</td></tr>
<tr><td>보통주식</td><td>A000003</td><td>123</td></tr>
<tr><td>3. 사유</td><td>이전상장</td></tr>
<tr><td>4. 적용일</td><td>2024-01-05</td></tr>
<tr><td>5. 근거규정</td><td>유가증권시장업무규정 테스트</td></tr></table></body></html>""".encode()
EXIT = body("DELISTING").replace(b"</table>", "<tr><td>5.상장폐지사유</td><td>유가증권시장 상장</td></tr></table>".encode())
MERGER = body("DELISTING").replace(b"000003", b"000004").replace(b"</table>", "<tr><td>5.상장폐지사유</td><td>피흡수합병(스팩소멸합병)</td></tr><tr><td>9.기타</td><td>가상존속회사가 흡수합병합니다. 상장될 예정입니다.</td></tr></table>".encode())


def setup_events(tmp_path):
    scope = Scope.model_validate({"schemaVersion": "SAGOPALGO_UNIVERSE_EVENT_SCOPE_V1", "startDate": "2024-01-01", "endDate": "2024-01-10",
        "transfers": [{"caseId": "test-transfer", "stockCode": "000003", "sourceIssuerName": "가상회사000003",
                       "destinationIssuerName": "가상회사000003", "fromMarket": "KOSDAQ", "toMarket": "KOSPI", "exitUrl": EXIT_URL, "entryUrl": ENTRY_URL}],
        "mergerDelistings": [{"caseId": "test-merger", "stockCode": "000004", "issuerName": "가상회사000004",
                             "survivingIssuerName": "가상존속회사", "market": "KOSDAQ", "url": MERGER_URL}]})
    cache = tmp_path / "cache"
    for url, raw in [(EXIT_URL, EXIT), (ENTRY_URL, ENTRY), (MERGER_URL, MERGER)]:
        _, folder, _ = capture_source(url, cache, Opener(raw))
        receipt = json.loads((folder / "receipt.json").read_bytes())
        receipt.update(startedAt=CAPTURED, capturedAt=CAPTURED)
        (folder / "receipt.json").write_bytes(canonical(receipt))
    return scope, cache


def change_source(cache, url, transform):
    folder = cache / digest(url.encode())
    raw = transform((folder / "body.html").read_bytes())
    (folder / "body.html").write_bytes(raw)
    receipt = json.loads((folder / "receipt.json").read_bytes())
    receipt["bodySha256"] = digest(raw)
    (folder / "receipt.json").write_bytes(canonical(receipt))


def test_transfer_produces_two_markets_not_a_global_delisting(tmp_path):
    scope, cache = setup_events(tmp_path)
    report = build_report(scope, cache)
    assert report["verifiedCaseCount"] == 2 and len(report["venueEvents"]) == 3
    assert report["caseStudyComplete"] and not report["marketUniverseComplete"]
    fact = report["facts"][0]
    assert len(fact["sources"]) == 2 and fact["knownAt"] == CAPTURED
    before = as_of(report, "000003", CAPTURED, "2024-01-04")
    assert before["venueMembership"] == []
    after = as_of(report, "000003", CAPTURED, "2024-01-05")
    assert {v["market"]: v["eligible"] for v in after["venueMembership"]} == {"KOSDAQ": False, "KOSPI": True}
    assert "referencePack" not in report and "membership" not in after
    assert not after["allMarketsMembershipConfirmed"] and not after["actualTradabilityConfirmed"]


def test_transfer_is_not_visible_until_both_sources_are_observed(tmp_path):
    scope, cache = setup_events(tmp_path)
    folder = cache / digest(ENTRY_URL.encode())
    receipt = json.loads((folder / "receipt.json").read_bytes())
    receipt["capturedAt"] = "2026-11-04T00:00:00Z"
    (folder / "receipt.json").write_bytes(canonical(receipt))
    report = build_report(scope, cache)
    assert not as_of(report, "000003", CAPTURED, "2024-01-05")["venueMembership"]
    assert len(as_of(report, "000003", receipt["capturedAt"], "2024-01-05")["venueMembership"]) == 2


def test_merger_delisting_does_not_invent_ratio_legal_completion_or_survivor_listing(tmp_path):
    scope, cache = setup_events(tmp_path)
    report = build_report(scope, cache)
    fact = report["facts"][1]
    assert fact["kind"] == "MERGER_DELISTING" and fact["exchangeRatio"] is None
    assert not fact["legalMergerCompletionConfirmed"] and not fact["survivorListingConfirmed"]
    assert "NOT_LEGAL_MERGER_DATE" in fact["dateBasis"]
    assert not as_of(report, "000004", "2024-01-05T08:00:00Z", "2024-01-05")["venueMembership"]
    assert as_of(report, "000004", CAPTURED, "2024-01-04")["venueMembership"] == []
    values = as_of(report, "000004", CAPTURED, "2024-01-05")["venueMembership"]
    assert len(values) == 1 and values[0]["eligible"] is False


@pytest.mark.parametrize("old,new,diagnostic", [
    ("2024-01-05", "2024-01-06", "DATES_CONFLICT"), ("A000003", "A999999", "CODE_MISMATCH"),
    ("보통주식", "우선주식", "CODE_MISMATCH"), ("가상회사000003", "다른회사", "IDENTITY_MISMATCH"),
    ("이전상장</td>", "신규상장</td>", "IDENTITY_MISMATCH"),
    ("유가증권시장업무규정", "코스닥시장업무규정", "MARKET_MISMATCH"),
    ("</body>", "<p>정정신고</p></body>", "CORRECTION_UNSUPPORTED"),
    ("</table>", "<tr><td>4. 적용일</td><td>2024-01-05</td></tr></table>", "FIELD_AMBIGUOUS"),
])
def test_transfer_rejects_conflicting_dates_identities_classes_and_revisions(tmp_path, old, new, diagnostic):
    scope, cache = setup_events(tmp_path)
    change_source(cache, ENTRY_URL, lambda raw: raw.replace(old.encode(), new.encode()))
    with pytest.raises(ResearchError, match=diagnostic):
        transfer_fact(scope.transfers[0], cache)


@pytest.mark.parametrize("kind", ["transfer-reason", "merger-reason", "merger-survivor"])
def test_other_delisting_reasons_or_survivors_are_not_silently_reclassified(tmp_path, kind):
    scope, cache = setup_events(tmp_path)
    if kind == "transfer-reason":
        change_source(cache, EXIT_URL, lambda raw: raw.replace("유가증권시장 상장".encode(), "기타 사유".encode()))
    else:
        before, after = ("피흡수합병(스팩소멸합병)", "기타") if kind == "merger-reason" else ("가상존속회사", "다른존속회사")
        change_source(cache, MERGER_URL, lambda raw: raw.replace(before.encode(), after.encode()))
    with pytest.raises(ResearchError):
        build_report(scope, cache)


def test_missing_pair_is_reported_without_a_single_sided_transfer(tmp_path):
    scope, _ = setup_events(tmp_path)
    cache = tmp_path / "partial"
    capture_source(EXIT_URL, cache, Opener(EXIT))
    report = build_report(scope, cache)
    assert report["verifiedCaseCount"] == 0 and len(report["missingCaseIds"]) == 2
    assert not report["venueEvents"] and not report["caseStudyComplete"]


def test_invalid_scope_duplicate_sources_and_report_tampering_fail(tmp_path):
    scope, cache = setup_events(tmp_path)
    data = scope.model_dump()
    data["transfers"][0]["toMarket"] = "KOSDAQ"
    with pytest.raises(ValidationError):
        Scope.model_validate(data)
    data = scope.model_dump()
    data["mergerDelistings"][0]["url"] = EXIT_URL
    with pytest.raises(ValidationError):
        Scope.model_validate(data)
    path = tmp_path / "report.json"
    report = build_report(scope, cache)
    path.write_bytes(canonical(report))
    assert audit_report(scope, cache, path) == report
    changed = copy.deepcopy(report)
    changed["marketUniverseComplete"] = True
    path.write_bytes(canonical(changed))
    with pytest.raises(ResearchError, match="REPORT_TAMPERED"):
        audit_report(scope, cache, path)


def test_cli_offline_reuse_and_preflight_budget(tmp_path, monkeypatch, capsys):
    scope, cache = setup_events(tmp_path)
    scope_path = tmp_path / "scope.json"
    scope_path.write_bytes(canonical(scope.model_dump()))
    monkeypatch.setattr("urllib.request.build_opener", lambda *_: pytest.fail("no network"))
    args = ["--scope", str(scope_path), "--cache", str(cache)]
    path = tmp_path / "output" / "report.json"
    for command in ["build", "audit", "build"]:
        assert main([command, *args, "--report", str(path)]) == 0
        assert json.loads(capsys.readouterr().out)["verifiedCaseCount"] == 2
    assert main(["as-of", *args, "--report", str(path), "--stock", "000003", "--at", CAPTURED, "--date", "2024-01-05"]) == 0
    assert len(json.loads(capsys.readouterr().out)["venueMembership"]) == 2
    assert main(["capture", *args, "--max-new-requests", "0"]) == 0
    assert json.loads(capsys.readouterr().out)["reusedSources"] == 3
    assert main(["capture", "--scope", str(scope_path), "--cache", str(tmp_path / "empty"), "--max-new-requests", "2"]) == 2
    assert json.loads(capsys.readouterr().out)["diagnostic"] == "UNIVERSE_EVENT_REQUEST_BUDGET_EXCEEDED"
    assert not (tmp_path / "empty").exists()
