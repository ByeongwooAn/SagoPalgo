import copy
from datetime import datetime, timezone
import io
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.replay.calendar_fetch import calendar_reference, fetch_calendar_once
from app.replay.dataset import canonical, digest
from app.replay.history import audit, collect, KisHistoryTransport
from app.replay.local_use import bind_local_use, load_local_use
from app.replay.models import ResearchError, utc
from app.replay.reference import ReferencePack, combine, reconcile, references_as_of, check_reference_files
from app.replay.reference_cli import main
from test_history import FakeTransport, job

EXAMPLE = Path(__file__).parents[1] / "examples/replay/reference-pack.json"


def pack(**changes):
    value = json.loads(EXAMPLE.read_bytes())
    value.update(changes)
    return ReferencePack.model_validate(value)


def collected(tmp_path):
    target, _ = job(tmp_path, startDate="2024-01-02", endDate="2024-01-03")
    collect(target, FakeTransport(), sleeper=lambda _: None)
    report, rows = audit(target, check_daily=True)
    return target, report, rows


def test_local_use_binds_exact_corpus_without_rewriting_original_declarations(tmp_path):
    target, report, rows = collected(tmp_path)
    originals = {name: (target / name).read_bytes() for name in ["request.json", "plan.json", "journal.json", "audit.json", "daily.jsonl"]}
    profile = tmp_path / "local-use.json"
    value = bind_local_use(target, profile)
    assert value["basis"] == "PERSONAL_ANALYSIS_INTERPRETATION" and value["providerExplicitAiGrant"] is False
    loaded = load_local_use(profile, report, originals["daily.jsonl"])
    assert loaded.localStorageOnly and not loaded.externalAiTransfer and not loaded.thirdPartyProvision
    assert all((target / name).read_bytes() == raw for name, raw in originals.items())
    with pytest.raises(FileExistsError):
        bind_local_use(target, profile)


@pytest.mark.parametrize("field,value", [("externalAiTransfer", True), ("thirdPartyProvision", True),
                                          ("localStorageOnly", False), ("providerExplicitAiGrant", True),
                                          ("externalAiTransfer", 0)])
def test_local_profile_cannot_expand_scope_or_claim_explicit_provider_ai_permission(tmp_path, field, value):
    target, report, _ = collected(tmp_path)
    path = tmp_path / "scope.json"
    body = bind_local_use(target, path)
    body[field] = value
    body.pop("policyId")
    body["policyId"] = digest(canonical(body))
    path.write_bytes(canonical(body))
    with pytest.raises(ValidationError):
        load_local_use(path, report, (target / "daily.jsonl").read_bytes())


def test_local_profile_rejects_wrong_dataset_and_hash_tampering(tmp_path):
    target, report, _ = collected(tmp_path)
    path = tmp_path / "scope.json"
    bind_local_use(target, path)
    with pytest.raises(ResearchError, match="DATASET_MISMATCH"):
        load_local_use(path, report, b"different corpus")
    body = json.loads(path.read_bytes())
    body["policyId"] = "0" * 64
    path.write_bytes(canonical(body))
    with pytest.raises(ResearchError, match="TAMPERED"):
        load_local_use(path, report, (target / "daily.jsonl").read_bytes())


def test_incomplete_collection_cannot_be_accepted_as_finished_input(tmp_path):
    target, _ = job(tmp_path)
    with pytest.raises(ResearchError):
        collect(target, FakeTransport(fail_call=2), sleeper=lambda _: None)
    with pytest.raises(ResearchError, match="REQUIRES_AUDITED_COLLECTION"):
        bind_local_use(target, tmp_path / "scope.json")


def test_known_at_and_effective_date_prevent_future_listing_and_action_leak():
    reference = pack()
    before = references_as_of([reference], "000001", utc("2023-12-31T00:00:00Z"), "2024-01-02")
    assert before["membership"] is None and before["actions"] == [] and before["session"] is None
    first = references_as_of([reference], "000001", utc("2024-01-02T06:30:00Z"), "2024-01-02")
    assert first["membership"]["eligible"] is True and first["actions"] == []
    announced = references_as_of([reference], "000001", utc("2024-01-02T09:00:00Z"), "2024-01-02")
    assert announced["actions"][0]["effectiveDate"] == "2024-01-03"
    premature = references_as_of([reference], "000001", utc("2024-01-01T12:00:00Z"), "2024-01-01")
    assert premature["membership"] is None


def test_explicit_late_open_is_preserved_without_default_session_filling():
    reference = pack()
    assert reference.sessions[0].openAt == utc("2024-01-02T01:00:00Z")
    assert len(reference.sessions) == 1
    body = reference.model_dump(mode="json")
    body["sessions"][0]["closeAt"] = "2024-01-03T00:00:00Z"
    with pytest.raises(ValidationError):
        ReferencePack.model_validate(body)


