"""Retrospective evidence ledger for every immutable KRX membership observation."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from . import kind_cases, kind_membership_status, krx_universe_history as history, universe_events
from .dataset import canonical, digest, read_bytes, read_json
from .history import day
from .krx_baseline_validation import immutable_json
from .models import ResearchError, utc

MATCHED = {"DISCLOSURE_MATCH", "STATUS_LIST_MATCH"}
MEMBERSHIP = {"ADDED_OBSERVED", "REMOVED_OBSERVED", "MARKET_TRANSFER_OBSERVED"}
POLICY = "SAGOPALGO_UNIVERSE_EVIDENCE_MATCH_1"


def normalized_name(name):
    value = re.sub(r"\s+", "", name)
    value = re.sub(r"^(?:주식회사|\(주\)|㈜)", "", value)
    value = re.sub(r"(?:주식회사|\(주\)|㈜)$", "", value)
    return value


def input_history(job, derived):
    history.build(job, derived, verify=True)
    report = read_json(read_bytes(derived / "report.json"))
    if report["pendingRequests"] or report["unreviewedRecords"] or report["capturedDates"] != report["plannedDates"]:
        raise ResearchError("RECONCILIATION_HISTORY_INCOMPLETE")
    observations = [read_json(v) for v in read_bytes(derived / "changes.jsonl").splitlines()]
    ids = [digest(canonical(v)) for v in observations]
    if len(ids) != len(set(ids)):
        raise ResearchError("RECONCILIATION_DUPLICATE_OBSERVATION")
    return report, observations


def history_aliases(job, observations):
    """Read only observed identities' original full/abbreviated names; never append a code digit."""
    plan, _, _, latest = history.load_job(job)
    targets = defaultdict(dict)
    for observation in observations:
        for side, date_field in [("before", "observedFrom"), ("after", "observedTo")]:
            issue = observation[side]
            if issue:
                key = (observation[date_field], issue["market"])
                old = targets[key].get(issue["isin"])
                if old is not None and old != issue:
                    raise ResearchError("RECONCILIATION_IDENTITY_CONFLICT")
                targets[key][issue["isin"]] = issue
    aliases, times = defaultdict(set), defaultdict(list)
    ambiguous_keys = set()
    evidence = []
    for (stamp, market), wanted in sorted(targets.items()):
        entry = history.observations(job, plan, latest, stamp)[market]
        raw = history.entry_raw(job, entry, entry["seed"])
        rows = {v["ISU_CD"]:v for v in history.envelope(raw)}
        prefixes = defaultdict(set)
        for row in rows.values():
            if row["KIND_STKCERT_TP_NM"] == "보통주":
                prefixes[row["ISU_SRT_CD"][:5]].add((row["ISU_CD"],row["ISU_SRT_CD"]))
        for isin, issue in sorted(wanted.items()):
            row = rows.get(isin)
            if (row is None or row["ISU_SRT_CD"] != issue["symbol"] or row["ISU_NM"] != issue["name"]
                    or digest(canonical(row)) != issue["sourceRowSha256"]):
                raise ResearchError("RECONCILIATION_IDENTITY_CONFLICT")
            names = sorted({row["ISU_NM"], row["ISU_ABBRV"]})
            if len(prefixes[issue["symbol"][:5]]) != 1:
                ambiguous_keys.add((stamp,market,isin))
            aliases[isin].update(normalized_name(v) for v in names)
            times[isin].append(entry["capturedAt"])
            evidence.append({"isin":isin, "date":stamp, "market":market, "symbol":issue["symbol"],
                             "names":names, "knownAt":entry["capturedAt"], "sourceRowSha256":issue["sourceRowSha256"],
                             "sourceSha256":entry["sha256"]})
    ambiguous_ids = {digest(canonical(v)) for v in observations if any(v[side] and
                     (v[date_field],v[side]["market"],v[side]["isin"]) in ambiguous_keys
                     for side,date_field in [("before","observedFrom"),("after","observedTo")])}
    return aliases, {k:max(v, key=utc) for k,v in times.items()}, digest(canonical(evidence)), ambiguous_ids


