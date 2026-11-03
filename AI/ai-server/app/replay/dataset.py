"""Content-addressed bundles and conservative point-in-time selection."""
import hashlib
import json
import os
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

from .models import Bar, DatasetSpec, Membership, Record, ResearchContent, ResearchError

VERSION = "SAGOPALGO_REPLAY_V1"
MAX_BYTES = 128 * 1024 * 1024
MAX_ROWS = 200000
FILES = ("spec.json", "raw.jsonl", "records.jsonl", "quality.json")


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ResearchError("INPUT_FILE_INVALID")
    value = path.read_bytes()
    if len(value) > MAX_BYTES:
        raise ResearchError("INPUT_SIZE_LIMIT")
    return value


def read_json(value: bytes):
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ResearchError("DUPLICATE_JSON_KEY")
            result[key] = item
        return result
    return json.loads(value.decode("utf-8-sig"), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ResearchError("INVALID_JSON_NUMBER")))


def known_at(record: Record, spec: DatasetSpec):
    source = next(s for s in spec.sources if s.sourceId == record.sourceId)
    # A legacy baseline has no trustworthy historical observation time.
    if record.revision > 1 or (isinstance(record.payload, ResearchContent) and record.payload.origin == "LEGACY_BASELINE"):
        return record.observedAt
    return record.observedAt if source.availability == "OBSERVED_AT" else record.publishedAt


def normalize(raw: bytes, spec: DatasetSpec) -> list[Record]:
    sources = {s.sourceId for s in spec.sources}
    rows = raw.splitlines()
    if len(rows) > MAX_ROWS:
        raise ResearchError("INPUT_ROW_LIMIT")
    groups = defaultdict(dict)
    for line in rows:
        if not line.strip():
            raise ResearchError("BLANK_INPUT_ROW")
        item = Record.model_validate(read_json(line))
        if item.sourceId not in sources:
            raise ResearchError("UNKNOWN_SOURCE")
        old = groups[item.key].get(item.revision)
        if old and old != item:
            raise ResearchError("REVISION_CONFLICT")
        groups[item.key][item.revision] = item
    if not groups:
        raise ResearchError("EMPTY_DATASET")
    records = []
    intervals = {}
    for key in sorted(groups):
        versions = sorted(groups[key].values(), key=lambda r: r.revision)
        for n, item in enumerate(versions, 1):
            if item.revision != n:
                raise ResearchError("REVISION_GAP")
            if item.stockCode != versions[0].stockCode:
                raise ResearchError("REVISION_IDENTITY_CHANGED")
            if n > 1 and (known_at(item, spec) < known_at(versions[n - 2], spec)
                          or item.observedAt < versions[n - 2].observedAt):
                raise ResearchError("REVISION_TIME_REVERSED")
            if isinstance(item.payload, Bar):
                first = versions[0].payload
                identity = (item.payload.startAt, item.payload.endAt, item.payload.timeframe)
                if identity != (first.startAt, first.endAt, first.timeframe):
                    raise ResearchError("BAR_INTERVAL_CHANGED")
                slot = (item.sourceId, item.stockCode, *identity)
                if slot in intervals and intervals[slot] != item.itemId:
                    raise ResearchError("AMBIGUOUS_BAR")
                intervals[slot] = item.itemId
            records.append(item)
    # Overlapping bars from one price series cannot be used as independent observations.
    series = defaultdict(list)
    for item in records:
        if item.kind == "BAR" and item.revision == 1:
            series[(item.sourceId, item.stockCode, item.payload.timeframe)].append(item.payload)
    for bars in series.values():
        bars.sort(key=lambda b: b.startAt)
        if any(a.endAt > b.startAt for a, b in zip(bars, bars[1:])):
            raise ResearchError("OVERLAPPING_BARS")
    return records


def snapshot(records: list[Record], spec: DatasetSpec, at) -> list[Record]:
    latest = {}
    for item in records:
        if known_at(item, spec) <= at and (item.key not in latest or item.revision > latest[item.key].revision):
            latest[item.key] = item
    # Effective dates are applied AFTER revision selection, preventing old versions from resurfacing.
    return [item for key, item in sorted(latest.items())
            if not isinstance(item.payload, Membership) or item.payload.effectiveAt <= at]


def membership(records: list[Record], source: str, stock: str):
    candidates = [r for r in records if r.kind == "UNIVERSE" and r.sourceId == source and r.stockCode == stock]
    if not candidates:
        return None
    newest = max(r.payload.effectiveAt for r in candidates)
    newest_rows = [r for r in candidates if r.payload.effectiveAt == newest]
    if len(newest_rows) != 1:
        raise ResearchError("AMBIGUOUS_MEMBERSHIP")
    return newest_rows[0]