@pytest.mark.parametrize("ratio", ["0", "-1", 2, None])
def test_split_ratio_is_not_rounded_or_invented(ratio):
    value = pack().model_dump(mode="json")
    value["actions"][0]["ratio"] = ratio
    with pytest.raises(ValidationError):
        ReferencePack.model_validate(value)


def test_conflicting_snapshots_and_ambiguous_membership_are_not_selected_for_favorable_results():
    first = pack()
    value = first.model_dump(mode="json")
    value["calendar"][0]["tradingDay"] = False
    with pytest.raises(ResearchError, match="REFERENCE_CONFLICT"):
        combine([first, ReferencePack.model_validate(value)])
    value = first.model_dump(mode="json")
    duplicate = {**value["listings"][0], "eventId": "other", "eligible": False}
    value["listings"].append(duplicate)
    with pytest.raises(ResearchError, match="MEMBERSHIP_AMBIGUOUS"):
        references_as_of([ReferencePack.model_validate(value)], "000001", utc("2024-01-02T06:30:00Z"), "2024-01-02")


def test_missing_reference_is_unknown_and_does_not_use_weekend_or_current_survivor_guesses(tmp_path):
    _, report, rows = collected(tmp_path)
    result = reconcile(report, rows, [])
    assert result["knownCalendarDates"] == 0 and result["referenceScopeReady"] is False
    codes = {i["code"] for i in result["issues"]}
    assert {"CALENDAR_UNKNOWN", "MARKET_UNIVERSE_UNCONFIRMED", "CORPORATE_ACTIONS_COVERAGE_UNCONFIRMED"} <= codes
    assert result["priceAdjustmentApplied"] is False


def complete_pack():
    value = pack().model_dump(mode="json")
    value["listings"][0]["stockCode"] = "005930"
    value["sessions"].append({"businessDate": "2024-01-03", "openAt": "2024-01-03T00:00:00Z", "closeAt": "2024-01-03T06:30:00Z",
                               "knownAt": "2024-01-01T00:00:00Z", "evidence": "SYNTHETIC explicit session"})
    value["coverage"] = [{"dimension": d, "startDate": "2024-01-02", "endDate": "2024-01-03", "scope": "MARKET", "stockCodes": [],
                           "status": "COMPLETE", "evidence": "SYNTHETIC declaration only"} for d in ["CALENDAR", "SESSION", "UNIVERSE", "CORPORATE_ACTIONS"]]
    return value


def test_complete_fixture_is_only_declared_reference_scope_and_not_trading_or_training_readiness(tmp_path):
    _, report, rows = collected(tmp_path)
    result = reconcile(report, rows, [ReferencePack.model_validate(complete_pack())])
    assert result["status"] == "EVIDENCE_SCOPES_RECONCILED" and result["referenceScopeReady"] is True
    assert not result["usableForTraining"] and not result["usableForTrading"] and result["declaredCoverageOnly"]
    assert result["syntheticSources"]


def test_real_history_cannot_be_declared_complete_using_synthetic_calendar(tmp_path):
    _, report, rows = collected(tmp_path)
    report["provenance"] = "PROVIDER_HISTORICAL"
    result = reconcile(report, rows, [ReferencePack.model_validate(complete_pack())])
    assert "SYNTHETIC_REFERENCE_WITH_REAL_HISTORY" in {i["code"] for i in result["issues"]}


def test_market_universe_coverage_can_be_evidenced_in_separate_date_partitions(tmp_path):
    _, report, rows = collected(tmp_path)
    value = complete_pack()
    whole = next(c for c in value["coverage"] if c["dimension"] == "UNIVERSE")
    value["coverage"] = [c for c in value["coverage"] if c["dimension"] != "UNIVERSE"]
    value["coverage"].extend([{**whole, "startDate": stamp, "endDate": stamp} for stamp in ["2024-01-02", "2024-01-03"]])
    result = reconcile(report, rows, [ReferencePack.model_validate(value)])
    assert result["marketUniverseDeclaredComplete"] and result["referenceScopeReady"]


def test_missing_price_closed_day_price_and_unknown_session_are_separate_diagnostics(tmp_path):
    _, report, rows = collected(tmp_path)
    value = complete_pack()
    value["calendar"][0]["tradingDay"] = False
    value["calendar"][0]["openDay"] = False
    result = reconcile(report, rows[:1], [ReferencePack.model_validate(value)])
    codes = {i["code"] for i in result["issues"]}
    assert {"NO_PRICE_ON_DECLARED_OPEN_DAY", "PRICE_ON_DECLARED_CLOSED_DAY", "SESSION_ON_CLOSED_DAY"} <= codes


def test_trading_open_and_settlement_flags_are_not_conflated(tmp_path):
    _, report, rows = collected(tmp_path)
    value = complete_pack()
    value["calendar"][0].update(tradingDay=True, openDay=False, settlementDay=True)
    result = reconcile(report, rows[1:], [ReferencePack.model_validate(value)])
    assert result["knownTradingDates"] == 2 and result["knownOpenDates"] == 1
    assert result["calendarFlagDifferences"] == ["2024-01-02"]
    assert "NO_PRICE_ON_DECLARED_OPEN_DAY" not in {i["code"] for i in result["issues"]}


