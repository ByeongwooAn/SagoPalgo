"""V7 records the final inventory phase without erasing a conflicting official date."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

from . import remaining_membership_disclosures as acquisition, remaining_membership_facts as facts
from . import delisting_coverage_reconciliation as prior, membership_reconciliation as membership, universe_reconciliation as original
from .dataset import canonical,digest,read_bytes,read_json
from .krx_baseline_validation import immutable_json
from .models import ResearchError,utc


def overlay(parent,supplement,inventory,parent_sha):
    if (parent.get('schemaVersion')!='SAGOPALGO_UNIVERSE_RECONCILIATION_V6' or supplement['parentSha256']!=parent_sha
            or supplement['sourceKind']!=parent['sourceKind']):raise ResearchError('REMAINING_OVERLAY_PARENT_CONFLICT')
    targets={t['observationId']:t for t in acquisition.targets_from(parent,inventory)}
    result=deepcopy(parent);rows={r['observationId']:r for r in result['rows']};seen=set()
    for f in supplement['facts']:
        identity=f['observationId']
        if identity not in targets or identity in seen:raise ResearchError('REMAINING_OVERLAY_UNEXPECTED_FACT')
        seen.add(identity);row=rows[identity];t=targets[identity];o=row['observation']
        kind='MEMBERSHIP_EXIT' if t['kind']=='REMOVED_OBSERVED' else 'MEMBERSHIP_ENTRY'
        basis='EXCHANGE_RELISTING_DATE' if t['category']=='RELISTING' else 'EXCHANGE_DELISTING_DATE' if kind=='MEMBERSHIP_EXIT' else 'EXCHANGE_LISTING_DATE'
        if ((f['kind'],f['category'],f['stockCode'],f['historyIsin'],f['market'])!=(kind,t['category'],t['symbol'],t['isin'],t['market'])
                or f.get('sourceIsin') not in {None,t['isin']} or f['date']!=t['statusDate'] or f['statusDate']!=t['statusDate']
                or (f['statusReferenceId'],f['statusEventType'])!=(t['statusReferenceId'],t['statusEventType']) or f['dateBasis']!=basis
                or not o['observedFrom']<f['date']<=o['observedTo']
                or t['category']=='INBOUND_TRANSFER' and (f.get('destinationEntryOnlyConfirmed') is not True
                    or f.get('sourceMarketHistoryConfirmed') is not False or f.get('completeTransferPairConfirmed') is not False)):
            raise ResearchError('REMAINING_OVERLAY_IDENTITY_DATE_OR_SCOPE_CONFLICT')
        row.update(previousResolution=row['resolution'],resolution='DISCLOSURE_MATCH',membershipDateConfirmedByDisclosure=True,
            exchangeMembershipDate=f['date'],exchangeMembershipDateBasis=f['dateBasis'],supplementalRemainingEvidenceId=digest(canonical(f)),
            individualDisclosureStatus='VERIFIED',knownAt=max([row['knownAt'],f['knownAt']],key=utc))
        row['evidence'].append(deepcopy(f))
    for review in supplement['reviews']:
        identity=review['observationId']
        if identity not in targets or identity in seen or review['category']!=targets[identity]['category']:
            raise ResearchError('REMAINING_OVERLAY_UNEXPECTED_REVIEW')
        seen.add(identity);row=rows[identity]
        if 'membershipDisclosureReview' in row:row['previousMembershipDisclosureReview']=deepcopy(row['membershipDisclosureReview'])
        row.update(individualDisclosureStatus='REVIEW_REQUIRED',membershipDisclosureReview=deepcopy(review),
                   knownAt=max([row['knownAt'],review['knownAt']],key=utc))
    if seen!=set(targets) or supplement['targets']!=len(targets):raise ResearchError('REMAINING_OVERLAY_INCOMPLETE_SCOPE')
    counts=Counter(r['resolution'] for r in result['rows']);pending=Counter(r['category'] for r in supplement['reviews'])
    verified=Counter(f['category'] for f in supplement['facts'])
    result.update(schemaVersion='SAGOPALGO_UNIVERSE_RECONCILIATION_V7',policy='SAGOPALGO_UNIVERSE_EVIDENCE_MATCH_7',
        parentV6ReportSha256=parent_sha,remainingSupplementSha256=digest(canonical(supplement)),resolutionCounts=dict(counts),
        disclosureMatched=parent['disclosureMatched']+len(supplement['facts']),
        membershipAwaitingIndividualDisclosure=parent['membershipAwaitingIndividualDisclosure']-len(supplement['facts']),
        remainingDisclosureTargets=len(targets),remainingDisclosureVerified=len(supplement['facts']),remainingDisclosureReviewRequired=len(supplement['reviews']),
        relistingVerified=verified['RELISTING'],inboundDestinationEntriesVerified=verified['INBOUND_TRANSFER'],
        delistingVerified=parent['delistingVerified']+verified['DELISTING_REVIEW'],delistingReviewRequired=pending['DELISTING_REVIEW'],
        laterPhasePending=0,membershipPendingByPhase={'NEW_LISTING_REVIEW':0,'DELISTING_REVIEW':pending['DELISTING_REVIEW'],
            'RELISTING':pending['RELISTING'],'INBOUND_TRANSFER':pending['INBOUND_TRANSFER']})
    return result


def build(history_job,parent,parent_path,job,inventory_path):
    immutable_json(parent_path,parent,True);parent_sha=digest(read_bytes(parent_path));inventory=read_json(read_bytes(inventory_path))
    plan,_,_=acquisition.load(job)
    if (parent.get('listingInventorySha256')!=digest(read_bytes(inventory_path)) or plan['parentSha256']!=parent_sha
            or plan['inventorySha256']!=digest(read_bytes(inventory_path)) or plan['sourceKind']!=parent['sourceKind']
            or plan['targets']!=acquisition.targets_from(parent,inventory) or (plan['startDate'],plan['endDate'])!=(parent['startDate'],parent['endDate'])):
        raise ResearchError('REMAINING_OVERLAY_PLAN_CONFLICT')
    supplement=facts.build(job,membership.contexts(history_job,parent,plan))
    return overlay(parent,supplement,inventory,parent_sha),supplement


def audited_parent(args):
    v5=prior.audited_parent(args)
    v6,_=prior.build(args.history_job,v5,args.parent_v5,args.delisting_job,args.inventory,args.revision_job)
    return v6


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for command in ['build','audit','as-of']:
        q=sub.add_parser(command)
        for flag in ['history-job','history-derived','status-job','cases','case-report','events','event-report','cache','parent-report',
            'evidence-job','parent-v2','name-job','parent-v3','alias-job','alias-cases','parent-v4','coverage-job','inventory',
            'parent-v5','delisting-job','revision-job','parent-v6','remaining-job','facts-output','output']:
            q.add_argument('--'+flag,type=Path,required=True)
        q.add_argument('--corrections-job',type=Path)
        if command=='as-of':q.add_argument('--at',required=True);q.add_argument('--symbol')
    args=p.parse_args(argv)
    try:
        result,supplement=build(args.history_job,audited_parent(args),args.parent_v6,args.remaining_job,args.inventory)
        for path,value in [(args.facts_output,supplement),(args.output,result)]:immutable_json(path,value,args.command!='build')
        if args.command=='as-of':result=original.as_of(result,args.at,args.symbol)
        print(json.dumps({k:v for k,v in result.items() if k not in {'rows','unusedStatusReferences'}},sort_keys=True));return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'diagnostic':str(exc) if isinstance(exc,ResearchError) else 'REMAINING_OVERLAY_INPUT_INVALID'}));return 2


if __name__=='__main__':raise SystemExit(main())
