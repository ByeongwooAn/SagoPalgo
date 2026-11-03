import copy
from datetime import date, datetime, timedelta
import io
import json
from pathlib import Path
from urllib import error

import pytest
from pydantic import ValidationError

from app.replay.dataset import canonical, digest, read_json
from app.replay.history import (
    BASE, DAILY_PATH, HistoryConfig, KisHistoryTransport, NoRedirect, audit, collect,
    comparable, load_job, main, parameters, parse_page, plan, prepare,
)
from app.replay.models import ResearchError


def config(**changes):
    values = {"schemaVersion": "SAGOPALGO_KIS_DAILY_REQUEST_V1", "stockCode": "005930", "startDate": "2024-01-01",
              "endDate": "2024-01-24", "provenance": "SYNTHETIC", "queryRightsConfirmed": True,
              "queryRightsEvidence": "SYNTHETIC_TEST_ONLY", "windowDays": 12, "maxRequests": 32, "minIntervalSeconds": 1}
    values.update(changes)
    return HistoryConfig.model_validate(values)


def job(tmp_path, **changes):
    cfg = config(**changes)
    source = tmp_path / "request.json"
    source.write_bytes(canonical(cfg.model_dump()))
    target = tmp_path / "job"
    prepare(source, target)
    return target, cfg


def page(params, modify=None):
    first = datetime.strptime(params["FID_INPUT_DATE_1"], "%Y%m%d").date()
    last = datetime.strptime(params["FID_INPUT_DATE_2"], "%Y%m%d").date()
    rows = []
    current = first
    while current <= last:
        if current.weekday() < 5:
            rows.append({"stck_bsop_date": current.strftime("%Y%m%d"), "stck_oprc": "100", "stck_hgpr": "110",
                         "stck_lwpr": "90", "stck_clpr": "105", "acml_vol": "123456789012345678901234",
                         "flng_cls_code": "00", "prtt_rate": "0.00", "mod_yn": "N", "revl_issu_reas": "0"})
        current += timedelta(days=1)
    result = {"rt_cd": "0", "msg_cd": "OK", "msg1": "", "output1": {"stck_shrn_iscd": params["FID_INPUT_ISCD"]}, "output2": list(reversed(rows))}
    if modify:
        modify(result)
    return canonical(result)


class FakeTransport:
    def __init__(self, target=None, fail_call=None, mutate_call=None):
        self.target, self.fail_call, self.mutate_call = target, fail_call, mutate_call
        self.calls = []

    def authenticate(self):
        self.calls.append("AUTH")

    def fetch(self, params):
        self.calls.append(copy.deepcopy(params))
        if self.target:
            journal = read_json((self.target / "journal.json").read_bytes())
            assert journal["attempts"][-1]["status"] == "IN_FLIGHT"
            assert len(journal["attempts"]) >= len(self.calls)
        if len(self.calls) == self.fail_call:
            raise ResearchError("HISTORY_HTTP_FAILED")
        if len(self.calls) == self.mutate_call:
            return page(params, lambda value: value["output2"][0].update(stck_clpr="106"))
        return page(params)


def test_plan_covers_multiyear_range_with_small_overlapping_raw_requests():
    cfg = config(startDate="2021-01-01", endDate="2024-01-01", windowDays=60, maxRequests=64)
    planned = plan(cfg)
    covered = set()
    for params in planned["windows"]:
        assert params["FID_ORG_ADJ_PRC"] == "1" and params["FID_PERIOD_DIV_CODE"] == "D"
        assert params["FID_COND_MRKT_DIV_CODE"] == "J"
        first, last = [datetime.strptime(params[key], "%Y%m%d").date() for key in ["FID_INPUT_DATE_1", "FID_INPUT_DATE_2"]]
        assert 0 <= (last - first).days < 60
        covered.update(first + timedelta(days=n) for n in range((last - first).days + 1))
    assert min(covered) == date(2021, 1, 1) and max(covered) == date(2024, 1, 1)
    assert len(covered) == (date(2024, 1, 1) - date(2021, 1, 1)).days + 1
    assert plan(cfg) == planned


def test_end_to_end_partial_windows_verification_precision_and_no_redundant_recollect(tmp_path):
    target, cfg = job(tmp_path)
    transport = FakeTransport(target)
    result = collect(target, transport, sleeper=lambda _: None)
    assert result["status"] == "COLLECTED" and result["verificationPassed"] == 3
    assert result["overlapComparisons"] > 0 and result["marketCoverage"] == "UNVERIFIED_NO_CALENDAR"
    assert result["trainingRightsConfirmed"] is False and result["usableForTraining"] is False
    report, rows = audit(target, check_daily=True)
    assert len(rows) == 18 and all(row["datePrecision"] == "DATE" for row in rows)
    assert rows[0]["volume"] == "123456789012345678901234"
    assert rows[0]["exchange"] == "KRX" and rows[0]["currency"] == "KRW" and rows[0]["timeframe"] == "DAY"
    assert not any("startAt" in row or "publishedAt" in row for row in rows)
    before = len(transport.calls)
    collect(target, transport, sleeper=lambda _: None)
    assert len(transport.calls) == before


