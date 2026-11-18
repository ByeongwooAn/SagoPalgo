"""Train and independently evaluate the two-stock personal-local daily prototype."""

import argparse
import platform
from dataclasses import asdict, dataclass
from importlib.metadata import version
from math import log, log1p
from pathlib import Path
from statistics import mean
from tempfile import TemporaryDirectory
from time import perf_counter
from warnings import catch_warnings, simplefilter

from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from ..daily_features import FEATURE_NAMES, LOOKBACK_SESSIONS, daily_features
from .dataset import canonical, digest, read_bytes, read_json
from .file_publish import publish_directory
from .hynix_daily_training import CAPTURE as HYNIX_CAPTURE
from .models import ResearchError
from .samsung_daily_training import HISTORY_CAPTURE, SOURCE_SHA256

VERSION = "daily-l2-logistic-v1"
TRAIN, VALIDATION, FINAL = "TRAIN", "VALIDATION", "FINAL_EVALUATION"
COUNTS = {TRAIN: 424, VALIDATION: 141, FINAL: 142}
INPUTS = {
    "005930": (
        (f"{HISTORY_CAPTURE}/job/daily.jsonl", SOURCE_SHA256["daily"]),
        ("samsung-daily-training-20261118/dates.json",
         "e6fb972eff83efe7e1fa099754a51802f7545969a9831985d8a9ba627e75e88b"),
    ),
    "000660": (
        (f"{HYNIX_CAPTURE}/training-input/daily.jsonl",
         "a36bcf89357a31eb81c700ce32a3a9ccb3749ba6d258c33e9492ec3ced3c4ed9"),
        (f"{HYNIX_CAPTURE}/training-input/dates.json",
         "fc05b64753127094375c5db73d11dcb852de0a3cce816d8f59af98a3d71d77d4"),
    ),
}
THRESHOLDS = tuple(bps / 10_000 for bps in range(5000, 7501, 250)) + (None,)
VALIDATION_BLOCK_SIZE = 47
MODEL_SETTINGS = {"C": 1.0, "penalty": "l2", "solver": "lbfgs", "max_iter": 1000, "tol": 1e-9}


@dataclass(frozen=True)
class Bar:
    date: str
    opened: int
    high: int
    low: int
    closed: int
    volume: int


@dataclass(frozen=True)
class Sample:
    signal_date: str
    target_date: str
    features: tuple[float, ...]
    forward_return: float

    @property
    def label(self):
        return int(self.forward_return > 0)


@dataclass(frozen=True)
class Costs:
    feeBpsPerSide: int
    slippageBpsPerSide: int
    sellTaxBps: int

    def net_return(self, gross_return):
        fee = self.feeBpsPerSide / 10_000
        slip = self.slippageBpsPerSide / 10_000
        sell_tax = self.sellTaxBps / 10_000
        return (1 + gross_return) * (1 - slip) * (1 - fee - sell_tax) / (
            (1 + slip) * (1 + fee)
        ) - 1


COSTS = {"base": Costs(5, 5, 20), "stress": Costs(10, 15, 20)}


def pinned_input(root, spec):
    relative_path, expected_hash = spec
    raw = read_bytes(root / relative_path)
    if digest(raw) != expected_hash:
        raise ResearchError("DAILY_LEARNING_PINNED_INPUT_CHANGED")
    return raw


def load_snapshot(root, code):
    daily_spec, dates_spec = INPUTS[code]
    rows = [read_json(line) for line in pinned_input(root, daily_spec).splitlines()]
    manifest = read_json(pinned_input(root, dates_spec))
    days = [day for day in manifest["dates"] if "oldestFeatureDate" in day]
    if (manifest["stockCode"] != code or manifest["priceBasis"] != "RAW"
            or len(rows) != 730
            or [row["businessDate"] for row in rows] != [day["businessDate"] for day in days]
            or any(a["businessDate"] >= b["businessDate"] for a, b in zip(days, days[1:]))):
        raise ResearchError("DAILY_LEARNING_SNAPSHOT_MISMATCH")
    bars = []
    for row in rows:
        if (row["stockCode"], row["priceBasis"], row["status"]) != (code, "RAW", "OBSERVED_PRICE"):
            raise ResearchError("DAILY_LEARNING_INVALID_BAR_SCOPE")
        bar = Bar(row["businessDate"], *(int(row[key]) for key in ("open", "high", "low", "close", "volume")))
        if (not 0 < bar.low <= min(bar.opened, bar.closed)
                or max(bar.opened, bar.closed) > bar.high or bar.volume <= 0):
            raise ResearchError("DAILY_LEARNING_INVALID_BAR")
        bars.append(bar)
    return bars, days


