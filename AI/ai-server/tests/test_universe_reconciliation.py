"""Evidence levels, ISIN identity, conflicting dates and retrospective availability."""
import pytest

from app.replay import krx_universe_history as history, kind_membership_status as status, universe_reconciliation as ledger
from app.replay.dataset import canonical, digest, read_bytes, read_json
from app.replay.krx_baseline_validation import immutable_json
from app.replay.models import ResearchError
from test_krx_universe import response, row
from test_krx_universe_history import Client, Reservations
from test_kind_membership_status import page

AT = "2026-11-04T12:00:00Z"


def issue(symbol="000010", market="KOSPI", name="가상회사"):
    return {"symbol":symbol,"isin":"KR"+symbol+"0001","market":market,"name":name,
            "classification":"COMMON_SHARE","sourceRowSha256":"a"*64}


def observation(kind="ADDED_OBSERVED", before=None, after=None):
    if kind == "ADDED_OBSERVED": after = after or issue()
    if kind == "REMOVED_OBSERVED": before = before or issue()
    if kind == "MARKET_TRANSFER_OBSERVED":
        before, after = before or issue(market="KOSDAQ"), after or issue()
    return {"kind":kind,"isin":(after or before)["isin"],"before":before,"after":after,
            "observedFrom":"2024-01-02","observedTo":"2024-01-03","knownAt":AT,
            "emptyResponseDatesBetween":[],"legalEventConfirmed":False,"effectiveDate":None}


def source_row(kind="LISTING", market="KOSPI", key="00001", name="가상회사", stamp="2024-01-03", event_type="신규상장"):
    return {"kind":kind,"market":market,"providerIssuerKey":key,"issuerName":name,"date":stamp,
            "eventType":event_type,"knownAt":AT,"sourceSha256":"b"*64,"sourceRowSha256":"c"*64}


def resolve(obs, refs, facts=(), names=None, ambiguous=False):
    isin = obs["isin"]
    rows, used = ledger.reconcile([obs],{"records":refs},list(facts),{isin:set(names or ["가상회사"])},{isin:AT},
                                  {digest(canonical(obs))} if ambiguous else set())
    return rows[0], used


def test_status_match_is_retrospective_and_does_not_mutate_observation_or_confirm_legal_effects():
    obs = observation()
    frozen = canonical(obs)
    result, used = resolve(obs,[source_row()])
    assert result["resolution"] == "STATUS_LIST_MATCH" and len(used) == 1
    assert not result["membershipDateConfirmedByDisclosure"] and result["exchangeMembershipDate"] is None
    assert not result["allLegalEffectsConfirmed"] and not result["usableForTraining"]
    assert canonical(obs) == frozen and canonical(result["observation"]) == frozen


@pytest.mark.parametrize("change,expected", [({"name":"different"},"STATUS_IDENTITY_REVIEW"),
    ({"stamp":"2024-01-04"},"STATUS_DATE_CONFLICT"),({"stamp":"2024-01-02"},"STATUS_DATE_CONFLICT"),
    ({"market":"KOSDAQ"},"NO_STATUS_EVIDENCE"),({"key":"00002"},"ISSUER_KEY_MAPPING_REQUIRED"),
    ({"event_type":"재상장 폐지"},"STATUS_EVENT_TYPE_CONFLICT")])
def test_candidates_require_matching_identity_market_window_and_event_type(change, expected):
    result, used = resolve(observation(),[source_row(**change)])
    assert result["resolution"] == expected and not used


def test_prefix_collision_and_duplicate_candidates_are_never_auto_approved():
    result, _ = resolve(observation(),[source_row()],ambiguous=True)
    assert result["resolution"] == "STATUS_IDENTITY_REVIEW"
    result, _ = resolve(observation(),[source_row(),source_row()])
    assert result["resolution"] == "STATUS_IDENTITY_REVIEW"


