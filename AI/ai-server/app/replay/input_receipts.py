"""Explicit local HTTP input receipt; no model, broker, subscription or order calls."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import shutil
import tempfile
import time
from typing import Annotated, Literal
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener
from uuid import uuid4

from pydantic import Field, ValidationError, model_validator

from .dataset import MAX_BYTES, canonical, digest, read_bytes, read_json
from .file_publish import publish_directory
from .models import ResearchError, StrictModel, Timestamp, utc
from .stored import StoredExportV2
from .ticks import TickAuditConfig, audit_ticks

Domain = Annotated[str, Field(pattern=r"^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$")]
Nanos = Annotated[int, Field(ge=0, le=2**63-1)]


class ClockPoint(StrictModel):
    at: Timestamp
    elapsedNanos: Nanos
    quality: Literal["MONOTONIC_STABLE", "CLOCK_STEP_DETECTED"]


class Delivery(StrictModel):
    schemaVersion: Literal["SAGOPALGO_INPUT_DELIVERY_V1"]
    requestId: Domain
    deliveryId: Domain
    producerClockDomain: Domain
    producerReceived: ClockPoint
    producerSent: ClockPoint
    payloadJson: str = Field(max_length=MAX_BYTES)
    payloadSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    utcSynchronized: Literal[False]

    @model_validator(mode="after")
    def order(self):
        if (self.producerReceived.elapsedNanos > self.producerSent.elapsedNanos
                or self.producerReceived.at > self.producerSent.at):
            raise ValueError("producer clock order")
        delta=self.producerSent.at-self.producerReceived.at
        utc_ns=(delta.days*86400+delta.seconds)*1000000000+delta.microseconds*1000
        if abs(utc_ns-(self.producerSent.elapsedNanos-self.producerReceived.elapsedNanos))>1000000:
            raise ValueError("producer clock representation mismatch")
        return self


class ReceiptPolicy(StrictModel):
    maxRoundTripMs: int = Field(default=2000, ge=1, le=10000)
    maxUncertaintyMs: int = Field(default=200, ge=1, le=1000)
    maxValidationMs: int = Field(default=2000, ge=1, le=10000)
    relativeRatePpm: int = Field(default=100, ge=0, le=1000)
    timestampErrorNs: int = Field(default=1000000, ge=0, le=50000000)
    mappingHorizonMs: int = Field(default=5000, ge=1, le=60000)


class ConsumerClock:
    """Process identity and monotonic anchor; wall stability never certifies UTC."""
    def __init__(self, wall=time.time_ns, monotonic=time.monotonic_ns):
        self._wall=wall;self._monotonic=monotonic
        self._anchor=wall();self._start=monotonic();self._last=0;self._unstable=False
        self.domain=str(uuid4())

    def mark(self):
        elapsed=self._monotonic()-self._start
        if elapsed<self._last:raise ResearchError("CONSUMER_CLOCK_REVERSED")
        self._last=elapsed
        projected=self._anchor+elapsed
        if abs(self._wall()-projected)>250_000_000:self._unstable=True
        micros=(projected+999)//1000
        at=datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(microseconds=micros)
        return {"at":at.isoformat(),"elapsedNanos":elapsed,
                "quality":"CLOCK_STEP_DETECTED" if self._unstable else "MONOTONIC_STABLE"}


def clock_relation(delivery, sent, received, policy):
    """Four timestamps constrain origin offset under an explicit rate assumption."""
    c0,c3=sent["elapsedNanos"],received["elapsedNanos"]
    s1,s2=delivery.producerReceived.elapsedNanos,delivery.producerSent.elapsedNanos
    duration=c3-c0
    if duration<0:raise ResearchError("CONSUMER_CLOCK_REVERSED")
    margin=(duration*policy.relativeRatePpm+999999)//1000000+2*policy.timestampErrorNs+1
    low,high=s2-c3-margin,s1-c0+margin
    reasons=[]
    if high<low:reasons.append("CLOCK_EXCHANGE_INCONSISTENT")
    if duration>policy.maxRoundTripMs*1000000:reasons.append("ROUND_TRIP_LIMIT")
    if high-low>policy.maxUncertaintyMs*1000000:reasons.append("CLOCK_UNCERTAINTY_LIMIT")
    if any(p["quality"]!="MONOTONIC_STABLE" for p in [sent,received]):reasons.append("CONSUMER_CLOCK_UNSTABLE")
    if any(p.quality!="MONOTONIC_STABLE" for p in [delivery.producerReceived,delivery.producerSent]):reasons.append("PRODUCER_CLOCK_UNSTABLE")
    return {"status":"UNCONFIRMED" if reasons else "BOUNDED_UNDER_RATE_ASSUMPTION",
            "producerMinusConsumerLowerNs":low,"producerMinusConsumerUpperNs":high,
            "uncertaintyNs":max(0,high-low),"roundTripNs":duration,"producerProcessingNs":s2-s1,
            "relativeRatePpmAssumption":policy.relativeRatePpm,"timestampErrorNsAssumption":policy.timestampErrorNs,
            "utcSynchronized":False,"reasons":reasons}


def publication_relation(row, delivery, relation, policy):
    observation=row.get("availabilityObservation")
    if not observation:return {"status":"PUBLICATION_NOT_RECORDED"}
    if observation["clockDomain"]!=delivery.producerClockDomain:return {"status":"PRODUCER_DOMAIN_CHANGED"}
    p=observation["publishedElapsedNanos"]
    s1,s2=delivery.producerReceived.elapsedNanos,delivery.producerSent.elapsedNanos
    if p>s2:raise ResearchError("PUBLICATION_AFTER_DELIVERY")
    # UTC-shaped labels are comparable here only inside the matched producer domain.
    delta=delivery.producerSent.at-utc(observation["inputPublishedAt"])
    at_ns=(delta.days*86400+delta.seconds)*1000000000+delta.microseconds*1000
    if abs(at_ns-(s2-p))>1000000:raise ResearchError("PUBLICATION_CLOCK_REPRESENTATION")
    if observation["clockQuality"]!="MONOTONIC_STABLE":return {"status":"PUBLICATION_CLOCK_UNSTABLE"}
    age=max(abs(p-s1),abs(p-s2))
    if age>policy.mappingHorizonMs*1000000:return {"status":"OUTSIDE_MAPPING_HORIZON"}
    if relation["reasons"]:return {"status":"CLOCK_RELATION_UNCONFIRMED"}
    margin=(age*policy.relativeRatePpm+999999)//1000000+2*policy.timestampErrorNs+1
    return {"status":"BOUNDED_UNDER_RATE_ASSUMPTION",
            "consumerLowerElapsedNs":p-relation["producerMinusConsumerUpperNs"]-margin,
            "consumerUpperElapsedNs":p-relation["producerMinusConsumerLowerNs"]+margin}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ResearchError("DELIVERY_REDIRECT_FORBIDDEN")


def local_get(url):
    # No proxy inheritance, credentials, redirects or arbitrary outbound destination.
    opener=build_opener(ProxyHandler({}),NoRedirect())
    deadline=time.monotonic()+5
    try:
        with opener.open(url,timeout=5) as response:
            if response.status!=200:raise ResearchError("DELIVERY_HTTP_STATUS")
            if response.headers.get_content_type()!="application/json":raise ResearchError("DELIVERY_CONTENT_TYPE")
            chunks=[];size=0
            while True:
                if time.monotonic()>deadline:raise ResearchError("DELIVERY_TIMEOUT")
                chunk=response.read1(min(65536,MAX_BYTES+1-size))
                if not chunk:break
                chunks.append(chunk);size+=len(chunk)
                if size>MAX_BYTES:raise ResearchError("DELIVERY_SIZE_LIMIT")
            return b"".join(chunks)
    except (URLError,TimeoutError,OSError):raise ResearchError("DELIVERY_TRANSPORT_FAILED") from None


def local_origin(value):
    try:
        parsed=urlsplit(value)
        valid=(parsed.scheme=="http" and parsed.hostname=="127.0.0.1" and parsed.port is not None
               and 1<=parsed.port<=65535 and parsed.username is None and parsed.password is None
               and parsed.path in {"","/"} and not parsed.query and not parsed.fragment)
    except ValueError:valid=False
    if not valid:raise ResearchError("LOCAL_DELIVERY_ORIGIN_REQUIRED")
    return value.rstrip("/")


class ReceivedInput:
    """Validated research input, released only after receipt persistence succeeds."""
    def __init__(self, receipt, records):
        self.receipt=receipt;self._records=records

    def snapshot(self, domain, elapsed_ns):
        r=self.receipt
        visible=(domain==r["consumerClockDomain"] and elapsed_ns>=r["consumerAccepted"]["elapsedNanos"]
                 and r["status"]=="ACCEPTED_CAUSAL_RESEARCH_ONLY")
        return {"receiptId":r["receiptId"],"consumerClockDomain":domain,"atElapsedNanos":elapsed_ns,
                "records":self._records if visible else [],"utcSynchronized":False,
                "basis":"VALIDATED_PYTHON_RESEARCH_RECEIPT","usableForTrading":False,
                "usableForStrategyValidation":False}


class InputConsumer:
    def __init__(self,clock=None,policy=None):
        self.clock=clock or ConsumerClock();self.policy=policy or ReceiptPolicy()
        self._deliveries=set();self._last_source={}

    def snapshot(self,received_input):
        point=self.clock.mark()
        if point["quality"]!="MONOTONIC_STABLE":
            return {**received_input.snapshot("",point["elapsedNanos"]),"blockedReason":"CONSUMER_CLOCK_UNSTABLE"}
        return received_input.snapshot(self.clock.domain,point["elapsedNanos"])

    def receive(self,origin,config,output,fetch=local_get):
        origin=local_origin(origin)
        if output.exists() or output.is_symlink():raise ResearchError("RECEIPT_OUTPUT_EXISTS")
        request_id=str(uuid4())
        query=urlencode({"requestId":request_id,"stockCode":config.stockCode,
                         "from":config.startAt.isoformat(),"to":config.endAt.isoformat()})
        sent=self.clock.mark()
        raw=fetch(origin+"/api/v1/research/input-delivery?"+query)
        received=self.clock.mark()
        if len(raw)>MAX_BYTES:raise ResearchError("DELIVERY_SIZE_LIMIT")
        value=read_json(raw)
        if not isinstance(value,dict) or set(value)-{"success","data","error","message"} or value.get("success") is not True or value.get("error") is not None:
            raise ResearchError("DELIVERY_RESPONSE_INVALID")
        delivery=Delivery.model_validate(value.get("data"))
        if delivery.requestId!=request_id:raise ResearchError("DELIVERY_REQUEST_MISMATCH")
        if delivery.deliveryId in self._deliveries:raise ResearchError("DELIVERY_REPLAYED")
        previous=self._last_source.get(delivery.producerClockDomain)
        if previous is not None and delivery.producerReceived.elapsedNanos<previous:raise ResearchError("PRODUCER_SEQUENCE_REVERSED")
        payload=delivery.payloadJson.encode("utf-8")
        if digest(payload)!=delivery.payloadSha256:raise ResearchError("DELIVERY_PAYLOAD_HASH_MISMATCH")
        StoredExportV2.model_validate(read_json(payload))
        records,audit=audit_ticks(payload,config,[])
        relation=clock_relation(delivery,sent,received,self.policy)
        items=[{"eventId":row["eventId"],"contentHash":row["rawSha256"],
                "publicationRelation":publication_relation(row,delivery,relation,self.policy)} for row in records]
        accepted=self.clock.mark() # after body reception, hash/type/scope validation
        if accepted["quality"]!="MONOTONIC_STABLE" and "CONSUMER_CLOCK_UNSTABLE" not in relation["reasons"]:
            relation["reasons"].append("CONSUMER_CLOCK_UNSTABLE");relation["status"]="UNCONFIRMED"
        blocked=list(relation["reasons"])
        if accepted["elapsedNanos"]-received["elapsedNanos"]>self.policy.maxValidationMs*1000000:
            blocked.append("INPUT_VALIDATION_DELAY")
        if not records:blocked.append("NO_INPUT_SAMPLE")
        receipt={"schemaVersion":"SAGOPALGO_INPUT_RECEIPT_V1","receiptId":str(uuid4()),
                 "requestId":request_id,"deliveryId":delivery.deliveryId,"responseSha256":digest(raw),
                 "sourceExportSha256":digest(payload),"configSha256":digest(canonical(config.model_dump(mode="json"))),
                 "producerClockDomain":delivery.producerClockDomain,"consumerClockDomain":self.clock.domain,
                 "producerReceived":delivery.producerReceived.model_dump(mode="json"),
                 "producerSent":delivery.producerSent.model_dump(mode="json"),
                 "consumerSent":sent,"consumerReceived":received,"consumerAccepted":accepted,
                 "clockRelation":relation,"policy":self.policy.model_dump(mode="json"),"inputs":items,
                 "status":"BLOCKED" if blocked else "ACCEPTED_CAUSAL_RESEARCH_ONLY","blockedReasons":blocked,
                 "utcSynchronized":False,"globalUtcDecisionStatus":"BLOCKED_UTC_UNCONFIRMED",
                 "consumerBoundary":"VALIDATED_PYTHON_RESEARCH_INPUT","modelEvaluated":False,
                 "usableForTrading":False,"usableForStrategyValidation":False}
        # Do not backdate a new receipt to market time, export time or an old producer domain.
        visible=[{**row,"sourceKnownAt":row["knownAt"],"knownAt":accepted["at"],
                  "knownAtElapsedNanos":accepted["elapsedNanos"],"knownAtClockDomain":self.clock.domain,
                  "knownAtBasis":"VALIDATED_PYTHON_RESEARCH_RECEIPT"} for row in records]
        output.parent.mkdir(parents=True,exist_ok=True)
        work=Path(tempfile.mkdtemp(prefix=".input-receipt-",dir=output.parent))
        try:
            files={"source-response.json":raw,"source-export.json":payload,
                   "config.json":canonical(config.model_dump(mode="json")),"receipt.json":canonical(receipt),
                   "records.json":canonical(visible)}
            for name,data in files.items():
                with (work/name).open("xb") as stream:stream.write(data)
            publish_directory(work,output)
        finally:
            if work.exists():shutil.rmtree(work)
        self._deliveries.add(delivery.deliveryId)
        self._last_source[delivery.producerClockDomain]=delivery.producerSent.elapsedNanos
        return ReceivedInput(receipt,visible)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url",required=True)
    parser.add_argument("--config",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        config=TickAuditConfig.model_validate(read_json(read_bytes(args.config)))
        result=InputConsumer().receive(args.base_url,config,args.output)
        r=result.receipt
        print(json.dumps({"status":r["status"],"receiptId":r["receiptId"],"rows":len(r["inputs"]),
                          "publicationRelations":dict(Counter(x["publicationRelation"]["status"] for x in r["inputs"])),
                          "utcSynchronized":False}))
        return 0 if r["status"]=="ACCEPTED_CAUSAL_RESEARCH_ONLY" else 1
    except ResearchError as error:code=str(error)
    except ValidationError:code="INPUT_SCHEMA_INVALID"
    except (ValueError,TypeError,KeyError,OverflowError):code="INPUT_INVALID"
    except OSError:code="FILE_OPERATION_FAILED"
    print(json.dumps({"status":"FAILED","code":code}));return 2


if __name__=="__main__":raise SystemExit(main())
