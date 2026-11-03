import copy
import json

import pytest

from app.replay.dataset import canonical, digest
from app.replay.kind_registry import (HEADERS, LIMIT, URLS, audit_capture, build_registry, build_seed,
                                      capture_registry, immutable_report, lookup, main, registry_rows)
from app.replay.models import ResearchError
from test_kind_cases import CAPTURED, Opener, setup_cases
from test_universe_events import setup_events
from app.replay import kind_cases, universe_events


def body(market, symbol=None):
    symbol = symbol or {"KOSPI": "000001", "KOSDAQ": "0000A0"}[market]
    cells = ["가상현재회사", {"KOSPI": "유가", "KOSDAQ": "코스닥"}[market], symbol,
             "테스트 업종", "테스트 제품", "1956-03-03", "12월", "가상대표", "", "가상지역"]
    html = ('<html><head><meta http-equiv="Content-Type" content="text/html; charset=euc-kr" />'
            '<title>상장법인목록(EXCEL)</title></head><body><table><tr>'
            + "".join("<th>" + value + "</th>" for value in HEADERS) + "</tr><tr>"
            + "".join("<td>" + value + "</td>" for value in cells) + "</tr></table></body></html>")
    return html.encode("cp949")


def setup_registry(tmp_path):
    cache = tmp_path / "registry"
    for market in URLS:
        _, folder, _ = capture_registry(market, cache, Opener(body(market)))
        receipt = json.loads((folder / "receipt.json").read_bytes())
        receipt.update(startedAt=CAPTURED, capturedAt=CAPTURED)
        (folder / "receipt.json").write_bytes(canonical(receipt))
    return cache


def test_current_rows_keep_early_dates_and_alphanumeric_codes_without_past_membership(tmp_path):
    cache = setup_registry(tmp_path)
    report = build_registry(cache)
    assert report["issuerCount"] == 2 and report["countsByMarket"] == {"KOSPI": 1, "KOSDAQ": 1}
    assert report["nonNumericSymbolCount"] == 1
    assert [v["symbol"] for v in report["rows"]] == ["000001", "0000A0"]
    assert all(v["reportedListingDate"] == "1956-03-03" and v["knownAt"] == CAPTURED for v in report["rows"])
    assert all(not v["commonShareConfirmed"] for v in report["rows"])
    assert not any(report[key] for key in ["snapshotAtomic", "independentTotalVerified", "historicalMembershipGenerated",
                                          "marketUniverseComplete", "usableForTraining", "usableForTrading"])
    assert report["providerAsOf"] is None


@pytest.mark.parametrize("change", ["market", "symbol", "date", "header", "encoding", "duplicate", "nested", "empty", "declaration"])
def test_unreviewed_invalid_or_duplicate_registry_data_fails_closed(change):
    value = body("KOSPI").decode("cp949")
    value = {
        "market": value.replace("<td>유가</td>", "<td>코스닥</td>"),
        "symbol": value.replace("000001", "000a01"),
        "date": value.replace("1956-03-03", "1956-02-31"),
        "header": value.replace("<th>상장일</th>", "<th>확인일</th>"),
        "encoding": value.replace("charset=euc-kr", "charset=utf-8"),
        "duplicate": value.replace("</table>", "<tr>" + value.split("<tr>")[2].split("</tr>")[0] + "</tr></table>"),
        "nested": value.replace("테스트 제품", "<table><tr><td>제품</td></tr></table>"),
        "empty": value.split("</tr>")[0] + "</tr></table></body></html>",
        "declaration": '<!DOCTYPE html SYSTEM "https://invalid.example">' + value,
    }[change]
    with pytest.raises((ResearchError, ValueError)):
        registry_rows(value.encode("cp949"), "KOSPI", CAPTURED)


def test_same_symbol_in_two_markets_is_not_silently_merged(tmp_path):
    cache = tmp_path / "registry"
    for market in URLS:
        capture_registry(market, cache, Opener(body(market, "000001")))
    with pytest.raises(ResearchError, match="CROSS_MARKET_DUPLICATE"):
        build_registry(cache)


def test_seed_preserves_missing_historical_issuers_and_provenance_without_listing_events(tmp_path):
    registry = build_registry(setup_registry(tmp_path))
    case_scope, cache = setup_cases(tmp_path)
    event_scope, _ = setup_events(tmp_path)
    cases = kind_cases.build_report(case_scope, cache)
    events = universe_events.build_report(event_scope, cache)
    seed = build_seed(registry, cases, events)
    assert seed["identityCount"] == 5 and seed["historicalOnlyIdentityCount"] == 3
    assert seed["currentIssuerCount"] == 2 and seed["nonNumericSymbolCount"] == 1
    assert seed["membershipEventsGeneratedFromCurrentSnapshot"] == 0
    assert not seed["historicalMembershipComplete"] and not seed["marketUniverseComplete"]
    assert all(observation["sourceHashes"] for identity in seed["identities"] for observation in identity["observations"])
    transfer = [v for v in lookup(seed, "000003", CAPTURED)["observations"] if v["caseId"] == "test-transfer"]
    assert len(transfer) == 1 and len(transfer[0]["sourceHashes"]) == 2
    assert not lookup(seed, "0000A0", "2024-01-05T08:00:00Z")["observations"]
    assert len(lookup(seed, "0000A0", CAPTURED)["observations"]) == 1
    assert lookup(seed, "000004", CAPTURED)["observations"][0]["caseId"] == "test-merger"
    changed = copy.deepcopy(events)
    changed["startDate"] = "2024-01-02"
    with pytest.raises(ResearchError, match="SCOPE_MISMATCH"):
        build_seed(registry, cases, changed)


