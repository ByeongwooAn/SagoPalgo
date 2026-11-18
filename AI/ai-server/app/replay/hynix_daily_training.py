"""Audit the SK hynix RAW capture and reproduce the two-stock prototype's common dates."""

import argparse
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from .dataset import canonical, digest, read_bytes, read_json
from .file_publish import publish_directory
from .history import audit as audit_history
from .history import comparable, load_job
from .models import ResearchError
from .samsung_daily_training import (
    CALENDAR_REPORT,
    boundary_observations,
    build_manifest as build_samsung_manifest,
    read_pinned,
    review_boundaries,
    validate_trading_dates,
)

CAPTURE = "kis-sk-hynix-daily-20261118"
JOBS = ("job", "continuation", "shorter-windows", "remaining")
SAMPLE_USES = {"TRAIN", "VALIDATION", "FINAL_EVALUATION"}
REVIEWED_CASH_DIVIDENDS = {
    "2023-12-27": "02",
    "2024-03-28": "05",
    "2024-06-27": "05",
    "2024-09-27": "05",
    "2025-02-27": "02",
    "2025-05-29": "05",
    "2025-08-28": "05",
    "2025-11-27": "05",
    "2026-02-26": "02",
    "2026-05-28": "05",
    "2026-08-28": "05",
}
REVIEWED_LARGE_MOVES = {
    "2025-01-31": ["OPEN_GAP_AT_LEAST_10_PERCENT"],
    "2025-04-10": ["OPEN_GAP_AT_LEAST_10_PERCENT"],
    "2026-03-05": ["OPEN_GAP_AT_LEAST_10_PERCENT"],
    "2026-05-27": ["OPEN_GAP_AT_LEAST_10_PERCENT"],
    "2026-06-08": ["OPEN_GAP_AT_LEAST_10_PERCENT"],
    "2026-06-09": ["CLOSE_MOVE_AT_LEAST_15_PERCENT"],
    "2026-06-25": ["OPEN_GAP_AT_LEAST_10_PERCENT"],
    "2026-07-13": ["CLOSE_MOVE_AT_LEAST_15_PERCENT"],
    "2026-07-15": ["OPEN_GAP_AT_LEAST_10_PERCENT"],
    "2026-07-31": ["OPEN_GAP_AT_LEAST_10_PERCENT", "CLOSE_MOVE_AT_LEAST_15_PERCENT"],
}


def merge_rows(batches):
    merged = {}
    overlaps = 0
    for rows in batches:
        for row in rows:
            date = row["businessDate"]
            if date in merged:
                if comparable(row) != comparable(merged[date]):
                    raise ResearchError("HYNIX_DAILY_CROSS_JOB_CONFLICT")
                overlaps += 1
            else:
                merged[date] = row
    return [merged[date] for date in sorted(merged)], overlaps


def audit_capture(capture):
    sources, batches, records = [], [], []
    for name in JOBS:
        job = capture / name
        report, rows = audit_history(job, check_daily=True)
        _, config, journal = load_job(job)
        if config.stockCode != "000660" or report["provenance"] != "PROVIDER_HISTORICAL":
            raise ResearchError("HYNIX_DAILY_CAPTURE_SCOPE_MISMATCH")
        responses = []
        for attempt in journal["attempts"]:
            if attempt.get("file"):
                responses.append({key: attempt[key] for key in ("file", "sha256", "status")})
                if attempt["status"] == "COMPLETE":
                    sources.append((job / attempt["file"], attempt["sha256"]))
        records.append({
            "job": name,
            "planId": report["planId"],
            "status": report["status"],
            "callsUsed": report["callsUsed"],
            "completedWindows": report["completedWindows"],
            "overlapComparisons": report["overlapComparisons"],
            "verificationPassed": report["verificationPassed"],
            "dailySha256": digest(read_bytes(job / "daily.jsonl")),
            "journalSha256": digest(read_bytes(job / "journal.json")),
            "originalResponses": responses,
        })
        batches.append(rows)
    rows, overlaps = merge_rows(batches)
    return rows, overlaps, sources, records


def frozen_hynix_dates(samsung_dates, reviews):
    # Both stocks have been audited against the same complete KOSPI open-day list.
    # Reuse the exact frozen feature/target dates and split boundaries.
    dates = []
    for day in samsung_dates:
        entry = dict(day)
        if "priceReview" in day:
            entry["priceReview"] = reviews.get(day["businessDate"], [])
        entry["commonSample"] = day["sampleUse"] in SAMPLE_USES
        dates.append(entry)
    return dates


def build_bundle(artifacts):
    samsung = build_samsung_manifest(artifacts)
    calendar = read_json(read_pinned(artifacts / CALENDAR_REPORT, "calendar"))
    rows, overlaps, sources, jobs = audit_capture(artifacts / CAPTURE)
    validate_trading_dates(calendar["days"], rows)
    reviews = review_boundaries(boundary_observations(sources), rows, REVIEWED_CASH_DIVIDENDS, REVIEWED_LARGE_MOVES)
    dates = frozen_hynix_dates(samsung["dates"], reviews)
    daily = b"".join(canonical(row) + b"\n" for row in rows)
    manifest = {
        "schemaVersion": "SAGOPALGO_HYNIX_DAILY_TRAINING_DATES_V1",
        "stockCode": "000660",
        "market": "KOSPI",
        "priceBasis": "RAW",
        "startDate": calendar["startDate"],
        "endDate": calendar["endDate"],
        "lookbackSessionsBeforeSignal": samsung["lookbackSessionsBeforeSignal"],
        "samsungDatesSha256": digest(canonical(samsung) + b"\n"),
        "calendarSha256": samsung["sourceSha256"]["calendar"],
        "dailySha256": digest(daily),
        "crossJobOverlapComparisons": overlaps,
        "captureJobs": jobs,
        "sampleCounts": dict(Counter(row["sampleUse"] for row in dates)),
        "commonSampleCounts": dict(Counter(row["sampleUse"] for row in dates if row["commonSample"])),
        "dates": dates,
    }
    return {"dates.json": canonical(manifest) + b"\n", "daily.jsonl": daily}, manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit"))
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        files, manifest = build_bundle(args.artifacts)
        if args.action == "build":
            with TemporaryDirectory(dir=args.output.parent) as stage:
                prepared = Path(stage) / "bundle"
                prepared.mkdir()
                for name, raw in files.items():
                    (prepared / name).write_bytes(raw)
                publish_directory(prepared, args.output)
        elif any(read_bytes(args.output / name) != raw for name, raw in files.items()):
            raise ResearchError("HYNIX_DAILY_BUNDLE_CHANGED")
    except ResearchError as error:
        print(error)
        return 2
    except OSError:
        print("HYNIX_DAILY_BUNDLE_IO_ERROR")
        return 2
    print(canonical({"manifestSha256": digest(files["dates.json"]), "dailySha256": manifest["dailySha256"],
                     "commonSampleCounts": manifest["commonSampleCounts"]}).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
