"""Resumable full-date KRX issue observations; empty responses are not holiday declarations."""
import argparse
from collections import Counter
from contextlib import nullcontext
from datetime import timedelta
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from . import krx_universe
from .dataset import canonical, digest, read_bytes, read_json
from .history import day, job_lock, now
from .krx_baseline_validation import POLICY, reviewed_records
from .krx_request_budget import Budget
from .krx_storage import atomic_json
from .models import ResearchError, StrictModel, utc


class Config(StrictModel):
    schemaVersion: Literal["SAGOPALGO_KRX_UNIVERSE_HISTORY_PLAN_V1"]
    startDate: str
    endDate: str
    sourceKind: Literal["PROVIDER_HISTORICAL", "SYNTHETIC"] = "PROVIDER_HISTORICAL"
    maxRequests: int = Field(default=2400, ge=1, le=8000)
    maxAttemptsPerRequest: int = Field(default=3, ge=1, le=3)

    @model_validator(mode="after")
    def bounds(self):
        first, last = day(self.startDate), day(self.endDate)
        if first < day("2010-01-04") or not 0 <= (last - first).days <= 3653:
            raise ValueError("bounded documented KRX date range required")
        return self


def dates(config):
    value = day(config.startDate)
    while value <= day(config.endDate):
        yield value.isoformat()
        value += timedelta(days=1)


def prepare(output, start, end, max_requests=2400, seed_job=None, source_kind="PROVIDER_HISTORICAL"):
    config = Config.model_validate({"schemaVersion": "SAGOPALGO_KRX_UNIVERSE_HISTORY_PLAN_V1", "startDate": start, "endDate": end,
                                   "maxRequests": max_requests, "sourceKind": source_kind})
    seed, bodies = None, {}
    if seed_job:
        original = krx_universe.audit(seed_job)
        if original["missingMarkets"] or original["sourceKind"] != source_kind or not start <= original["basisDate"] <= end:
            raise ResearchError("KRX_HISTORY_SEED_INVALID")
        _, _, journal, _ = krx_universe.load_job(seed_job)
        seed = {"date": original["basisDate"], "snapshotSha256": digest(canonical(original)), "sources": []}
        for entry in journal["attempts"]:
            bodies[entry["market"]] = read_bytes(seed_job / "raw" / (entry["market"] + ".json"))
            seed["sources"].append({"market": entry["market"], "capturedAt": entry["capturedAt"], "sha256": entry["sha256"]})
    if config.maxRequests < len(list(dates(config))) * 2 - (2 if seed else 0):
        raise ResearchError("KRX_HISTORY_PLAN_BUDGET_TOO_SMALL")
    payload = {"config": config.model_dump(mode="json"), "seed": seed}
    plan = {**payload, "planId": digest(canonical(payload))}
    output.mkdir(parents=True, exist_ok=False)
    (output / "raw").mkdir()
    if seed:
        (output / "seed").mkdir()
        for market, raw in bodies.items():
            (output / "seed" / (market + ".json")).write_bytes(raw)
    atomic_json(output / "plan.json", plan)
    atomic_json(output / "journal.json", {"planId": plan["planId"], "attempts": []})
    return plan


def request_id(plan_id, seq):
    return digest(canonical({"planId": plan_id, "seq": seq}))


