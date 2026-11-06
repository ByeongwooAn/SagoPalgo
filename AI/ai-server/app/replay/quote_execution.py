"""Conservative IOC depth scenarios. No broker fill, queue, or liquidity refresh claims."""
from collections import Counter
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext
from typing import Literal

from pydantic import Field, model_validator

from .dataset import canonical, digest
from .models import Identifier, Number, ResearchError, StrictModel, Timestamp
from .stored import precise_time
from .ticks import TickAuditConfig, audit_ticks
from .tick_quality import quality_profile
from .intraday import gate


class QuoteOrder(StrictModel):
    orderId: Identifier
    side: Literal["BUY","SELL"]
    orderType: Literal["MARKET","LIMIT"]
    decisionAt: Timestamp
    expiresAt: Timestamp
    quantity: int = Field(ge=1,le=100000000)
    limitPrice: Number | None = None

    @model_validator(mode="after")
    def valid(self):
        if not self.decisionAt<self.expiresAt or self.expiresAt-self.decisionAt>timedelta(days=1):
            raise ValueError("bounded IOC order required")
        if (self.orderType=="LIMIT") != (self.limitPrice is not None) or (self.limitPrice is not None and Decimal(self.limitPrice)<=0):
            raise ValueError("limit price required only for LIMIT")
        return self


class CaptureGap(StrictModel):
    startAt: Timestamp
    endAt: Timestamp

    @model_validator(mode="after")
    def valid(self):
        if not self.startAt<self.endAt:raise ValueError("positive gap required")
        return self


class QuoteExecutionPolicy(StrictModel):
    schemaVersion: Literal["SAGOPALGO_QUOTE_EXECUTION_V1"]
    availabilityMode: Literal["EXPORT_KNOWN_AT","RECEIPT_DERIVED_SCENARIO"] = "EXPORT_KNOWN_AT"
    quoteOrdering: Literal["REQUIRE_UNAMBIGUOUS_MARKET_TIME","CLIENT_RECEIPT_SCENARIO"] = "REQUIRE_UNAMBIGUOUS_MARKET_TIME"
    allowSynthetic: bool = False
    allowAnchoredQuoteDate: bool = False
    allowUnconfirmedContinuousSession: bool = False
    initialCash: Number
    initialPosition: int = Field(ge=0,le=100000000)
    maxOrderNotional: Number
    participationRate: Number
    tickSize: Number
    feeBps: Number
    sellTaxBps: Number
    latencyMs: int = Field(ge=0,le=60000)
    maxQuoteAgeMs: int = Field(ge=0,le=60000)
    assumptionsEvidence: str = Field(min_length=1,max_length=1000)
    captureGaps: list[CaptureGap] = Field(default_factory=list,max_length=1000)

    @model_validator(mode="after")
    def valid(self):
        if not 0<Decimal(self.participationRate)<=1 or Decimal(self.tickSize)<=0 or Decimal(self.maxOrderNotional)<=0:
            raise ValueError("positive price/rate/order limits required")
        if Decimal(self.feeBps)+Decimal(self.sellTaxBps)>10000:raise ValueError("combined bps limit")
        if self.quoteOrdering=="CLIENT_RECEIPT_SCENARIO" and self.availabilityMode!="RECEIPT_DERIVED_SCENARIO":
            raise ValueError("client receipt ordering requires explicit receipt scenario")
        return self


def estimate_quotes(raw, tick_config: TickAuditConfig, evidence_raw, policy: QuoteExecutionPolicy, orders: list[QuoteOrder], intraday=None):
    with localcontext() as context:
        context.prec=96
        return _estimate_quotes(raw,tick_config,evidence_raw,policy,orders,intraday)


