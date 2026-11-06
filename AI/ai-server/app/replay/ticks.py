"""Offline public-tape audit; matching a tape print never proves an account fill."""
from collections import Counter
from datetime import timedelta, timezone
from decimal import Decimal
from pathlib import Path
import shutil
import tempfile
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .dataset import canonical, digest, read_bytes, read_json
from .file_publish import publish_directory
from .models import Identifier, ResearchError, StrictModel, Timestamp
from .stored import StoredExport, payload, precise_time

Price = Annotated[str, Field(pattern=r"^[0-9]{1,24}(?:\.[0-9]{1,6})?$")]
Quantity = Annotated[str, Field(pattern=r"^[0-9]{1,24}$")]
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class Level(StrictModel):
    price: Price
    quantity: Quantity


class PublicPayload(StrictModel):
    eventId: Hash
    stockCode: str = Field(pattern=r"^[0-9]{6}$")
    type: Literal["TRADE", "QUOTE"]
    marketTime: str
    receivedAt: str
    price: Price | None = None
    volume: Quantity | None = None
    cumulativeVolume: Quantity | None = None
    asks: list[Level] = Field(max_length=10)
    bids: list[Level] = Field(max_length=10)
    session: str = Field(pattern=r"^[A-Za-z0-9]{0,4}$")
    dateBasis: Literal["PROVIDER_DATE", "RECEIVE_DATE_INFERRED"]

    @model_validator(mode="after")
    def numbers(self):
        if self.type == "TRADE":
            if self.price is None or self.volume is None or self.cumulativeVolume is None:
                raise ValueError("trade numbers required")
            if Decimal(self.price) <= 0 or int(self.cumulativeVolume) < int(self.volume) or self.asks or self.bids:
                raise ValueError("invalid trade")
        else:
            if any(x is not None for x in (self.price, self.volume, self.cumulativeVolume)):
                raise ValueError("quote cannot supply trade numbers")
        return self


class TickAuditConfig(StrictModel):
    schemaVersion: Literal["SAGOPALGO_TICK_AUDIT_V1"]
    sourceId: Identifier
    provider: Literal["KIS_KRX_PUBLIC"]
    market: Literal["KOSPI", "KOSDAQ"]
    stockCode: str = Field(pattern=r"^[0-9]{6}$")
    startAt: Timestamp
    endAt: Timestamp
    provenance: Literal["OBSERVED", "SYNTHETIC"]
    rights: Literal["UNCONFIRMED", "PERMITTED"]
    evidence: str = Field(min_length=1, max_length=500)
    regularSessionCodes: list[str] = Field(min_length=1, max_length=10)
    maxQuoteAgeMs: int = Field(ge=0, le=60000)

    @model_validator(mode="after")
    def scope(self):
        if not self.startAt < self.endAt or self.endAt - self.startAt > timedelta(days=1):
            raise ValueError("bounded sample required")
        if len(set(self.regularSessionCodes)) != len(self.regularSessionCodes) or any(
            not code.isalnum() or len(code) > 4 for code in self.regularSessionCodes
        ):
            raise ValueError("explicit distinct session codes required")
        return self


class ExecutionClaim(StrictModel):
    claimId: Identifier
    referenceTradeId: Hash
    side: Literal["BUY", "SELL"]
    decisionAt: Timestamp
    filledAt: Timestamp
    price: Price
    quantity: Quantity

    @model_validator(mode="after")
    def valid(self):
        if self.decisionAt > self.filledAt or Decimal(self.price) <= 0 or int(self.quantity) <= 0:
            raise ValueError("invalid execution claim")
        return self


