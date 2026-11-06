"""Synthetic book scenarios; independent broker fills/costs are never claimed."""
import hashlib
import json

import pytest
from pydantic import ValidationError

import test_tick_audit as tape
from app.replay import tick_quality
from app.replay.__main__ import main
from app.replay.dataset import canonical,digest
from app.replay.models import ResearchError
from app.replay.quote_execution import QuoteExecutionPolicy,QuoteOrder,estimate_quotes
from app.replay.tick_quality import quality_profile,session_evidence
from app.replay.ticks import audit_ticks
from app.replay.intraday import timeline_value, ReplayIntraday

EVIDENCE=("# 시간 구분 코드(0 : 장중 )\n"*2).encode()


@pytest.fixture(autouse=True)
def synthetic_source_pin(monkeypatch):
    monkeypatch.setattr(tick_quality,"SESSION_BLOB",hashlib.sha1(b"blob "+str(len(EVIDENCE)).encode()+b"\0"+EVIDENCE).hexdigest())


def cfg(**changes):return tape.config(regularSessionCodes=["0"],**changes)


def book(at="2025-11-03T00:00:03Z",received="2025-11-03T00:00:03.100000Z",**changes):
    r=tape.row("QUOTE",at=at,received=received,session="0",**changes)
    r["eventId"]=digest((at+received+json.dumps(changes,sort_keys=True)).encode())
    tape.modify(r,eventId=r["eventId"])
    return r


def data(*quotes):
    return canonical(tape.export(tape.row(session="0"),*(quotes or [book()])))


def policy(**changes):
    v=dict(schemaVersion="SAGOPALGO_QUOTE_EXECUTION_V1",availabilityMode="RECEIPT_DERIVED_SCENARIO",
           allowSynthetic=True,allowAnchoredQuoteDate=True,allowUnconfirmedContinuousSession=True,
           initialCash="10000",initialPosition=7,maxOrderNotional="10000",participationRate="1",tickSize="1",
           feeBps="1",sellTaxBps="10",latencyMs=0,maxQuoteAgeMs=2000,
           assumptionsEvidence="SYNTHETIC test assumptions only; not actual fee/tick/continuous-session proof")
    v.update(changes);return QuoteExecutionPolicy.model_validate(v)


def order(**changes):
    v=dict(orderId="a",side="BUY",orderType="MARKET",decisionAt="2025-11-03T00:00:03.200000Z",
           expiresAt="2025-11-03T00:00:05Z",quantity=8)
    v.update(changes);return QuoteOrder.model_validate(v)


def run(raw=None,pol=None,orders=None):return estimate_quotes(raw or data(),cfg(),EVIDENCE,pol or policy(),orders or [order()])


def test_source_hash_and_comment_tamper_rejected():
    assert session_evidence(EVIDENCE)["meaning"]=="INTRADAY_REPORTED"
    with pytest.raises(ResearchError,match="SESSION_SOURCE_EVIDENCE_MISMATCH"):session_evidence(EVIDENCE+b"changed")


def test_cross_feed_anchor_does_not_change_raw_date_or_availability():
    rows,_=audit_ticks(data(),cfg(),[]);profile,q=quality_profile(rows,EVIDENCE)
    quote=next(r for r in profile if r["type"]=="QUOTE")
    assert quote["dateBasis"]=="RECEIVE_DATE_INFERRED" and "UNCONFIRMED_BUSINESS_DATE" in quote["flags"]
    assert quote["dateEvidence"]["status"]=="CROSS_FEED_ANCHORED_ONLY"
    assert quote["knownAt"]=="2025-11-03T00:05:00+00:00"
    assert not q["sessionEvidence"]["continuousMatchingConfirmed"]