def samples_for(snapshot, use):
    bars, days = snapshot
    samples = []
    for index, day in enumerate(days):
        if day["sampleUse"] != use:
            continue
        oldest_index = index - LOOKBACK_SESSIONS
        if oldest_index < 0 or index + 1 >= len(bars):
            raise ResearchError("DAILY_LEARNING_INVALID_SAMPLE_WINDOW")
        target = bars[index + 1]
        if day["oldestFeatureDate"] != bars[oldest_index].date or day["targetDate"] != target.date:
            raise ResearchError("DAILY_LEARNING_FROZEN_DATE_MISMATCH")
        samples.append(Sample(bars[index].date, target.date,
                              daily_features(bars[oldest_index:index + 1]),
                              target.closed / target.opened - 1))
    if len(samples) != COUNTS[use]:
        raise ResearchError("DAILY_LEARNING_SAMPLE_COUNT_MISMATCH")
    return samples


def fit(samples):
    scaler = StandardScaler()
    x = scaler.fit_transform([row.features for row in samples])
    classifier = LogisticRegression(**MODEL_SETTINGS)
    with catch_warnings():
        simplefilter("error", ConvergenceWarning)
        classifier.fit(x, [row.label for row in samples])
    return scaler, classifier


def probabilities(model, samples):
    scaler, classifier = model
    x = scaler.transform([row.features for row in samples])
    return classifier.predict_proba(x)[:, 1].tolist()


def performance(samples, entries, costs):
    equity = peak = 1.0
    drawdown, trades = 0.0, 0
    for row, enter in zip(samples, entries, strict=True):
        if enter:
            trades += 1
            equity *= 1 + costs.net_return(row.forward_return)
        peak = max(peak, equity)
        drawdown = max(drawdown, 1 - equity / peak)
    return {"netReturn": equity - 1, "maxDrawdown": drawdown, "trades": trades}


def entries_for(probabilities_, threshold):
    return [threshold is not None and p >= threshold for p in probabilities_]


def select_threshold(validation, predictions):
    candidates = [
        {"threshold": threshold, **performance(validation, entries_for(predictions, threshold), COSTS["base"])}
        for threshold in THRESHOLDS
    ]
    selected = max(candidates, key=lambda result: (
        result["netReturn"], -result["trades"],
        1 if result["threshold"] is None else result["threshold"],
    ))
    return selected["threshold"], candidates


def freeze_model(code, train, validation, input_hashes, runtime):
    previous = train
    predictions, folds = [], []
    for start in range(0, len(validation), VALIDATION_BLOCK_SIZE):
        block = validation[start:start + VALIDATION_BLOCK_SIZE]
        cutoff = block[0].signal_date
        eligible = [row for row in previous if row.target_date < cutoff]
        predictions.extend(probabilities(fit(eligible), block))
        folds.append({
            "trainingCount": len(eligible), "lastTrainingTargetDate": eligible[-1].target_date,
            "firstSignalDate": cutoff, "lastSignalDate": block[-1].signal_date,
            "validationCount": len(block),
        })
        previous = previous + block

    threshold, candidates = select_threshold(validation, predictions)
    model = fit(train)
    scaler, classifier = model
    manifest = {
        "version": VERSION, "stockCode": code, "priceBasis": "RAW",
        "features": FEATURE_NAMES, "runtime": runtime, "inputSha256": input_hashes,
        "settings": MODEL_SETTINGS, "trainedOn": period(train),
        "means": scaler.mean_.tolist(), "scales": scaler.scale_.tolist(),
        "coefficients": classifier.coef_[0].tolist(), "intercept": float(classifier.intercept_[0]),
        "threshold": threshold, "trainingUpFrequency": mean(row.label for row in train),
    }
    details = {"period": period(validation), "folds": folds, "thresholdCandidates": candidates,
               "rows": prediction_rows(validation, predictions)}
    return model, manifest, details


def period(samples):
    return {"samples": len(samples), "firstSignalDate": samples[0].signal_date,
            "lastSignalDate": samples[-1].signal_date, "firstTargetDate": samples[0].target_date,
            "lastTargetDate": samples[-1].target_date}


def prediction_rows(samples, predictions):
    return [
        {"signalDate": row.signal_date, "targetDate": row.target_date, "up": row.label,
         "upProbability": p, "grossReturn": row.forward_return, "closeReturn5": row.features[2]}
        for row, p in zip(samples, predictions, strict=True)
    ]


def prediction_metrics(samples, predictions):
    labels = [row.label for row in samples]
    bounded = [min(max(p, 1e-15), 1 - 1e-15) for p in predictions]
    return {
        "accuracy": mean((p >= 0.5) == label for p, label in zip(predictions, labels, strict=True)),
        "logLoss": -mean(log(p) if label else log1p(-p) for p, label in zip(bounded, labels, strict=True)),
    }


