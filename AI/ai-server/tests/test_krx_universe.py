"""Synthetic snapshots validate access boundaries and detect current data posing as historical."""
import copy
import io
import json
from urllib import error

import pytest

from app.replay import kind_cases, universe_events
from app.replay.dataset import canonical
from app.replay.krx_universe import (BASE, ENDPOINTS, LIMIT, Transport, audit, collect, compare_evidence, load_environment,
                                     load_job, main, parse_snapshot, prepare, report)
from app.replay.models import ResearchError
from test_kind_cases import CAPTURED, setup_cases
from test_universe_events import setup_events

KEY = "synthetic-credential-for-test-only"


def row(market="KOSPI", symbol="000001", **fields):
    value = {"ISU_CD": "KR" + symbol + "0001", "ISU_SRT_CD": symbol, "ISU_NM": "가상종목", "ISU_ABBRV": "가상",
             "ISU_ENG_NM": "Synthetic issue", "LIST_DD": "19560303", "MKT_TP_NM": market, "SECUGRP_NM": "주권",
             "SECT_TP_NM": "-", "KIND_STKCERT_TP_NM": "보통주", "PARVAL": "100", "LIST_SHRS": "0"}
    value.update(fields)
    return value


def response(rows):
    return canonical({"OutBlock_1": rows})


class FakeTransport:
    source_kind = "SYNTHETIC"

    def __init__(self, values=None, fail=None):
        self.values = values or {"KOSPI": response([row()]), "KOSDAQ": response([row("KOSDAQ", "000003"), row("KOSDAQ", "000004")])}
        self.calls, self.fail = [], fail

    def ready(self):
        pass

    def fetch(self, market, basis):
        self.calls.append((market, basis))
        if market == self.fail:
            raise OSError("private response details")
        return self.values[market]


def job(tmp_path):
    folder = tmp_path / "job"
    prepare(folder, "2024-01-02", "SYNTHETIC")
    return folder


def test_schema_preserves_leading_zero_alpha_codes_zero_share_count_and_date_only_knowledge():
    rows = parse_snapshot(response([row(), row(symbol="0000A0", KIND_STKCERT_TP_NM="우선주")]), "KOSPI", "2023-11-01", CAPTURED, "OFFICIAL_SAMPLE")
    assert rows[0]["symbol"] == "000001" and rows[0]["reportedListingDate"] == "1956-03-03"
    assert rows[0]["classification"] == "COMMON_SHARE" and rows[0]["knownAt"] == CAPTURED
    assert rows[0]["dateBasis"] == "REQUEST_BAS_DD" and rows[0]["knowledgeBasis"] == "FETCH_TIME_ONLY"
    assert rows[1]["symbol"] == "0000A0" and not rows[1]["numericCodeSupported"]
    assert rows[1]["classification"] == "OTHER_SHARE_CLASS" and rows[1]["sourceKind"] == "OFFICIAL_SAMPLE"


@pytest.mark.parametrize("change", ["root", "empty", "duplicate", "isin", "symbol", "market", "future", "invalid-date", "numeric-value", "missing", "extra", "nan"])
def test_invalid_responses_and_future_listings_fail_closed(change):
    rows = [row()]
    if change == "duplicate":
        rows.append(row())
    elif change in {"isin", "symbol", "market", "future", "invalid-date", "numeric-value", "extra"}:
        key, value = {"isin": ("ISU_CD", "invalid"), "symbol": ("ISU_SRT_CD", "a00001"), "market": ("MKT_TP_NM", "KOSDAQ"),
                      "future": ("LIST_DD", "20240103"), "invalid-date": ("LIST_DD", "20230231"),
                      "numeric-value": ("LIST_SHRS", 1), "extra": ("NEW_FIELD", "drift")}[change]
        rows[0][key] = value
    elif change == "missing":
        del rows[0]["SECUGRP_NM"]
    raw = response(rows)
    if change == "root":
        raw = canonical({"error": "authentication failed"})
    elif change == "empty":
        raw = response([])
    elif change == "nan":
        raw = b'{"OutBlock_1":NaN}'
    with pytest.raises((ResearchError, ValueError)):
        parse_snapshot(raw, "KOSPI", "2024-01-02", CAPTURED, "SYNTHETIC")


def test_unknown_security_or_share_labels_remain_visible_as_classification_gaps():
    rows = parse_snapshot(response([row(SECUGRP_NM="unknown"), row(symbol="000002", KIND_STKCERT_TP_NM="unknown")]),
                          "KOSPI", "2023-11-01", CAPTURED, "SYNTHETIC")
    assert len(rows) == 2 and all(v["classification"] == "UNREVIEWED_CLASSIFICATION" for v in rows)


