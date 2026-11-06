"""Convert bounded stored-public-data exports, preserving their original bytes separately."""
from collections import Counter, defaultdict
from datetime import timedelta, timezone
from decimal import Decimal
from itertools import groupby
from pathlib import Path
import os
import re
import shutil
import tempfile
from typing import Literal

from pydantic import Field, model_validator

from .dataset import MAX_BYTES, canonical, digest, normalize, read_bytes, read_json, records_bytes
from .models import DatasetSpec, Identifier, Record, ResearchError, StrictModel, Timestamp, utc
from .file_publish import publish_directory


class ConversionConfig(StrictModel):
    provenance: Literal["OBSERVED", "SYNTHETIC"]
    rights: Literal["UNCONFIRMED", "PERMITTED"]
    rightsEvidence: str = Field(min_length=1, max_length=400)
    regularSessionCodes: list[str] = Field(min_length=1, max_length=10)
    sessionEvidence: str = Field(min_length=1, max_length=400)
    availabilityMode: Literal["EXPORT_OBSERVED", "RECEIPT_DERIVED"] = "EXPORT_OBSERVED"

    @model_validator(mode="after")
    def session_codes(self):
        if len(set(self.regularSessionCodes)) != len(self.regularSessionCodes) or any(
            not re.fullmatch(r"[A-Za-z0-9]{1,4}", code) for code in self.regularSessionCodes
        ):
            raise ValueError("explicit distinct session codes required")
        return self


class StreamRow(StrictModel):
    eventId: str = Field(pattern=r"^[a-f0-9]{64}$")
    stockCode: str = Field(pattern=r"^[0-9]{6}$")
    type: Literal["TRADE", "QUOTE"]
    marketAt: Timestamp
    receivedAt: Timestamp
    payloadJson: str = Field(max_length=1048576)
    contentHash: str = Field(pattern=r"^[a-f0-9]{64}$")


class VersionRow(StrictModel):
    changeId: int = Field(ge=1)
    kind: Literal["NEWS", "DISCLOSURE"]
    provider: Identifier
    stockCode: str = Field(pattern=r"^[0-9]{6}$")
    itemKey: str = Field(pattern=r"^[a-f0-9]{64}$")
    revision: int = Field(ge=1, le=1000000)
    observedAt: Timestamp
    origin: Literal["OBSERVED", "LEGACY_BASELINE"]
    payloadJson: str = Field(max_length=1048576)
    contentHash: str = Field(pattern=r"^[a-f0-9]{64}$")


class StoredExport(StrictModel):
    schemaVersion: Literal["SAGOPALGO_STORED_EXPORT_V1"]
    stockCode: str = Field(pattern=r"^[0-9]{6}$")
    # API spells these fields 'from' and 'to'; aliases keep Python syntax valid.
    start: Timestamp = Field(alias="from")
    end: Timestamp = Field(alias="to")
    exportedAt: Timestamp
    readOnly: bool
    usableForTrading: bool
    consistency: Literal["REPEATABLE_READ"]
    streamCoverage: Literal["OBSERVED_ONLY"]
    researchScope: Literal["ALL_VERSIONS_OBSERVED_BEFORE_TO"]
    streamEvents: list[StreamRow] = Field(max_length=10000)
    researchVersions: list[VersionRow] = Field(max_length=10000)

    @model_validator(mode="after")
    def boundaries(self):
        if not self.readOnly or self.usableForTrading:
            raise ValueError("read-only research contract required")
        if not self.start < self.end <= self.exportedAt or self.end - self.start > timedelta(days=1):
            raise ValueError("invalid export window")
        if any(at.second or at.microsecond for at in [self.start, self.end]):
            raise ValueError("whole minute boundaries required")
        if any(r.stockCode != self.stockCode or not self.start <= r.marketAt < self.end for r in self.streamEvents):
            raise ValueError("stream outside scope")
        if any(r.stockCode != self.stockCode or r.observedAt >= self.end for r in self.researchVersions):
            raise ValueError("research outside scope")
        ids = [r.eventId for r in self.streamEvents]
        changes = [r.changeId for r in self.researchVersions]
        if len(ids) != len(set(ids)) or changes != sorted(set(changes)):
            raise ValueError("duplicate or unordered export identity")
        return self


