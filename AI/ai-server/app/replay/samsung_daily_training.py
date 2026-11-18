"""Freeze the personal-local Samsung RAW daily sample dates for prototype stage 1."""

import argparse
from collections import Counter
from pathlib import Path

from .dataset import canonical, digest, read_bytes, read_json
from .history import audit as audit_history
from .local_use import load_local_use
from .models import ResearchError

HISTORY_CAPTURE = "kis-daily-live-20261103-130145"
CALENDAR_REPORT = "calendar-sessions-20261105/report.json"
SOURCE_SHA256 = {
    "daily": "5ca574ab5c802d758ecc244190edad5d9249ac353b99799903ce90e1113969a5",
    "journal": "0fe82942381374f358027bef19a9420b890c91c1ffac1ba8c1aac53052fc47a9",
    "calendar": "8803fae3e2bfd85c323693f51a3daba1ed5b9d90df0d99bbeb63fd5f89b23849",
    "localUse": "a4a64585d1b85e78bdd070d4e77522f6ca22d20cfbc828e08e3cbf68be3a81f5",
}
LOOKBACK_SESSIONS = 20
REVIEWED_CASH_DIVIDEND_FLAGS = {
    "2023-12-27": "02",
    "2024-12-27": "02",
    "2025-12-29": "02",
    "2026-09-29": "05",
}
REVIEWED_LARGE_MOVES = {
    "2026-03-05": ["OPEN_GAP_AT_LEAST_10_PERCENT"],
    "2026-06-08": ["OPEN_GAP_AT_LEAST_10_PERCENT"],
    "2026-07-31": ["OPEN_GAP_AT_LEAST_10_PERCENT", "CLOSE_MOVE_AT_LEAST_15_PERCENT"],
}


def read_pinned(path, source):
    raw = read_bytes(path)
    if digest(raw) != SOURCE_SHA256[source]:
        raise ResearchError("SAMSUNG_DAILY_SNAPSHOT_CHANGED")
    return raw


def audit_boundaries(job, responses, rows):
    changes = {}
    for response in responses:
        raw = read_bytes(job / response["file"])
        if digest(raw) != response["sha256"]:
            raise ResearchError("HISTORY_RESPONSE_TAMPERED")
        for row in read_json(raw)["output2"]:
            stamp = row["stck_bsop_date"]
            change = (row["prdy_vrss"], row["flng_cls_code"], row["prtt_rate"], row["mod_yn"], row["revl_issu_reas"])
            if changes.setdefault(stamp, change) != change:
                raise ResearchError("SAMSUNG_DAILY_BOUNDARY_OVERLAP_CONFLICT")

    dividend_flags, large_moves = {}, {}
    for index, row in enumerate(rows):
        stamp = row["businessDate"]
        delta, flag, split, modified, revaluation = changes[stamp.replace("-", "")]
        if split != "0.00" or modified != "N" or revaluation != "":
            raise ResearchError("SAMSUNG_DAILY_UNREVIEWED_PRICE_BASIS_CHANGE")
        if flag != "00":
            dividend_flags[stamp] = flag
        if index == 0:
            continue
        previous_close = int(rows[index - 1]["close"])
        close_move = int(row["close"]) - previous_close
        if close_move != int(delta):
            raise ResearchError("SAMSUNG_DAILY_PREVIOUS_CLOSE_CONFLICT")
        flags = []
        if abs(int(row["open"]) - previous_close) * 100 >= previous_close * 10:
            flags.append("OPEN_GAP_AT_LEAST_10_PERCENT")
        if abs(close_move) * 100 >= previous_close * 15:
            flags.append("CLOSE_MOVE_AT_LEAST_15_PERCENT")
        if flags:
            large_moves[stamp] = flags

    if dividend_flags != REVIEWED_CASH_DIVIDEND_FLAGS or large_moves != REVIEWED_LARGE_MOVES:
        raise ResearchError("SAMSUNG_DAILY_UNREVIEWED_PRICE_BOUNDARY")
    reviews = {date: ["CASH_DIVIDEND_BOUNDARY_KEEP_RAW"] for date in dividend_flags}
    for date, flags in large_moves.items():
        reviews.setdefault(date, []).extend(flags)
    return reviews


