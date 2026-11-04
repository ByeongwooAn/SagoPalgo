"""V4 closes only the audited V3 name reviews, retaining all prior source and legal-effect limits."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

from . import name_alias_evidence as acquisition, name_alias_facts as facts, name_reconciliation as names
from . import kind_cases, universe_events, membership_reconciliation as membership, universe_reconciliation as original
from .dataset import canonical, digest, read_bytes, read_json
from .krx_baseline_validation import immutable_json
from .models import ResearchError, utc

RESOLUTIONS = {'EXCHANGE_TRADING_ALIAS_CHANGE': 'NAME_ALIAS_NOTICE_MATCH',
               'EXCHANGE_FORMAL_NAME_IDENTITY_BRIDGE': 'NAME_IDENTITY_BRIDGE_MATCH'}


def overlay(parent, supplement, parent_sha):
    if (parent.get('schemaVersion') != 'SAGOPALGO_UNIVERSE_RECONCILIATION_V3' or supplement['parentSha256'] != parent_sha
            or supplement['sourceKind'] != parent['sourceKind']):
        raise ResearchError('NAME_ALIAS_OVERLAY_PARENT_MISMATCH')
    result = deepcopy(parent)
    rows = {r['observationId']: r for r in result['rows']}
    if len(rows) != len(result['rows']): raise ResearchError('NAME_ALIAS_OVERLAY_DUPLICATE_PARENT')
    expected = {k for k, r in rows.items() if r['observation']['kind'] == 'NAME_CHANGE_OBSERVED' and r['resolution'] == 'NAME_CHANGE_NEEDS_DISCLOSURE'}
    seen = set()
    for f in supplement['facts']:
        identity = f['observationId']
        if identity not in expected or identity in seen or f['classification'] not in RESOLUTIONS:
            raise ResearchError('NAME_ALIAS_OVERLAY_UNEXPECTED_FACT')
        seen.add(identity); row = rows[identity]; o = row['observation']
        if (any((o[s]['symbol'], o[s]['isin'], o[s]['market'], o[s]['name'])
                != (f['stockCode'], f['historyIsin'], f['market'], f[s + 'Name']) for s in ['before', 'after'])
                or not o['observedFrom'] < f['date'] <= o['observedTo']):
            raise ResearchError('NAME_ALIAS_OVERLAY_IDENTITY_OR_DATE_CONFLICT')
        target = {'symbol': f['stockCode'], 'isin': f['historyIsin'], 'beforeName': o['before']['name'], 'afterName': o['after']['name'],
            'beforeMarket': o['before']['market'], 'afterMarket': o['after']['market'], 'observedFrom': o['observedFrom'], 'observedTo': o['observedTo']}
        if f['classification'] == 'EXCHANGE_TRADING_ALIAS_CHANGE': facts.alias_fact(f, target, f['instrumentContext'])
        else: facts.bridge_fact(f, target, f['instrumentContext'], row)
        row['previousNameReview'] = row.pop('nameReview')
        row.update(previousResolution=row['resolution'], resolution=RESOLUTIONS[f['classification']],
            exchangeNameDate=f['date'], exchangeNameDateBasis=f['dateBasis'], corporateLegalNameEffectiveDate=None,
            nameEvidenceId=digest(canonical(f)), knownAt=max([row['knownAt'], f['knownAt']], key=utc))
        row['evidence'].append(deepcopy(f))
    for review in supplement['reviews']:
        identity = review['observationId']
        if identity not in expected or identity in seen:
            raise ResearchError('NAME_ALIAS_OVERLAY_UNEXPECTED_REVIEW')
        seen.add(identity); row = rows[identity]
        row['aliasSupplementReview'] = deepcopy(review)
        row['knownAt'] = max([row['knownAt'], review['knownAt']], key=utc)
    if seen != expected or supplement['targets'] != len(expected):
        raise ResearchError('NAME_ALIAS_OVERLAY_INCOMPLETE_SCOPE')
    counts = Counter(r['resolution'] for r in result['rows'])
    all_matched = original.MATCHED | names.NAME_MATCHED | set(RESOLUTIONS.values())
    result.update(schemaVersion='SAGOPALGO_UNIVERSE_RECONCILIATION_V4', policy='SAGOPALGO_UNIVERSE_EVIDENCE_MATCH_4',
        parentV3ReportSha256=parent_sha, aliasSupplementReportSha256=digest(canonical(supplement)), resolutionCounts=dict(counts),
        nameDisclosureMatched=parent['nameDisclosureMatched'] + len(supplement['facts']),
        nameFormalChangeMatched=parent['nameDisclosureMatched'] + counts['NAME_IDENTITY_BRIDGE_MATCH'],
        nameTradingAliasMatched=counts['NAME_ALIAS_NOTICE_MATCH'], nameFormalIdentitiesBridged=counts['NAME_IDENTITY_BRIDGE_MATCH'],
        nameAliasRowsResolved=len(supplement['facts']), nameReviewRequired=len(supplement['reviews']),
        unresolvedObservations=sum(r['resolution'] not in all_matched for r in result['rows']))
    return result


def build(history_job, parent, parent_path, alias_job, cases_path):
    immutable_json(parent_path, parent, True)
    parent_sha = digest(read_bytes(parent_path)); raw = read_bytes(cases_path)
    scope = acquisition.Scope.model_validate(read_json(raw)); plan, _, _ = acquisition.load(alias_job)
    if (plan['parentSha256'] != parent_sha or plan['casesSha256'] != digest(raw) or plan['sourceKind'] != parent['sourceKind']
            or plan['targets'] != acquisition.targets_from(parent, scope)
            or (plan['startDate'], plan['endDate']) != (parent['startDate'], parent['endDate'])):
        raise ResearchError('NAME_ALIAS_OVERLAY_PLAN_MISMATCH')
    supplement = facts.build(alias_job, parent, facts.contexts(history_job, parent, plan))
    return overlay(parent, supplement, parent_sha), supplement


def audited_parent(args):
    cases = kind_cases.audit_report(kind_cases.load_scope(args.cases), args.cache, args.case_report)
    events = universe_events.audit_report(universe_events.load_scope(args.events), args.cache, args.event_report)
    parent, _ = membership.build(args.history_job, args.history_derived, args.status_job, cases, events,
        args.parent_report, args.evidence_job, args.corrections_job)
    result, _ = names.build(args.history_job, parent, args.parent_v2, args.name_job)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command', required=True)
    for command in ['build', 'audit', 'as-of']:
        p = sub.add_parser(command)
        for flag in ['history-job', 'history-derived', 'status-job', 'cases', 'case-report', 'events', 'event-report', 'cache',
                     'parent-report', 'evidence-job', 'parent-v2', 'name-job', 'parent-v3', 'alias-job', 'alias-cases', 'facts-output', 'output']:
            p.add_argument('--' + flag, type=Path, required=True)
        p.add_argument('--corrections-job', type=Path)
        if command == 'as-of': p.add_argument('--at', required=True); p.add_argument('--symbol')
    args = parser.parse_args(argv)
    try:
        result, supplement = build(args.history_job, audited_parent(args), args.parent_v3, args.alias_job, args.alias_cases)
        for path, value in [(args.facts_output, supplement), (args.output, result)]: immutable_json(path, value, args.command != 'build')
        if args.command == 'as-of': result = original.as_of(result, args.at, args.symbol)
        print(json.dumps({k: v for k, v in result.items() if k not in {'rows', 'unusedStatusReferences'}}, sort_keys=True), flush=True); return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'diagnostic': str(exc) if isinstance(exc, ResearchError) else 'NAME_ALIAS_OVERLAY_INPUT_INVALID'})); return 2


if __name__ == '__main__': raise SystemExit(main())
