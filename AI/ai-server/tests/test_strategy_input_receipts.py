"""Independent producer/consumer clock domains and actual consumer gate, all synthetic."""
from datetime import timedelta
from urllib.parse import parse_qs,urlsplit
from uuid import uuid4

import pytest
from pydantic import ValidationError

import test_tick_audit as tape
from app.replay import input_receipts as ir
from app.replay.dataset import canonical,digest,read_json
from app.replay.models import ResearchError,utc

PRODUCER="11111111-1111-4111-8111-111111111111"
OTHER="22222222-2222-4222-8222-222222222222"


class Clock:
    def __init__(self):self.domain=str(uuid4());self.current=0;self.quality="MONOTONIC_STABLE"
    def mark(self):
        self.current+=1000000
        return {"at":(utc("2025-11-03T01:00:00Z")+timedelta(microseconds=self.current//1000)).isoformat(),
                "elapsedNanos":self.current,"quality":self.quality}


def envelope(request,*,domain=PRODUCER,start=1001000000,end=1001500000,delivery_id=None,rows=None):
    d=tape.export(*(rows if rows is not None else [tape.row()]))
    d["schemaVersion"]="SAGOPALGO_STORED_EXPORT_V2"
    for row in d["streamEvents"]:
        row["availability"]={"contentHash":row["contentHash"],"clockDomain":domain,
            "commitObservedAt":"2025-11-03T00:00:00.999Z","inputPublishedAt":"2025-11-03T00:00:01Z",
            "commitElapsedNanos":999000000,"publishedElapsedNanos":1000000000,
            "clockQuality":"MONOTONIC_STABLE","clockBasis":"JVM_MONOTONIC_ANCHORED_UTC","utcSynchronized":False}
    payload=canonical(d).decode()
    point=lambda n:{"at":(utc("2025-11-03T00:00:00Z")+timedelta(microseconds=n//1000)).isoformat(),
                    "elapsedNanos":n,"quality":"MONOTONIC_STABLE"}
    return {"success":True,"data":{"schemaVersion":"SAGOPALGO_INPUT_DELIVERY_V1","requestId":request,
        "deliveryId":delivery_id or str(uuid4()),"producerClockDomain":PRODUCER,
        "producerReceived":point(start),"producerSent":point(end),
        "payloadJson":payload,"payloadSha256":digest(payload.encode()),"utcSynchronized":False},"error":None,"message":"test"}


def fetch(edit=None,**kwargs):
    def receive(url):
        request=parse_qs(urlsplit(url).query)["requestId"][0]
        v=envelope(request,**kwargs)
        if edit:edit(v)
        return canonical(v)
    return receive


def run(tmp_path,*,clock=None,policy=None,transport=None):
    consumer=ir.InputConsumer(clock or Clock(),policy)
    result=consumer.receive("http://127.0.0.1:18081",tape.config(),tmp_path/"receipt",transport or fetch())
    return consumer,result


def test_actual_validation_boundary_blocks_before_and_allows_exact_acceptance(tmp_path):
    consumer,result=run(tmp_path)
    r=result.receipt;n=r["consumerAccepted"]["elapsedNanos"];domain=r["consumerClockDomain"]
    assert result.snapshot(domain,n-1)["records"]==[]
    assert len(result.snapshot(domain,n)["records"])==1
    assert len(consumer.snapshot(result)["records"])==1
    assert result.snapshot(OTHER,n+1)["records"]==[]
    assert r["globalUtcDecisionStatus"]=="BLOCKED_UTC_UNCONFIRMED"
    assert not r["utcSynchronized"] and not r["modelEvaluated"]
    assert r["inputs"][0]["publicationRelation"]["status"]=="BOUNDED_UNDER_RATE_ASSUMPTION"
    assert r["clockRelation"]["producerMinusConsumerLowerNs"]<=999500000<=r["clockRelation"]["producerMinusConsumerUpperNs"]
    row=consumer.snapshot(result)["records"][0]
    assert row["knownAtElapsedNanos"]==n and row["sourceKnownAt"]!=row["knownAt"]
    assert not result.snapshot(domain,n)["usableForStrategyValidation"]


def test_old_source_domain_does_not_backdate_new_real_receipt(tmp_path):
    _,result=run(tmp_path,transport=fetch(domain=OTHER))
    assert result.receipt["status"]=="ACCEPTED_CAUSAL_RESEARCH_ONLY"
    assert result.receipt["inputs"][0]["publicationRelation"]=={"status":"PRODUCER_DOMAIN_CHANGED"}
    assert len(ir.InputConsumer(Clock()).snapshot(result)["records"])==0


@pytest.mark.parametrize("changes,reason",[
    ({"maxRoundTripMs":1},None), # exact inclusive 1ms exchange is allowed
    ({"maxUncertaintyMs":1,"timestampErrorNs":0},None),
])
def test_inclusive_policy_boundaries(tmp_path,changes,reason):
    _,result=run(tmp_path,policy=ir.ReceiptPolicy(**changes))
    assert result.receipt["status"]=="ACCEPTED_CAUSAL_RESEARCH_ONLY"


@pytest.mark.parametrize("kind,reason",[("delay","ROUND_TRIP_LIMIT"),("uncertainty","CLOCK_UNCERTAINTY_LIMIT"),
    ("consumer","CONSUMER_CLOCK_UNSTABLE"),("producer","PRODUCER_CLOCK_UNSTABLE"),("inconsistent","CLOCK_EXCHANGE_INCONSISTENT")])
def test_untrustworthy_exchange_is_persisted_but_never_released(tmp_path,kind,reason):
    clock=Clock()
    def edit(v):
        if kind=="delay":clock.current+=3000000000
        if kind=="uncertainty":clock.current+=300000000
        if kind=="consumer":clock.quality="CLOCK_STEP_DETECTED"
        if kind=="producer":v["data"]["producerSent"]["quality"]="CLOCK_STEP_DETECTED"
        if kind=="inconsistent":
            # Exceed both the round-trip interval and declared timestamp error bounds.
            v["data"]["producerSent"]["elapsedNanos"]+=30000000
            v["data"]["producerSent"]["at"]="2025-11-03T00:00:01.031500Z"
    consumer,result=run(tmp_path,clock=clock,transport=fetch(edit))
    assert result.receipt["status"]=="BLOCKED" and reason in result.receipt["blockedReasons"]
    assert consumer.snapshot(result)["records"]==[]
    assert (tmp_path/"receipt/receipt.json").exists()


@pytest.mark.parametrize("kind,code",[("nonce","DELIVERY_REQUEST_MISMATCH"),("hash","DELIVERY_PAYLOAD_HASH_MISMATCH"),
    ("future","PUBLICATION_AFTER_DELIVERY"),("error","DELIVERY_RESPONSE_INVALID")])
def test_forged_or_future_delivery_is_rejected_before_publication(tmp_path,kind,code):
    def edit(v):
        if kind=="nonce":v["data"]["requestId"]=OTHER
        if kind=="hash":v["data"]["payloadSha256"]="0"*64
        if kind=="error":v["success"]=False
        if kind=="future":
            d=read_json(v["data"]["payloadJson"].encode());d["streamEvents"][0]["availability"]["publishedElapsedNanos"]=2000000000
            v["data"]["payloadJson"]=canonical(d).decode();v["data"]["payloadSha256"]=digest(canonical(d))
    with pytest.raises(ResearchError,match=code):run(tmp_path,transport=fetch(edit))
    assert not (tmp_path/"receipt").exists()


def test_reversed_clock_or_claimed_utc_is_schema_failure(tmp_path):
    for kind in ["utc","order","representation"]:
        def edit(v):
            if kind=="utc":v["data"]["utcSynchronized"]=True
            if kind=="order":v["data"]["producerSent"]["elapsedNanos"]=0
            if kind=="representation":v["data"]["producerSent"]["at"]="2025-11-03T00:00:05Z"
        with pytest.raises(ValidationError):run(tmp_path,transport=fetch(edit))


def test_duplicate_delivery_and_source_order_reversal_are_rejected(tmp_path):
    consumer=ir.InputConsumer(Clock());delivery=str(uuid4())
    consumer.receive("http://127.0.0.1:18081",tape.config(),tmp_path/"first",fetch(delivery_id=delivery))
    with pytest.raises(ResearchError,match="DELIVERY_REPLAYED"):
        consumer.receive("http://127.0.0.1:18081",tape.config(),tmp_path/"duplicate",fetch(delivery_id=delivery))
    with pytest.raises(ResearchError,match="PRODUCER_SEQUENCE_REVERSED"):
        consumer.receive("http://127.0.0.1:18081",tape.config(),tmp_path/"reversed",fetch(start=1000000000,end=1000100000))


def test_no_old_publication_receipt_or_excessive_age_is_invented(tmp_path):
    for status,edit in [("PUBLICATION_NOT_RECORDED",lambda d:d["streamEvents"][0].pop("availability")),
                       ("OUTSIDE_MAPPING_HORIZON",lambda d:d["streamEvents"][0]["availability"].update(commitElapsedNanos=0,publishedElapsedNanos=0,commitObservedAt="2025-11-03T00:00:00Z",inputPublishedAt="2025-11-03T00:00:00Z"))]:
        def change(v):
            d=read_json(v["data"]["payloadJson"].encode());edit(d)
            v["data"]["payloadJson"]=canonical(d).decode();v["data"]["payloadSha256"]=digest(canonical(d))
        _,result=run(tmp_path/status,transport=fetch(change),policy=ir.ReceiptPolicy(mappingHorizonMs=100))
        assert result.receipt["inputs"][0]["publicationRelation"]["status"]==status


def test_source_producer_restart_allows_new_domain_but_no_old_consumer_receipt(tmp_path):
    consumer=ir.InputConsumer(Clock())
    first=consumer.receive("http://127.0.0.1:18081",tape.config(),tmp_path/"first",fetch())
    def restart(v):
        v["data"]["producerClockDomain"]=OTHER
    second=consumer.receive("http://127.0.0.1:18081",tape.config(),tmp_path/"second",fetch(restart,start=1,end=1000))
    assert first.receipt["producerClockDomain"]!=second.receipt["producerClockDomain"]
    assert ir.InputConsumer(Clock()).snapshot(first)["records"]==[]


def test_persistence_failure_returns_no_input_and_preserves_old_output(tmp_path,monkeypatch):
    def fail(*a):raise OSError("synthetic disk failure")
    monkeypatch.setattr(ir,"publish_directory",fail)
    with pytest.raises(OSError):run(tmp_path)
    assert not (tmp_path/"receipt").exists() and not list(tmp_path.glob('.input-receipt-*'))
    (tmp_path/"receipt").mkdir();(tmp_path/"receipt/old").write_bytes(b"preserve")
    with pytest.raises(ResearchError,match="RECEIPT_OUTPUT_EXISTS"):run(tmp_path)
    assert (tmp_path/"receipt/old").read_bytes()==b"preserve"


def test_raw_bytes_and_hash_links_are_preserved(tmp_path):
    _,result=run(tmp_path)
    p=tmp_path/"receipt";r=read_json((p/"receipt.json").read_bytes())
    assert r==result.receipt
    assert digest((p/"source-response.json").read_bytes())==r["responseSha256"]
    assert digest((p/"source-export.json").read_bytes())==r["sourceExportSha256"]
    assert digest((p/"config.json").read_bytes())==r["configSha256"]


@pytest.mark.parametrize("origin",["https://127.0.0.1:8080","http://localhost:8080","http://192.168.0.2:8080",
    "http://127.0.0.1:8080@evil.test","http://user:pass@127.0.0.1:8080","http://127.0.0.1:8080/a","http://127.0.0.1:8080?x=y"])
def test_nonlocal_or_ambiguous_origin_never_calls_transport(tmp_path,origin):
    def forbidden(*a):raise AssertionError("transport must not be called")
    with pytest.raises(ResearchError,match="LOCAL_DELIVERY_ORIGIN_REQUIRED"):
        ir.InputConsumer(Clock()).receive(origin,tape.config(),tmp_path/"receipt",forbidden)


def test_empty_sample_is_not_success(tmp_path):
    _,result=run(tmp_path,transport=fetch(rows=[]))
    assert result.receipt["status"]=="BLOCKED" and result.receipt["blockedReasons"]==["NO_INPUT_SAMPLE"]


def test_consumer_clock_step_is_latched_and_monotonic_reversal_raises():
    wall=[1762131600000000000];ns=[100]
    clock=ir.ConsumerClock(lambda:wall[0],lambda:ns[0]);ns[0]+=1000
    assert clock.mark()["quality"]=="MONOTONIC_STABLE"
    wall[0]+=1000000000
    assert clock.mark()["quality"]=="CLOCK_STEP_DETECTED"
    wall[0]-=1000000000
    assert clock.mark()["quality"]=="CLOCK_STEP_DETECTED"
    ns[0]-=1
    with pytest.raises(ResearchError,match="CONSUMER_CLOCK_REVERSED"):clock.mark()


def test_redirects_never_follow_other_origins():
    with pytest.raises(ResearchError,match="DELIVERY_REDIRECT_FORBIDDEN"):
        ir.NoRedirect().redirect_request(None,None,None,None,None,"http://external.test")


def test_real_loopback_http_transport_ignores_proxy_and_persists_receipt(tmp_path,monkeypatch):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from threading import Thread
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_GET(self):
            calls.append(self.path)
            request=parse_qs(urlsplit(self.path).query)["requestId"][0]
            body=canonical(envelope(request,end=1001000000))
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)))
            self.end_headers();self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    monkeypatch.setenv('HTTP_PROXY','http://127.0.0.1:1')
    try:
        consumer=ir.InputConsumer(policy=ir.ReceiptPolicy(maxUncertaintyMs=1000))
        result=consumer.receive('http://127.0.0.1:'+str(server.server_port),tape.config(),tmp_path/'http')
        assert result.receipt['status']=='ACCEPTED_CAUSAL_RESEARCH_ONLY'
        assert len(calls)==1 and calls[0].startswith('/api/v1/research/input-delivery?')
        assert len(consumer.snapshot(result)['records'])==1
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)


def test_validation_delay_blocks_input_even_with_short_transport(tmp_path,monkeypatch):
    clock=Clock();original=ir.audit_ticks
    def slow(*args):
        result=original(*args);clock.current+=3000000000;return result
    monkeypatch.setattr(ir,'audit_ticks',slow)
    consumer,result=run(tmp_path,clock=clock)
    assert result.receipt['blockedReasons']==['INPUT_VALIDATION_DELAY']
    assert consumer.snapshot(result)['records']==[]


def test_declared_timestamp_error_widens_interval_and_is_not_hidden(tmp_path):
    _,result=run(tmp_path,policy=ir.ReceiptPolicy(timestampErrorNs=5000000,maxUncertaintyMs=1))
    r=result.receipt
    assert r['clockRelation']['timestampErrorNsAssumption']==5000000
    assert r['clockRelation']['uncertaintyNs']>=20000000
    assert 'CLOCK_UNCERTAINTY_LIMIT' in r['blockedReasons']
