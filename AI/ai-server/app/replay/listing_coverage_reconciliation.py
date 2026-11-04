"""V5 upgrades only first-phase status matches with verified individual membership disclosures."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

from . import listing_disclosure_coverage as acquisition, listing_disclosure_facts as facts
from . import membership_reconciliation as membership, name_alias_reconciliation as aliases
from . import universe_reconciliation as original
from .dataset import canonical, digest, read_bytes, read_json
from .krx_baseline_validation import immutable_json
from .models import ResearchError, utc


def overlay(parent, supplement, inventory, parent_sha):
    if (parent.get('schemaVersion') != 'SAGOPALGO_UNIVERSE_RECONCILIATION_V4' or supplement['parentSha256'] != parent_sha
            or supplement['sourceKind'] != parent['sourceKind']):
        raise ResearchError('LISTING_OVERLAY_PARENT_MISMATCH')
    result = deepcopy(parent); rows = {r['observationId']: r for r in result['rows']}
    targets = {t['observationId']: t for t in acquisition.phase_targets(inventory)}
    if len(rows) != len(result['rows']): raise ResearchError('LISTING_OVERLAY_DUPLICATE_PARENT')
    seen = set()
    for f in supplement['facts']:
        identity = f['observationId']
        if identity not in targets or identity in seen: raise ResearchError('LISTING_OVERLAY_UNEXPECTED_FACT')
        seen.add(identity); row = rows[identity]; o = row['observation']; t = targets[identity]
        if (row['resolution'] != 'STATUS_LIST_MATCH' or o['kind'] != 'ADDED_OBSERVED' or f['kind'] != 'MEMBERSHIP_ENTRY'
                or (f['stockCode'], f['historyIsin'], f['market']) != (t['symbol'], t['isin'], t['market'])
                or f.get('sourceIsin') not in {None, t['isin']} or f['date'] != t['statusDate'] or f['statusDate'] != t['statusDate']
                or f['statusReferenceId'] != t['statusReferenceId'] or f['statusEventType'] != '신규상장'
                or not o['observedFrom'] < f['date'] <= o['observedTo']):
            raise ResearchError('LISTING_OVERLAY_IDENTITY_DATE_OR_STATUS_CONFLICT')
        row.update(previousResolution=row['resolution'], resolution='DISCLOSURE_MATCH', membershipDateConfirmedByDisclosure=True,
            exchangeMembershipDate=f['date'], exchangeMembershipDateBasis=f['dateBasis'], supplementalListingEvidenceId=digest(canonical(f)),
            individualDisclosureStatus='VERIFIED', knownAt=max([row['knownAt'], f['knownAt']], key=utc))
        row['evidence'].append(deepcopy(f))
    for review in supplement['reviews']:
        identity = review['observationId']
        if identity not in targets or identity in seen: raise ResearchError('LISTING_OVERLAY_UNEXPECTED_REVIEW')
        seen.add(identity); row = rows[identity]
        row.update(individualDisclosureStatus='REVIEW_REQUIRED', membershipDisclosureReview=deepcopy(review),
                   knownAt=max([row['knownAt'], review['knownAt']], key=utc))
    if seen != set(targets) or supplement['targets'] != len(targets): raise ResearchError('LISTING_OVERLAY_INCOMPLETE_PHASE')
    counts = Counter(r['resolution'] for r in result['rows'])
    result.update(schemaVersion='SAGOPALGO_UNIVERSE_RECONCILIATION_V5', policy='SAGOPALGO_UNIVERSE_EVIDENCE_MATCH_5',
        parentV4ReportSha256=parent_sha, listingInventorySha256=digest(canonical(inventory)), listingSupplementSha256=digest(canonical(supplement)),
        resolutionCounts=dict(counts), disclosureMatched=parent['disclosureMatched'] + len(supplement['facts']),
        membershipAwaitingIndividualDisclosure=parent['membershipAwaitingIndividualDisclosure'] - len(supplement['facts']),
        newListingTargets=len(targets), newListingVerified=len(supplement['facts']), newListingReviewRequired=len(supplement['reviews']),
        laterPhasePending=inventory['remaining'] - len(targets),
        membershipPendingByPhase={'NEW_LISTING_REVIEW': len(supplement['reviews']),
            **{k: v for k, v in inventory['categoryCounts'].items() if k != 'NEW_LISTING'}})
    return result


def build(history_job, parent, parent_path, job, inventory_path):
    immutable_json(parent_path, parent, True); parent_sha = digest(read_bytes(parent_path))
    report = acquisition.inventory(parent, parent_sha); immutable_json(inventory_path, report, True)
    plan, _, _ = acquisition.load(job)
    if (plan['parentSha256'] != parent_sha or plan['sourceKind'] != parent['sourceKind']
            or plan['inventorySha256'] != digest(read_bytes(inventory_path)) or plan['targets'] != acquisition.phase_targets(report)
            or (plan['startDate'], plan['endDate']) != (parent['startDate'], parent['endDate'])):
        raise ResearchError('LISTING_OVERLAY_PLAN_MISMATCH')
    supplement = facts.build(job, membership.contexts(history_job, parent, plan))
    return overlay(parent, supplement, report, parent_sha), supplement


def audited_parent(args):
    v3 = aliases.audited_parent(args)
    v4, _ = aliases.build(args.history_job, v3, args.parent_v3, args.alias_job, args.alias_cases)
    return v4


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command', required=True)
    for command in ['build', 'audit', 'as-of']:
        p = sub.add_parser(command)
        for flag in ['history-job','history-derived','status-job','cases','case-report','events','event-report','cache',
                     'parent-report','evidence-job','parent-v2','name-job','parent-v3','alias-job','alias-cases',
                     'parent-v4','coverage-job','inventory','facts-output','output']:
            p.add_argument('--' + flag, type=Path, required=True)
        p.add_argument('--corrections-job', type=Path)
        if command == 'as-of': p.add_argument('--at', required=True); p.add_argument('--symbol')
    args = parser.parse_args(argv)
    try:
        result, supplement = build(args.history_job, audited_parent(args), args.parent_v4, args.coverage_job, args.inventory)
        for path, value in [(args.facts_output, supplement), (args.output, result)]: immutable_json(path, value, args.command != 'build')
        if args.command == 'as-of': result = original.as_of(result, args.at, args.symbol)
        print(json.dumps({k: v for k, v in result.items() if k not in {'rows','unusedStatusReferences'}}, sort_keys=True), flush=True); return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'diagnostic': str(exc) if isinstance(exc, ResearchError) else 'LISTING_OVERLAY_INPUT_INVALID'})); return 2


if __name__ == '__main__': raise SystemExit(main())