def load_job(folder):
    plan = read_json(read_bytes(folder / "plan.json"))
    config = Config.model_validate(plan["config"])
    if set(plan) != {"config", "seed", "planId"} or plan["planId"] != digest(canonical({"config": config.model_dump(mode="json"), "seed": plan["seed"]})):
        raise ResearchError("KRX_HISTORY_PLAN_TAMPERED")
    seed = plan["seed"]
    if seed:
        if (not isinstance(seed, dict) or set(seed) != {"date", "snapshotSha256", "sources"}
                or not config.startDate <= seed["date"] <= config.endDate or len(seed["sources"]) != 2
                or [v["market"] for v in seed["sources"]] != list(krx_universe.ENDPOINTS)):
            raise ResearchError("KRX_HISTORY_SEED_INVALID")
        for entry in seed["sources"]:
            if set(entry) != {"market", "capturedAt", "sha256"}:
                raise ResearchError("KRX_HISTORY_SEED_INVALID")
            utc(entry["capturedAt"])
    journal = read_json(read_bytes(folder / "journal.json"))
    if (not isinstance(journal, dict) or set(journal) != {"planId", "attempts"} or journal["planId"] != plan["planId"]
            or not isinstance(journal["attempts"], list) or len(journal["attempts"]) > config.maxRequests):
        raise ResearchError("KRX_HISTORY_JOURNAL_INVALID")
    latest, counts = {}, Counter()
    for seq, entry in enumerate(journal["attempts"], 1):
        if (not isinstance(entry, dict) or type(entry.get("seq")) is not int or entry["seq"] != seq
                or entry.get("requestId") != request_id(plan["planId"], seq) or entry.get("market") not in krx_universe.ENDPOINTS
                or not isinstance(entry.get("date"), str) or not config.startDate <= entry["date"] <= config.endDate
                or entry.get("state") not in {"RESERVED", "CAPTURED", "FAILED"}):
            raise ResearchError("KRX_HISTORY_JOURNAL_INVALID")
        day(entry["date"])
        utc(entry["startedAt"])
        base = {"seq", "requestId", "market", "date", "state", "startedAt"}
        fields = base | {"sha256", "capturedAt", "rowCount"} if entry["state"] == "CAPTURED" else base
        if entry["state"] == "FAILED":
            fields |= {"diagnostic", "finishedAt"}
            if "sha256" in entry or "capturedAt" in entry:
                fields |= {"sha256", "capturedAt"}
            if utc(entry["finishedAt"]) < utc(entry["startedAt"]):
                raise ResearchError("KRX_HISTORY_JOURNAL_INVALID")
        if set(entry) != fields:
            raise ResearchError("KRX_HISTORY_JOURNAL_INVALID")
        if "capturedAt" in entry and utc(entry["capturedAt"]) < utc(entry["startedAt"]):
            raise ResearchError("KRX_HISTORY_JOURNAL_INVALID")
        if entry["state"] == "CAPTURED" and (type(entry["rowCount"]) is not int or not 0 <= entry["rowCount"] <= 20000):
            raise ResearchError("KRX_HISTORY_JOURNAL_INVALID")
        key = (entry["date"], entry["market"])
        if (seed and entry["date"] == seed["date"]) or (key in latest and latest[key]["state"] == "CAPTURED"):
            raise ResearchError("KRX_HISTORY_DUPLICATE_CAPTURE")
        counts[key] += 1
        if counts[key] > config.maxAttemptsPerRequest:
            raise ResearchError("KRX_HISTORY_ATTEMPT_LIMIT")
        latest[key] = entry
    return plan, config, journal, latest


def envelope(raw):
    if len(raw) > krx_universe.LIMIT:
        raise ResearchError("KRX_RESPONSE_LIMIT")
    value = read_json(raw)
    if (not isinstance(value, dict) or set(value) != {"OutBlock_1"} or not isinstance(value["OutBlock_1"], list)
            or len(value["OutBlock_1"]) > 20000):
        raise ResearchError("KRX_HISTORY_RESPONSE_INVALID")
    return value["OutBlock_1"]


def entry_raw(folder, entry, seed=False):
    path = folder / "seed" / (entry["market"] + ".json") if seed else folder / "raw" / (f"{entry['seq']:06d}.json")
    raw = read_bytes(path)
    if digest(raw) != entry["sha256"]:
        raise ResearchError("KRX_HISTORY_RAW_TAMPERED")
    rows = envelope(raw)
    if not seed and len(rows) != entry["rowCount"]:
        raise ResearchError("KRX_HISTORY_ROW_COUNT_CONFLICT")
    return raw


