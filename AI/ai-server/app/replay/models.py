from datetime import datetime, timezone
from decimal import Decimal
import re
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator


class ResearchError(ValueError):
    """A fixed diagnostic code safe to display without echoing input rows."""


def utc(value: object) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})", value
    ):
        raise ValueError("timezone-aware ISO string required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone required")
    result = parsed.astimezone(timezone.utc)
    if not 2000 <= result.year <= 2100:
        raise ValueError("supported research dates are 2000 through 2100")
    return result


Timestamp = Annotated[datetime, BeforeValidator(utc)]
Number = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]{0,17})(\.[0-9]{1,8})?$")]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,100}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Source(StrictModel):
    sourceId: Identifier
    provider: str = Field(min_length=1, max_length=100)
    reference: str = Field(min_length=1, max_length=500)
    rights: Literal["UNCONFIRMED", "PERMITTED"]
    provenance: Literal["OBSERVED", "PROVIDER_HISTORICAL", "SYNTHETIC", "DERIVED_OBSERVATIONS"]
    availability: Literal["OBSERVED_AT", "PUBLICATION_ASSUMED", "RECEIPT_DERIVED"]
    notes: str = Field(min_length=1, max_length=1000)


class ExpectedBar(StrictModel):
    sourceId: Identifier
    stockCode: str = Field(pattern=r"^[0-9]{6}$")
    startAt: Timestamp
    endAt: Timestamp

    @model_validator(mode="after")
    def duration(self):
        if self.endAt <= self.startAt:
            raise ValueError("invalid expected interval")
        return self


class DatasetSpec(StrictModel):
    schemaVersion: Literal["SAGOPALGO_REPLAY_V1"]
    name: str = Field(min_length=1, max_length=100)
    sources: list[Source] = Field(min_length=1, max_length=100)
    limitations: list[str] = Field(min_length=1, max_length=100)
    expectedBars: list[ExpectedBar] = Field(default_factory=list, max_length=200000)

    @model_validator(mode="after")
    def unique_sources(self):
        ids = [source.sourceId for source in self.sources]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate source")
        if any(item.sourceId not in ids for item in self.expectedBars):
            raise ValueError("unknown expected source")
        keys = [(v.sourceId, v.stockCode, v.startAt, v.endAt) for v in self.expectedBars]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate expected interval")
        return self


class Bar(StrictModel):
    startAt: Timestamp
    endAt: Timestamp
    timeframe: Literal["MINUTE_1", "DAY"]
    open: Number
    high: Number
    low: Number
    close: Number
    volume: str = Field(pattern=r"^(0|[1-9][0-9]{0,17})$")
    priceBasis: Literal["RAW"]
    session: Literal["REGULAR"]
    status: Literal["TRADABLE", "HALTED"]

    @model_validator(mode="after")
    def valid_bar(self):
        seconds = (self.endAt - self.startAt).total_seconds()
        if seconds <= 0 or seconds > 86400 or (self.timeframe == "MINUTE_1" and seconds != 60):
            raise ValueError("invalid bar interval")
        low, high, opened, closed = map(Decimal, [self.low, self.high, self.open, self.close])
        if not (0 < low <= min(opened, closed) <= max(opened, closed) <= high):
            raise ValueError("invalid OHLC")
        return self


class Membership(StrictModel):
    effectiveAt: Timestamp
    eligible: bool
    reason: str = Field(min_length=1, max_length=500)


class ResearchContent(StrictModel):
    title: str = Field(min_length=1, max_length=2000)
    summary: str = Field(max_length=10000)
    link: str = Field(max_length=2000)
    origin: Literal["OBSERVED", "LEGACY_BASELINE"]


class Record(StrictModel):
    sourceId: Identifier
    kind: Literal["BAR", "UNIVERSE", "NEWS", "DISCLOSURE"]
    itemId: Identifier
    revision: int = Field(ge=1, le=1000000)
    stockCode: str = Field(pattern=r"^[0-9]{6}$")
    exchange: Literal["KRX"]
    currency: Literal["KRW"]
    publishedAt: Timestamp
    observedAt: Timestamp
    payload: Bar | Membership | ResearchContent

    @model_validator(mode="after")
    def valid_record(self):
        expected = {"BAR": Bar, "UNIVERSE": Membership, "NEWS": ResearchContent, "DISCLOSURE": ResearchContent}
        if not isinstance(self.payload, expected[self.kind]):
            raise ValueError("kind/payload mismatch")
        if self.observedAt < self.publishedAt:
            raise ValueError("observation precedes publication")
        if isinstance(self.payload, Bar) and self.publishedAt < self.payload.endAt:
            raise ValueError("bar published before close")
        return self

    @property
    def key(self) -> tuple[str, str, str]:
        return self.sourceId, self.kind, self.itemId

    @property
    def ref(self) -> str:
        return f"{self.sourceId}/{self.kind}/{self.itemId}/{self.revision}"


class Intent(StrictModel):
    intentId: Identifier
    stockCode: str = Field(pattern=r"^[0-9]{6}$")
    decisionAt: Timestamp
    expiresAt: Timestamp
    side: Literal["BUY", "SELL"]
    quantity: int = Field(ge=1, le=1000000000)
    evidence: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def expiry(self):
        if self.expiresAt <= self.decisionAt:
            raise ValueError("invalid intent validity")
        if len(self.evidence) != len(set(self.evidence)):
            raise ValueError("duplicate evidence")
        return self


class ReplayConfig(StrictModel):
    barSourceId: Identifier
    universeSourceId: Identifier
    startAt: Timestamp
    endAt: Timestamp
    initialCash: str = Field(pattern=r"^[1-9][0-9]{0,17}$")
    feeBps: Number
    sellTaxBps: Number
    halfSpreadBps: Number
    slippageBps: Number
    participationRate: Number
    tickSize: str = Field(pattern=r"^[1-9][0-9]{0,8}$")
    latencyMs: int = Field(ge=0, le=600000)
    maxSignalAgeSeconds: int = Field(ge=1, le=86400)
    maxMarkAgeSeconds: int = Field(ge=1, le=86400)
    maxOrderNotional: str = Field(pattern=r"^[1-9][0-9]{0,17}$")
    allowSynthetic: bool = False
    allowAssumedAvailability: bool = False
    allowDerivedAvailability: bool = False
    intents: list[Intent] = Field(max_length=1000)

    @model_validator(mode="after")
    def bounds(self):
        if self.endAt <= self.startAt:
            raise ValueError("invalid replay window")
        if any(Decimal(v) > 1000 for v in [self.feeBps, self.sellTaxBps, self.halfSpreadBps, self.slippageBps]):
            raise ValueError("cost out of bounds")
        if not 0 < Decimal(self.participationRate) <= 1:
            raise ValueError("invalid participation")
        ids = [item.intentId for item in self.intents]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate intent")
        if any(not self.startAt <= i.decisionAt < i.expiresAt <= self.endAt for i in self.intents):
            raise ValueError("intent outside window")
        return self