@pytest.mark.parametrize("received",["2025-11-03T00:00:04Z","2025-11-03T00:00:00Z"])
def test_future_or_stale_anchor_cannot_confirm_quote_date(received):
    t=tape.row(received=received,session="0")
    raw=canonical(tape.export(t,book()))
    rows,_=audit_ticks(raw,cfg(),[]);profile,_=quality_profile(rows,EVIDENCE,anchor_age_ms=1000)
    assert next(r for r in profile if r["type"]=="QUOTE")["dateEvidence"]["status"]=="UNCONFIRMED"


def test_negative_receipt_lag_preserved_not_corrected():
    rows,_=audit_ticks(data(book(received="2025-11-03T00:00:02.900000Z")),cfg(),[])
    profile,q=quality_profile(rows,EVIDENCE)
    assert q["receiptBeforeMarketCount"]==1 and not q["historicalClockCorrectionApplied"]
    assert next(r for r in profile if r["type"]=="QUOTE")["receiptLagMs"]==pytest.approx(-100)


def test_buy_sweeps_depth_fee_and_cash_exactly():
    r=run();o=r["outcomes"][0]
    assert o["status"]=="ESTIMATED_FILLED" and o["quantityEstimated"]==8
    assert [(f["price"],f["quantity"]) for f in o["fills"]]==[("101",5),("102",3)]
    assert o["notional"]=="811" and o["fee"]=="1" and r["endingCash"]=="9188"
    assert r["endingPosition"]==15 and r["accountFillStatus"]=="NOT_PROVEN"


def test_sell_respects_position_and_tax():
    r=run(orders=[order(side="SELL")]);o=r["outcomes"][0]
    assert o["quantityEstimated"]==7 and o["remainderCancelled"]==1
    assert o["notional"]=="692" and o["fee"]=="1" and o["sellTax"]=="1"
    assert r["endingPosition"]==0 and r["endingCash"]=="10690"


@pytest.mark.parametrize("changes",[dict(side="BUY",orderType="LIMIT",limitPrice="100"),
                                  dict(side="SELL",orderType="LIMIT",limitPrice="100")])
def test_nonmarketable_limit_cancels_without_queue_claim(changes):
    o=run(orders=[order(**changes)])["outcomes"][0]
    assert o["status"]=="ESTIMATED_UNFILLED_IOC" and o["quantityEstimated"]==0 and o["fee"]=="0"


def test_partial_fill_capacity_participation_cash_and_order_caps():
    assert run(orders=[order(quantity=100)])["outcomes"][0]["quantityEstimated"]==50
    assert run(pol=policy(participationRate="0.1"))["outcomes"][0]["quantityEstimated"]==0
    assert run(pol=policy(initialCash="102"))["outcomes"][0]["quantityEstimated"]==1
    assert run(pol=policy(maxOrderNotional="202"))["outcomes"][0]["quantityEstimated"]==2


def test_repeated_snapshot_does_not_replenish_same_price_liquidity():
    q2=book(at="2025-11-03T00:00:04Z",received="2025-11-03T00:00:04.100000Z")
    p=json.loads(q2["payloadJson"])
    for level in p["asks"]:level["price"]+=".00"
    tape.modify(q2,asks=p["asks"])
    r=run(data(book(),q2),orders=[order(quantity=50),order(orderId="b",quantity=1,decisionAt="2025-11-03T00:00:04.200000Z")])
    assert r["outcomes"][0]["quantityEstimated"]==50
    assert r["outcomes"][1]["quantityEstimated"]==0


@pytest.mark.parametrize("pol,reason",[
    (policy(availabilityMode="EXPORT_KNOWN_AT"),"HISTORICAL_AVAILABILITY_UNCONFIRMED"),
    (policy(allowAnchoredQuoteDate=False),"QUOTE_BUSINESS_DATE_UNCONFIRMED"),
    (policy(allowUnconfirmedContinuousSession=False),"CONTINUOUS_SESSION_UNCONFIRMED"),
    (policy(maxQuoteAgeMs=1),"STALE_QUOTE"),
    (policy(latencyMs=2000),"EXPIRED_BEFORE_ATTEMPT")])