def verify_captures(folder, plan, journal):
    for entry in journal["attempts"]:
        if entry["state"] == "CAPTURED":
            entry_raw(folder, entry)
        elif "sha256" in entry:
            raw = read_bytes(folder / "raw" / (f"{entry['seq']:06d}.json"))
            if digest(raw) != entry["sha256"]:
                raise ResearchError("KRX_HISTORY_RAW_TAMPERED")
    if plan["seed"]:
        for entry in plan["seed"]["sources"]:
            entry_raw(folder, entry, True)


def observations(folder, plan, latest, stamp):
    if plan["seed"] and plan["seed"]["date"] == stamp:
        return {v["market"]: {**v, "date": stamp, "state": "CAPTURED", "seed": True} for v in plan["seed"]["sources"]}
    return {market: {**latest[(stamp, market)], "seed": False} for market in krx_universe.ENDPOINTS if (stamp, market) in latest}


def summary(folder):
    plan, config, journal, latest = load_job(folder)
    captured, nonempty, empty, inconsistent = [], [], [], []
    rows = 0
    for stamp in dates(config):
        values = observations(folder, plan, latest, stamp)
        if len(values) == 2 and all(v["state"] == "CAPTURED" for v in values.values()):
            counts = [len(envelope(entry_raw(folder, v, True))) if v["seed"] else v["rowCount"] for v in values.values()]
            captured.append(stamp)
            rows += sum(counts)
            (empty if not any(counts) else nonempty if all(counts) else inconsistent).append(stamp)
    return {"planId": plan["planId"], "startDate": config.startDate, "endDate": config.endDate,
            "plannedDates": len(list(dates(config))), "capturedDates": len(captured), "nonemptyPairDates": len(nonempty),
            "emptyPairDates": len(empty), "inconsistentPairDates": inconsistent, "capturedSourceRows": rows,
            "attemptsUsed": len(journal["attempts"]), "maxRequests": config.maxRequests,
            "seedMarketsReused": 2 if plan["seed"] else 0, "lastCompleteDate": captured[-1] if captured else None,
            "unfinishedRequests": sum(v["state"] != "CAPTURED" for v in latest.values()),
            "pendingRequests": len(list(dates(config))) * 2 - (2 if plan["seed"] else 0) - sum(v["state"] == "CAPTURED" for v in latest.values()),
            "sourceKind": config.sourceKind, "marketUniverseComplete": False, "usableForTrading": False}


def collect(folder, transport, budget, max_new_requests, retry_incomplete=False):
    if type(max_new_requests) is not int or not 0 <= max_new_requests <= 8000:
        raise ResearchError("KRX_HISTORY_RUN_BUDGET_INVALID")
    with job_lock(folder):
        plan, config, journal, latest = load_job(folder)
        verify_captures(folder, plan, journal)
        if any(v["state"] != "CAPTURED" for v in latest.values()) and not retry_incomplete:
            raise ResearchError("KRX_HISTORY_EXPLICIT_RECOVERY_REQUIRED")
        if transport.source_kind != config.sourceKind:
            raise ResearchError("KRX_SOURCE_KIND_MISMATCH")
        used = 0
        for stamp in dates(config):
            for market in krx_universe.ENDPOINTS:
                if plan["seed"] and stamp == plan["seed"]["date"]:
                    continue
                key = (stamp, market)
                if key in latest and latest[key]["state"] == "CAPTURED":
                    continue
                if used >= max_new_requests:
                    return summary(folder)
                if len(journal["attempts"]) >= config.maxRequests:
                    raise ResearchError("KRX_HISTORY_PLAN_BUDGET_EXHAUSTED")
                if sum((v["date"], v["market"]) == key for v in journal["attempts"]) >= config.maxAttemptsPerRequest:
                    raise ResearchError("KRX_HISTORY_ATTEMPT_LIMIT")
                transport.ready()
                seq = len(journal["attempts"]) + 1
                entry = {"seq": seq, "requestId": request_id(plan["planId"], seq), "date": stamp, "market": market,
                         "state": "RESERVED", "startedAt": now()}
                journal["attempts"].append(entry)
                atomic_json(folder / "journal.json", journal)
                try:
                    budget.reserve(entry["requestId"])
                    raw = transport.fetch(market, stamp)
                    (folder / "raw" / (f"{seq:06d}.json")).write_bytes(raw)
                    entry.update(sha256=digest(raw), capturedAt=now())
                    values = envelope(raw)
                    if values:
                        krx_universe.parse_snapshot(raw, market, stamp, entry["capturedAt"], config.sourceKind)
                    entry.update(state="CAPTURED", rowCount=len(values))
                    atomic_json(folder / "journal.json", journal)
                except Exception as exc:
                    code = str(exc) if isinstance(exc, ResearchError) else "KRX_HISTORY_CAPTURE_FAILED"
                    entry.pop("rowCount", None)
                    entry.update(state="FAILED", diagnostic=code, finishedAt=now())
                    atomic_json(folder / "journal.json", journal)
                    raise ResearchError(code) from None
                latest[key] = entry
                used += 1
                if used % 20 == 0:
                    print(json.dumps({"progress": True, "date": stamp, "market": market, "newRequests": used,
                                      "attemptsUsed": len(journal["attempts"])}), flush=True)
        return summary(folder)