def test_two_market_collect_audits_and_reuses_without_more_requests(tmp_path):
    folder = job(tmp_path)
    client = FakeTransport()
    result = collect(folder, client)
    assert result["capturedMarkets"] == ["KOSPI", "KOSDAQ"] and result["sourceRecords"] == 3
    assert result["providerHistoricalRecords"] == 0 and result["attemptsUsed"] == result["maxRequests"] == 2
    assert not result["marketUniverseComplete"] and not result["usableForTraining"]
    assert collect(folder, client) == result and len(client.calls) == 2
    assert audit(folder) == result


@pytest.mark.parametrize("enabled,key,code", [(False, KEY, "DISABLED"), (True, None, "KEY_MISSING"), (True, "bad\nkey", "KEY_INVALID")])
def test_missing_or_disabled_access_does_not_reserve_requests_or_call_network(tmp_path, enabled, key, code):
    folder = tmp_path / "live"
    prepare(folder)
    before = (folder / "journal.json").read_bytes()
    with pytest.raises(ResearchError, match=code):
        collect(folder, Transport(key, enabled, Opener(b"")))
    assert before == (folder / "journal.json").read_bytes()
    assert not list((folder / "raw").iterdir())


def test_mismatched_source_mode_cannot_promote_samples_to_provider_data(tmp_path):
    folder = tmp_path / "live"
    prepare(folder)
    client = FakeTransport()
    with pytest.raises(ResearchError, match="SOURCE_KIND_MISMATCH"):
        collect(folder, client)
    assert not client.calls and report(folder)["providerHistoricalRecords"] == 0


def test_failed_request_stops_and_explicit_rerun_does_not_retry(tmp_path):
    folder = job(tmp_path)
    client = FakeTransport(fail="KOSDAQ")
    with pytest.raises(ResearchError, match="CAPTURE_FAILED"):
        collect(folder, client)
    assert report(folder)["status"] == "STOPPED" and report(folder)["countsByMarket"]["KOSPI"] == 1
    with pytest.raises(ResearchError, match="RECOVERY_REQUIRED"):
        collect(folder, client)
    assert len(client.calls) == 2
    assert "private response" not in (folder / "journal.json").read_text()


def test_schema_failure_preserves_received_original_and_detects_later_tampering(tmp_path):
    folder = job(tmp_path)
    client = FakeTransport(values={"KOSPI": response([row(LIST_DD="20250101")])})
    with pytest.raises(ResearchError, match="FUTURE_LISTING"):
        collect(folder, client)
    assert (folder / "raw" / "KOSPI.json").read_bytes() == client.values["KOSPI"]
    assert report(folder)["status"] == "STOPPED"
    (folder / "raw" / "KOSPI.json").write_bytes(b"changed")
    with pytest.raises(ResearchError, match="RAW_TAMPERED"):
        load_job(folder)


def test_cross_market_duplicates_fail_instead_of_silently_deduplicating(tmp_path):
    folder = job(tmp_path)
    client = FakeTransport(values={"KOSPI": response([row()]), "KOSDAQ": response([row("KOSDAQ")])})
    with pytest.raises(ResearchError, match="CROSS_MARKET_DUPLICATE"):
        collect(folder, client)


class Opener:
    def __init__(self, raw, http_status=None):
        self.raw, self.http_status, self.calls = raw, http_status, []

    def open(self, req, timeout):
        self.calls.append(req)
        if self.http_status:
            raise error.HTTPError(req.full_url, self.http_status, "private provider detail", {}, None)
        return io.BytesIO(self.raw)


def test_authenticated_transport_uses_only_fixed_production_url_date_and_secret_header():
    opener = Opener(response([row()]))
    raw = Transport(KEY, True, opener).fetch("KOSPI", "2023-11-01")
    assert raw == opener.raw
    req = opener.calls[0]
    assert req.method == "GET" and req.full_url == BASE + ENDPOINTS["KOSPI"] + "?basDd=20231101"
    assert KEY not in req.full_url and req.get_header("Auth_key") == KEY and not req.data


@pytest.mark.parametrize("raw,status,code", [(b"", 403, "ACCESS_DENIED"), (KEY.encode(), None, "SECRET_REFLECTION"),
                                           (b"x" * (LIMIT + 1), None, "RESPONSE_LIMIT")],
                         ids=["access-denied", "key-reflected", "oversized-response"])
def test_transport_redacts_provider_errors_and_rejects_secret_reflections(raw, status, code):
    opener = Opener(raw, status)
    with pytest.raises(ResearchError, match=code):
        Transport(KEY, True, opener).fetch("KOSPI", "2023-11-01")