def audit_ticks(raw: bytes, config: TickAuditConfig, claims: list[ExecutionClaim]):
    value = read_json(raw)
    if isinstance(value, dict) and "success" in value:
        if set(value) - {"success", "data", "error", "message"} or value.get("success") is not True or value.get("error") is not None:
            raise ResearchError("STORED_EXPORT_FAILED")
        value = value.get("data")
    export = StoredExport.model_validate(value)
    if (export.stockCode, export.start, export.end) != (config.stockCode, config.startAt, config.endAt):
        raise ResearchError("TICK_SCOPE_MISMATCH")
    if len({c.claimId for c in claims}) != len(claims):
        raise ResearchError("DUPLICATE_CLAIM_ID")
    if any(not config.startAt <= c.decisionAt <= c.filledAt < config.endAt for c in claims):
        raise ResearchError("CLAIM_OUTSIDE_SCOPE")
    issues = Counter()
    normalized = []
    for row in export.streamEvents:
        item = PublicPayload.model_validate(payload(row))
        at, received = precise_time(item.marketTime), precise_time(item.receivedAt)
        if item.eventId != row.eventId or item.type != row.type:
            raise ResearchError("STORED_EVENT_INVALID")
        if at != row.marketAt or abs(received - row.receivedAt) > timedelta(microseconds=1) or received > export.exportedAt:
            raise ResearchError("STORED_EVENT_TIME_MISMATCH")
        if at > received + timedelta(seconds=5) or at < received - timedelta(days=1):
            raise ResearchError("TICK_CLOCK_OUTSIDE_DECODER_CONTRACT")
        if item.type == "TRADE":
            identity = f'TRADE|{row.stockCode}|{at.astimezone(timezone(timedelta(hours=9))).date()}|{int(item.cumulativeVolume)}'
            if digest(identity.encode()) != row.eventId:
                raise ResearchError("STORED_TRADE_ID_MISMATCH")
        flags = []
        if item.dateBasis != "PROVIDER_DATE":
            flags.append("UNCONFIRMED_BUSINESS_DATE")
        if item.session not in config.regularSessionCodes:
            flags.append("UNMAPPED_SESSION")
        if received < at:
            flags.append("RECEIPT_BEFORE_MARKET_TIME")
        if item.type == "TRADE" and int(item.volume) == 0:
            flags.append("ZERO_VOLUME_TRADE")
        if item.type == "QUOTE":
            if len(item.asks) != 10 or len(item.bids) != 10:
                flags.append("INCOMPLETE_BOOK_LEVELS")
            asks = [Decimal(x.price) for x in item.asks if Decimal(x.price) > 0 and int(x.quantity) > 0]
            bids = [Decimal(x.price) for x in item.bids if Decimal(x.price) > 0 and int(x.quantity) > 0]
            if not asks or not bids:
                flags.append("EMPTY_BOOK_SIDE")
            if asks != sorted(asks) or bids != sorted(bids, reverse=True):
                flags.append("UNORDERED_BOOK")
            if asks and bids and bids[0] >= asks[0]:
                flags.append("LOCKED_OR_CROSSED_BOOK")
        issues.update(flags)
        normalized.append({
            "schemaVersion": "SAGOPALGO_PUBLIC_TICK_V1", "sourceId": config.sourceId,
            "provider": config.provider, "market": config.market, "stockCode": row.stockCode,
            "provenance": config.provenance, "type": row.type, "eventId": row.eventId,
            "marketAt": at.isoformat(), "receivedAt": received.isoformat(),
            # No historical DB commit/strategy availability evidence exists in V1.
            "knownAt": export.exportedAt.isoformat(), "exchangeSequence": None,
            "dateBasis": item.dateBasis, "session": item.session,
            "price": item.price, "volume": item.volume, "cumulativeVolume": item.cumulativeVolume,
            "asks": [x.model_dump() for x in item.asks], "bids": [x.model_dump() for x in item.bids],
            "rawSha256": row.contentHash, "sourceExportSha256": digest(raw), "flags": flags,
        })
    # Export order is market_at,event_id, NOT provider sequence or arrival order.
    trades = [x for x in normalized if x["type"] == "TRADE"]
    by_market = sorted(trades, key=lambda x: (x["marketAt"], int(x["cumulativeVolume"])))
    for previous, current in zip(by_market, by_market[1:]):
        kst = timezone(timedelta(hours=9))
        if precise_time(previous["marketAt"]).astimezone(kst).date() != precise_time(current["marketAt"]).astimezone(kst).date():
            continue
        delta = int(current["cumulativeVolume"]) - int(previous["cumulativeVolume"])
        if delta < 0:
            issues["CUMULATIVE_VOLUME_REGRESSION"] += 1
        elif delta != int(current["volume"]):
            issues["POSSIBLE_TRADE_GAP"] += 1
        if current["receivedAt"] < previous["receivedAt"]:
            issues["OUT_OF_ORDER_RECEIPT"] += 1
    comparisons = []
    by_id = {x["eventId"]: x for x in trades}
    for claim in claims:
        trade = by_id.get(claim.referenceTradeId)
        reasons = []
        if config.provenance == "SYNTHETIC": reasons.append("SYNTHETIC_REFERENCE")
        if config.rights != "PERMITTED": reasons.append("RIGHTS_UNCONFIRMED")
        if trade is None: reasons.append("REFERENCE_TRADE_MISSING")
        elif trade["flags"]: reasons.extend(trade["flags"])
        status = "NOT_ASSESSABLE"
        if not reasons:
            status = "MATCH"
            if precise_time(trade["marketAt"]) != claim.filledAt:
                reasons.append("TRADE_TIME_MISMATCH")
            if Decimal(trade["price"]) != Decimal(claim.price):
                reasons.append("TRADE_PRICE_MISMATCH")
            if int(claim.quantity) > int(trade["volume"]):
                reasons.append("QUANTITY_EXCEEDS_OBSERVED_PRINT")
            if reasons: status = "MISMATCH"
        # Visible quote candidates must satisfy BOTH market and receipt time. V1
        # export availability remains a separate conservative historical gate.
        quotes = [q for q in normalized if q["type"] == "QUOTE"
                  and precise_time(q["marketAt"]) <= claim.decisionAt
                  and precise_time(q["receivedAt"]) <= claim.decisionAt]
        quotes.sort(key=lambda q: (q["marketAt"], q["receivedAt"], q["eventId"]))
        quote = quotes[-1] if quotes else None
        quote_reasons = []
        if quote is not None and sum(q["marketAt"] == quote["marketAt"] for q in quotes) > 1:
            # Hash order is deterministic but is not exchange update order.
            quote_reasons.append("AMBIGUOUS_QUOTE_ORDER")
            quote = None
        if quote is None: quote_reasons.append("NO_PRIOR_QUOTE")
        else:
            quote_reasons.extend(quote["flags"])
            if (claim.decisionAt - precise_time(quote["marketAt"])).total_seconds() * 1000 > config.maxQuoteAgeMs:
                quote_reasons.append("STALE_QUOTE")
        if export.exportedAt > claim.decisionAt:
            quote_reasons.append("HISTORICAL_AVAILABILITY_UNCONFIRMED")
        if config.provenance == "SYNTHETIC": quote_reasons.append("SYNTHETIC_REFERENCE")
        if config.rights != "PERMITTED": quote_reasons.append("RIGHTS_UNCONFIRMED")
        comparisons.append({"claimId": claim.claimId, "referenceTradeId": claim.referenceTradeId,
                            "marketReferenceStatus": status, "reasons": sorted(set(reasons)),
                            "quoteEventId": quote["eventId"] if quote else None,
                            "quoteStatus": "NOT_ASSESSABLE" if quote_reasons else "REFERENCE_ONLY",
                            "quoteReasons": sorted(set(quote_reasons)),
                            "accountFillStatus": "NOT_PROVEN"})
    normalized.sort(key=lambda x: (x["marketAt"], x["eventId"]))
    report = {"schemaVersion": "SAGOPALGO_TICK_AUDIT_V1", "sourceExportSha256": digest(raw),
              "config": config.model_dump(mode="json"), "counts": dict(Counter(x["type"] for x in normalized)),
              "status": "NO_TICK_SAMPLE" if not normalized else "AUDITED_OBSERVATIONS",
              "issues": dict(sorted(issues.items())), "comparisons": comparisons,
              "comparisonCounts": dict(Counter(x["marketReferenceStatus"] for x in comparisons)),
              "missingCapabilities": ["EXCHANGE_SEQUENCE", "RAW_WS_FRAME", "DB_COMMIT_AT",
                                      "STRATEGY_AVAILABLE_AT", "ACCOUNT_ORDER_FILL", "QUEUE_POSITION",
                                      "INDEPENDENT_TICK_SIZE_FEE_TAX_EVIDENCE"],
              "quoteDatePolicy": "INFERRED_DATES_NOT_PROMOTED", "coverage": "OBSERVED_ONLY",
              "declarations": "MARKET_PROVENANCE_RIGHTS_SESSION_CODES_ARE_CALLER_EVIDENCE_NOT_AUTOMATIC_VERIFICATION",
              "usableForTrading": False, "usableForStrategyValidation": False}
    return normalized, report