def day_snapshot(folder, plan, latest, stamp):
    values = observations(folder, plan, latest, stamp)
    sources, records = [], []
    for market in krx_universe.ENDPOINTS:
        entry = values.get(market)
        if not entry or entry["state"] != "CAPTURED":
            sources.append({"market": market, "status": "UNAVAILABLE"})
            continue
        raw = entry_raw(folder, entry, entry["seed"])
        parsed = reviewed_records(krx_universe.parse_snapshot(raw, market, stamp, entry["capturedAt"], plan["config"]["sourceKind"])) if envelope(raw) else []
        sources.append({"market": market, "status": "OBSERVED" if parsed else "EMPTY_RESPONSE", "sha256": entry["sha256"],
                        "knownAt": entry["capturedAt"], "rows": len(parsed)})
        records.extend({key: value[key] for key in ["symbol", "isin", "name", "market", "classification", "sourceRowSha256"]} for value in parsed)
    if any(len({v[key] for v in records}) != len(records) for key in ["symbol", "isin"]):
        raise ResearchError("KRX_HISTORY_CROSS_MARKET_DUPLICATE")
    missing = any(v["status"] == "UNAVAILABLE" for v in sources)
    nonempty = all(v["status"] == "OBSERVED" for v in sources)
    empty = all(v["status"] == "EMPTY_RESPONSE" for v in sources)
    return {"schemaVersion": "SAGOPALGO_KRX_HISTORY_DAY_V1", "date": stamp, "classificationPolicy": POLICY,
            "status": "UNAVAILABLE" if missing else "OBSERVED" if nonempty else "EMPTY_RESPONSE" if empty else "INCONSISTENT_RESPONSE",
            "sources": sources, "issues": records, "unreviewedRecords": sum(v["classification"] == "UNREVIEWED_CLASSIFICATION" for v in records)}


def changes(previous, current, empty_dates):
    before = {v["isin"]: v for v in previous["issues"]}
    after = {v["isin"]: v for v in current["issues"]}
    known = max([v["knownAt"] for snapshot in [previous, current] for v in snapshot["sources"]], key=utc)
    for isin in sorted(set(before) | set(after)):
        old, new = before.get(isin), after.get(isin)
        old_common = old is not None and old["classification"] == "COMMON_SHARE"
        new_common = new is not None and new["classification"] == "COMMON_SHARE"
        kinds = []
        if old_common and new_common:
            kinds = [kind for field, kind in [("market", "MARKET_TRANSFER_OBSERVED"), ("symbol", "SYMBOL_CHANGE_OBSERVED"),
                                              ("name", "NAME_CHANGE_OBSERVED")] if old[field] != new[field]]
        elif old_common != new_common:
            kinds = ["CLASSIFICATION_CHANGE_OBSERVED" if old is not None and new is not None else "ADDED_OBSERVED" if new_common else "REMOVED_OBSERVED"]
        for kind in kinds:
            yield {"kind": kind, "isin": isin, "observedFrom": previous["date"], "observedTo": current["date"],
                   "before": old, "after": new, "knownAt": known, "emptyResponseDatesBetween": empty_dates,
                   "legalEventConfirmed": False, "effectiveDate": None}


