"""Synthetic live-validation fixtures preserve the frozen parser and avoid training eligibility claims."""
import copy
import json

import pytest

from app.replay import krx_universe, krx_baseline_validation as baseline
from app.replay.dataset import canonical
from app.replay.models import ResearchError
from test_kind_cases import CAPTURED
from test_krx_universe import FakeTransport, Opener, KEY, job, response, row


def basic_job(tmp_path):
    folder = job(tmp_path)
    client = FakeTransport(values={"KOSPI": response([row(), row(symbol="000005", KIND_STKCERT_TP_NM="구형우선주"),
                                                       row(symbol="000006", KIND_STKCERT_TP_NM="종류주권"),
                                                       row(symbol="000007", SECUGRP_NM="선박투자회사")]),
                                   "KOSDAQ": response([row("KOSDAQ", "000003"), row("KOSDAQ", "000004")])})
    krx_universe.collect(folder, client)
    return folder


def daily_row(market="KOSPI", symbol="000001", **fields):
    value = {key: "0" for key in baseline.DAILY_FIELDS}
    value.update(BAS_DD="20240102", ISU_CD=symbol, ISU_NM="가상종목", MKT_NM=market, SECT_TP_NM="-", LIST_SHRS="0")
    value.update(fields)
    return value


class FakeDaily(FakeTransport):
    def __init__(self, fail=None, zero_for_first=False):
        super().__init__(values={"KOSPI": response([daily_row(symbol=s, ACC_TRDVOL="0" if zero_for_first else "10")
                                                   for s in ["000001", "000005", "000006", "000007"]]),
                                 "KOSDAQ": response([daily_row("KOSDAQ", s, ACC_TRDVOL="10") for s in ["000003", "000004"]])}, fail=fail)


def test_versioned_review_resolves_real_world_labels_without_rewriting_frozen_snapshot(tmp_path):
    folder = basic_job(tmp_path)
    original = krx_universe.audit(folder)
    reviewed = baseline.reviewed_snapshot(folder)
    assert original["unreviewedRecords"] == 3 and reviewed["unreviewedRecords"] == 0
    assert original["commonShareRecords"] == 3 and reviewed["commonShareRecords"] == 4
    assert len(reviewed["classificationChanges"]) == 3
    assert reviewed["classificationPolicy"] == baseline.POLICY
    assert reviewed["schemaVersion"] != original["schemaVersion"]
    assert all(old["sourceRowSha256"] == new["sourceRowSha256"] for old, new in zip(original["records"], reviewed["records"]))
    assert krx_universe.audit(folder) == original
    assert not reviewed["marketUniverseComplete"] and not reviewed["usableForTraining"]


def test_review_does_not_silently_approve_unseen_security_or_share_types(tmp_path):
    folder = job(tmp_path)
    krx_universe.collect(folder, FakeTransport(values={"KOSPI": response([row(SECUGRP_NM="unreviewed type")]),
                                                     "KOSDAQ": response([row("KOSDAQ", "000002")])}))
    assert baseline.reviewed_snapshot(folder)["unreviewedRecords"] == 1


def test_daily_parser_accepts_global_segment_and_retains_zero_volume_without_market_migration():
    rows = baseline.parse_daily(response([daily_row("KOSDAQ GLOBAL", "0000A0")]), "KOSDAQ", "2024-01-02", CAPTURED)
    assert rows[0]["symbol"] == "0000A0" and rows[0]["market"] == "KOSDAQ"
    assert rows[0]["reportedMarket"] == "KOSDAQ GLOBAL" and rows[0]["volume"] == "0"


@pytest.mark.parametrize("field,value", [("BAS_DD", "20240103"), ("MKT_NM", "KOSDAQ"), ("ISU_CD", "invalid"),
                                        ("ACC_TRDVOL", "-1"), ("LIST_SHRS", "NaN"), ("TDD_CLSPRC", 1)])
def test_daily_wrong_date_market_code_and_noncanonical_values_fail(field, value):
    with pytest.raises(ResearchError, match="ROW_INVALID"):
        baseline.parse_daily(response([daily_row(**{field: value})]), "KOSPI", "2024-01-02", CAPTURED)


def test_daily_duplicate_and_empty_responses_fail():
    with pytest.raises(ResearchError, match="DUPLICATE"):
        baseline.parse_daily(response([daily_row(), daily_row()]), "KOSPI", "2024-01-02", CAPTURED)
    with pytest.raises(ResearchError, match="SCHEMA_INVALID"):
        baseline.parse_daily(response([]), "KOSPI", "2024-01-02", CAPTURED)


def test_authenticated_daily_transport_only_changes_fixed_endpoint():
    opener = Opener(response([daily_row()]))
    baseline.DailyTransport(KEY, True, opener).fetch("KOSPI", "2024-01-02")
    assert opener.calls[0].full_url == krx_universe.BASE + "stk_bydd_trd?basDd=20240102"
    assert KEY not in opener.calls[0].full_url


