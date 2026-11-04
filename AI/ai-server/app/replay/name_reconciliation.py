"""Version-three name evidence overlay, retaining version-two membership and original observations."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

from . import kind_cases, universe_events, membership_reconciliation as prior, universe_reconciliation as original
from . import name_disclosures as acquisition, name_facts, krx_universe_history as history
from .dataset import canonical, digest, read_bytes, read_json
from .krx_baseline_validation import immutable_json
from .models import ResearchError, utc

NAME_MATCHED = {"NAME_DISCLOSURE_MATCH", "TRANSFER_NAME_FORMAT_MATCH"}


def contexts(job, parent, plan):
    config, _, _, latest = history.load_job(job)
    rows = {v["observationId"]: v["observation"] for v in parent["rows"]}
    result = {}
    for target in plan["targets"]:
        identity = target["observationId"]
        obs = rows[identity]
        result[identity] = {}
        for side, date_field in [("before", "observedFrom"), ("after", "observedTo")]:
            issue = obs[side]
            entry = history.observations(job, config, latest, obs[date_field])[issue["market"]]
            raw = history.entry_raw(job, entry, entry["seed"])
            selected = [v for v in history.envelope(raw) if v["ISU_CD"] == issue["isin"]]
            if (len(selected) != 1 or digest(canonical(selected[0])) != issue["sourceRowSha256"]
                    or selected[0]["ISU_SRT_CD"] != issue["symbol"] or selected[0]["ISU_NM"] != issue["name"]):
                raise ResearchError("NAME_OVERLAY_SOURCE_CONTEXT_MISMATCH")
            row = selected[0]
            result[identity][side] = {"symbol": issue["symbol"], "isin": issue["isin"], "market": issue["market"],
                "date": obs[date_field], "name": row["ISU_NM"], "abbreviatedName": row["ISU_ABBRV"],
                "securityType": row["SECUGRP_NM"], "shareType": row["KIND_STKCERT_TP_NM"],
                "knownAt": entry["capturedAt"], "sourceRowSha256": issue["sourceRowSha256"], "sourceSha256": entry["sha256"]}
    return result


def overlay(parent, supplement, parent_sha):
    if supplement["parentSha256"] != parent_sha or supplement["sourceKind"] != parent["sourceKind"]:
        raise ResearchError("NAME_OVERLAY_PARENT_MISMATCH")
    result = deepcopy(parent)
    by_id = {v["observationId"]: v for v in result["rows"]}
    expected = {v["observationId"] for v in result["rows"] if v["observation"]["kind"] == "NAME_CHANGE_OBSERVED"}
    seen = set()
    for fact in supplement["facts"]:
        identity = fact["observationId"]
        if identity not in expected or identity in seen:
            raise ResearchError("NAME_OVERLAY_DUPLICATE_OR_UNKNOWN")
        seen.add(identity)
        row = by_id[identity]
        obs = row["observation"]
        if (row["resolution"] != "NAME_CHANGE_NEEDS_DISCLOSURE"
                or fact["classification"] not in {"EXCHANGE_NAME_CHANGE", "MARKET_TRANSFER_COMMON_SHARE_LABEL"}
                or any((obs[side]["symbol"], obs[side]["isin"]) != (fact["stockCode"], fact["historyIsin"]) for side in ["before", "after"])
                or not obs["observedFrom"] < fact["date"] <= obs["observedTo"]):
            raise ResearchError("NAME_OVERLAY_IDENTITY_OR_DATE_CONFLICT")
        if fact["classification"] == "EXCHANGE_NAME_CHANGE":
            if any(not name_facts.name_matches(fact[side + "Name"], obs[side]["name"], obs[side]["market"], fact["sourceIsin"])
                   and not (side == "after" and fact.get("afterAbbreviatedName")
                            and name_facts.name_key(fact["afterAbbreviatedName"]) == name_facts.name_key(obs[side]["name"])) for side in ["before", "after"]):
                raise ResearchError("NAME_OVERLAY_NAME_CONFLICT")
            resolution = "NAME_DISCLOSURE_MATCH"
        else:
            transfers = [v for v in parent["rows"] if v["observationId"] == fact.get("transferObservationId")
                         and v["observation"]["kind"] == "MARKET_TRANSFER_OBSERVED" and v["resolution"] == "DISCLOSURE_MATCH"
                         and v["membershipDateConfirmedByDisclosure"] and v["exchangeMembershipDate"] == fact["date"]
                         and all(v["observation"][k] == obs[k] for k in ["before", "after", "observedFrom", "observedTo"])]
            if (fact["beforeName"] != obs["before"]["name"] or fact["afterName"] != obs["after"]["name"]
                    or (obs["before"]["market"], obs["after"]["market"]) != ("KOSDAQ", "KOSPI")
                    or fact["afterName"] != fact["beforeName"] + "보통주" or len(transfers) != 1):
                raise ResearchError("NAME_OVERLAY_NAME_CONFLICT")
            resolution = "TRANSFER_NAME_FORMAT_MATCH"
        row.update(previousResolution=row["resolution"], resolution=resolution,
                   exchangeNameDate=fact["date"], exchangeNameDateBasis=fact["dateBasis"],
                   corporateLegalNameEffectiveDate=None, nameEvidenceId=digest(canonical(fact)))
        row["evidence"].append(deepcopy(fact))
        row["knownAt"] = max([row["knownAt"], fact["knownAt"]], key=utc)
    for review in supplement["reviews"]:
        identity = review["observationId"]
        if identity not in expected or identity in seen:
            raise ResearchError("NAME_OVERLAY_DUPLICATE_OR_UNKNOWN")
        seen.add(identity)
        by_id[identity]["nameReview"] = review
        by_id[identity]["knownAt"] = max([by_id[identity]["knownAt"], review["knownAt"]], key=utc)
    if seen != expected or supplement["targets"] != len(expected):
        raise ResearchError("NAME_OVERLAY_SCOPE_INCOMPLETE")
    counts = Counter(v["resolution"] for v in result["rows"])
    result.update(schemaVersion="SAGOPALGO_UNIVERSE_RECONCILIATION_V3", policy="SAGOPALGO_UNIVERSE_EVIDENCE_MATCH_3",
        parentV2ReportSha256=parent_sha, nameSupplementSha256=digest(canonical(supplement)), resolutionCounts=dict(counts),
        nameObservations=len(expected), nameDisclosureMatched=counts["NAME_DISCLOSURE_MATCH"],
        transferNameLabelsExplained=counts["TRANSFER_NAME_FORMAT_MATCH"], nameReviewRequired=len(supplement["reviews"]),
        unresolvedObservations=sum(v["resolution"] not in original.MATCHED | NAME_MATCHED for v in result["rows"]))
    return result


def build(job, parent, parent_path, name_job):
    immutable_json(parent_path, parent, True)
    parent_sha = digest(read_bytes(parent_path))
    plan, _, _ = acquisition.load(name_job)
    if (plan["parentSha256"] != parent_sha or plan["sourceKind"] != parent["sourceKind"]
            or plan["targets"] != acquisition.targets_from(parent)
            or (plan["startDate"], plan["endDate"]) != (parent["startDate"], parent["endDate"])):
        raise ResearchError("NAME_OVERLAY_PLAN_PARENT_MISMATCH")
    supplement = name_facts.build(name_job, parent, contexts(job, parent, plan))
    return overlay(parent, supplement, parent_sha), supplement


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ["build", "audit", "as-of"]:
        p = sub.add_parser(command)
        for flag in ["history-job", "history-derived", "status-job", "cases", "case-report", "events", "event-report", "cache",
                     "parent-report", "evidence-job", "parent-v2", "name-job", "facts-output", "output"]:
            p.add_argument("--" + flag, type=Path, required=True)
        p.add_argument("--corrections-job", type=Path)
        if command == "as-of":
            p.add_argument("--at", required=True)
            p.add_argument("--symbol")
    args = parser.parse_args(argv)
    try:
        cases = kind_cases.audit_report(kind_cases.load_scope(args.cases), args.cache, args.case_report)
        events = universe_events.audit_report(universe_events.load_scope(args.events), args.cache, args.event_report)
        parent, _ = prior.build(args.history_job, args.history_derived, args.status_job, cases, events,
                                args.parent_report, args.evidence_job, args.corrections_job)
        result, supplement = build(args.history_job, parent, args.parent_v2, args.name_job)
        for path, value in [(args.facts_output, supplement), (args.output, result)]:
            immutable_json(path, value, args.command != "build")
        if args.command == "as-of":
            result = original.as_of(result, args.at, args.symbol)
        print(json.dumps({k: v for k, v in result.items() if k not in {"rows", "unusedStatusReferences"}}, sort_keys=True), flush=True)
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"diagnostic": str(exc) if isinstance(exc, ResearchError) else "NAME_OVERLAY_INPUT_INVALID"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
