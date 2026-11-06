"""Commit/publication observations are clock-domain bound, never fabricated for V1."""
import copy
import hashlib

import pytest
from pydantic import ValidationError

import test_tick_audit as tape
import test_quote_execution as book
import test_stored_conversion as stored_test
from app.replay import tick_quality
from app.replay.__main__ import main
from app.replay.dataset import canonical,known_at
from app.replay.models import utc
from app.replay.quote_execution import estimate_quotes,QuoteExecutionPolicy
from app.replay.stored import convert,StoredExportV2
from app.replay.ticks import audit_ticks,observed_snapshot

DOMAIN="11111111-1111-4111-8111-111111111111"
OTHER="22222222-2222-4222-8222-222222222222"


@pytest.fixture(autouse=True)
def synthetic_pin(monkeypatch):
    raw=book.EVIDENCE
    monkeypatch.setattr(tick_quality,"SESSION_BLOB",hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest())


def fixture():
    value=tape.export(tape.row(session="0"),book.book())
    value["schemaVersion"]="SAGOPALGO_STORED_EXPORT_V2"
    for row,commit,published in zip(value["streamEvents"],["02.010000","03.150000"],["02.020000","03.160000"]):
        row["availability"]=dict(contentHash=row["contentHash"],clockDomain=DOMAIN,
            commitObservedAt="2025-11-03T00:00:"+commit+"Z",inputPublishedAt="2025-11-03T00:00:"+published+"Z",
            commitElapsedNanos=100,publishedElapsedNanos=200,clockQuality="MONOTONIC_STABLE",
            clockBasis="JVM_MONOTONIC_ANCHORED_UTC",utcSynchronized=False)
    return value


def policy(**changes):
    return book.policy(availabilityMode="INPUT_PUBLICATION_OBSERVED",decisionClockDomain=DOMAIN,**changes)


def test_snapshot_is_inclusive_only_at_observed_publication_and_matching_clock():
    raw=canonical(fixture());cfg=book.cfg()
    before=observed_snapshot(raw,cfg,utc("2025-11-03T00:00:03.159999Z"),DOMAIN)
    at=observed_snapshot(raw,cfg,utc("2025-11-03T00:00:03.160000Z"),DOMAIN)
    assert [r["type"] for r in before["records"]]==["TRADE"]
    assert len(at["records"])==2
    assert all(utc(r["knownAt"])<=utc(at["at"]) for r in at["records"])
    assert all(r["exportObservedAt"]=="2025-11-03T00:05:00+00:00" for r in at["records"])
    assert observed_snapshot(raw,cfg,utc("2025-11-03T00:01:00Z"),OTHER)["records"]==[]
    assert not at["utcSynchronized"] and not at["usableForTrading"]


def test_old_rows_and_clock_step_have_no_invented_availability():
    value=fixture();value["streamEvents"][0].pop("availability")
    value["streamEvents"][1]["availability"]["clockQuality"]="CLOCK_STEP_DETECTED"
    assert observed_snapshot(canonical(value),book.cfg(),utc("2025-11-03T00:01:00Z"),DOMAIN)["records"]==[]
    assert observed_snapshot(canonical(tape.export(tape.row())),book.cfg(),utc("2025-11-03T00:01:00Z"),DOMAIN)["records"]==[]


@pytest.mark.parametrize("edit",[
    {"contentHash":"0"*64},{"commitObservedAt":"2025-11-03T00:01:00Z"},
    {"publishedElapsedNanos":0},{"utcSynchronized":True},{"clockDomain":"unbound"},
    {"clockBasis":"TRUSTED_UTC"}])
def test_forged_binding_order_or_clock_claim_is_rejected(edit):
    value=fixture();value["streamEvents"][1]["availability"].update(edit)
    with pytest.raises(ValidationError):audit_ticks(canonical(value),book.cfg(),[])


def test_new_receipt_does_not_implicitly_change_legacy_export_known_at():
    records,_=audit_ticks(canonical(fixture()),book.cfg(),[])
    assert all(r["knownAt"]=="2025-11-03T00:05:00+00:00" for r in records)
    assert "decisionClockDomain" not in book.run()["policy"]


def test_actual_publication_mode_blocks_before_marker_and_allows_after_with_explicit_other_assumptions():
    raw=canonical(fixture());cfg=book.cfg()
    before=estimate_quotes(raw,cfg,book.EVIDENCE,policy(),[book.order(decisionAt="2025-11-03T00:00:03.159999Z")])
    after=estimate_quotes(raw,cfg,book.EVIDENCE,policy(),[book.order(decisionAt="2025-11-03T00:00:03.160000Z")])
    assert before["outcomes"][0]["reasons"]==["OBSERVED_PUBLICATION_NOT_VISIBLE"]
    assert after["outcomes"][0]["status"]=="ESTIMATED_FILLED"
    assert after["causalAvailability"]=="INPUT_PUBLICATION_SAME_CLOCK_DOMAIN"
    assert not after["usableForStrategyValidation"]


def test_date_anchor_also_requires_its_own_published_evidence():
    value=fixture();value["streamEvents"][0].pop("availability")
    r=estimate_quotes(canonical(value),book.cfg(),book.EVIDENCE,policy(),[book.order()])
    assert "DATE_ANCHOR_NOT_PUBLISHED" in r["outcomes"][0]["reasons"]


def test_observation_mode_requires_domain_and_cannot_leak_into_old_mode():
    with pytest.raises(ValidationError):book.policy(availabilityMode="INPUT_PUBLICATION_OBSERVED")
    with pytest.raises(ValidationError):book.policy(decisionClockDomain=DOMAIN)


def test_v2_converter_remains_export_conservative_by_default():
    v=fixture();v["streamEvents"]=v["streamEvents"][:1]
    tape.modify(v["streamEvents"][0],session="R")
    v["streamEvents"][0]["availability"]["contentHash"]=v["streamEvents"][0]["contentHash"]
    spec,records,_=convert(canonical(v),stored_test.config())
    assert records and all(known_at(r,spec)==utc("2025-11-03T00:05:00Z") for r in records)


def test_snapshot_cli_is_offline_and_exclusive(tmp_path,monkeypatch):
    import socket
    def blocked(*a,**kw):raise AssertionError("network forbidden")
    monkeypatch.setattr(socket.socket,"connect",blocked)
    inp,cfg,out=tmp_path/"input.json",tmp_path/"config.json",tmp_path/"result.json"
    inp.write_bytes(canonical(fixture()));cfg.write_bytes(canonical(book.cfg().model_dump(mode="json")))
    args=["snapshot-inputs","--input",str(inp),"--config",str(cfg),"--at","2025-11-03T00:00:03.160000Z","--clock-domain",DOMAIN,"--output",str(out)]
    assert main(args)==0
    saved=out.read_bytes();assert main(args)==2 and out.read_bytes()==saved