def audit_tick_files(input_path: Path, config_path: Path, output: Path, claims_path: Path | None = None):
    raw, config_raw = read_bytes(input_path), read_bytes(config_path)
    config = TickAuditConfig.model_validate(read_json(config_raw))
    claims_raw = read_bytes(claims_path) if claims_path else b"[]"
    values = read_json(claims_raw)
    if not isinstance(values, list) or len(values) > 10000:
        raise ResearchError("CLAIM_LIST_INVALID")
    normalized, report = audit_ticks(raw, config, [ExecutionClaim.model_validate(x) for x in values])
    if output.exists():
        raise ResearchError("OUTPUT_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".tick-audit-", dir=output.parent))
    prepared = False
    try:
        files = {"source-export.json": raw, "config.json": config_raw, "claims.json": claims_raw,
                 "ticks.jsonl": b"".join(canonical(x) + b"\n" for x in normalized)}
        report["files"] = {name: digest(content) for name, content in files.items()}
        report["reportId"] = digest(canonical(report))
        files["audit.json"] = canonical(report) + b"\n"
        for name, content in files.items():
            with (stage / name).open("xb") as stream:
                stream.write(content)
        prepared = True
        publish_directory(stage, output)
    finally:
        if not prepared and stage.exists(): shutil.rmtree(stage)
    return report