def test_transfer_needs_both_markets_and_transfer_reason():
    obs = observation("MARKET_TRANSFER_OBSERVED")
    refs = [source_row(event_type="이전상장"),source_row("DELISTING","KOSDAQ",event_type="유가증권시장 상장")]
    assert resolve(obs,refs)[0]["resolution"] == "STATUS_LIST_MATCH"
    assert resolve(obs,refs[:1])[0]["resolution"] == "NO_STATUS_EVIDENCE"
    refs[1]["eventType"] = "피흡수합병"
    assert resolve(obs,refs)[0]["resolution"] == "STATUS_EVENT_TYPE_CONFLICT"


def fact(stamp="2024-01-03"):
    return {"caseId":"test-ipo","kind":"IPO","stockCode":"000010","market":"KOSPI","date":stamp,
            "knownAt":AT,"dateBasis":"LISTING_DATE","sourceUrl":"https://kind.krx.co.kr/example", "sourceSha256":"d"*64}


def test_audited_disclosure_has_separate_evidence_level_and_conflicts_are_preserved():
    result, _ = resolve(observation(),[source_row()],[fact()])
    assert result["resolution"] == "DISCLOSURE_MATCH" and result["membershipDateConfirmedByDisclosure"]
    assert result["exchangeMembershipDate"] == "2024-01-03" and not result["allLegalEffectsConfirmed"]
    assert resolve(observation(),[source_row(stamp="2024-01-04")],[fact()])[0]["resolution"] == "EVIDENCE_CONFLICT"
    assert resolve(observation(),[source_row()],[fact("2024-01-04")])[0]["resolution"] == "DISCLOSURE_DATE_OR_IDENTITY_CONFLICT"
    assert resolve(observation(),[],[fact()])[0]["resolution"] == "DISCLOSURE_MATCH"


def test_name_change_aliases_do_not_confirm_name_change_dates_or_reused_code_isins():
    obs = observation("NAME_CHANGE_OBSERVED",before=issue(name="old"),after=issue(name="new"))
    assert resolve(obs,[source_row(name="new")],names=["old","new"])[0]["resolution"] == "NAME_CHANGE_NEEDS_DISCLOSURE"
    # A different ISIN has no access to the original issue's names.
    new = observation(after={**issue(),"isin":"KR9999990001"})
    rows, _ = ledger.reconcile([new],{"records":[source_row()]},[],{obs["isin"]:{"가상회사"}},{obs["isin"]:AT})
    assert rows[0]["resolution"] == "STATUS_IDENTITY_REVIEW"


def setup_history(tmp_path, collision=False):
    job = tmp_path / "history"
    history.prepare(job,"2024-01-02","2024-01-04",source_kind="SYNTHETIC")
    def r(symbol, market="KOSPI", name=None):
        return row(market,symbol,ISU_NM=name or "가상"+symbol,ISU_ABBRV=name or "가상"+symbol)
    values = {}
    for stamp in ["2024-01-02","2024-01-03","2024-01-04"]:
        kospi = [r("000010",name="새이름" if stamp=="2024-01-04" else "가상000010")]
        if collision: kospi.append(r("000015"))
        if stamp >= "2024-01-03": kospi.append(r("000030"))
        values[(stamp,"KOSPI")] = response(kospi)
        values[(stamp,"KOSDAQ")] = response([r("000040" if stamp=="2024-01-04" else "000020","KOSDAQ")])
    history.collect(job,Client(values),Reservations(),6)
    derived = tmp_path / "derived"
    history.build(job,derived)
    status_job = tmp_path / "status"
    status.prepare(status_job,"2024-01-02","2024-01-04","SYNTHETIC")
    class TableClient:
        source_kind = "SYNTHETIC"
        def fetch(self, source):
            kind,market = source["kind"],source["market"]
            items = []
            if kind == "LISTING":
                symbol,stamp = ("000030","2024-01-03") if market=="KOSPI" else ("000040","2024-01-04")
                items = [{"key":symbol[:5],"date":stamp,"name":"가상"+symbol,"type":"신규상장"}]
            elif market == "KOSDAQ":
                items = [{"key":"00002","date":"2024-01-04","name":"가상000020","type":"폐지"}]
            return page(kind,market,items)
    status.capture(status_job,TableClient(),4,sleep=lambda _:None)
    empty = {"startDate":"2024-01-02","endDate":"2024-01-04","facts":[]}
    return job,derived,status_job,empty


