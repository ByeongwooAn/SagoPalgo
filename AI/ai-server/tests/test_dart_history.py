import copy
import io
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from app.replay.dart_history import Transport, audit, collect, instrument_scope, load_job, main, prepare
from app.replay.dataset import canonical, digest
from app.replay.history import job_lock
from app.replay.local_use import bind_local_use
from app.replay.models import ResearchError
from test_reference import collected


def job(tmp_path, max_requests=12):
    source = tmp_path / "prices"
    source.mkdir()
    history, _, _ = collected(source)
    scope = tmp_path / "local-use.json"
    bind_local_use(history, scope)
    target = tmp_path / "dart"
    prepare(history, scope, "00126380", target, max_requests)
    return target


def row(index=0, **changes):
    value = {"corp_code": "00126380", "stock_code": "005930", "corp_cls": "Y", "corp_name": "가상 회사",
             "rcept_no": "20240102" + f"{index:06d}", "rcept_dt": "20240102", "report_nm": "현금ㆍ현물배당 결정", "rm": "유"}
    value.update(changes)
    return value


def page(number=1, total=101):
    first, last = (number - 1) * 100, min(number * 100, total)
    return {"status": "000", "page_no": number, "page_count": 100, "total_count": total,
            "total_page": max(1, (total + 99) // 100), "list": [row(index) for index in range(first, last)]}


class FakeTransport:
    fingerprint = digest(b"fake-dart-key")

    def __init__(self, fail_call=None, change=None):
        self.calls = []
        self.fail_call = fail_call
        self.change = change

    def fetch(self, endpoint, params):
        self.calls.append((endpoint, params))
        if len(self.calls) == self.fail_call:
            raise ResearchError("DART_HTTP_FAILED")
        if endpoint == "company":
            value = {"status": "000", "stock_code": "005930", "corp_cls": "Y"}
        elif params["pblntf_ty"] == "I":
            value = {"status": "013", "message": "조회된 데이터 없음"}
        else:
            value = page(int(params["page_no"]))
        if self.change:
            self.change(endpoint, params, value)
        return canonical(value)


def test_complete_index_is_issuer_bound_date_only_and_not_an_effective_action_or_universe(tmp_path):
    target = job(tmp_path)
    transport = FakeTransport()
    report = collect(target, transport, sleeper=lambda _: None)
    assert report["uniqueReceipts"] == 101 and report["reviewCandidates"] == 101 and report["callsUsed"] == 4
    assert report["queryScopes"]["I"]["providerStatus"] == "013"
    assert report["currentIssuer"]["corpClass"] == "Y" and report["referenceEventsEmitted"] == 0
    assert not report["historicalUniverseComplete"] and not report["corporateActionsComplete"] and not report["usableForTraining"]
    entries = [json.loads(line) for line in (target / "disclosures.jsonl").read_bytes().splitlines()]
    assert all(r["publishedAt"] is None and r["effectiveDate"] is None and r["knownAt"] == r["observedAt"] for r in entries)
    assert all(r["datePrecision"] == "DATE" and r["reviewState"] == "ORIGINAL_DOCUMENT_REQUIRED" for r in entries)
    assert all(params["last_reprt_at"] == "N" for endpoint, params in transport.calls if endpoint == "list")
    assert audit(target) == report
    assert collect(target, transport, sleeper=lambda _: None) == report and len(transport.calls) == 4


def test_explicit_retry_reuses_captured_pages_and_counts_failed_attempts_in_same_budget(tmp_path):
    target = job(tmp_path)
    first = FakeTransport(fail_call=3)
    with pytest.raises(ResearchError, match="HTTP_FAILED"):
        collect(target, first, sleeper=lambda _: None)
    assert audit(target)["status"] == "PARTIAL"
    assert not (target / "disclosures.jsonl").exists()
    second = FakeTransport()
    result = collect(target, second, sleeper=lambda _: None)
    assert result["callsUsed"] == 5 and len(second.calls) == 2
    assert second.calls[0][1]["page_no"] == "2"
    assert audit(target) == result


def test_budget_exhaustion_never_sends_an_unreserved_request(tmp_path):
    target = job(tmp_path, max_requests=3)
    transport = FakeTransport()
    with pytest.raises(ResearchError, match="BUDGET_EXHAUSTED"):
        collect(target, transport, sleeper=lambda _: None)
    assert len(transport.calls) == 3 and len(load_job(target)[2]["attempts"]) == 3
    with pytest.raises(ResearchError, match="BUDGET_EXHAUSTED"):
        collect(target, transport, sleeper=lambda _: None)
    assert len(transport.calls) == 3


@pytest.mark.parametrize("change,code", [
    (lambda d: d.update(page_no=2), "PAGE_DRIFT"),
    (lambda d: d.update(page_count=20), "PAGE_DRIFT"),
    (lambda d: d.update(total_page=5), "PAGE_DRIFT"),
    (lambda d: d.update(total_count=True), "PAGINATION_INVALID"),
    (lambda d: d["list"].pop(), "PAGE_LENGTH_INVALID"),
    (lambda d: d["list"][0].update(corp_code="99999999"), "ROW_ISSUER_MISMATCH"),
    (lambda d: d["list"][0].update(stock_code="000001"), "ROW_ISSUER_MISMATCH"),
    (lambda d: d["list"][0].update(rcept_dt="20240104"), "ROW_INVALID"),
    (lambda d: d["list"][0].update(rcept_no="invalid"), "RECEIPT_INVALID"),
    (lambda d: d["list"][0].update(rm=None), "ROW_INVALID"),
    (lambda d: d["list"].__setitem__(1, copy.deepcopy(d["list"][0])), "DUPLICATE_RECEIPT"),
], ids=["wrong-page", "wrong-size", "wrong-total", "boolean-count", "missing-row", "wrong-corp", "wrong-stock", "outside-window", "bad-receipt", "bad-remarks", "overlap"])
def test_invalid_page_never_publishes_complete_index(tmp_path, change, code):
    target = job(tmp_path)
    def mutate(endpoint, params, value):
        if endpoint == "list" and params["pblntf_ty"] == "B": change(value)
    with pytest.raises(ResearchError, match=code):
        collect(target, FakeTransport(change=mutate), sleeper=lambda _: None)
    assert not (target / "report.json").exists()


def test_changed_pagination_totals_are_detected_before_accepting_later_page(tmp_path):
    target = job(tmp_path)
    def mutate(endpoint, params, value):
        if endpoint == "list" and params.get("page_no") == "2": value.update(total_count=102)
    with pytest.raises(ResearchError, match="PAGE_DRIFT"):
        collect(target, FakeTransport(change=mutate), sleeper=lambda _: None)


def test_wrong_current_company_mapping_stops_before_historical_requests(tmp_path):
    target = job(tmp_path)
    def mutate(endpoint, params, value):
        if endpoint == "company": value["stock_code"] = "000001"
    transport = FakeTransport(change=mutate)
    with pytest.raises(ResearchError, match="ISSUER_MISMATCH"):
        collect(target, transport, sleeper=lambda _: None)
    assert len(transport.calls) == 1


def test_corrections_withdrawals_and_company_divisions_are_preserved_without_parent_guess(tmp_path):
    target = job(tmp_path)
    def mutate(endpoint, params, value):
        if endpoint == "list" and params["pblntf_ty"] == "B" and params["page_no"] == "1":
            value["list"][0].update(report_nm="[기재정정]회사분할 결정", rm="유정철")
    report = collect(target, FakeTransport(change=mutate), sleeper=lambda _: None)
    first = json.loads((target / "disclosures.jsonl").read_bytes().splitlines()[0])
    assert first["correctionIndicated"] and first["withdrawalIndicated"] and first["parentReceiptNumber"] is None
    assert first["categories"] == ["CORPORATE_DIVISION_NOTICE"]
    assert report["uniqueReceipts"] == 101 and report["withdrawalIndications"] == 1


def test_overseas_or_subsidiary_title_does_not_imply_domestic_listing_membership():
    assert instrument_scope("주요사항보고서(해외 증권시장 주권등 상장폐지결정)") == "OVERSEAS_SECURITIES"
    assert instrument_scope("상장폐지 결정(종속회사의 주요경영사항)") == "SUBSIDIARY"
    assert instrument_scope("상장폐지 결정") == "UNVERIFIED"


@pytest.mark.parametrize("name", ["raw/0001.json", "disclosures.jsonl", "report.json"])
def test_offline_audit_detects_raw_or_derived_tampering(tmp_path, name):
    target = job(tmp_path)
    collect(target, FakeTransport(), sleeper=lambda _: None)
    (target / name).write_bytes(b"{}")
    with pytest.raises(ResearchError, match="TAMPERED"):
        audit(target)


def test_plan_binding_lock_and_key_scope_are_enforced(tmp_path):
    target = job(tmp_path)
    with job_lock(target):
        with pytest.raises(ResearchError, match="LOCKED"): collect(target, FakeTransport())
        with pytest.raises(ResearchError, match="LOCKED"): audit(target)
    collect(target, FakeTransport(), sleeper=lambda _: None)
    other = FakeTransport()
    other.fingerprint = "other-key"
    with pytest.raises(ResearchError, match="KEY_SCOPE_MISMATCH"):
        collect(target, other)
    plan = json.loads((target / "plan.json").read_bytes())
    plan["config"]["stockCode"] = "000001"
    (target / "plan.json").write_bytes(canonical(plan))
    with pytest.raises(ResearchError, match="PLAN_TAMPERED"):
        audit(target)


class Opener:
    def __init__(self, body=b'{"status":"013"}', fail=False): self.calls = []; self.body = body; self.fail = fail
    def open(self, req, timeout):
        self.calls.append(req)
        if self.fail: raise OSError(req.full_url)
        return io.BytesIO(self.body)


def test_fixed_official_transport_redacts_query_key_errors_and_secret_echo(tmp_path):
    key = "a" * 40
    opener = Opener(fail=True)
    client = Transport(key, True, opener)
    with pytest.raises(ResearchError) as caught:
        client.fetch("company", {"corp_code": "00126380"})
    assert str(caught.value) == "DART_HTTP_FAILED" and key not in str(caught.value)
    req = opener.calls[0]
    assert req.full_url.startswith("https://opendart.fss.or.kr/api/company.json?")
    assert parse_qs(urlsplit(req.full_url).query)["crtfc_key"] == [key]
    assert req.method == "GET" and req.data is None
    with pytest.raises(ResearchError, match="SENSITIVE_RESPONSE"):
        Transport(key, True, Opener(key.encode())).fetch("company", {})
    with pytest.raises(ResearchError, match="DISABLED"): Transport(key)


def test_empty_status_does_not_claim_no_corporate_actions(tmp_path):
    target = job(tmp_path)
    def mutate(endpoint, params, value):
        if endpoint == "list": value.clear(); value.update(status="013")
    report = collect(target, FakeTransport(change=mutate), sleeper=lambda _: None)
    assert report["uniqueReceipts"] == 0 and not report["corporateActionsComplete"]
    assert report["queryScopes"]["B"]["providerStatus"] == "013"


def test_cli_audit_needs_no_credentials_and_default_collect_is_disabled(tmp_path, monkeypatch, capsys):
    target = job(tmp_path)
    monkeypatch.delenv("SAGOPALGO_OPEN_DART_ENABLED", raising=False)
    monkeypatch.delenv("SAGOPALGO_OPEN_DART_API_KEY", raising=False)
    assert main(["audit", "--job", str(target)]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "PARTIAL"
    assert main(["collect", "--job", str(target)]) == 2
    assert json.loads(capsys.readouterr().err)["code"] == "DART_DISABLED"
