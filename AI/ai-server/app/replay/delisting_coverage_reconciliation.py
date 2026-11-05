"""V6 upgrades the exact delisting phase while retaining the audited V1–V5 evidence chain."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

from . import delisting_disclosure_coverage as acquisition, delisting_disclosure_facts as facts
from . import delisting_revision_facts as revisions, listing_coverage_reconciliation as listings
from . import membership_reconciliation as membership, universe_reconciliation as original
from .dataset import canonical, digest, read_bytes, read_json
from .krx_baseline_validation import immutable_json
from .models import ResearchError, utc


def overlay(parent, supplement, inventory, parent_sha):
    if (parent.get('schemaVersion') != 'SAGOPALGO_UNIVERSE_RECONCILIATION_V5'
            or supplement['parentSha256'] != parent_sha or supplement['sourceKind'] != parent['sourceKind']):
        raise ResearchError('DELISTING_OVERLAY_PARENT_MISMATCH')
    targets = {t['observationId']: t for t in acquisition.targets_from(parent, inventory)}
    result = deepcopy(parent); rows = {r['observationId']: r for r in result['rows']}; seen = set()
    for f in supplement['facts']:
        identity = f['observationId']
        if identity not in targets or identity in seen: raise ResearchError('DELISTING_OVERLAY_UNEXPECTED_FACT')
        seen.add(identity); row = rows[identity]; o = row['observation']; t = targets[identity]
        if (row['resolution'] != 'STATUS_LIST_MATCH' or o['kind'] != 'REMOVED_OBSERVED' or f['kind'] != 'MEMBERSHIP_EXIT'
                or (f['stockCode'], f['historyIsin'], f['market']) != (t['symbol'], t['isin'], t['market'])
                or f.get('sourceIsin') not in {None, t['isin']} or f['date'] != t['statusDate'] or f['statusDate'] != t['statusDate']
                or (f['statusReferenceId'], f['statusEventType']) != (t['statusReferenceId'], t['statusEventType'])
                or f['dateBasis'] != 'EXCHANGE_DELISTING_DATE' or not o['observedFrom'] < f['date'] <= o['observedTo']):
            raise ResearchError('DELISTING_OVERLAY_IDENTITY_DATE_OR_STATUS_CONFLICT')
        row.update(previousResolution=row['resolution'], resolution='DISCLOSURE_MATCH', membershipDateConfirmedByDisclosure=True,
            exchangeMembershipDate=f['date'], exchangeMembershipDateBasis=f['dateBasis'], supplementalDelistingEvidenceId=digest(canonical(f)),
            individualDisclosureStatus='VERIFIED', knownAt=max([row['knownAt'], f['knownAt']], key=utc))
        row['evidence'].append(deepcopy(f))
    for review in supplement['reviews']:
        identity = review['observationId']
        if identity not in targets or identity in seen: raise ResearchError('DELISTING_OVERLAY_UNEXPECTED_REVIEW')
        seen.add(identity); row = rows[identity]
        row.update(individualDisclosureStatus='REVIEW_REQUIRED', membershipDisclosureReview=deepcopy(review),
                   knownAt=max([row['knownAt'], review['knownAt']], key=utc))
    if seen != set(targets) or supplement['targets'] != len(targets): raise ResearchError('DELISTING_OVERLAY_INCOMPLETE_PHASE')
    counts = Counter(r['resolution'] for r in result['rows'])
    result.update(schemaVersion='SAGOPALGO_UNIVERSE_RECONCILIATION_V6', policy='SAGOPALGO_UNIVERSE_EVIDENCE_MATCH_6',
        parentV5ReportSha256=parent_sha, delistingSupplementSha256=digest(canonical(supplement)), resolutionCounts=dict(counts),
        disclosureMatched=parent['disclosureMatched'] + len(supplement['facts']),
        membershipAwaitingIndividualDisclosure=parent['membershipAwaitingIndividualDisclosure'] - len(supplement['facts']),
        delistingTargets=len(targets), delistingVerified=len(supplement['facts']), delistingReviewRequired=len(supplement['reviews']),
        laterPhasePending=inventory['remaining'] - inventory['categoryCounts'].get('NEW_LISTING', 0) - len(targets),
        membershipPendingByPhase={'NEW_LISTING_REVIEW': parent.get('newListingReviewRequired', 0),
            'DELISTING_REVIEW': len(supplement['reviews']),
            **{k: v for k, v in inventory['categoryCounts'].items() if k not in {'NEW_LISTING', 'DELISTING'}}})
    return result


def build(history_job, parent, parent_path, job, inventory_path, revision_job):
    immutable_json(parent_path, parent, True); parent_sha = digest(read_bytes(parent_path))
    inventory = read_json(read_bytes(inventory_path)); plan, _, _ = acquisition.load(job)
    if (parent.get('listingInventorySha256') != digest(read_bytes(inventory_path))
            or plan['parentSha256'] != parent_sha or plan['inventorySha256'] != digest(read_bytes(inventory_path))
            or plan['sourceKind'] != parent['sourceKind'] or plan['targets'] != acquisition.targets_from(parent, inventory)
            or (plan['startDate'], plan['endDate']) != (parent['startDate'], parent['endDate'])):
        raise ResearchError('DELISTING_OVERLAY_PLAN_MISMATCH')
    contexts = membership.contexts(history_job, parent, plan)
    supplement = revisions.build(revision_job, job, contexts, facts.build(job, contexts))
    return overlay(parent, supplement, inventory, parent_sha), supplement


def audited_parent(args):
    v4 = listings.audited_parent(args)
    v5, _ = listings.build(args.history_job, v4, args.parent_v4, args.coverage_job, args.inventory)
    return v5


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command', required=True)
    for command in ['build', 'audit', 'as-of']:
        p = sub.add_parser(command)
        for flag in ['history-job','history-derived','status-job','cases','case-report','events','event-report','cache',
                     'parent-report','evidence-job','parent-v2','name-job','parent-v3','alias-job','alias-cases',
                     'parent-v4','coverage-job','inventory','parent-v5','delisting-job','revision-job','facts-output','output']:
            p.add_argument('--' + flag, type=Path, required=True)
        p.add_argument('--corrections-job', type=Path)
        if command == 'as-of': p.add_argument('--at', required=True); p.add_argument('--symbol')
    args = parser.parse_args(argv)
    try:
        result, supplement = build(args.history_job, audited_parent(args), args.parent_v5, args.delisting_job, args.inventory, args.revision_job)
        for path, value in [(args.facts_output, supplement), (args.output, result)]: immutable_json(path, value, args.command != 'build')
        if args.command == 'as-of': result = original.as_of(result, args.at, args.symbol)
        print(json.dumps({k: v for k, v in result.items() if k not in {'rows','unusedStatusReferences'}}, sort_keys=True), flush=True); return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'diagnostic': str(exc) if isinstance(exc, ResearchError) else 'DELISTING_OVERLAY_INPUT_INVALID'})); return 2


if __name__ == '__main__': raise SystemExit(main())