def test_complete_build_preserves_all_observation_ids_alias_lineage_and_unresolved_names(tmp_path):
    job,derived,status_job,empty = setup_history(tmp_path)
    result = ledger.build(job,derived,status_job,empty,empty)
    assert result["observations"] == 4 and result["membershipObservations"] == result["membershipMatched"] == 3
    assert result["resolutionCounts"] == {"STATUS_LIST_MATCH":3,"NAME_CHANGE_NEEDS_DISCLOSURE":1}
    assert result["unresolvedObservations"] == 1 and result["sourceKind"] == "SYNTHETIC"
    originals = [read_json(v) for v in read_bytes(derived / "changes.jsonl").splitlines()]
    assert [v["observation"] for v in result["rows"]] == originals
    assert not result["independentTotalVerified"] and not result["marketUniverseComplete"]
    assert ledger.as_of(result,"2024-01-04T23:59:59+09:00")["visibleObservations"] == 0
    assert ledger.as_of(result,"2099-01-01T00:00:00Z","000030")["visibleObservations"] == 1
    path = tmp_path / "ledger.json"
    immutable_json(path,result)
    assert ledger.build(job,derived,status_job,empty,empty) == result
    path.write_bytes(read_bytes(path)+b" ")
    with pytest.raises(ResearchError,match="TAMPERED"):
        immutable_json(path,result,True)


def test_actual_prefix_ambiguity_is_detected_from_raw_common_shares(tmp_path):
    job,derived,_,_ = setup_history(tmp_path,collision=True)
    obs = [read_json(v) for v in read_bytes(derived / "changes.jsonl").splitlines()]
    _,_,_,ambiguous = ledger.history_aliases(job,obs)
    changed_name = next(v for v in obs if v["kind"] == "NAME_CHANGE_OBSERVED")
    assert digest(canonical(changed_name)) in ambiguous


@pytest.mark.parametrize("target", ["history", "status", "scope"])
def test_mutated_inputs_and_evidence_scope_are_rejected(tmp_path,target):
    job,derived,status_job,empty = setup_history(tmp_path)
    if target == "history":
        path = derived / "days" / "2024-01-02.json"
        path.write_bytes(read_bytes(path)+b" ")
    if target == "status":
        (status_job / "raw" / "1.html").write_bytes(b"mutated")
    if target == "scope":
        empty = {**empty,"endDate":"2024-01-05"}
    with pytest.raises(ResearchError):
        ledger.build(job,derived,status_job,empty,empty)


def test_cli_as_of_recomputes_and_rejects_mutated_output_before_showing_records(tmp_path,monkeypatch,capsys):
    report = {"rows":[resolve(observation(),[source_row()])[0]]}
    path = tmp_path / "report.json"
    immutable_json(path,report)
    monkeypatch.setattr(ledger.kind_cases,"load_scope",lambda _:None)
    monkeypatch.setattr(ledger.universe_events,"load_scope",lambda _:None)
    monkeypatch.setattr(ledger.kind_cases,"audit_report",lambda *_:{})
    monkeypatch.setattr(ledger.universe_events,"audit_report",lambda *_:{})
    calls = []
    def rebuild(*args):
        calls.append(args)
        return report
    monkeypatch.setattr(ledger,"build",rebuild)
    args = ["as-of","--output",str(path),"--at","2024-01-03T00:00:00Z"]
    for flag in ["history-job","history-derived","status-job","cases","case-report","events","event-report","cache"]:
        args += ["--"+flag,str(tmp_path)]
    assert ledger.main(args) == 0 and '"visibleObservations": 0' in capsys.readouterr().out
    altered = read_json(read_bytes(path))
    altered["rows"][0]["knownAt"] = "2020-01-01T00:00:00Z"
    path.write_bytes(canonical(altered))
    assert ledger.main(args) == 2 and "TAMPERED" in capsys.readouterr().out
    assert len(calls) == 2