def test_pending_snapshot_is_not_counted_as_matching_absence_and_synthetic_pass_is_test_only(tmp_path):
    folder = job(tmp_path)
    case_scope, cache = setup_cases(tmp_path)
    event_scope, _ = setup_events(tmp_path)
    cases = kind_cases.build_report(case_scope, cache)
    events = universe_events.build_report(event_scope, cache)
    pending = compare_evidence(report(folder), cases, events, cache)
    assert pending["pendingChecks"] == 5 and all(v["status"] == "PENDING_SOURCE" for v in pending["checks"])
    result = collect(folder, FakeTransport())
    compared = compare_evidence(result, cases, events, cache)
    assert compared["mismatches"] == compared["pendingChecks"] == 0 and compared["status"] == "TEST_ONLY"
    assert not compared["independentTotalVerified"] and not compared["marketUniverseComplete"]
    altered = copy.deepcopy(result)
    altered["records"].append(parse_snapshot(response([row("KOSDAQ", "000002")]), "KOSDAQ", "2024-01-02", CAPTURED, "SYNTHETIC")[0])
    assert compare_evidence(altered, cases, events, cache)["mismatches"] == 1


def test_environment_loads_only_krx_fields_and_process_values_override_file(tmp_path, monkeypatch):
    monkeypatch.delenv("SAGOPALGO_KRX_AUTH_KEY", raising=False)
    monkeypatch.setenv("SAGOPALGO_KRX_OPEN_API_ENABLED", "false")
    path = tmp_path / ".env"
    path.write_text('SAGOPALGO_KRX_AUTH_KEY="' + KEY + '"\nSAGOPALGO_KRX_OPEN_API_ENABLED=true\nOTHER_SECRET=private\n')
    assert load_environment(path) == (KEY, False)


def test_completed_first_market_is_reused_when_resuming_a_partial_job(tmp_path):
    folder = job(tmp_path)
    from app.replay.history import now
    from app.replay.dataset import digest
    raw = response([row()])
    (folder / "raw" / "KOSPI.json").write_bytes(raw)
    journal = json.loads((folder / "journal.json").read_bytes())
    stamp = now()
    journal["attempts"] = [{"market": "KOSPI", "basisDate": "2024-01-02", "state": "CAPTURED",
                            "startedAt": stamp, "capturedAt": stamp, "sha256": digest(raw)}]
    (folder / "journal.json").write_bytes(canonical(journal))
    client = FakeTransport()
    assert collect(folder, client)["sourceRecords"] == 3
    assert client.calls == [("KOSDAQ", "2024-01-02")]
    assert (folder / "raw" / "KOSPI.json").read_bytes() == raw


def test_check_cli_keeps_missing_sources_pending_and_audits_derived_output(tmp_path, capsys):
    folder = job(tmp_path)
    case_scope, cache = setup_cases(tmp_path)
    event_scope, _ = setup_events(tmp_path)
    cases, events = kind_cases.build_report(case_scope, cache), universe_events.build_report(event_scope, cache)
    inputs = {"case-scope": case_scope.model_dump(), "case-report": cases,
              "event-scope": event_scope.model_dump(), "event-report": events}
    args = ["check", "--job", str(folder), "--case-cache", str(cache), "--output", str(tmp_path / "comparison.json")]
    for key, value in inputs.items():
        path = tmp_path / (key + ".json")
        path.write_bytes(canonical(value))
        args.extend(["--" + key, str(path)])
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["pendingChecks"] == 5 and result["status"] == "TEST_ONLY"
    assert main(args) == 0
    capsys.readouterr()
    (tmp_path / "comparison.json").write_bytes(b"tampered")
    assert main(args) == 2
    assert "COMPARISON_TAMPERED" in capsys.readouterr().out


def test_cli_status_collect_and_audit_do_not_leak_credentials_and_reports_are_immutable(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "job"
    assert main(["plan", "--output", str(folder)]) == 0
    capsys.readouterr()
    monkeypatch.setenv("SAGOPALGO_KRX_OPEN_API_ENABLED", "false")
    monkeypatch.setenv("SAGOPALGO_KRX_AUTH_KEY", KEY)
    monkeypatch.setattr("urllib.request.build_opener", lambda *_: pytest.fail("network forbidden"))
    assert main(["status", "--job", str(folder)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["keyConfigured"] and not status["collectionEnabled"] and status["providerHistoricalRecords"] == 0
    assert main(["collect", "--job", str(folder)]) == 2
    output = capsys.readouterr().out
    assert KEY not in output and "DISABLED" in output
    assert main(["audit", "--job", str(folder)]) == 0
    assert KEY not in capsys.readouterr().out
    (folder / "report.json").write_bytes(b"tampered")
    assert main(["audit", "--job", str(folder)]) == 2
    assert "REPORT_TAMPERED" in capsys.readouterr().out