def quality(records: list[Record], spec: DatasetSpec, input_rows: int) -> dict:
    bars = [r for r in records if r.kind == "BAR" and r.revision == 1]
    slots = {(r.sourceId, r.stockCode, r.payload.startAt, r.payload.endAt) for r in bars}
    missing = [e.model_dump(mode="json") for e in spec.expectedBars
               if (e.sourceId, e.stockCode, e.startAt, e.endAt) not in slots]
    return {
        "status": "RESEARCH_ONLY", "usableForTrading": False, "usableForStrategyValidation": False,
        "recordCount": len(records), "inputRows": input_rows, "exactDuplicates": input_rows - len(records),
        "stocks": sorted({r.stockCode for r in records}),
        "kindCounts": {k: sum(r.kind == k for r in records) for k in ["BAR", "UNIVERSE", "NEWS", "DISCLOSURE"]},
        "revisionCount": sum(r.revision > 1 for r in records),
        "syntheticSources": [s.sourceId for s in spec.sources if s.provenance == "SYNTHETIC"],
        "unconfirmedRights": [s.sourceId for s in spec.sources if s.rights == "UNCONFIRMED"],
        "assumedAvailability": [s.sourceId for s in spec.sources if s.availability == "PUBLICATION_ASSUMED"],
        "coverage": "EXPECTED_SLOTS_ONLY" if spec.expectedBars else "UNVERIFIED_NO_CALENDAR",
        "expectedBarCount": len(spec.expectedBars), "missingBarCount": len(missing), "missingBars": missing[:100],
        "corporateActions": "UNVERIFIED", "universeCompleteness": "UNVERIFIED",
        "limitations": spec.limitations,
    }


def records_bytes(records: list[Record]) -> bytes:
    return b"".join(canonical(r.model_dump(mode="json")) + b"\n" for r in records)


def build_bundle(spec_path: Path, input_path: Path, output: Path) -> dict:
    spec_raw, raw = read_bytes(spec_path), read_bytes(input_path)
    spec = DatasetSpec.model_validate(read_json(spec_raw))
    records = normalize(raw, spec)
    report = quality(records, spec, len(raw.splitlines()))
    contents = dict(zip(FILES, [spec_raw, raw, records_bytes(records), canonical(report)]))
    if any(len(value) > MAX_BYTES for value in contents.values()):
        raise ResearchError("OUTPUT_SIZE_LIMIT")
    manifest = {"schemaVersion": VERSION, "engineVersion": "R5_FOUNDATION_1",
                "files": {name: {"sha256": digest(data), "bytes": len(data)} for name, data in contents.items()}}
    manifest["datasetId"] = digest(canonical(manifest))
    if output.exists() or output.is_symlink():
        raise ResearchError("OUTPUT_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".replay-build-", dir=output.parent))
    try:
        for name, data in contents.items():
            (staging / name).write_bytes(data)
        (staging / "manifest.json").write_bytes(canonical(manifest))
        # Rename publishes a complete bundle, never a partially written manifest.
        if output.exists():
            raise ResearchError("OUTPUT_EXISTS")
        os.rename(staging, output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return manifest


def load_bundle(path: Path):
    manifest = read_json(read_bytes(path / "manifest.json"))
    if not isinstance(manifest, dict) or set(manifest) != {"schemaVersion", "engineVersion", "files", "datasetId"}:
        raise ResearchError("MANIFEST_INVALID")
    body = {k: v for k, v in manifest.items() if k != "datasetId"}
    if body["schemaVersion"] != VERSION or body["engineVersion"] != "R5_FOUNDATION_1" or digest(canonical(body)) != manifest["datasetId"]:
        raise ResearchError("MANIFEST_HASH_MISMATCH")
    if not isinstance(body["files"], dict) or set(body["files"]) != set(FILES):
        raise ResearchError("MANIFEST_FILES_INVALID")
    contents = {}
    for name in FILES:
        value = read_bytes(path / name)
        if body["files"][name] != {"sha256": digest(value), "bytes": len(value)}:
            raise ResearchError("ARTIFACT_HASH_MISMATCH")
        contents[name] = value
    spec = DatasetSpec.model_validate(read_json(contents["spec.json"]))
    records = normalize(contents["raw.jsonl"], spec)
    if records_bytes(records) != contents["records.jsonl"]:
        raise ResearchError("NORMALIZATION_MISMATCH")
    report = quality(records, spec, len(contents["raw.jsonl"].splitlines()))
    if canonical(report) != contents["quality.json"]:
        raise ResearchError("QUALITY_MISMATCH")
    return manifest, spec, records, report