def build(folder, output, verify=False):
    with job_lock(folder):
        plan, config, journal, latest = load_job(folder)
        verify_captures(folder, plan, journal)
        if not verify:
            output.mkdir(parents=True, exist_ok=False)
            (output / "days").mkdir()
        report = {"schemaVersion": "SAGOPALGO_KRX_HISTORY_REPORT_V1", **summary(folder), "classificationPolicy": POLICY,
                  "dayFiles": [], "changeCounts": {}, "unreviewedRecords": 0, "usableForTraining": False,
                  "calendarCompletenessConfirmed": False, "allLegalEventsConfirmed": False}
        previous, empties, counts = None, [], Counter()
        changes_hash = hashlib.sha256()
        with (nullcontext(None) if verify else (output / "changes.jsonl").open("wb")) as stream:
            for stamp in dates(config):
                snapshot = day_snapshot(folder, plan, latest, stamp)
                raw = canonical(snapshot)
                day_path = output / "days" / (stamp + ".json")
                if verify:
                    if read_bytes(day_path) != raw:
                        raise ResearchError("KRX_HISTORY_DERIVED_TAMPERED")
                else:
                    day_path.write_bytes(raw)
                common = sum(v["classification"] == "COMMON_SHARE" for v in snapshot["issues"])
                report["dayFiles"].append({"date": stamp, "status": snapshot["status"], "sha256": digest(raw), "commonShares": common})
                report["unreviewedRecords"] += snapshot["unreviewedRecords"]
                if snapshot["status"] == "OBSERVED" and not snapshot["unreviewedRecords"]:
                    if previous:
                        for change in changes(previous, snapshot, empties):
                            encoded = canonical(change) + b"\n"
                            changes_hash.update(encoded)
                            if stream:
                                stream.write(encoded)
                            counts[change["kind"]] += 1
                    previous, empties = snapshot, []
                elif snapshot["status"] == "EMPTY_RESPONSE":
                    empties = [*empties, stamp]
                else:
                    previous, empties = None, []
        report["changeCounts"] = dict(counts)
        report["changesSha256"] = changes_hash.hexdigest()
        if verify:
            if (digest(read_bytes(output / "changes.jsonl")) != report["changesSha256"]
                    or read_bytes(output / "report.json") != canonical(report)):
                raise ResearchError("KRX_HISTORY_DERIVED_TAMPERED")
        else:
            atomic_json(output / "report.json", report)
        return {key: value for key, value in report.items() if key != "dayFiles"}


def as_of(folder, stamp, at):
    plan, config, _, latest = load_job(folder)
    day(stamp)
    utc(at)
    if not config.startDate <= stamp <= config.endDate:
        raise ResearchError("KRX_HISTORY_QUERY_OUTSIDE_SCOPE")
    snapshot = day_snapshot(folder, plan, latest, stamp)
    visible = {v["market"] for v in snapshot["sources"] if "knownAt" in v and utc(v["knownAt"]) <= utc(at)}
    return {"date": stamp, "asOf": at, "observedStatus": snapshot["status"], "visibleMarkets": sorted(visible),
            "members": [v for v in snapshot["issues"] if v["market"] in visible and v["classification"] == "COMMON_SHARE"],
            "completeAtCutoff": len(visible) == 2 and snapshot["status"] == "OBSERVED" and not snapshot["unreviewedRecords"],
            "usableForTraining": False, "usableForTrading": False}