def test_unconfirmed_quality_and_latency_do_not_consume_resources(pol,reason):
    r=run(pol=pol);o=r["outcomes"][0]
    assert o["status"]=="NOT_ASSESSABLE" and reason in o["reasons"]
    assert r["endingCash"]==pol.initialCash and r["endingPosition"]==pol.initialPosition


def test_future_negative_and_ambiguous_quotes_cannot_fill():
    for raw,reason in [
        (data(book(at="2025-11-03T00:00:04Z",received="2025-11-03T00:00:04Z")),"NO_VISIBLE_QUOTE"),
        (data(book(received="2025-11-03T00:00:02.900000Z")),"RECEIPT_BEFORE_MARKET_TIME"),
        (data(book(),book(received="2025-11-03T00:00:03.110000Z")),"AMBIGUOUS_QUOTE_ORDER")]:
        assert reason in run(raw)["outcomes"][0]["reasons"]


def test_gap_at_decision_and_stale_book_across_reconnect_are_blocked():
    p=policy(captureGaps=[{"startAt":"2025-11-03T00:00:03.150000Z","endAt":"2025-11-03T00:00:03.180000Z"}])
    assert "QUOTE_BEFORE_CAPTURE_GAP" in run(pol=p)["outcomes"][0]["reasons"]
    p=policy(latencyMs=100,captureGaps=[{"startAt":"2025-11-03T00:00:03.150000Z","endAt":"2025-11-03T00:00:03.250000Z"}])
    assert "DECISION_DURING_CAPTURE_GAP" in run(pol=p)["outcomes"][0]["reasons"]


def test_client_receipt_order_is_explicit_scenario_and_equal_receipt_still_ambiguous():
    raw=data(book(),book(received="2025-11-03T00:00:03.110000Z"))
    assert run(raw,pol=policy(quoteOrdering="CLIENT_RECEIPT_SCENARIO"))["outcomes"][0]["status"]=="ESTIMATED_FILLED"
    with pytest.raises(ValidationError):policy(quoteOrdering="CLIENT_RECEIPT_SCENARIO",availabilityMode="EXPORT_KNOWN_AT")
    q1=book();q2=book();q2["eventId"]=digest(b"same-receipt-different-frame")
    tape.modify(q2,eventId=q2["eventId"])
    assert "AMBIGUOUS_QUOTE_ORDER" in run(data(q1,q2),pol=policy(quoteOrdering="CLIENT_RECEIPT_SCENARIO"))["outcomes"][0]["reasons"]


def test_assumed_tick_grid_rejects_misaligned_limit_before_costs():
    r=run(pol=policy(tickSize="10"),orders=[order(orderType="LIMIT",limitPrice="103")])
    assert r["outcomes"][0]["reasons"]==["PRICE_OFF_ASSUMED_TICK_GRID"] and r["endingCash"]=="10000"


def test_sell_fee_rounding_cannot_overdraw_zero_cash():
    q=book(bids=[{"price":"1","quantity":"1"}]+[{"price":"0","quantity":"0"} for _ in range(9)])
    r=run(data(q),pol=policy(initialCash="0",initialPosition=1,feeBps="1",sellTaxBps="1"),orders=[order(side="SELL",quantity=1)])
    # Notional 1, rounded fee 1 + tax 1: a sale cannot fund both without cash.
    assert r["endingCash"]=="0" and r["endingPosition"]==1 and not r["outcomes"][0]["fills"]
    r=run(data(q),pol=policy(initialCash="1",initialPosition=1,feeBps="1",sellTaxBps="1"),orders=[order(side="SELL",quantity=1)])
    assert r["endingCash"]=="0" and r["endingPosition"]==0 and r["outcomes"][0]["quantityEstimated"]==1


@pytest.mark.parametrize("change",[dict(tickSize="0"),dict(participationRate="1.1"),dict(feeBps="10001"),dict(initialPosition=-1)])
def test_policy_validation(change):
    with pytest.raises(ValidationError):policy(**change)