class AvailabilityObservation(StrictModel):
    contentHash: str = Field(pattern=r"^[a-f0-9]{64}$")
    clockDomain: str = Field(pattern=r"^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$")
    commitObservedAt: Timestamp
    inputPublishedAt: Timestamp
    commitElapsedNanos: int = Field(ge=0)
    publishedElapsedNanos: int = Field(ge=0)
    clockQuality: Literal["MONOTONIC_STABLE", "CLOCK_STEP_DETECTED"]
    clockBasis: Literal["JVM_MONOTONIC_ANCHORED_UTC"]
    utcSynchronized: Literal[False]

    @model_validator(mode="after")
    def chronology(self):
        if self.commitObservedAt > self.inputPublishedAt or self.commitElapsedNanos > self.publishedElapsedNanos:
            raise ValueError("availability observations out of causal order")
        return self


class StreamRowV2(StreamRow):
    availability: AvailabilityObservation | None = None

    @model_validator(mode="after")
    def binding(self):
        if self.availability and self.availability.contentHash != self.contentHash:
            raise ValueError("availability must bind to the original source payload")
        return self


class StoredExportV2(StoredExport):
    schemaVersion: Literal["SAGOPALGO_STORED_EXPORT_V2"]
    streamEvents: list[StreamRowV2] = Field(max_length=10000)


def parse_export(value):
    return (StoredExportV2 if isinstance(value, dict) and value.get("schemaVersion")=="SAGOPALGO_STORED_EXPORT_V2"
            else StoredExport).model_validate(value)


def precise_time(value):
    """Conservatively CEIL source nanoseconds to supported microseconds; never round earlier."""
    if not isinstance(value, str):
        raise ResearchError("STORED_TIMESTAMP_INVALID")
    matched = re.fullmatch(r"(.{19})(?:\.([0-9]{1,9}))?(Z|[+-][0-9]{2}:[0-9]{2})", value)
    if not matched:
        raise ResearchError("STORED_TIMESTAMP_INVALID")
    prefix, fraction, offset = matched.groups()
    fraction = (fraction or "").ljust(9, "0")
    at = utc(prefix + "." + fraction[:6] + offset)
    return at + (timedelta(microseconds=1) if int(fraction[6:]) else timedelta())


def payload(row):
    raw = row.payloadJson.encode("utf-8")
    if digest(raw) != row.contentHash:
        raise ResearchError("STORED_PAYLOAD_HASH_MISMATCH")
    value = read_json(raw)
    if not isinstance(value, dict) or value.get("stockCode") != row.stockCode:
        raise ResearchError("STORED_PAYLOAD_IDENTITY_MISMATCH")
    return value