def test_failure_resumes_only_missing_windows_and_counts_prior_calls(tmp_path):
    target, _ = job(tmp_path)
    first = FakeTransport(target, fail_call=3)
    with pytest.raises(ResearchError, match="HISTORY_HTTP_FAILED"):
        collect(target, first, sleeper=lambda _: None)
    report, rows = audit(target, check_daily=True)
    assert report["completedWindows"] == 1 and report["status"] == "PARTIAL" and rows
    second = FakeTransport(target)
    done = collect(target, second, sleeper=lambda _: None)
    assert done["status"] == "COLLECTED"
    assert second.calls[1] != first.calls[1]
    assert done["callsUsed"] == len(first.calls) + len(second.calls)


def test_failed_verification_can_resume_with_exact_remaining_budget(tmp_path):
    target, _ = job(tmp_path, startDate="2024-01-02", endDate="2024-01-02", maxRequests=5)
    with pytest.raises(ResearchError):
        collect(target, FakeTransport(fail_call=3), sleeper=lambda _: None)
    result = collect(target, FakeTransport(), sleeper=lambda _: None)
    assert result["callsUsed"] == 5 and result["status"] == "COLLECTED"


def test_conflicting_overlap_does_not_merge_corrupted_page(tmp_path):
    target, _ = job(tmp_path)
    class Conflict(FakeTransport):
        def fetch(self, params):
            self.calls.append(params)
            if len(self.calls) == 3:
                return page(params, lambda value: value["output2"][-1].update(stck_clpr="106"))
            return page(params)
    with pytest.raises(ResearchError, match="HISTORY_OVERLAP_CONFLICT"):
        collect(target, Conflict(), sleeper=lambda _: None)
    report, rows = audit(target, check_daily=True)
    assert report["completedWindows"] == 1
    assert all(row["close"] == "105" for row in rows)


@pytest.mark.parametrize("mutation,code", [
    (lambda v: v.update(rt_cd="1"), "PROVIDER_REJECTED"),
    (lambda v: v["output1"].update(stck_shrn_iscd="000660"), "IDENTITY_UNCONFIRMED"),
    (lambda v: v["output2"][0].update(acml_vol=1.5), "ROW_NUMBER_INVALID"),
    (lambda v: v["output2"][0].update(stck_clpr="1e2"), "ROW_NUMBER_INVALID"),
    (lambda v: v["output2"][0].update(stck_lwpr="120"), "OHLC_INVALID"),
    (lambda v: v["output2"][0].update(stck_bsop_date="20240125"), "ROW_OUTSIDE_WINDOW"),
    (lambda v: v["output2"].append(v["output2"][0]), "DUPLICATE_DATE"),
])
def test_protocol_rejects_failed_wrong_instrument_and_invalid_rows(mutation, code):
    cfg = config()
    params = parameters(cfg, date(2024, 1, 1), date(2024, 1, 24))
    with pytest.raises(ResearchError, match=code):
        parse_page(page(params, mutation), params, "2026-01-01T00:00:00Z")


def test_provider_padding_and_zero_activity_are_preserved_distinctly():
    params = parameters(config(), date(2024, 1, 2), date(2024, 1, 2))
    def mutate(value):
        value["output2"][0].update(stck_oprc="0", stck_hgpr="0", stck_lwpr="0", stck_clpr="0", acml_vol="0")
        value["output2"].append({"stck_bsop_date": ""})
    rows, padding = parse_page(page(params, mutate), params, "2026-01-01T00:00:00Z")
    assert padding == 1 and rows["2024-01-02"]["status"] == "NON_TRADING_OR_UNKNOWN"


@pytest.mark.parametrize("change", [
    {"windowDays": 7}, {"windowDays": 100}, {"startDate": "2024-02-30"},
    {"stockCode": "../bad"}, {"minIntervalSeconds": 0}, {"trainingRightsConfirmed": True},
])
def test_invalid_config_is_rejected(change):
    with pytest.raises((ValidationError, ResearchError)):
        config(**change)


def test_budget_rights_future_or_lock_blocks_before_authentication(tmp_path):
    with pytest.raises(ResearchError, match="BUDGET_TOO_SMALL"):
        plan(config(maxRequests=2))
    target, _ = job(tmp_path, queryRightsConfirmed=False)
    transport = FakeTransport()
    with pytest.raises(ResearchError, match="QUERY_RIGHTS_REQUIRED"):
        collect(target, transport, sleeper=lambda _: None)
    assert transport.calls == []
    (target / ".collect.lock").write_text("other worker")
    with pytest.raises(ResearchError, match="JOB_LOCKED"):
        collect(target, transport, sleeper=lambda _: None)
    assert (target / ".collect.lock").read_text() == "other worker"


def test_hash_or_journal_scope_tampering_is_detected(tmp_path):
    target, _ = job(tmp_path)
    collect(target, FakeTransport(), sleeper=lambda _: None)
    journal = read_json((target / "journal.json").read_bytes())
    file = target / next(a["file"] for a in journal["attempts"] if a.get("file"))
    original = file.read_bytes()
    file.write_bytes(original + b" ")
    with pytest.raises(ResearchError, match="RESPONSE_TAMPERED"):
        audit(target)
    file.write_bytes(original)
    journal["attempts"][1]["params"]["FID_INPUT_ISCD"] = "000660"
    (target / "journal.json").write_bytes(canonical(journal))
    with pytest.raises(ResearchError, match="JOURNAL_INVALID"):
        audit(target)