def evaluate(samples, model, manifest):
    if samples[0].signal_date <= manifest["trainedOn"]["lastTargetDate"]:
        raise ResearchError("DAILY_LEARNING_FINAL_OVERLAPS_TRAINING")
    predictions = probabilities(model, samples)
    entries = {
        "model": entries_for(predictions, manifest["threshold"]),
        "daily": [True] * len(samples),
        "trend5": [row.features[2] > 0 for row in samples],
        "cash": [False] * len(samples),
    }
    return {
        "period": period(samples),
        "upDays": sum(row.label for row in samples),
        "prediction": {
            "model": prediction_metrics(samples, predictions),
            "trainingFrequency": prediction_metrics(samples, [manifest["trainingUpFrequency"]] * len(samples)),
        },
        "strategies": {
            scenario: {name: performance(samples, signals, costs) for name, signals in entries.items()}
            for scenario, costs in COSTS.items()
        },
    }, prediction_rows(samples, predictions)


def run(root):
    started = perf_counter()
    snapshots = {code: load_snapshot(root, code) for code in INPUTS}
    audited = perf_counter()
    common = None
    for _, days in snapshots.values():
        pairs = [(day["businessDate"], day["targetDate"], day["sampleUse"])
                 for day in days if day["sampleUse"] in COUNTS]
        if common is not None and (
            common != pairs or any(not day["commonSample"] for day in days if day["sampleUse"] in COUNTS)
        ):
            raise ResearchError("DAILY_LEARNING_COMMON_DATES_MISMATCH")
        common = pairs
    runtime = {name: version(name) for name in ("numpy", "scipy", "scikit-learn", "threadpoolctl", "joblib")}
    runtime.update(python=platform.python_version(), platform=platform.system())
    frozen, files, details, stocks = {}, {}, {}, {}
    with threadpool_limits(limits=1):
        for code, snapshot in snapshots.items():
            train, validation = (samples_for(snapshot, use) for use in (TRAIN, VALIDATION))
            if train[-1].target_date >= validation[0].signal_date:
                raise ResearchError("DAILY_LEARNING_VALIDATION_OVERLAPS_TRAINING")
            input_hashes = dict(zip(("daily", "dates"), (spec[1] for spec in INPUTS[code]), strict=True))
            model, manifest, details[code] = freeze_model(code, train, validation, input_hashes, runtime)
            files[f"{code}-model.json"] = canonical(manifest) + b"\n"
            frozen[code] = model, manifest
        trained = perf_counter()

        # Materialize final features and outcomes only after both models and thresholds are frozen.
        for code, (model, manifest) in frozen.items():
            final = samples_for(snapshots[code], FINAL)
            if details[code]["period"]["lastTargetDate"] >= final[0].signal_date:
                raise ResearchError("DAILY_LEARNING_FINAL_OVERLAPS_VALIDATION")
            evaluation, details[code]["finalRows"] = evaluate(final, model, manifest)
            stocks[code] = {"threshold": manifest["threshold"], "version": VERSION,
                            "modelSha256": digest(files[f"{code}-model.json"]), **evaluation}

    summary = {
        "schemaVersion": "SAGOPALGO_DAILY_LEARNING_SUMMARY_V1",
        "purpose": "PERSONAL_LOCAL_RESEARCH",
        "commonFinalPeriod": next(iter(stocks.values()))["period"],
        "costs": {name: asdict(costs) for name, costs in COSTS.items()},
        "stocks": stocks,
    }
    files["app-summary.json"] = canonical(summary) + b"\n"
    files["evaluation.json"] = canonical({
        **summary, "details": details, "sampleCounts": COUNTS, "runtime": runtime,
        "commonFinalPairs": [[signal, target] for signal, target, use in common if use == FINAL],
    }) + b"\n"
    return files, {
        "snapshotCheckMs": round((audited - started) * 1000, 2),
        "featuresAndFitMs": round((trained - audited) * 1000, 2),
        "evaluationAndSerializationMs": round((perf_counter() - trained) * 1000, 2),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ResearchError("DAILY_LEARNING_OUTPUT_EXISTS")
        files, timing = run(args.artifacts)
        with TemporaryDirectory(dir=args.output.parent) as stage:
            prepared = Path(stage) / "bundle"
            prepared.mkdir()
            for name, raw in files.items():
                (prepared / name).write_bytes(raw)
            publish_directory(prepared, args.output)
    except ResearchError as error:
        print(error)
        return 2
    except (ValueError, ConvergenceWarning):
        print("DAILY_LEARNING_FIT_OR_INPUT_ERROR")
        return 2
    except OSError:
        print("DAILY_LEARNING_IO_ERROR")
        return 2
    print(canonical({"sha256": {name: digest(raw) for name, raw in files.items()}, "timing": timing}).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
