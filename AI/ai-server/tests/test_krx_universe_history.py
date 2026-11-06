"""Synthetic histories exercise resume, identity, quotas and knowledge-time boundaries."""
from datetime import datetime, timedelta

import pytest

from app.replay import krx_universe, krx_universe_history as history
from app.replay.dataset import canonical, digest, read_bytes, read_json
from app.replay.history import atomic_json
from app.replay.krx_request_budget import Budget
from app.replay.models import ResearchError
from test_krx_universe import FakeTransport, KEY, response, row


class Reservations:
    def __init__(self):
        self.ids = []

    def reserve(self, request_id):
        assert request_id not in self.ids
        self.ids.append(request_id)


class Client(FakeTransport):
    def __init__(self, by_date=None, fail=None):
        super().__init__(fail=fail)
        self.by_date = by_date or {}

    def fetch(self, market, basis):
        value = super().fetch(market, basis)
        return self.by_date.get((basis, market), value)


def planned(tmp_path, end="2024-01-04", **options):
    folder = tmp_path / "history"
    history.prepare(folder, "2024-01-02", end, source_kind="SYNTHETIC", **options)
    return folder


def test_full_calendar_includes_weekend_and_reuses_completed_requests(tmp_path):
    folder = planned(tmp_path, end="2024-01-07")
    client, budget = Client(), Reservations()
    first = history.collect(folder, client, budget, 3)
    assert first["capturedDates"] == 1 and first["attemptsUsed"] == 3
    assert history.collect(folder, client, budget, 20)["capturedDates"] == 6
    assert len(client.calls) == len(budget.ids) == 12
    assert ("KOSDAQ", "2024-01-07") in client.calls
    assert history.collect(folder, client, budget, 20)["attemptsUsed"] == 12
    assert len(client.calls) == 12


def test_seed_is_immutable_and_does_not_spend_new_budget(tmp_path):
    seed = tmp_path / "seed"
    krx_universe.prepare(seed, "2024-01-02", "SYNTHETIC")
    krx_universe.collect(seed, Client())
    before = {str(p): digest(read_bytes(p)) for p in seed.rglob("*.json")}
    folder = planned(tmp_path, seed_job=seed)
    client, budget = Client(), Reservations()
    result = history.collect(folder, client, budget, 4)
    assert result["capturedDates"] == 3 and result["seedMarketsReused"] == 2
    assert len(client.calls) == len(budget.ids) == 4
    assert all(stamp != "2024-01-02" for _, stamp in client.calls)
    assert before == {str(p): digest(read_bytes(p)) for p in seed.rglob("*.json")}


def test_failed_request_requires_explicit_recovery_and_keeps_old_attempt(tmp_path):
    folder = planned(tmp_path)
    client, budget = Client(fail="KOSDAQ"), Reservations()
    with pytest.raises(ResearchError, match="CAPTURE_FAILED"):
        history.collect(folder, client, budget, 6)
    journal = read_json(read_bytes(folder / "journal.json"))
    assert journal["attempts"][1]["state"] == "FAILED"
    with pytest.raises(ResearchError, match="EXPLICIT_RECOVERY"):
        history.collect(folder, Client(), budget, 6)
    recovered = Client()
    assert history.collect(folder, recovered, budget, 6, True)["capturedDates"] == 3
    assert ("KOSPI", "2024-01-02") not in recovered.calls
    assert read_json(read_bytes(folder / "journal.json"))["attempts"][:2] == journal["attempts"]


def test_reserved_crash_is_not_silently_retried_and_per_pair_limit_is_bounded(tmp_path):
    folder = planned(tmp_path)
    plan, _, journal, _ = history.load_job(folder)
    for seq in range(1, 4):
        journal["attempts"].append({"seq": seq, "requestId": history.request_id(plan["planId"], seq),
                                    "date": "2024-01-02", "market": "KOSPI", "state": "RESERVED",
                                    "startedAt": "2026-11-04T00:00:00+00:00"})
    atomic_json(folder / "journal.json", journal)
    with pytest.raises(ResearchError, match="EXPLICIT_RECOVERY"):
        history.collect(folder, Client(), Reservations(), 6)
    with pytest.raises(ResearchError, match="ATTEMPT_LIMIT"):
        history.collect(folder, Client(), Reservations(), 6, True)