def status_id(row):
    return digest(canonical(row))


def choose_status(rows, kind, market, issue, aliases, observation):
    # Five-character KIND issuer keys are candidate keys. Confirm against an actual historical
    # six-character code and the same ISIN's original names before accepting a table match.
    candidates = [v for v in rows if v["kind"] == kind and v["market"] == market
                  and issue["symbol"].startswith(v["providerIssuerKey"])]
    inside = [v for v in candidates if observation["observedFrom"] < v["date"] <= observation["observedTo"]]
    named = [v for v in inside if normalized_name(v["issuerName"]) in aliases]
    if len(named) == 1 and len(inside) == 1:
        return "MATCH", named
    if inside:
        return "IDENTITY_REVIEW", inside
    named = [v for v in candidates if normalized_name(v["issuerName"]) in aliases]
    if named:
        return "DATE_CONFLICT", named
    unkeyed = [v for v in rows if v["kind"] == kind and v["market"] == market
               and observation["observedFrom"] < v["date"] <= observation["observedTo"]
               and normalized_name(v["issuerName"]) in aliases]
    return ("KEY_MAPPING_REQUIRED", unkeyed) if unkeyed else ("MISSING", [])


def status_evidence(row):
    return {"referenceId":status_id(row), "kind":row["kind"], "market":row["market"],
            "providerIssuerKey":row["providerIssuerKey"], "issuerName":row["issuerName"],
            "date":row["date"], "eventType":row["eventType"], "knownAt":row["knownAt"],
            "sourceSha256":row["sourceSha256"], "sourceRowSha256":row["sourceRowSha256"],
            "fullStockCodeProvided":False, "isinProvided":False}


def disclosure_candidates(observation, facts):
    before, after = observation["before"], observation["after"]
    result = []
    for fact in facts:
        kind = observation["kind"]
        if kind == "ADDED_OBSERVED":
            match = fact["kind"] == "IPO" and fact["stockCode"] == after["symbol"] and fact["market"] == after["market"]
        elif kind == "REMOVED_OBSERVED":
            match = (fact["kind"] in {"DELISTING", "MERGER_DELISTING"} and fact["stockCode"] == before["symbol"]
                     and fact.get("market", fact.get("fromMarket")) == before["market"])
        elif kind == "MARKET_TRANSFER_OBSERVED":
            match = (fact["kind"] == "MARKET_TRANSFER" and fact["stockCode"] == before["symbol"] == after["symbol"]
                     and fact["fromMarket"] == before["market"] and fact["toMarket"] == after["market"])
        else:
            match = False
        if match:
            result.append(fact)
    return result