def _estimate_quotes(raw, tick_config, evidence_raw, policy, orders, intraday):
    records,audit=audit_ticks(raw,tick_config,[])
    records,quality=quality_profile(records,evidence_raw)
    if len(orders)>10000 or len({o.orderId for o in orders})!=len(orders):raise ResearchError("ORDER_ID_OR_COUNT_INVALID")
    if any(not tick_config.startAt<=o.decisionAt<o.expiresAt<=tick_config.endAt for o in orders):
        raise ResearchError("QUOTE_ORDER_OUTSIDE_SAMPLE")
    if tick_config.provenance=="SYNTHETIC" and not policy.allowSynthetic:raise ResearchError("SYNTHETIC_OPT_IN_REQUIRED")
    if intraday is not None:
        if intraday.market!=tick_config.market:raise ResearchError("INTRADAY_MARKET_MISMATCH")
        if intraday.timeline.provenance=="SYNTHETIC" and not policy.allowSynthetic:raise ResearchError("SYNTHETIC_OPT_IN_REQUIRED")
    quotes=[r for r in records if r["type"]=="QUOTE"]
    times={q["eventId"]:(precise_time(q["marketAt"]),precise_time(q["receivedAt"]),precise_time(q["knownAt"])) for q in quotes}
    cash=Decimal(policy.initialCash);position=policy.initialPosition
    used={};outcomes=[]
    scenario=policy.availabilityMode=="RECEIPT_DERIVED_SCENARIO"
    for order in sorted(orders,key=lambda o:(o.decisionAt,o.orderId)):
        at=order.decisionAt+timedelta(milliseconds=policy.latencyMs)
        result={"orderId":order.orderId,"at":at.isoformat(),"quantityRequested":order.quantity,
                "quantityEstimated":0,"remainderCancelled":order.quantity,"fills":[],"accountFillStatus":"NOT_PROVEN"}
        reasons=[]
        if at>=order.expiresAt:reasons.append("EXPIRED_BEFORE_ATTEMPT")
        if tick_config.rights!="PERMITTED":reasons.append("RIGHTS_UNCONFIRMED")
        if any(g.startAt<=at<g.endAt for g in policy.captureGaps):reasons.append("CAPTURE_GAP")
        if any(g.startAt<=order.decisionAt<g.endAt for g in policy.captureGaps):reasons.append("DECISION_DURING_CAPTURE_GAP")
        if intraday is not None and not reasons:
            blocked=None
            for stage,moment in [("DECISION",order.decisionAt),("EXECUTION",at)]:
                blocked=gate(intraday,moment,moment+timedelta(microseconds=1),order.side)
                if blocked:
                    outcomes.append({**result,"status":"NOT_ASSESSABLE","reasons":[blocked['status']],
                                     "intraday":{"stage":stage,**blocked}})
                    break
            if blocked:continue
        visible=[q for q in quotes if times[q["eventId"]][0]<=at and times[q["eventId"]][1]<=at
                 and (scenario or times[q["eventId"]][2]<=at)]
        if not visible:
            reasons.append("NO_VISIBLE_QUOTE" if scenario else "HISTORICAL_AVAILABILITY_UNCONFIRMED")
            quote=None
        else:
            latest=max(times[q["eventId"]][0] for q in visible)
            latest_quotes=[q for q in visible if times[q["eventId"]][0]==latest]
            if len(latest_quotes)>1 and policy.quoteOrdering=="CLIENT_RECEIPT_SCENARIO":
                latest_received=max(times[q["eventId"]][1] for q in latest_quotes)
                latest_quotes=[q for q in latest_quotes if times[q["eventId"]][1]==latest_received]
            quote=latest_quotes[0] if len(latest_quotes)==1 else None
            if quote is None:reasons.append("AMBIGUOUS_QUOTE_ORDER")
        if quote:
            market_at,received,known=times[quote["eventId"]]
            result["quoteEventId"]=quote["eventId"]
            if at-market_at>timedelta(milliseconds=policy.maxQuoteAgeMs):reasons.append("STALE_QUOTE")
            if any(market_at<g.endAt<=at for g in policy.captureGaps):reasons.append("QUOTE_BEFORE_CAPTURE_GAP")
            if quote["clockQuality"]!="ORDERED_OBSERVATION":reasons.append("RECEIPT_BEFORE_MARKET_TIME")
            if quote["sessionMeaning"]!="INTRADAY_REPORTED":reasons.append("UNCONFIRMED_SESSION_CODE")
            if not policy.allowUnconfirmedContinuousSession:reasons.append("CONTINUOUS_SESSION_UNCONFIRMED")
            if quote["dateEvidence"]["status"]!="PROVIDER_DATE" and not (
                policy.allowAnchoredQuoteDate and quote["dateEvidence"]["status"]=="CROSS_FEED_ANCHORED_ONLY"
            ):reasons.append("QUOTE_BUSINESS_DATE_UNCONFIRMED")
            reasons.extend(flag for flag in quote["flags"] if flag in {
                "INCOMPLETE_BOOK_LEVELS","UNORDERED_BOOK","LOCKED_OR_CROSSED_BOOK","EMPTY_BOOK_SIDE"})
        if reasons:
            outcomes.append({**result,"status":"NOT_ASSESSABLE","reasons":sorted(set(reasons))});continue
        levels=quote["asks"] if order.side=="BUY" else quote["bids"]
        tick=Decimal(policy.tickSize)
        if (order.limitPrice is not None and Decimal(order.limitPrice)%tick!=0) or any(
            Decimal(level["price"])>0 and int(level["quantity"])>0 and Decimal(level["price"])%tick!=0 for level in levels
        ):
            outcomes.append({**result,"status":"NOT_ASSESSABLE","reasons":["PRICE_OFF_ASSUMED_TICK_GRID"]});continue
        quantity=0;notional=Decimal(0);fee=Decimal(0);tax=Decimal(0)
        def costs(value):
            f=(value*Decimal(policy.feeBps)/10000).to_integral_value(rounding=ROUND_CEILING)
            t=(value*Decimal(policy.sellTaxBps)/10000).to_integral_value(rounding=ROUND_CEILING) if order.side=="SELL" else Decimal(0)
            return f,t
        for level in levels:
            price=Decimal(level["price"])
            if price<=0 or int(level["quantity"])<=0:continue
            if order.limitPrice is not None and ((order.side=="BUY" and price>Decimal(order.limitPrice)) or (
                order.side=="SELL" and price<Decimal(order.limitPrice))):break
            # Same resting liquidity may reappear in many snapshots. Never infer
            # replenishment: consume a side/price budget for the entire sample.
            key=(order.side,price)
            capacity=max(0,int((Decimal(level["quantity"])*Decimal(policy.participationRate)).to_integral_value(rounding=ROUND_FLOOR))-used.get(key,0))
            take=min(order.quantity-quantity,capacity,int((Decimal(policy.maxOrderNotional)-notional)//price))
            if order.side=="SELL":take=min(take,position)
            else:
                lo,hi=0,take
                while lo<hi:
                    mid=(lo+hi+1)//2;new_fee,_=costs(notional+price*mid)
                    if price*mid+new_fee-fee<=cash:lo=mid
                    else:hi=mid-1
                take=lo
            if take<=0:continue
            next_notional=notional+price*take;next_fee,next_tax=costs(next_notional)
            if order.side=="SELL" and next_fee-fee+next_tax-tax>cash+price*take:continue
            cash+=(-price*take-(next_fee-fee)) if order.side=="BUY" else price*take-(next_fee-fee)-(next_tax-tax)
            position+=take if order.side=="BUY" else -take
            used[key]=used.get(key,0)+take;quantity+=take;notional=next_notional;fee=next_fee;tax=next_tax
            result["fills"].append({"price":format(price,"f"),"quantity":take,"quoteEventId":quote["eventId"]})
            if quantity==order.quantity:break
        result.update(quantityEstimated=quantity,remainderCancelled=order.quantity-quantity,
                      status="ESTIMATED_FILLED" if quantity==order.quantity else "ESTIMATED_PARTIAL_IOC" if quantity else "ESTIMATED_UNFILLED_IOC",
                      reasons=[],notional=format(notional,"f"),fee=format(fee,"f"),sellTax=format(tax,"f"))
        outcomes.append(result)
    report={"schemaVersion":"SAGOPALGO_QUOTE_EXECUTION_V1","sourceExportSha256":digest(raw),
            "policy":policy.model_dump(mode="json"),"tickConfig":tick_config.model_dump(mode="json"),
            "ordersSha256":digest(canonical([o.model_dump(mode="json") for o in orders])),
            "quality":quality,"inputIssues":audit["issues"],"outcomes":outcomes,
            "statusCounts":dict(Counter(o["status"] for o in outcomes)),"endingCash":format(cash,"f"),"endingPosition":position,
            "liquidityRefreshPolicy":"NO_REPLENISHMENT_WITHOUT_ORDER_IDS","orderDuration":"ONE_ATTEMPT_IOC",
            "costAndTickEvidence":"CALLER_ASSUMPTIONS_NOT_BROKER_VERIFIED","causalAvailability":"RECEIPT_DERIVED_ASSUMPTION" if scenario else "EXPORT_KNOWN_AT",
            "accountFillStatus":"NOT_PROVEN","usableForTrading":False,"usableForStrategyValidation":False}
    if intraday is not None:
        report["intradayBinding"]={"timelineSha256":intraday.timelineSha256,"market":intraday.market,"orderClass":intraday.orderClass}
    report["reportId"]=digest(canonical(report))
    return report