def test_daily_capture_reuses_complete_caches_without_repeating_requests(tmp_path):
    folder = basic_job(tmp_path)
    original = krx_universe.audit(folder)
    output = tmp_path / "daily"
    client = FakeDaily(zero_for_first=True)
    assert baseline.capture_daily(original, output, client)["capturedSources"] == 2
    assert baseline.capture_daily(original, output, client)["reusedSources"] == 2
    assert len(client.calls) == 2
    reviewed = baseline.reviewed_snapshot(folder)
    report = baseline.reconcile_daily(folder, reviewed, baseline.daily_report(original, output))
    assert report["status"] == "TEST_ONLY" and report["basicRowCounts"] == report["dailyRowCounts"]
    assert not report["missingDailySymbols"] and not report["shareCountMismatches"]
    assert report["zeroVolumeCommonSymbolsPreserved"] == [("KOSPI", "000001"), ("KOSPI", "000007")]
    assert not report["crossEndpointTotalsVerified"] and not report["tradingHaltCoverageVerified"]


def test_daily_failure_is_not_retried_and_valid_first_market_is_preserved(tmp_path):
    original = krx_universe.audit(basic_job(tmp_path))
    output = tmp_path / "daily"
    client = FakeDaily(fail="KOSDAQ")
    with pytest.raises(ResearchError, match="CAPTURE_FAILED"):
        baseline.capture_daily(original, output, client)
    assert (output / "KOSPI" / "body.json").exists()
    with pytest.raises(ResearchError, match="RECOVERY_REQUIRED"):
        baseline.capture_daily(original, output, client)
    assert len(client.calls) == 2
    assert "private response" not in (output / "KOSDAQ" / "receipt.json").read_text()


def test_parent_hashes_and_received_daily_bytes_are_bound_to_the_exact_baseline(tmp_path):
    original = krx_universe.audit(basic_job(tmp_path))
    output = tmp_path / "daily"
    baseline.capture_daily(original, output, FakeDaily())
    other = copy.deepcopy(original)
    other["basisDate"] = "2024-01-03"
    with pytest.raises(ResearchError, match="DERIVED_TAMPERED"):
        baseline.daily_report(other, output)
    (output / "KOSPI" / "body.json").write_bytes(b"tampered")
    with pytest.raises(ResearchError, match="RAW_TAMPERED"):
        baseline.daily_report(original, output)


@pytest.mark.parametrize("change", ["missing-daily", "daily-only", "share-count"])
def test_daily_count_and_share_differences_remain_visible(change, tmp_path):
    folder = basic_job(tmp_path)
    original = krx_universe.audit(folder)
    output = tmp_path / "daily"
    baseline.capture_daily(original, output, FakeDaily())
    daily = baseline.daily_report(original, output)
    if change == "missing-daily":
        daily["records"] = daily["records"][1:]
    elif change == "daily-only":
        daily["records"].append({**daily["records"][0], "symbol": "999999"})
    else:
        daily["records"][0]["listedShares"] = "1"
    # This low-level comparison reports each difference; the CLI always re-audits raw source records.
    result = baseline.reconcile_daily(folder, baseline.reviewed_snapshot(folder), daily)
    assert result[{"missing-daily": "missingDailySymbols", "daily-only": "dailyOnlySymbols", "share-count": "shareCountMismatches"}[change]]


def test_review_and_reconciliation_cli_are_offline_and_derived_files_immutable(tmp_path, monkeypatch, capsys):
    folder = basic_job(tmp_path)
    daily = tmp_path / "daily"
    baseline.capture_daily(krx_universe.audit(folder), daily, FakeDaily())
    monkeypatch.setattr("urllib.request.build_opener", lambda *_: pytest.fail("network forbidden"))
    reviewed = tmp_path / "reviewed.json"
    for command in ["review", "audit-review"]:
        assert baseline.main([command, "--job", str(folder), "--output", str(reviewed)]) == 0
        assert json.loads(capsys.readouterr().out)["unreviewedRecords"] == 0
    output = tmp_path / "reconciliation.json"
    args = ["reconcile", "--job", str(folder), "--reviewed", str(reviewed), "--daily", str(daily), "--output", str(output)]
    assert baseline.main(args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "TEST_ONLY"
    assert baseline.main(["capture-daily", "--job", str(folder), "--output", str(daily)]) == 0
    assert json.loads(capsys.readouterr().out)["reusedSources"] == 2
    output.write_bytes(b"tampered")
    assert baseline.main(args) == 2
    assert "DERIVED_TAMPERED" in capsys.readouterr().out


def test_reviewed_anchor_check_and_synthetic_access_status_remain_distinct(tmp_path, capsys):
    from test_kind_cases import setup_cases
    from test_universe_events import setup_events
    from app.replay import kind_cases, universe_events
    folder = basic_job(tmp_path)
    case_scope, cache = setup_cases(tmp_path)
    event_scope, _ = setup_events(tmp_path)
    reviewed_path = tmp_path / "reviewed.json"
    baseline.immutable_json(reviewed_path, baseline.reviewed_snapshot(folder))
    inputs = {"case-scope": case_scope.model_dump(), "case-report": kind_cases.build_report(case_scope, cache),
              "event-scope": event_scope.model_dump(), "event-report": universe_events.build_report(event_scope, cache)}
    args = ["check", "--job", str(folder), "--reviewed", str(reviewed_path), "--case-cache", str(cache),
            "--output", str(tmp_path / "checked.json")]
    for name, value in inputs.items():
        path = tmp_path / (name + ".json")
        path.write_bytes(canonical(value))
        args.extend(["--" + name, str(path)])
    assert krx_universe.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mismatches"] == result["pendingChecks"] == 0 and result["status"] == "TEST_ONLY"
    assert krx_universe.main(["status", "--job", str(folder)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["serviceApprovalStatus"] == "NOT_VERIFIED" and not any(result["serviceAccessObservedByMarket"].values())