def reconcile(observations, status, facts, aliases, alias_times, ambiguous_ids=()):
    results, used = [], set()
    for observation in observations:
        issue = observation["after"] or observation["before"]
        isin, kind = issue["isin"], observation["kind"]
        selections, problems, evidence = [], [], []
        if kind in MEMBERSHIP:
            channels = []
            if kind != "REMOVED_OBSERVED": channels.append(("LISTING", observation["after"]))
            if kind != "ADDED_OBSERVED": channels.append(("DELISTING", observation["before"]))
            for channel, side in channels:
                state, matches = choose_status(status["records"], channel, side["market"], side, aliases.get(isin,set()), observation)
                selections.extend(matches)
                if state != "MATCH": problems.append(state)
            if digest(canonical(observation)) in ambiguous_ids:
                problems.append("IDENTITY_REVIEW")
            if not problems:
                if kind == "MARKET_TRANSFER_OBSERVED":
                    listing = next(v for v in selections if v["kind"] == "LISTING")
                    exit_row = next(v for v in selections if v["kind"] == "DELISTING")
                    reason = "유가증권시장상장" if observation["after"]["market"] == "KOSPI" else "코스닥시장상장"
                    if listing["eventType"] != "이전상장" or reason not in re.sub(r"\s+", "", exit_row["eventType"]):
                        problems.append("EVENT_TYPE_CONFLICT")
                elif kind == "ADDED_OBSERVED" and selections[0]["eventType"] not in {"신규상장", "이전상장", "재상장", "재상장 합병"}:
                    problems.append("EVENT_TYPE_CONFLICT")
            resolution = ("STATUS_LIST_MATCH" if not problems else "STATUS_DATE_CONFLICT" if "DATE_CONFLICT" in problems
                          else "STATUS_IDENTITY_REVIEW" if "IDENTITY_REVIEW" in problems else "STATUS_EVENT_TYPE_CONFLICT"
                          if "EVENT_TYPE_CONFLICT" in problems else "ISSUER_KEY_MAPPING_REQUIRED"
                          if "KEY_MAPPING_REQUIRED" in problems else "NO_STATUS_EVIDENCE")
        else:
            resolution = "NAME_CHANGE_NEEDS_DISCLOSURE" if kind == "NAME_CHANGE_OBSERVED" else "UNSUPPORTED_OBSERVATION"
        evidence = [status_evidence(v) for v in selections]
        disclosures = disclosure_candidates(observation, facts)
        inside = [v for v in disclosures if observation["observedFrom"] < v["date"] <= observation["observedTo"]]
        outside = [v for v in disclosures if v not in inside]
        if outside or len(inside) > 1:
            resolution = "DISCLOSURE_DATE_OR_IDENTITY_CONFLICT"
        elif len(inside) == 1:
            # A second source that contradicts the disclosure remains a conflict.
            resolution = "EVIDENCE_CONFLICT" if problems and any(v != "MISSING" for v in problems) else "DISCLOSURE_MATCH"
        for fact in disclosures:
            sources = fact.get("sources", [{"url":fact.get("sourceUrl"), "sha256":fact.get("sourceSha256"), "knownAt":fact["knownAt"]}])
            evidence.append({"caseId":fact["caseId"], "kind":fact["kind"], "date":fact["date"], "dateBasis":fact["dateBasis"],
                             "stockCode":fact["stockCode"], "knownAt":fact["knownAt"], "sources":sources})
        if resolution in MATCHED:
            used.update(status_id(v) for v in selections)
        known_times = [observation["knownAt"], alias_times.get(isin, observation["knownAt"]), *[v["knownAt"] for v in evidence]]
        results.append({"observationId":digest(canonical(observation)), "observation":observation,
                        "resolution":resolution, "evidence":evidence, "knownAt":max(known_times,key=utc),
                        "identityEvidenceKnownAt":alias_times.get(isin), "reconciliationBasis":"RETROSPECTIVE_CHECK_ONLY",
                        "membershipDateConfirmedByDisclosure":resolution == "DISCLOSURE_MATCH",
                        "exchangeMembershipDate":inside[0]["date"] if resolution == "DISCLOSURE_MATCH" else None,
                        "allLegalEffectsConfirmed":False, "usableForTraining":False, "usableForTrading":False})
    return results, used