def test_duplicates_scope_and_synthetic_require_explicit_opt_in():
    with pytest.raises(ResearchError,match="ORDER_ID_OR_COUNT_INVALID"):run(orders=[order(),order()])
    with pytest.raises(ResearchError,match="QUOTE_ORDER_OUTSIDE_SAMPLE"):run(orders=[order(expiresAt="2025-11-03T00:03:00Z")])
    with pytest.raises(ResearchError,match="SYNTHETIC_OPT_IN_REQUIRED"):run(pol=policy(allowSynthetic=False))


def test_cli_profile_and_scenario_preserve_inputs_and_refuse_overwrite(tmp_path,monkeypatch,capsys):
    import socket
    def blocked(*a,**kw):raise AssertionError("network forbidden")
    monkeypatch.setattr(socket.socket,"connect",blocked)
    files={"raw.json":data(),"config.json":canonical(cfg().model_dump(mode="json")),"source.txt":EVIDENCE,
           "policy.json":canonical(policy().model_dump(mode="json")),"orders.json":canonical([order().model_dump(mode="json")])}
    for name,raw in files.items():(tmp_path/name).write_bytes(raw)
    common=["--input",str(tmp_path/"raw.json"),"--config",str(tmp_path/"config.json"),"--session-evidence",str(tmp_path/"source.txt")]
    args=["quote-scenario",*common,"--policy",str(tmp_path/"policy.json"),"--orders",str(tmp_path/"orders.json"),"--output",str(tmp_path/"result.json")]
    assert main(args)==0 and main(args)==2
    assert main(["profile-ticks",*common,"--output",str(tmp_path/"profile.json")])==0
    assert all((tmp_path/name).read_bytes()==raw for name,raw in files.items())


@pytest.mark.parametrize("kind,order_class,blocked",[("HALT","ORDINARY",True),("REOPENING_AUCTION","ORDINARY",True),
    ("PROGRAM_BUY_PAUSE","PROGRAM",True),("PROGRAM_BUY_PAUSE","ORDINARY",False),("PROGRAM_SELL_PAUSE","PROGRAM",False)])
def test_explicit_scenario_never_overrides_bound_known_restriction(kind,order_class,blocked):
    timeline=timeline_value(dict(schemaVersion="SAGOPALGO_INTRADAY_TIMELINE_V1",sourceDecisionSha256="0"*64,
        provenance="SYNTHETIC",createdAt="2025-11-03T00:10:00Z",allIntradayInterruptionsComplete=False,
        usableForTrading=False,usableForStrategyValidation=False,
        days=[dict(market="KOSPI",businessDate="2025-11-03",coverage="COMPLETE",knownAt="2025-11-02T00:00:00Z",
                   openAt="2025-11-03T00:00:00Z",closeAt="2025-11-03T06:00:00Z")],
        phases=[dict(phaseId="p1",market="KOSPI",businessDate="2025-11-03",kind=kind,
                     startAt="2025-11-03T00:00:03Z",endAt="2025-11-03T00:00:04Z",knownAt="2025-11-02T00:00:00Z",
                     evidence=["https://synthetic.test/phase"],bodySha256s=["a"*64])]))
    binding=ReplayIntraday.model_validate(dict(timeline=timeline.model_dump(mode="json"),
        timelineSha256=digest(canonical(timeline.model_dump(mode="json"))),market="KOSPI",orderClass=order_class))
    r=estimate_quotes(data(),cfg(),EVIDENCE,policy(),[order()],binding)
    if blocked:
        assert r["outcomes"][0]["status"]=="NOT_ASSESSABLE" and r["endingCash"]=="10000"
        assert r["outcomes"][0]["intraday"]["stage"]=="DECISION"
    else:assert r["outcomes"][0]["status"]=="ESTIMATED_FILLED"