def test_daily_artifact_tampering_is_detected(tmp_path):
    target, _ = job(tmp_path)
    collect(target, FakeTransport(), sleeper=lambda _: None)
    (target / "daily.jsonl").write_bytes(b"{}\n")
    with pytest.raises(ResearchError, match="DAILY_TAMPERED"):
        audit(target, check_daily=True)


def test_unresolved_durable_request_does_not_automatically_repeat(tmp_path):
    target, _ = job(tmp_path)
    planned, _, journal = load_job(target)
    journal["attempts"].append({"number": 1, "kind": "WINDOW", "target": "0", "params": planned["windows"][0],
                                "startedAt": "2026-01-01T00:00:00Z", "status": "IN_FLIGHT"})
    (target / "journal.json").write_bytes(canonical(journal))
    transport = FakeTransport()
    with pytest.raises(ResearchError, match="UNRESOLVED_ATTEMPT"):
        collect(target, transport, sleeper=lambda _: None)
    assert transport.calls == []


def test_transport_uses_only_official_auth_and_daily_endpoints_and_does_not_save_secrets():
    class Response(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
    class Opener:
        def __init__(self): self.requests = []
        def open(self, req, timeout):
            self.requests.append(req)
            if req.full_url.endswith("tokenP"):
                return Response(b'{"access_token":"bearer-token-test"}')
            return Response(page(parameters(config(), date(2024, 1, 2), date(2024, 1, 2))))
    opener = Opener()
    client = KisHistoryTransport("app-key-test", "app-secret-test", opener)
    client.authenticate()
    result = client.fetch(parameters(config(), date(2024, 1, 2), date(2024, 1, 2)))
    assert opener.requests[0].full_url == BASE + "/oauth2/tokenP" and opener.requests[0].method == "POST"
    assert opener.requests[1].full_url.startswith(BASE + DAILY_PATH + "?") and opener.requests[1].method == "GET"
    assert all(secret not in opener.requests[1].full_url for secret in ["app-key-test", "app-secret-test", "bearer-token-test"])
    assert b"bearer-token-test" not in result
    assert NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.test") is None


def test_cli_plan_is_offline_and_rejects_existing_output(tmp_path, capsys):
    cfg = tmp_path / "config.json"
    cfg.write_bytes(canonical(config(queryRightsConfirmed=False).model_dump()))
    args = ["plan", "--config", str(cfg), "--output", str(tmp_path / "job")]
    assert main(args) == 0
    assert main(args) == 2
    assert "HISTORY_FILE_FAILED" in capsys.readouterr().err


def test_future_daily_window_blocks_before_authentication(tmp_path):
    target, _ = job(tmp_path, startDate="2099-01-01", endDate="2099-01-01")
    transport = FakeTransport()
    with pytest.raises(ResearchError, match="CLOSED_DATES_REQUIRED"):
        collect(target, transport, sleeper=lambda _: None)
    assert transport.calls == []


def test_verification_mismatch_does_not_overwrite_collected_prices(tmp_path):
    target, _ = job(tmp_path)
    with pytest.raises(ResearchError, match="VERIFICATION_MISMATCH"):
        collect(target, FakeTransport(mutate_call=6), sleeper=lambda _: None)
    report, rows = audit(target, check_daily=True)
    assert report["status"] == "PARTIAL" and all(row["close"] == "105" for row in rows)


def test_duplicate_completed_target_is_not_counted_twice(tmp_path):
    target, _ = job(tmp_path)
    collect(target, FakeTransport(), sleeper=lambda _: None)
    journal = read_json((target / "journal.json").read_bytes())
    duplicate = copy.deepcopy(journal["attempts"][1])
    duplicate["number"] = len(journal["attempts"]) + 1
    journal["attempts"].append(duplicate)
    (target / "journal.json").write_bytes(canonical(journal))
    with pytest.raises(ResearchError, match="JOURNAL_INVALID"):
        audit(target)


def test_http_failure_never_echoes_provider_body_or_credentials():
    class Opener:
        def open(self, req, timeout):
            raise error.HTTPError(req.full_url, 401, "private-provider-body", {}, None)
    client = KisHistoryTransport("private-key", "private-secret", Opener())
    with pytest.raises(ResearchError) as caught:
        client.authenticate()
    assert str(caught.value) == "HISTORY_HTTP_FAILED"


def test_cli_audit_does_not_misdiagnose_files_during_another_collection(tmp_path, capsys):
    target, _ = job(tmp_path)
    collect(target, FakeTransport(), sleeper=lambda _: None)
    (target / ".collect.lock").write_text("another worker")
    assert main(["audit", "--job", str(target)]) == 2
    assert "HISTORY_JOB_LOCKED" in capsys.readouterr().err
    assert (target / ".collect.lock").read_text() == "another worker"