def build(job, derived, status_job, cases, events):
    parent, observations = input_history(job, derived)
    status = kind_membership_status.report(status_job)
    if status["missingSources"] or (status["startDate"],status["endDate"]) != (parent["startDate"],parent["endDate"]):
        raise ResearchError("RECONCILIATION_STATUS_INCOMPLETE_OR_SCOPE_MISMATCH")
    synthetic = parent["sourceKind"] == "SYNTHETIC"
    if synthetic != (status["sourceKind"] == "SYNTHETIC"):
        raise ResearchError("RECONCILIATION_SOURCE_KIND_MISMATCH")
    for report in [cases, events]:
        if (report["startDate"],report["endDate"]) != (parent["startDate"],parent["endDate"]):
            raise ResearchError("RECONCILIATION_DISCLOSURE_SCOPE_MISMATCH")
    aliases, times, alias_sha, ambiguous = history_aliases(job, observations)
    rows, used = reconcile(observations, status, [*cases["facts"],*events["facts"]], aliases, times, ambiguous)
    counts = Counter(v["resolution"] for v in rows)
    membership = [v for v in rows if v["observation"]["kind"] in MEMBERSHIP]
    unused = [{"referenceId":status_id(v), "kind":v["kind"], "market":v["market"], "providerIssuerKey":v["providerIssuerKey"],
               "issuerName":v["issuerName"], "date":v["date"], "eventType":v["eventType"],
               "reason":"AT_SCOPE_START_REQUIRES_BASELINE_CHECK" if v["date"] == parent["startDate"] else "NO_CONFIRMED_OBSERVATION_LINK"}
              for v in status["records"] if status_id(v) not in used]
    return {"schemaVersion":"SAGOPALGO_UNIVERSE_RECONCILIATION_V1", "policy":POLICY,
            "sourceKind":"SYNTHETIC" if synthetic else "PROVIDER_OBSERVATIONS", "startDate":parent["startDate"], "endDate":parent["endDate"],
            "historyReportSha256":digest(read_bytes(derived / "report.json")), "historyChangesSha256":parent["changesSha256"],
            "identityAliasesSha256":alias_sha, "statusReportSha256":digest(canonical(status)),
            "ambiguousHistoryIdentityObservations":len(ambiguous),
            "caseReportSha256":digest(canonical(cases)), "eventReportSha256":digest(canonical(events)),
            "observations":len(rows), "resolutionCounts":dict(counts), "membershipObservations":len(membership),
            "membershipMatched":sum(v["resolution"] in MATCHED for v in membership),
            "membershipAwaitingIndividualDisclosure":len(membership)-sum(v["resolution"]=="DISCLOSURE_MATCH" for v in membership),
            "disclosureMatched":counts["DISCLOSURE_MATCH"], "unresolvedObservations":sum(v["resolution"] not in MATCHED for v in rows),
            "sourceRowsByChannel":{k:{m:sum(v["kind"]==k and v["market"]==m for v in status["records"]) for m in kind_membership_status.MARKETS}
                                   for k in kind_membership_status.ENDPOINTS},
            "unusedStatusReferences":unused, "rows":rows,
            "providerIssuerKeyIsNotFullStockCode":True, "sameProviderCrossCheck":True, "independentTotalVerified":False,
            "corporateNameChangeDatesConfirmed":False, "allLegalEffectsConfirmed":False,
            "marketUniverseComplete":False, "usableForTraining":False, "usableForTrading":False}


def as_of(report, at, symbol=None):
    instant = utc(at)
    if symbol is not None and not re.fullmatch(r"[A-Z0-9]{6}", symbol):
        raise ResearchError("RECONCILIATION_SYMBOL_INVALID")
    rows = [v for v in report["rows"] if utc(v["knownAt"]) <= instant and (symbol is None
            or any(v["observation"][side] and v["observation"][side]["symbol"] == symbol for side in ["before","after"]))]
    return {"asOf":at, "symbol":symbol, "rows":rows, "visibleObservations":len(rows),
            "usableForTraining":False, "usableForTrading":False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ["build", "audit", "as-of"]:
        p = sub.add_parser(command)
        p.add_argument("--output", type=Path, required=True)
        if command == "as-of":
            p.add_argument("--at", required=True)
            p.add_argument("--symbol")
        for flag in ["history-job","history-derived","status-job","cases","case-report","events","event-report","cache"]:
            p.add_argument("--"+flag, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        cases = kind_cases.audit_report(kind_cases.load_scope(args.cases), args.cache, args.case_report)
        events = universe_events.audit_report(universe_events.load_scope(args.events), args.cache, args.event_report)
        result = build(args.history_job,args.history_derived,args.status_job,cases,events)
        immutable_json(args.output,result,require_existing=args.command!="build")
        if args.command == "as-of":
            result = as_of(result,args.at,args.symbol)
        print(json.dumps({k:v for k,v in result.items() if k not in {"rows","unusedStatusReferences"}},sort_keys=True),flush=True)
        return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({"diagnostic":str(exc) if isinstance(exc,ResearchError) else "RECONCILIATION_INPUT_INVALID"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