def validate_trading_dates(calendar, rows):
    trading_dates = [day["businessDate"] for day in calendar if day["openDay"]]
    if [row["businessDate"] for row in rows] != trading_dates:
        raise ResearchError("SAMSUNG_DAILY_CALENDAR_MISMATCH")
    if any(row["status"] != "OBSERVED_PRICE" or int(row["volume"]) <= 0 for row in rows):
        raise ResearchError("SAMSUNG_DAILY_NOT_TRADED")
    return trading_dates


def freeze_dates(calendar, trading_dates, reviews):
    # Divide eligible signal dates using the cumulative 60% and 80% cut points.
    eligible = len(trading_dates) - LOOKBACK_SESSIONS - 1
    train_end = LOOKBACK_SESSIONS + eligible * 3 // 5
    validation_end = LOOKBACK_SESSIONS + eligible * 4 // 5
    trading_index = {date: index for index, date in enumerate(trading_dates)}
    manifest = []
    for day in calendar:
        stamp = day["businessDate"]
        entry = {"businessDate": stamp, "calendarBasis": day["basis"]}
        if not day["openDay"]:
            entry.update(sampleUse="EXCLUDED_MARKET_CLOSED", holidayReason=day["holidayReason"])
        else:
            index = trading_index[stamp]
            entry.update(
                oldestFeatureDate=trading_dates[index - LOOKBACK_SESSIONS] if index >= LOOKBACK_SESSIONS else None,
                targetDate=trading_dates[index + 1] if index + 1 < len(trading_dates) else None,
                priceReview=reviews.get(stamp, []),
            )
            if index < LOOKBACK_SESSIONS:
                entry["sampleUse"] = "EXCLUDED_INSUFFICIENT_LOOKBACK"
            elif entry["targetDate"] is None:
                entry["sampleUse"] = "EXCLUDED_TARGET_OUTSIDE_SNAPSHOT"
            elif index + 1 in (train_end, validation_end):
                entry["sampleUse"] = "EXCLUDED_TARGET_CROSSES_SPLIT"
            elif index < train_end:
                entry["sampleUse"] = "TRAIN"
            elif index < validation_end:
                entry["sampleUse"] = "VALIDATION"
            else:
                entry["sampleUse"] = "FINAL_EVALUATION"
        manifest.append(entry)
    return manifest


def build_manifest(artifacts):
    capture = artifacts / HISTORY_CAPTURE
    job = capture / "job"
    daily_raw = read_pinned(job / "daily.jsonl", "daily")
    journal = read_json(read_pinned(job / "journal.json", "journal"))
    calendar = read_json(read_pinned(artifacts / CALENDAR_REPORT, "calendar"))
    local_use = capture / "personal-local-use.json"
    read_pinned(local_use, "localUse")
    history, rows = audit_history(job, check_daily=True)
    load_local_use(local_use, history, daily_raw)
    if len(rows) != 730 or any(row["stockCode"] != "005930" or row["priceBasis"] != "RAW" for row in rows):
        raise ResearchError("SAMSUNG_DAILY_SCOPE_MISMATCH")

    responses = [{key: attempt[key] for key in ("file", "sha256")} for attempt in journal["attempts"] if attempt.get("file")]
    # Match calendar order before comparing adjacent observations or their targets.
    trading_dates = validate_trading_dates(calendar["days"], rows)
    reviews = audit_boundaries(job, responses, rows)
    dates = freeze_dates(calendar["days"], trading_dates, reviews)
    return {
        "schemaVersion": "SAGOPALGO_SAMSUNG_DAILY_TRAINING_DATES_V1",
        "stockCode": "005930",
        "market": "KOSPI",
        "priceBasis": "RAW",
        "startDate": calendar["startDate"],
        "endDate": calendar["endDate"],
        "lookbackSessionsBeforeSignal": LOOKBACK_SESSIONS,
        "sourceSha256": SOURCE_SHA256,
        "historyPlanId": history["planId"],
        "originalResponses": responses,
        "sampleCounts": dict(Counter(row["sampleUse"] for row in dates)),
        "dates": dates,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit"))
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = build_manifest(args.artifacts)
        raw = canonical(manifest) + b"\n"
        if args.action == "build":
            with args.output.open("xb") as stream:
                stream.write(raw)
        elif read_bytes(args.output) != raw:
            raise ResearchError("SAMSUNG_DAILY_MANIFEST_CHANGED")
    except ResearchError as error:
        print(error)
        return 2
    except OSError:
        print("SAMSUNG_DAILY_MANIFEST_IO_ERROR")
        return 2
    print(canonical({"manifestSha256": digest(raw), "sampleCounts": manifest["sampleCounts"]}).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