def test_capture_only_uses_official_url_and_audits_before_reuse(tmp_path):
    opener = Opener(body("KOSPI"))
    receipt, folder, reused = capture_registry("KOSPI", tmp_path, opener)
    assert not reused and receipt["maxGetRequests"] == 1
    assert opener.calls[0].full_url == URLS["KOSPI"] and not opener.calls[0].has_header("Authorization")
    assert capture_registry("KOSPI", tmp_path, opener)[2] and len(opener.calls) == 1
    (folder / "body.html").write_bytes(b"tampered")
    with pytest.raises(ResearchError, match="CACHE_TAMPERED"):
        audit_capture(folder, "KOSPI")
    with pytest.raises(ResearchError, match="MARKET_INVALID"):
        capture_registry("UNKNOWN", tmp_path, opener)
    assert len(opener.calls) == 1


@pytest.mark.parametrize("raw,fail,code", [(b"", True, "CAPTURE_FAILED"), (b"x" * (LIMIT + 1), False, "RESPONSE_LIMIT")],
                         ids=["transport-failure", "oversized-response"])
def test_failed_capture_keeps_reservation_and_no_automatic_retry(tmp_path, raw, fail, code):
    opener = Opener(raw, fail)
    with pytest.raises(ResearchError, match=code):
        capture_registry("KOSPI", tmp_path, opener)
    with pytest.raises(ResearchError, match="CAPTURE_RESERVED"):
        capture_registry("KOSPI", tmp_path, opener)
    assert len(opener.calls) == 1


@pytest.mark.parametrize("field,value", [("market", "KOSDAQ"), ("url", "https://invalid.example"),
                                        ("maxGetRequests", True), ("capturedAt", "2001-01-01T00:00:00Z")])
def test_receipt_identity_budget_and_capture_order_are_verified(tmp_path, field, value):
    _, folder, _ = capture_registry("KOSPI", tmp_path, Opener(body("KOSPI")))
    receipt = json.loads((folder / "receipt.json").read_bytes())
    receipt[field] = value
    (folder / "receipt.json").write_bytes(canonical(receipt))
    with pytest.raises(ResearchError, match="CACHE_TAMPERED"):
        audit_capture(folder, "KOSPI")


def test_cli_snapshot_and_seed_recompute_offline_and_detect_tampering(tmp_path, monkeypatch, capsys):
    cache = setup_registry(tmp_path)
    case_scope, case_cache = setup_cases(tmp_path)
    event_scope, _ = setup_events(tmp_path)
    paths = {}
    for label, scope, report in [("case", case_scope, kind_cases.build_report(case_scope, case_cache)),
                                 ("event", event_scope, universe_events.build_report(event_scope, case_cache))]:
        scope_path, report_path = tmp_path / (label + "-scope.json"), tmp_path / (label + "-report.json")
        scope_path.write_bytes(canonical(scope.model_dump()))
        report_path.write_bytes(canonical(report))
        paths[label] = (scope_path, report_path)
    monkeypatch.setattr("urllib.request.build_opener", lambda *_: pytest.fail("network forbidden"))
    assert main(["capture", "--cache", str(cache), "--max-new-requests", "0"]) == 0
    assert json.loads(capsys.readouterr().out)["reusedSources"] == 2
    snapshot = tmp_path / "output" / "snapshot.json"
    for command in ["build", "audit"]:
        assert main([command, "--cache", str(cache), "--report", str(snapshot)]) == 0
        assert json.loads(capsys.readouterr().out)["issuerCount"] == 2
    seed_path = tmp_path / "output" / "seed.json"
    args = ["--cache", str(cache), "--report", str(seed_path), "--case-cache", str(case_cache),
            "--case-scope", str(paths["case"][0]), "--case-report", str(paths["case"][1]),
            "--event-scope", str(paths["event"][0]), "--event-report", str(paths["event"][1])]
    for command in ["seed-build", "seed-audit"]:
        assert main([command, *args]) == 0
        assert json.loads(capsys.readouterr().out)["historicalOnlyIdentityCount"] == 3
    assert main(["seed-lookup", *args, "--symbol", "0000A0", "--at", "2024-01-05T08:00:00Z"]) == 0
    assert not json.loads(capsys.readouterr().out)["observations"]
    with pytest.raises(ResearchError, match="REPORT_TAMPERED"):
        immutable_report(seed_path, {"changed": True})
    assert main(["capture", "--cache", str(tmp_path / "empty"), "--max-new-requests", "1"]) == 2
    assert json.loads(capsys.readouterr().out)["diagnostic"] == "REGISTRY_REQUEST_BUDGET_EXCEEDED"
    assert not (tmp_path / "empty").exists()