@pytest.mark.parametrize("kind", ["raw", "journal", "plan"])
def test_tampering_is_rejected_before_more_network_requests(tmp_path, kind):
    folder = planned(tmp_path)
    history.collect(folder, Client(), Reservations(), 2)
    if kind == "raw":
        (folder / "raw" / "000001.json").write_bytes(response([]))
    elif kind == "journal":
        value = read_json(read_bytes(folder / "journal.json"))
        value["attempts"][0]["rowCount"] = 999
        atomic_json(folder / "journal.json", value)
    else:
        value = read_json(read_bytes(folder / "plan.json"))
        value["config"]["maxRequests"] = 100
        atomic_json(folder / "plan.json", value)
    client = Client()
    with pytest.raises(ResearchError):
        history.collect(folder, client, Reservations(), 2)
        history.build(folder, tmp_path / "derived")
    assert client.calls == []


def test_invalid_response_is_kept_for_diagnosis_and_not_accepted_as_empty(tmp_path):
    folder = planned(tmp_path)
    client = Client({("2024-01-02", "KOSPI"): canonical({"error": "invalid"})})
    with pytest.raises(ResearchError, match="RESPONSE_INVALID"):
        history.collect(folder, client, Reservations(), 1)
    _, _, journal, _ = history.load_job(folder)
    attempt = journal["attempts"][0]
    assert attempt["state"] == "FAILED" and "rowCount" not in attempt
    assert digest(read_bytes(folder / "raw" / "000001.json")) == attempt["sha256"]


def history_with_change(tmp_path, gap="EMPTY_RESPONSE"):
    values = {}
    for market in krx_universe.ENDPOINTS:
        values[("2024-01-03", market)] = response([])
    # One ISIN moves markets. A reused short code with a new ISIN remains a distinct issue.
    values[("2024-01-04", "KOSPI")] = response([row(symbol="000003", ISU_CD="KR0000039999")])
    values[("2024-01-04", "KOSDAQ")] = response([row("KOSDAQ", "000001"), row("KOSDAQ", "000004")])
    if gap == "INCONSISTENT_RESPONSE":
        values[("2024-01-03", "KOSPI")] = response([row()])
    folder = planned(tmp_path)
    history.collect(folder, Client(values), Reservations(), 6)
    return folder


def test_empty_dates_are_not_closed_days_and_changes_keep_observation_windows(tmp_path):
    folder = history_with_change(tmp_path)
    output = tmp_path / "derived"
    report = history.build(folder, output)
    assert report["capturedDates"] == 3 and report["emptyPairDates"] == 1
    assert report["changeCounts"] == {"MARKET_TRANSFER_OBSERVED": 1, "REMOVED_OBSERVED": 1, "ADDED_OBSERVED": 1}
    assert not report["calendarCompletenessConfirmed"] and not report["marketUniverseComplete"]
    changes = [read_json(raw) for raw in read_bytes(output / "changes.jsonl").splitlines()]
    assert all(c["effectiveDate"] is None and not c["legalEventConfirmed"] for c in changes)
    assert all(c["observedFrom"] == "2024-01-02" and c["observedTo"] == "2024-01-04" for c in changes)
    assert all(c["emptyResponseDatesBetween"] == ["2024-01-03"] for c in changes)
    assert history.build(folder, output, verify=True) == report


def test_inconsistent_market_pair_breaks_change_chain(tmp_path):
    folder = history_with_change(tmp_path, "INCONSISTENT_RESPONSE")
    report = history.build(folder, tmp_path / "derived")
    assert report["inconsistentPairDates"] == ["2024-01-03"] and not report["changeCounts"]


@pytest.mark.parametrize("target", ["days/2024-01-02.json", "changes.jsonl", "report.json"])
def test_recomputed_audit_rejects_derived_mutation(tmp_path, target):
    folder = history_with_change(tmp_path)
    output = tmp_path / "derived"
    history.build(folder, output)
    path = output / target
    path.write_bytes(read_bytes(path) + b" ")
    with pytest.raises(ResearchError, match="DERIVED_TAMPERED"):
        history.build(folder, output, verify=True)


def test_as_of_uses_current_capture_time_and_never_fills_empty_or_missing_day(tmp_path):
    folder = history_with_change(tmp_path)
    early = history.as_of(folder, "2024-01-02", "2024-01-02T23:59:59+09:00")
    assert early["members"] == [] and not early["completeAtCutoff"]
    late = history.as_of(folder, "2024-01-02", "2099-01-01T00:00:00+00:00")
    assert len(late["members"]) == 3 and late["completeAtCutoff"]
    assert not late["usableForTraining"] and not late["usableForTrading"]
    assert history.as_of(folder, "2024-01-03", "2099-01-01T00:00:00+00:00")["members"] == []
    with pytest.raises(ResearchError, match="OUTSIDE_SCOPE"):
        history.as_of(folder, "2024-01-01", "2099-01-01T00:00:00+00:00")


