"""Audit the two NASDAQ histories and train the personal-local daily models."""

import argparse
from dataclasses import asdict
from datetime import date, timedelta
from decimal import Decimal, DecimalException
from importlib.metadata import version
from pathlib import Path
import platform
from tempfile import TemporaryDirectory

from threadpoolctl import threadpool_limits

from ..daily_features import LOOKBACK_SESSIONS, daily_features
from .daily_learning import Bar, Costs, Sample, evaluate, freeze_model
from .dataset import canonical, digest, read_bytes, read_json
from .file_publish import publish_directory
from .models import ResearchError
from .us_daily_capture import END, START, SYMBOLS, rows_from_page

VERSION = "us-daily-l2-logistic-v1"
CALENDAR = (Path(__file__).resolve().parents[4]
            / "Back/spring-server/src/main/resources/nasdaq-daily-prototype.properties")
# Research assumptions, in basis points. No currency conversion or overnight holdings.
COSTS = {"base": Costs(10, 5, 0), "stress": Costs(25, 15, 1)}


def session_dates(calendar_raw):
    properties = dict(line.split("=", 1) for line in calendar_raw.decode().splitlines()
                      if line and not line.startswith("#"))
    closed = {date.fromisoformat(value) for value in properties["closed"].split(",")}
    if not date.fromisoformat(properties["start"]) <= START <= END <= date.fromisoformat(properties["end"]):
        raise ResearchError("US_DAILY_CALENDAR_UNAVAILABLE")
    break_date = date.fromisoformat(properties["NVDA.split"])
    sessions = [day for offset in range((END - START).days + 1)
                if (day := START + timedelta(days=offset)).weekday() < 5 and day not in closed]
    return sessions, {"NVDA": break_date}


def read_bar(row):
    day = date.fromisoformat(row["xymd"])
    # A cent fraction is preserved in both training and the HTTP inference request.
    opened, high, low, closed, volume = (Decimal(row[key]) for key in ("open", "high", "low", "clos", "tvol"))
    if not (0 < low <= min(opened, closed) <= max(opened, closed) <= high
            and volume > 0 and volume == volume.to_integral_value()
            and all(value.is_finite() for value in (opened, high, low, closed, volume))):
        raise ResearchError("US_DAILY_INVALID_BAR")
    return day, Bar(day.isoformat(), float(opened), float(high), float(low), float(closed), int(volume))


def audit_capture(capture):
    raw_manifest = read_bytes(capture / "capture.json")
    manifest = read_json(raw_manifest)
    calendar = read_bytes(CALENDAR).replace(b"\r\n", b"\n")
    sessions, splits = session_dates(calendar)
    expected_dates = set(sessions)
    if (manifest["provider"], manifest["market"], manifest["currency"], manifest["priceBasis"],
        manifest["start"], manifest["end"]) != ("KIS", "NASDAQ", "USD", "RAW", str(START), str(END)):
        raise ResearchError("US_DAILY_CAPTURE_SCOPE")
    records = {symbol: {} for symbol in SYMBOLS}
    seen = set()
    for page in manifest["pages"]:
        symbol = page["ticker"]
        filename = page["file"]
        if symbol not in records or filename in seen or filename != Path(filename).name or not filename.startswith(symbol + "-"):
            raise ResearchError("US_DAILY_RECEIPT_INVALID")
        seen.add(filename)
        raw = read_bytes(capture / filename)
        if digest(raw) != page["sha256"]:
            raise ResearchError("US_DAILY_CAPTURE_CHANGED")
        rows = rows_from_page(raw)
        identity = read_json(raw)["output1"]["rsym"]
        if identity not in (f"NAS{symbol}", f"DNAS{symbol}", f"RNAS{symbol}") or len(rows) != page["rows"]:
            raise ResearchError("US_DAILY_PAGE_IDENTITY_OR_SIZE")
        by_date = date.fromisoformat(page["byDate"])
        for row in rows:
            day, bar = read_bar(row)
            if day > by_date:
                raise ResearchError("US_DAILY_PAGE_AFTER_CURSOR")
            if START <= day <= END:
                existing = records[symbol].setdefault(day, bar)
                if existing != bar:
                    raise ResearchError(f"{symbol} {day}: US_DAILY_CONFLICTING_BAR")
    for symbol, bars in records.items():
        missing = sorted(expected_dates - bars.keys())
        extra = sorted(bars.keys() - expected_dates)
        if missing or extra:
            raise ResearchError(f"{symbol} US_DAILY_CALENDAR_MISMATCH: missing={missing}, extra={extra}")
        for left_day, right_day in zip(sessions, sessions[1:]):
            ratio = bars[right_day].opened / bars[left_day].closed
            if right_day == splits.get(symbol):
                if not 0.08 < ratio < 0.12:
                    raise ResearchError("US_DAILY_SPLIT_RAW_PRICE_NOT_CONFIRMED")
            elif not 0.65 < ratio < 1.35:
                raise ResearchError(f"{symbol} {right_day}: US_DAILY_UNREVIEWED_PRICE_BREAK")
    return sessions, records, splits, {"capture": digest(raw_manifest), "calendar": digest(calendar)}


