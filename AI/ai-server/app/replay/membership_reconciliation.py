"""Version-two disclosure overlay; the version-one ledger and observations remain immutable."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

from . import universe_reconciliation as parent_ledger,kind_membership_status,kind_cases,universe_events
from . import kind_membership_evidence as acquisition,membership_evidence_facts as facts
from . import krx_universe_history as history
from .dataset import canonical,digest,read_bytes,read_json
from .krx_baseline_validation import immutable_json
from .models import ResearchError,utc


def contexts(job,parent,plan):
    capture_plan,_,_,latest=history.load_job(job)
    observations={v["observationId"]:v["observation"] for v in parent["rows"]}
    result={}
    for target in plan["targets"]:
        obs=observations.get(target["observationId"])
        if not obs or digest(canonical(obs))!=target["observationId"]:
            raise ResearchError("MEMBERSHIP_OVERLAY_TARGET_INVALID")
        side="after" if target["kind"]=="ADDED_OBSERVED" else "before"
        issue=obs[side]
        stamp=obs["observedTo"] if side=="after" else obs["observedFrom"]
        if ((target["kind"],target["symbol"],target["isin"],target["market"],target["observedFrom"],target["observedTo"])
                !=(obs["kind"],issue["symbol"],issue["isin"],issue["market"],obs["observedFrom"],obs["observedTo"])):
            raise ResearchError("MEMBERSHIP_OVERLAY_TARGET_INVALID")
        entry=history.observations(job,capture_plan,latest,stamp)[issue["market"]]
        raw=history.entry_raw(job,entry,entry["seed"])
        selected=[v for v in history.envelope(raw) if v["ISU_CD"]==issue["isin"]]
        if len(selected)!=1 or digest(canonical(selected[0]))!=issue["sourceRowSha256"] or selected[0]["ISU_SRT_CD"]!=issue["symbol"]:
            raise ResearchError("MEMBERSHIP_OVERLAY_INSTRUMENT_MISMATCH")
        row=selected[0]
        result[target["observationId"]]={"symbol":issue["symbol"],"isin":issue["isin"],"securityType":row["SECUGRP_NM"],
                "shareType":row["KIND_STKCERT_TP_NM"],"sourceRowSha256":issue["sourceRowSha256"],
                "sourceSha256":entry["sha256"],"knownAt":entry["capturedAt"]}
    return result


def overlay(parent,supplement,status,parent_sha):
    result=deepcopy(parent)
    by_id={v["observationId"]:v for v in result["rows"]}
    if len(by_id)!=len(result["rows"]):
        raise ResearchError("MEMBERSHIP_OVERLAY_PARENT_DUPLICATE")
    seen=set()
    for fact in supplement["facts"]:
        identity=fact["observationId"]
        if identity in seen or identity not in by_id:
            raise ResearchError("MEMBERSHIP_OVERLAY_FACT_DUPLICATE_OR_UNKNOWN")
        seen.add(identity)
        row=by_id[identity]; obs=row["observation"]
        side=obs["after"] or obs["before"]
        expected_kind="MEMBERSHIP_ENTRY" if obs["kind"]=="ADDED_OBSERVED" else "MEMBERSHIP_EXIT" if obs["kind"]=="REMOVED_OBSERVED" else None
        if (row["resolution"] in parent_ledger.MATCHED or fact["kind"]!=expected_kind
                or (fact["stockCode"],fact["historyIsin"],fact["market"])!=(side["symbol"],side["isin"],side["market"])
                or not obs["observedFrom"]<fact["date"]<=obs["observedTo"]
                or fact.get("sourceIsin") and fact["sourceIsin"]!=side["isin"]):
            raise ResearchError("MEMBERSHIP_OVERLAY_FACT_IDENTITY_OR_DATE_CONFLICT")
        row["previousResolution"]=row["resolution"]
        row["resolution"]="DISCLOSURE_MATCH"
        row["membershipDateConfirmedByDisclosure"]=True
        row["exchangeMembershipDate"]=fact["date"]
        row["exchangeMembershipDateBasis"]=fact["dateBasis"]
        row["supplementalDisclosureId"]=digest(canonical(fact))
        row["evidence"].append(deepcopy(fact))
        # A full-code disclosure and its full-code viewer can bridge the table's name/key.
        # No transliteration or constructed six-character stock codes are used.
        names={parent_ledger.normalized_name(fact[k]) for k in ["issuerName","viewerIssuerName"]}
        channel="LISTING" if expected_kind=="MEMBERSHIP_ENTRY" else "DELISTING"
        candidates=[v for v in status["records"] if v["kind"]==channel and v["market"]==fact["market"] and v["date"]==fact["date"]
                    and parent_ledger.normalized_name(v["issuerName"]) in names]
        if len(candidates)==1:
            ref=parent_ledger.status_evidence(candidates[0])
            if ref["referenceId"] not in {v.get("referenceId") for v in row["evidence"]}:
                row["evidence"].append(ref)
            row["statusIdentityBridge"]={"basis":"AUDITED_DISCLOSURE_FULL_CODE_AND_VIEWER_NAME",
                                         "providerIssuerKey":ref["providerIssuerKey"],"referenceId":ref["referenceId"]}
        row["knownAt"]=max([row["knownAt"],fact["knownAt"],*[v["knownAt"] for v in row["evidence"]]],key=utc)
    for review in supplement["reviews"]:
        if review["observationId"] not in by_id or review["observationId"] in seen:
            raise ResearchError("MEMBERSHIP_OVERLAY_REVIEW_INVALID")
        by_id[review["observationId"]]["supplementalReview"]=review
    counts=Counter(v["resolution"] for v in result["rows"])
    members=[v for v in result["rows"] if v["observation"]["kind"] in parent_ledger.MEMBERSHIP]
    used={e["referenceId"] for v in result["rows"] if v["resolution"] in parent_ledger.MATCHED for e in v["evidence"] if "referenceId" in e}
    result.update(schemaVersion="SAGOPALGO_UNIVERSE_RECONCILIATION_V2",policy="SAGOPALGO_UNIVERSE_EVIDENCE_MATCH_2",
        parentReportSha256=parent_sha,supplementReportSha256=digest(canonical(supplement)),
        parentMembershipMatched=parent["membershipMatched"],resolvedParentTargets=len(seen),supplementReviewRequired=len(supplement["reviews"]),
        supplementCorrectionHeaderDateIssues=supplement.get("correctionHeaderDateIssues",0),
        resolutionCounts=dict(counts),disclosureMatched=counts["DISCLOSURE_MATCH"],
        membershipMatched=sum(v["resolution"] in parent_ledger.MATCHED for v in members),
        membershipAwaitingIndividualDisclosure=len(members)-sum(v["resolution"]=="DISCLOSURE_MATCH" for v in members),
        unresolvedObservations=sum(v["resolution"] not in parent_ledger.MATCHED for v in result["rows"]),
        unusedStatusReferences=[v for v in parent["unusedStatusReferences"] if v["referenceId"] not in used])
    return result


def build(job,derived,status_job,cases,events,parent_path,evidence_job,corrections_job=None):
    parent=parent_ledger.build(job,derived,status_job,cases,events)
    immutable_json(parent_path,parent,True)
    parent_sha=digest(read_bytes(parent_path))
    plan,_,_=acquisition.load(evidence_job)
    if plan["parentSha256"]!=parent_sha or plan["sourceKind"]!=parent["sourceKind"]:
        raise ResearchError("MEMBERSHIP_OVERLAY_PARENT_MISMATCH")
    instrument_contexts=contexts(job,parent,plan)
    supplement=facts.build(evidence_job,instrument_contexts)
    if corrections_job is not None:
        from . import membership_corrections
        supplement=membership_corrections.apply(corrections_job,evidence_job,supplement,instrument_contexts)
    status=kind_membership_status.report(status_job)
    return overlay(parent,supplement,status,parent_sha),supplement


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    for command in ["build","audit","as-of"]:
        p=sub.add_parser(command)
        for flag in ["history-job","history-derived","status-job","cases","case-report","events","event-report","cache",
                     "parent-report","evidence-job","output","facts-output"]: p.add_argument("--"+flag,type=Path,required=True)
        p.add_argument("--corrections-job",type=Path)
        if command=="as-of": p.add_argument("--at",required=True); p.add_argument("--symbol")
    args=parser.parse_args(argv)
    try:
        cases=kind_cases.audit_report(kind_cases.load_scope(args.cases),args.cache,args.case_report)
        events=universe_events.audit_report(universe_events.load_scope(args.events),args.cache,args.event_report)
        result,supplement=build(args.history_job,args.history_derived,args.status_job,cases,events,args.parent_report,args.evidence_job,args.corrections_job)
        for path,value in [(args.output,result),(args.facts_output,supplement)]: immutable_json(path,value,args.command!="build")
        if args.command=="as-of": result=parent_ledger.as_of(result,args.at,args.symbol)
        print(json.dumps({k:v for k,v in result.items() if k not in {"rows","unusedStatusReferences"}},sort_keys=True),flush=True)
        return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({"diagnostic":str(exc) if isinstance(exc,ResearchError) else "MEMBERSHIP_OVERLAY_INPUT_INVALID"}))
        return 2


if __name__=="__main__": raise SystemExit(main())
