"""Offline, as-of audit of market-specific calendar evidence and separate KIS observations."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from . import calendar_fetch, market_calendar_evidence
from .dataset import canonical, digest, read_bytes
from .history import day
from .models import ResearchError, utc


MARKETS = ("KOSPI", "KOSDAQ")
FLAGS = ("businessDay", "tradingDay", "openDay", "settlementDay")
STATUSES = ("EXPLICIT_SCHEDULE", "RECONSTRUCTED", "CONFLICT", "UNKNOWN")
SCHEMA = "SAGOPALGO_CALENDAR_FLAG_AUDIT_V1"


def resolve(claims, evidence, cutoff=None):
    visible = [claim for claim in claims if cutoff is None or utc(evidence[claim["sourceId"]]["knownAt"]) <= cutoff]
    values = {claim["value"] for claim in visible}
    if len(values) > 1:
        status = "CONFLICT"
    elif not values:
        status = "UNKNOWN"
    elif any(evidence[claim["sourceId"]]["kind"] == "DATED_MARKET_NOTICE" for claim in visible):
        status = "EXPLICIT_SCHEDULE"
    else:
        status = "RECONSTRUCTED"
    return {"status": status, "value": next(iter(values)) if len(values) == 1 else None, "claims": visible}


def build(scope_path, cache, year_job, baseline_path, kis_folder=None):
    baseline, notice_rows, scope = market_calendar_evidence.rebuild_with_notice_rows(scope_path, cache, year_job)
    baseline_bytes = read_bytes(baseline_path)
    if baseline_bytes != canonical(baseline):
        raise ResearchError("CALENDAR_FLAG_BASELINE_MISMATCH")
    verified_sources = {source["sourceId"]: source for source in baseline["sources"]}
    yearly_sources = {source["year"]: source for source in baseline["yearSources"]}
    dates = {row["businessDate"]: row for row in baseline["days"]}
    evidence = {}
    explicit = defaultdict(list)
    for source in scope.sources:
        if source.expectedDate is None:
            continue
        source_id = "notice:" + source.sourceId
        verified = verified_sources[source.sourceId]
        evidence[source_id] = {
            "kind": "DATED_MARKET_NOTICE", "markets": source.markets, "knownAt": verified["knownAt"],
            "sourceUrl": verified["url"], "rawSha256": verified["sha256"], "role": source.role,
        }
        for market in source.markets:
            explicit[market, source.expectedDate, "openDay"].append({"sourceId": source_id, "value": True})
    for market, source_id, row in notice_rows:
        if row["businessDate"] not in dates:
            continue
        for flag in FLAGS:
            if row[flag] is None:
                continue
            claim = {"sourceId": "notice:" + source_id, "value": row[flag]}
            bucket = explicit[market, row["businessDate"], flag]
            if claim not in bucket:
                bucket.append(claim)

    market_reports = {}
    for market in MARKETS:
        rule = baseline["currentRules"][market]
        for year, yearly in yearly_sources.items():
            evidence[f"reconstruction:{market}:{year}"] = {
                "kind": "ANNUAL_HOLIDAYS_AND_REVIEWED_RULE_RECONSTRUCTION", "markets": [market],
                "knownAt": baseline["knownAt"], "sourceUrl": yearly["sourceUrl"], "rawSha256": yearly["sourceSha256"],
                "ruleSourceUrl": rule["sourceUrl"], "ruleRawSha256": rule["sourceSha256"],
                "historicalRuleContinuityConfirmed": False,
            }
        summary = {flag: Counter(dict.fromkeys(STATUSES, 0)) for flag in FLAGS}
        rows = []
        for date, reconstructed in dates.items():
            fields = {}
            for flag in FLAGS:
                claims = list(explicit[market, date, flag])
                if flag == "openDay":
                    claims.append({"sourceId": f"reconstruction:{market}:{date[:4]}", "value": reconstructed["openDay"],
                                   "basis": reconstructed["basis"], "holidayReason": reconstructed["holidayReason"]})
                fields[flag] = resolve(claims, evidence)
                summary[flag][fields[flag]["status"]] += 1
            rows.append({"businessDate": date, "fields": fields})
        market_reports[market] = {"dates": len(rows), "summary": summary, "rows": rows}

    provider = None if kis_folder is None else provider_page(kis_folder, dates, baseline["knownAt"])
    return {
        "schemaVersion": SCHEMA, "startDate": baseline["startDate"], "endDate": baseline["endDate"],
        "scopeSha256": baseline["scopeSha256"], "baselineSha256": digest(baseline_bytes),
        "sourceKind": baseline["sourceKind"], "knowledgeBasis": "FETCH_TIME_ONLY",
        "historicalFirstPublicationConfirmed": False, "marketReports": market_reports,
        "marketEvidence": evidence, "providerObservations": provider,
        "allCalendarFlagsComplete": all(
            row["fields"][flag]["status"] == "EXPLICIT_SCHEDULE"
            for report in market_reports.values() for row in report["rows"] for flag in FLAGS
        ),
        "usableForTrading": False, "usableForTraining": False, "usableForStrategyValidation": False,
    }


def provider_page(folder, dates, reconstruction_known_at):
    pack, receipt = calendar_fetch.audit_cached_calendar(folder)
    rows = []
    comparison_counts = Counter({"MATCH": 0, "DISAGREE": 0, "OUTSIDE_SCOPE": 0})
    distinct_flags = 0
    for entry in sorted(pack.calendar, key=lambda value: value.businessDate):
        row = entry.model_dump(mode="json")
        reconstructed = dates.get(row["businessDate"])
        if reconstructed is None:
            comparison = "OUTSIDE_SCOPE"
        else:
            comparison = "MATCH" if row["openDay"] == reconstructed["openDay"] else "DISAGREE"
        comparison_counts[comparison] += 1
        distinct_flags += row["tradingDay"] != row["openDay"]
        rows.append({**row, "openComparison": comparison})
    return {
        "provider": "KIS_CALENDAR", "scope": "DOMESTIC_NO_EXPLICIT_MARKET", "appliedToMarketFlags": False,
        "sourceUrl": calendar_fetch.SOURCE, "knownAt": receipt["capturedAt"], "basisDate": receipt["basisDate"],
        "bodySha256": receipt["bodySha256"], "referenceSha256": receipt["referenceSha256"], "hasMore": receipt["hasMore"],
        "rowsObserved": len(rows), "tradingAndOpenFlagsDiffer": distinct_flags, "openComparisonCounts": comparison_counts,
        "openComparisonKnownAt": max(receipt["capturedAt"], reconstruction_known_at, key=utc),
        "comparisonScope": "KIS_OPEN_FLAG_VS_SHARED_KRX_OPEN_RECONSTRUCTION_ONLY", "rows": rows,
    }


def as_of(report, market, date, at):
    day(date)
    cutoff = utc(at)
    if market not in MARKETS or not report["startDate"] <= date <= report["endDate"]:
        raise ResearchError("CALENDAR_FLAG_QUERY_OUTSIDE_SCOPE")
    row = next(item for item in report["marketReports"][market]["rows"] if item["businessDate"] == date)
    evidence = report["marketEvidence"]
    fields = {flag: resolve(row["fields"][flag]["claims"], evidence, cutoff) for flag in FLAGS}
    visible_ids = {claim["sourceId"] for field in fields.values() for claim in field["claims"]}
    provider = report["providerObservations"]
    observation = None
    if provider is not None and utc(provider["knownAt"]) <= cutoff:
        entry = next((item for item in provider["rows"] if item["businessDate"] == date), None)
        if entry:
            observation = {key: entry[key] for key in FLAGS}
            observation.update(scope=provider["scope"], knownAt=provider["knownAt"], bodySha256=provider["bodySha256"],
                               openComparison=entry["openComparison"] if utc(provider["openComparisonKnownAt"]) <= cutoff else None)
    return {
        "schemaVersion": SCHEMA, "market": market, "businessDate": date, "asOf": cutoff.isoformat(),
        "fields": fields, "marketEvidence": {source_id: evidence[source_id] for source_id in sorted(visible_ids)},
        "providerObservation": observation, "usableForTrading": False, "usableForTraining": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "audit", "as-of"):
        sub = commands.add_parser(command)
        for flag in ("scope", "cache", "year-job", "baseline", "output"):
            sub.add_argument("--" + flag, type=Path, required=True)
        sub.add_argument("--kis-cache-page", type=Path)
        if command == "as-of":
            sub.add_argument("--market", choices=MARKETS, required=True)
            sub.add_argument("--date", required=True)
            sub.add_argument("--at", required=True)
    args = parser.parse_args(argv)
    try:
        report = build(args.scope, args.cache, args.year_job, args.baseline, args.kis_cache_page)
        encoded = canonical(report)
        if args.command == "build":
            with args.output.open("xb") as stream:
                stream.write(encoded)
        elif read_bytes(args.output) != encoded:
            raise ResearchError("CALENDAR_FLAG_REPORT_MISMATCH")
        if args.command == "as-of":
            result = as_of(report, args.market, args.date, args.at)
        else:
            result = {
                "markets": {market: row["summary"] for market, row in report["marketReports"].items()},
                "providerRowsObserved": report["providerObservations"]["rowsObserved"] if report["providerObservations"] else 0,
                "allCalendarFlagsComplete": report["allCalendarFlagsComplete"], "reportSha256": digest(encoded),
            }
        print(canonical(result).decode("utf-8"))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"diagnostic": str(error) if isinstance(error, ResearchError) else "CALENDAR_FLAG_INPUT_INVALID"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