def test_unknown_classification_breaks_chain_and_cross_market_duplicates_fail(tmp_path):
    folder = planned(tmp_path)
    values = {("2024-01-03", "KOSPI"): response([row(SECUGRP_NM="unknown")])}
    history.collect(folder, Client(values), Reservations(), 6)
    report = history.build(folder, tmp_path / "derived")
    assert report["unreviewedRecords"] == 1 and not report["changeCounts"]
    _, _, _, latest = history.load_job(folder)
    entry = latest[("2024-01-02", "KOSDAQ")]
    bad = response([row("KOSDAQ")])
    (folder / "raw" / f"{entry['seq']:06d}.json").write_bytes(bad)
    value = read_json(read_bytes(folder / "journal.json"))
    value["attempts"][1].update(sha256=digest(bad), rowCount=1)
    atomic_json(folder / "journal.json", value)
    with pytest.raises(ResearchError, match="CROSS_MARKET_DUPLICATE"):
        history.as_of(folder, "2024-01-02", "2099-01-01T00:00:00+00:00")


class Clock:
    def __init__(self, at="2026-11-04T00:00:00+00:00"):
        self.at = datetime.fromisoformat(at)
        self.waits = []

    def __call__(self):
        return self.at

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.at += timedelta(seconds=seconds)


def test_shared_budget_reserves_failures_priors_spacing_and_duplicate_ids(tmp_path):
    clock = Clock()
    budget = Budget(tmp_path, KEY, limit=4, prior_requests=1, clock=clock, sleep=clock.sleep)
    assert budget.reserve("a")["used"] == 2
    assert budget.reserve("b")["used"] == 3 and clock.waits == [0.5]
    with pytest.raises(ResearchError, match="ALREADY_RESERVED"):
        budget.reserve("b")
    shared = Budget(tmp_path, KEY, limit=8000, clock=clock, sleep=clock.sleep)
    assert shared.reserve("c")["limit"] == 4
    with pytest.raises(ResearchError, match="EXHAUSTED"):
        shared.reserve("d")
    assert KEY not in str(list(tmp_path.rglob("*")))


def test_budget_clock_regression_and_midnight_do_not_sleep_unbounded_or_send(tmp_path):
    clock = Clock("2026-11-04T14:59:59.800000+00:00")
    budget = Budget(tmp_path, KEY, clock=clock, sleep=clock.sleep)
    budget.reserve("a")
    clock.at -= timedelta(seconds=1)
    with pytest.raises(ResearchError, match="CLOCK_REGRESSION"):
        budget.reserve("b")
    clock.at += timedelta(seconds=1)
    with pytest.raises(ResearchError, match="DAY_CHANGED"):
        budget.reserve("b")
    assert budget.reserve("b")["localDay"] == "2026-11-05"


def test_plan_insufficient_budget_invalid_range_and_run_budget_fail(tmp_path):
    with pytest.raises(ResearchError, match="BUDGET_TOO_SMALL"):
        planned(tmp_path, max_requests=2)
    with pytest.raises(ValueError):
        planned(tmp_path, end="2024-01-01")
    folder = planned(tmp_path)
    with pytest.raises(ResearchError, match="RUN_BUDGET_INVALID"):
        history.collect(folder, Client(), Reservations(), -1)


@pytest.mark.parametrize("failures", [2, 8])
def test_windows_replacement_retry_is_bounded_and_preserves_previous_checkpoint(tmp_path, monkeypatch, failures):
    from app.replay import krx_storage
    from app.replay import file_publish
    monkeypatch.setattr(file_publish, 'WINDOWS', True)
    path = tmp_path / "checkpoint.json"
    atomic_json(path, {"version": 1})
    original = file_publish.os.replace
    calls = []

    def replace(source, target):
        calls.append((source, target))
        if len(calls) <= failures:
            error = PermissionError("synthetic sharing violation")
            error.winerror = 32
            raise error
        return original(source, target)

    waits = []
    monkeypatch.setattr(file_publish.os, "replace", replace)
    monkeypatch.setattr(file_publish.time, "sleep", waits.append)
    if failures == 8:
        with pytest.raises(PermissionError):
            krx_storage.atomic_json(path, {"version": 2})
        assert read_json(read_bytes(path)) == {"version": 1}
        assert len(calls) == 8 and len(waits) == 7
    else:
        krx_storage.atomic_json(path, {"version": 2})
        assert read_json(read_bytes(path)) == {"version": 2}
        assert len(calls) == 3 and len(waits) == 2