def check_events(folder, cases, events, cache):
    """Compare the day before and event day, without upgrading observations to legal facts."""
    with job_lock(folder):
        plan, config, _, latest = load_job(folder)
        targets = [v for v in cases["facts"] if v["kind"] in {"IPO", "DELISTING"}] + events["facts"]
        checks = []
        for fact in targets:
            for offset in [-1, 0]:
                stamp = (day(fact["date"]) + timedelta(days=offset)).isoformat()
                if not config.startDate <= stamp <= config.endDate:
                    raise ResearchError("KRX_HISTORY_EVENT_BOUNDARY_OUTSIDE_SCOPE")
                snapshot = day_snapshot(folder, plan, latest, stamp)
                compared = krx_universe.compare_evidence({"basisDate": stamp, "records": snapshot["issues"],
                    "missingMarkets": [v["market"] for v in snapshot["sources"] if v["status"] != "OBSERVED"],
                    "unreviewedRecords": snapshot["unreviewedRecords"], "sourceKind": config.sourceKind,
                    "planId": plan["planId"]}, cases, events, cache)
                for check in compared["checks"]:
                    if check["caseId"] == fact["caseId"]:
                        checks.append({**check, "date": stamp, "historySnapshotSha256": digest(canonical(snapshot))})
        mismatches = sum(v["status"] == "MISMATCH" for v in checks)
        pending = sum(v["status"] == "PENDING_SOURCE" for v in checks)
        return {"schemaVersion": "SAGOPALGO_KRX_HISTORY_EVENT_CHECK_V1", "planId": plan["planId"],
                "caseReportSha256": digest(canonical(cases)), "eventReportSha256": digest(canonical(events)),
                "sourceKind": config.sourceKind, "checks": checks, "mismatches": mismatches, "pendingChecks": pending,
                "status": "TEST_ONLY" if config.sourceKind != "PROVIDER_HISTORICAL" else "NO_ANCHORS" if not checks
                    else "BOUNDARY_MISMATCHES" if mismatches else "PENDING_SOURCES" if pending else "SELECTED_BOUNDARIES_MATCH",
                "allLegalEventsConfirmed": False, "marketUniverseComplete": False, "usableForTraining": False, "usableForTrading": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ["plan", "status", "collect", "build", "audit", "as-of", "check-events"]:
        p = sub.add_parser(command)
        if command == "plan":
            p.add_argument("--output", type=Path, required=True)
            p.add_argument("--start", default="2023-11-01")
            p.add_argument("--end", default="2026-11-02")
            p.add_argument("--max-requests", type=int, default=2400)
            p.add_argument("--seed-job", type=Path)
        else:
            p.add_argument("--job", type=Path, required=True)
        if command == "collect":
            p.add_argument("--env-file", type=Path)
            p.add_argument("--budget-cache", type=Path, required=True)
            p.add_argument("--max-new-requests", type=int, required=True)
            p.add_argument("--prior-requests", type=int, default=4)
            p.add_argument("--retry-incomplete", action="store_true")
        if command in {"build", "audit"}:
            p.add_argument("--output", type=Path, required=True)
        if command == "as-of":
            p.add_argument("--date", required=True)
            p.add_argument("--at", required=True)
        if command == "check-events":
            for flag in ["cases", "case-report", "events", "event-report", "cache", "output"]:
                p.add_argument("--" + flag, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            result = prepare(args.output, args.start, args.end, args.max_requests, args.seed_job)
        elif args.command == "status":
            result = summary(args.job)
        elif args.command == "collect":
            key, enabled = krx_universe.load_environment(args.env_file)
            result = collect(args.job, krx_universe.Transport(key, enabled), Budget(args.budget_cache, key, prior_requests=args.prior_requests),
                             args.max_new_requests, args.retry_incomplete)
        elif args.command in {"build", "audit"}:
            result = build(args.job, args.output, verify=args.command == "audit")
        elif args.command == "check-events":
            from . import kind_cases, universe_events
            from .krx_baseline_validation import immutable_json
            cases = kind_cases.audit_report(kind_cases.load_scope(args.cases), args.cache, args.case_report)
            events = universe_events.audit_report(universe_events.load_scope(args.events), args.cache, args.event_report)
            result = check_events(args.job, cases, events, args.cache)
            immutable_json(args.output, result)
        else:
            result = as_of(args.job, args.date, args.at)
        print(json.dumps(result, ensure_ascii=True, sort_keys=True), flush=True)
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"diagnostic": str(exc) if isinstance(exc, ResearchError) else "KRX_HISTORY_INPUT_INVALID"}), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