def test_stock_subset_is_not_a_complete_historical_market_universe():
    value = complete_pack()
    value["coverage"][0]["stockCodes"] = ["005930"]
    with pytest.raises(ValidationError):
        ReferencePack.model_validate(value)


def test_reference_knowledge_cannot_postdate_pack_observation():
    value = complete_pack()
    value["listings"][0]["knownAt"] = "2025-01-01T00:00:00Z"
    with pytest.raises(ValidationError):
        ReferencePack.model_validate(value)


def test_local_cli_and_report_bind_input_hashes_and_refuse_overwrite(tmp_path):
    target, _, _ = collected(tmp_path)
    policy = tmp_path / "scope.json"
    assert main(["accept-local", "--job", str(target), "--output", str(policy)]) == 0
    output = tmp_path / "report.json"
    assert main(["check", "--job", str(target), "--local-use", str(policy), "--reference", str(EXAMPLE), "--output", str(output)]) == 1
    value = json.loads(output.read_bytes())
    assert value["localUseAccepted"] and value["useBasis"] == "PERSONAL_ANALYSIS_INTERPRETATION"
    assert value["referenceHashes"] == [digest(EXAMPLE.read_bytes())]
    with pytest.raises(FileExistsError):
        check_reference_files(target, policy, [EXAMPLE], output)


def calendar_body(flag="Y"):
    return canonical({"rt_cd": "0", "ctx_area_nk": "next", "output": [
        {"bass_dt": "20240102", "bzdy_yn": "Y", "tr_day_yn": flag, "opnd_yn": "Y", "sttl_day_yn": "N"}]})


class CalendarResponse(io.BytesIO):
    def __init__(self, body, continuation="M"):
        super().__init__(body)
        self.headers = {"tr_cont": continuation}
    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class CalendarOpener:
    def __init__(self, fail=False): self.calls = []; self.fail = fail
    def open(self, req, timeout):
        self.calls.append(req)
        if req.full_url.endswith("tokenP"):
            return CalendarResponse(b'{"access_token":"calendar-token-test"}')
        if self.fail:
            raise OSError("private-body")
        return CalendarResponse(calendar_body())


def test_calendar_rate_guard_caches_same_request_and_never_paginates(tmp_path):
    opener = CalendarOpener()
    client = KisHistoryTransport("calendar-key-test", "calendar-secret-test", opener)
    at = datetime(2026, 11, 3, tzinfo=timezone.utc)
    value, folder, cached = fetch_calendar_once(tmp_path, "2024-01-02", client, at)
    assert not cached and len(opener.calls) == 2
    assert len(value.calendar) == 1 and value.sessions == [] and value.actions == []
    receipt = json.loads((folder / "receipt.json").read_bytes())
    assert receipt["hasMore"] and not receipt["autoPagination"]
    _, _, cached = fetch_calendar_once(tmp_path, "2024-01-02", client, at)
    assert cached and len(opener.calls) == 2
    with pytest.raises(ResearchError, match="DAILY_REQUEST_RESERVED"):
        fetch_calendar_once(tmp_path, "2024-01-03", client, at)
    assert len(opener.calls) == 2


def test_calendar_failure_keeps_daily_reservation_and_does_not_echo_body(tmp_path):
    opener = CalendarOpener(fail=True)
    client = KisHistoryTransport("calendar-key-test", "calendar-secret-test", opener)
    at = datetime(2026, 11, 3, tzinfo=timezone.utc)
    with pytest.raises(ResearchError) as caught:
        fetch_calendar_once(tmp_path, "2024-01-02", client, at)
    assert str(caught.value) == "CALENDAR_REQUEST_FAILED"
    with pytest.raises(ResearchError, match="DAILY_REQUEST_RESERVED"):
        fetch_calendar_once(tmp_path, "2024-01-02", client, at)
    assert len(opener.calls) == 2


def test_calendar_cache_tampering_detected_before_any_new_network_call(tmp_path):
    opener = CalendarOpener()
    client = KisHistoryTransport("calendar-key-test", "calendar-secret-test", opener)
    at = datetime(2026, 11, 3, tzinfo=timezone.utc)
    _, folder, _ = fetch_calendar_once(tmp_path, "2024-01-02", client, at)
    (folder / "reference.json").write_bytes(b"{}")
    with pytest.raises(ResearchError, match="CACHE_TAMPERED"):
        fetch_calendar_once(tmp_path, "2024-01-02", client, at)
    assert len(opener.calls) == 2


@pytest.mark.parametrize("flag", ["", "UNKNOWN", True, "y"])
def test_unknown_calendar_flags_are_not_converted_into_closed_days(flag):
    with pytest.raises(ResearchError, match="FLAG_INVALID"):
        calendar_reference(calendar_body(flag), "2026-11-03T00:00:00Z", "M")