def test_lowered_shared_limit_cannot_be_raised_by_a_later_instance(tmp_path):
    clock = Clock()
    Budget(tmp_path, KEY, clock=clock, sleep=clock.sleep).reserve("a")
    Budget(tmp_path, KEY, limit=2, clock=clock, sleep=clock.sleep).reserve("b")
    with pytest.raises(ResearchError, match="EXHAUSTED"):
        Budget(tmp_path, KEY, clock=clock, sleep=clock.sleep).reserve("c")


@pytest.mark.parametrize("condition", ["match", "mismatch", "pending"])
def test_event_boundaries_compare_before_and_effective_day_without_global_completion(tmp_path, condition):
    folder = planned(tmp_path)
    values = {("2024-01-03", "KOSDAQ"): response([row("KOSDAQ", "000002"), row("KOSDAQ", "000004")]),
              ("2024-01-04", "KOSDAQ"): response([row("KOSDAQ", "000002")])}
    if condition == "mismatch":
        del values[("2024-01-04", "KOSDAQ")]
    history.collect(folder, Client(values), Reservations(), 4 if condition == "pending" else 6)
    cases = {"startDate": "2024-01-01", "endDate": "2024-01-10", "facts": [
        {"caseId": "ipo", "kind": "IPO", "date": "2024-01-03", "stockCode": "000002", "market": "KOSDAQ",
         "knownAt": "2026-11-03T00:00:00Z"},
        {"caseId": "delist", "kind": "DELISTING", "date": "2024-01-04", "stockCode": "000004", "market": "KOSDAQ",
         "details": {"originalListingDate": "2020-01-01"}, "knownAt": "2026-11-03T00:00:00Z"}]}
    events = {"startDate": "2024-01-01", "endDate": "2024-01-10", "facts": []}
    result = history.check_events(folder, cases, events, tmp_path)
    assert len(result["checks"]) == 4
    assert result["status"] == "TEST_ONLY" and not result["allLegalEventsConfirmed"]
    assert result["mismatches"] == (1 if condition == "mismatch" else 0)
    assert result["pendingChecks"] == (1 if condition == "pending" else 0)
    assert all(v["evidenceBasis"] == "RETROSPECTIVE_CHECK_NOT_HISTORICAL_KNOWLEDGE" for v in result["checks"])


def test_simultaneous_identity_changes_are_all_preserved_and_classification_is_not_delisting():
    old = {"isin": "KR0000010001", "symbol": "000001", "market": "KOSPI", "name": "old", "classification": "COMMON_SHARE"}
    new = {**old, "symbol": "000002", "market": "KOSDAQ", "name": "new"}
    sources = [{"knownAt": "2026-11-04T00:00:00Z"}]
    before = {"date": "2024-01-02", "issues": [old], "sources": sources}
    after = {"date": "2024-01-03", "issues": [new], "sources": sources}
    assert {v["kind"] for v in history.changes(before, after, [])} == {
        "MARKET_TRANSFER_OBSERVED", "SYMBOL_CHANGE_OBSERVED", "NAME_CHANGE_OBSERVED"}
    after["issues"] = [{**old, "classification": "OTHER_SHARE_CLASS"}]
    assert [v["kind"] for v in history.changes(before, after, [])] == ["CLASSIFICATION_CHANGE_OBSERVED"]


def test_failed_checkpoint_after_receiving_raw_remains_auditable_and_explicitly_resumable(tmp_path, monkeypatch):
    folder = planned(tmp_path, end="2024-01-02")
    original = history.atomic_json
    failures = []

    def fail_one_capture(path, value):
        if path.name == "journal.json" and value["attempts"][-1]["state"] == "CAPTURED" and not failures:
            failures.append(True)
            raise PermissionError("synthetic persistent checkpoint replacement failure")
        return original(path, value)

    monkeypatch.setattr(history, "atomic_json", fail_one_capture)
    budget = Reservations()
    with pytest.raises(ResearchError, match="CAPTURE_FAILED"):
        history.collect(folder, Client(), budget, 2)
    _, _, journal, _ = history.load_job(folder)
    failed = journal["attempts"][0]
    assert failed["state"] == "FAILED" and "sha256" in failed and "rowCount" not in failed
    raw = read_bytes(folder / "raw" / "000001.json")
    assert history.collect(folder, Client(), budget, 2, True)["capturedDates"] == 1
    assert read_bytes(folder / "raw" / "000001.json") == raw