def convert(raw: bytes, config: ConversionConfig):
    value = read_json(raw)
    if isinstance(value, dict) and "success" in value:
        if set(value) - {"success", "data", "error", "message"} or value.get("success") is not True or value.get("error") is not None:
            raise ResearchError("STORED_EXPORT_FAILED")
        value = value.get("data")
    export = parse_export(value)
    skipped = Counter()
    trades = defaultdict(list)
    sources = {}
    converted = []
    reference = "stored-export:sha256:" + digest(raw)
    derived = config.availabilityMode == "RECEIPT_DERIVED"

    def source(source_id, provider, availability, bars=False):
        sources[source_id] = {
            "sourceId": source_id, "provider": provider, "reference": reference,
            "rights": config.rights, "provenance": "SYNTHETIC" if config.provenance == "SYNTHETIC"
            else ("DERIVED_OBSERVATIONS" if bars else "OBSERVED"), "availability": availability,
            "notes": config.rightsEvidence + ("; session mapping: " + config.sessionEvidence if bars else ""),
        }

    def record(source_id, kind, item, revision, published, observed, body):
        return {"sourceId": source_id, "kind": kind, "itemId": item, "revision": revision,
                "stockCode": export.stockCode, "exchange": "KRX", "currency": "KRW",
                "publishedAt": published.isoformat(), "observedAt": observed.isoformat(), "payload": body}

    for row in export.streamEvents:
        item = payload(row)
        allowed = {"eventId", "stockCode", "type", "marketTime", "receivedAt", "price", "volume",
                   "cumulativeVolume", "asks", "bids", "session", "dateBasis"}
        if set(item) - allowed or item.get("eventId") != row.eventId or item.get("type") != row.type:
            raise ResearchError("STORED_EVENT_INVALID")
        at, received = precise_time(item.get("marketTime")), precise_time(item.get("receivedAt"))
        if at != row.marketAt or abs(received - row.receivedAt) > timedelta(microseconds=1) or received > export.exportedAt:
            raise ResearchError("STORED_EVENT_TIME_MISMATCH")
        if row.type == "QUOTE":
            skipped["QUOTE_NOT_A_BAR"] += 1
            continue
        if item.get("dateBasis") != "PROVIDER_DATE":
            skipped["UNCONFIRMED_BUSINESS_DATE"] += 1
            continue
        if item.get("session") not in config.regularSessionCodes:
            skipped["UNMAPPED_SESSION"] += 1
            continue
        for field in ["price", "volume", "cumulativeVolume"]:
            pattern = r"[0-9]{1,24}(?:\.[0-9]{1,6})?" if field == "price" else r"[0-9]{1,24}"
            if not isinstance(item.get(field), str) or not re.fullmatch(pattern, item[field]):
                raise ResearchError("STORED_TRADE_NUMBER_INVALID")
        if Decimal(item["price"]) <= 0 or int(item["cumulativeVolume"]) < int(item["volume"]):
            raise ResearchError("STORED_TRADE_NUMBER_INVALID")
        identity = f'TRADE|{export.stockCode}|{at.astimezone(timezone(timedelta(hours=9))).date()}|{int(item["cumulativeVolume"])}'
        if digest(identity.encode()) != row.eventId:
            raise ResearchError("STORED_TRADE_ID_MISMATCH")
        if int(item["volume"]) == 0:
            skipped["ZERO_VOLUME_TRADE"] += 1
            continue
        minute = at.replace(second=0, microsecond=0)
        trades[minute].append((received, at, int(item["cumulativeVolume"]), Decimal(item["price"]), int(item["volume"])))
    if trades:
        source("r2-kis", "KIS_KRX_OBSERVED_TICKS", "RECEIPT_DERIVED" if derived else "OBSERVED_AT", True)
    for minute, items in sorted(trades.items()):
        end = minute + timedelta(minutes=1)
        visible = []
        revision = 0
        # Coalesce everything known by close; each later receipt group is a new version.
        groups = groupby(sorted(items), key=lambda t: max(end, t[0]) if derived else export.exportedAt)
        for available, arrived in groups:
            visible.extend(arrived)
            ordered = sorted(visible, key=lambda t: (t[1], t[2]))
            prices = [t[3] for t in ordered]
            revision += 1
            converted.append(record("r2-kis", "BAR", export.stockCode + "-" + minute.strftime("%Y%m%dT%H%M%S"),
                revision, available if derived else end, export.exportedAt,
                {"startAt": minute.isoformat(), "endAt": end.isoformat(), "timeframe": "MINUTE_1",
                 "open": format(prices[0], "f"), "high": format(max(prices), "f"), "low": format(min(prices), "f"),
                 "close": format(prices[-1], "f"), "volume": str(sum(t[4] for t in ordered)),
                 "priceBasis": "RAW", "session": "REGULAR", "status": "TRADABLE"}))
    versions = defaultdict(list)
    for row in export.researchVersions:
        versions[(row.kind, row.provider, row.itemKey)].append((row, payload(row)))
    for (kind, provider, item_key), history in sorted(versions.items()):
        previous = None
        for n, (row, item) in enumerate(history, 1):
            if row.revision != n or (previous is not None and row.observedAt < previous):
                raise ResearchError("STORED_RESEARCH_LINEAGE_INVALID")
            previous = row.observedAt
            allowed = {"provider", "stockCode", "title", "link", "summary", "publishedAt"} if kind == "NEWS" else {
                "provider", "stockCode", "corpCode", "corpName", "reportName", "receiptNumber", "submitterName", "receiptDate", "link"}
            if set(item) - allowed or item.get("provider") != provider:
                raise ResearchError("STORED_RESEARCH_PAYLOAD_INVALID")
        if kind == "DISCLOSURE":
            skipped["DATE_ONLY_DISCLOSURE"] += len(history)
            continue
        prepared = []
        reason = None
        for row, item in history:
            if not item.get("publishedAt"):
                reason = "UNKNOWN_PUBLICATION_TIME"
                break
            published = precise_time(item["publishedAt"])
            if published > row.observedAt:
                reason = "PUBLICATION_AFTER_OBSERVATION"
                break
            source_id = "r3-" + digest(provider.encode())[:16]
            prepared.append(record(source_id, kind, item_key, row.revision, published, row.observedAt,
                {"title": item.get("title"), "summary": item.get("summary") or "", "link": item.get("link") or "", "origin": row.origin}))
        if reason:
            skipped[reason] += len(history)
            continue
        source(source_id, provider, "OBSERVED_AT")
        converted.extend(prepared)
    if not sources:
        source("stored-empty", "STORED_PUBLIC_EXPORT", "OBSERVED_AT")
    spec = DatasetSpec.model_validate({"schemaVersion": "SAGOPALGO_REPLAY_V1", "name": "Stored public observations " + export.stockCode,
        "sources": [sources[k] for k in sorted(sources)], "expectedBars": [], "limitations": [
            "OBSERVED_ONLY: no exchange/calendar completeness or corporate action/universe proof.",
            "Original export retained; quotes and date-only disclosures are not silently made into timestamped bars/events.",
            "Receipt-derived availability is hypothetical calculation time, not DB commit or historical strategy availability."
            if derived else "Derived bars become known at export time; no earlier calculation/commit timestamp is invented."]})
    data = b"".join(canonical(r) + b"\n" for r in converted)
    records = normalize(data, spec) if converted else []
    report = {"schemaVersion": "SAGOPALGO_STORED_CONVERSION_V1", "inputSha256": digest(raw),
              "config": config.model_dump(mode="json"), "readOnly": True, "usableForTrading": False,
              "streamInputCount": len(export.streamEvents), "researchInputCount": len(export.researchVersions),
              "outputRecordCount": len(records), "excludedCounts": dict(sorted(skipped.items())), "universe": "NOT_PROVIDED",
              "status": "NO_CONVERTIBLE_RECORDS" if not records else ("CONVERTED_WITH_EXCLUSIONS" if skipped else "CONVERTED")}
    return spec, records, report


def convert_file(input_path: Path, config_path: Path, output: Path):
    raw = read_bytes(input_path)
    config = ConversionConfig.model_validate(read_json(read_bytes(config_path)))
    spec, records, report = convert(raw, config)
    contents = {"source-export.json": raw, "spec.json": canonical(spec.model_dump(mode="json")),
                "records.jsonl": records_bytes(records)}
    if any(len(data) > MAX_BYTES for data in contents.values()):
        raise ResearchError("OUTPUT_SIZE_LIMIT")
    report["files"] = {name: {"sha256": digest(data), "bytes": len(data)} for name, data in contents.items()}
    if output.exists() or output.is_symlink():
        raise ResearchError("OUTPUT_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".stored-convert-", dir=output.parent))
    prepared = False
    try:
        for name, data in contents.items():
            (staging / name).write_bytes(data)
        (staging / "conversion.json").write_bytes(canonical(report))
        if output.exists():
            raise ResearchError("OUTPUT_EXISTS")
        prepared = True
        publish_directory(staging, output)
    finally:
        if staging.exists() and not prepared:
            shutil.rmtree(staging)
    return report