def sample_dates(sessions, splits):
    # Use the same eligible signal/target pair in both evaluations. Index in the full calendar.
    eligible, excluded = [], []
    for index in range(LOOKBACK_SESSIONS, len(sessions) - 1):
        oldest, signal, target = sessions[index - LOOKBACK_SESSIONS], sessions[index], sessions[index + 1]
        pair = {"oldestFeatureDate": str(oldest), "signalDate": str(signal), "targetDate": str(target)}
        if any(oldest < split <= signal for split in splits.values()):
            excluded.append({**pair, "reason": "NVDA_SPLIT_IN_FEATURE_WINDOW"})
        else:
            eligible.append(pair)
    train_end, validation_end = len(eligible) * 3 // 5, len(eligible) * 4 // 5
    train, validation, final = eligible[:train_end], eligible[train_end:validation_end], eligible[validation_end:]
    for earlier, later in ((train, validation), (validation, final)):
        if earlier[-1]["targetDate"] >= later[0]["signalDate"]:
            excluded.append({**earlier.pop(), "reason": "LABEL_OVERLAPS_NEXT_PERIOD"})
    return {"train": train, "validation": validation, "final": final, "excluded": excluded}


def samples(pairs, sessions, bars):
    indices = {str(day): index for index, day in enumerate(sessions)}
    result = []
    for pair in pairs:
        index = indices[pair["signalDate"]]
        window = [bars[day] for day in sessions[index - LOOKBACK_SESSIONS:index + 1]]
        target = bars[sessions[index + 1]]
        result.append(Sample(pair["signalDate"], target.date, daily_features(window), target.closed / target.opened - 1))
    return result


def run(capture):
    sessions, records, splits, input_hashes = audit_capture(capture)
    dates = sample_dates(sessions, splits)
    input_hashes["dates"] = digest(canonical(dates))
    runtime = {name: version(name) for name in ("numpy", "scipy", "scikit-learn", "threadpoolctl", "joblib")}
    runtime.update(python=platform.python_version(), platform=platform.system())
    files, frozen, stocks = {"dates.json": canonical(dates) + b"\n"}, {}, {}
    with threadpool_limits(limits=1):
        for symbol, bars in records.items():
            train, validation = [samples(dates[period], sessions, bars) for period in ("train", "validation")]
            model, manifest, details = freeze_model(symbol, train, validation, input_hashes, runtime, COSTS["base"])
            manifest.update(version=VERSION, market="NASDAQ", currency="USD")
            raw = canonical(manifest) + b"\n"
            files[f"{symbol}-model.json"] = raw
            frozen[symbol] = (model, manifest, details, digest(raw))

        for symbol, (model, manifest, details, sha256) in frozen.items():
            final = samples(dates["final"], sessions, records[symbol])
            evaluation, details["finalRows"] = evaluate(final, model, manifest, COSTS)
            stocks[symbol] = {"modelSha256": sha256, "version": VERSION, "threshold": manifest["threshold"],
                              **evaluation, "details": details}
    costs = {name: asdict(cost) for name, cost in COSTS.items()}
    files["app-summary.json"] = canonical({
        "schemaVersion": "SAGOPALGO_DAILY_LEARNING_SUMMARY_V1",
        "purpose": "PERSONAL_LOCAL_RESEARCH", "market": "NASDAQ", "currency": "USD",
        "commonFinalPeriod": stocks["AAPL"]["period"], "costs": costs,
        "stocks": {symbol: {key: value for key, value in stock.items() if key != "details"}
                   for symbol, stock in stocks.items()},
    }) + b"\n"
    files["evaluation.json"] = canonical({
        "version": VERSION, "market": "NASDAQ", "currency": "USD", "provider": "KIS",
        "inputSha256": input_hashes, "sessions": len(sessions), "runtime": runtime,
        "sampleCounts": {name: len(pairs) for name, pairs in dates.items()},
        "costs": costs, "stocks": stocks,
    }) + b"\n"
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ResearchError("US_DAILY_OUTPUT_EXISTS")
        files = run(args.capture)
        with TemporaryDirectory(dir=args.output.parent) as directory:
            stage = Path(directory) / "bundle"
            stage.mkdir()
            for name, raw in files.items():
                (stage / name).write_bytes(raw)
            publish_directory(stage, args.output)
        print(canonical({name: digest(raw) for name, raw in files.items()}).decode())
        return 0
    except ResearchError as exc:
        print(exc)
    except (OSError, ValueError, TypeError, KeyError, DecimalException):
        print("US_DAILY_LEARNING_INPUT_OR_IO_ERROR")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
