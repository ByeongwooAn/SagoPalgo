"""Full remaining membership inventory and bounded first-phase new-listing disclosure capture."""
import argparse
from collections import Counter
from datetime import timedelta
import json
from pathlib import Path
import re
from typing import Literal
from urllib.parse import urlencode

from pydantic import Field, model_validator

from . import name_disclosures as engine
from .dataset import canonical, digest, read_bytes, read_json
from .history import day
from .krx_baseline_validation import immutable_json
from .krx_storage import atomic_json
from .models import ResearchError, StrictModel

SCHEMA = 'SAGOPALGO_NEW_LISTING_COVERAGE_PLAN_V1'


class Target(StrictModel):
    observationId: str = Field(pattern=r'^[0-9a-f]{64}$')
    kind: Literal['ADDED_OBSERVED']
    symbol: str = Field(pattern=r'^[0-9A-Z]{6}$')
    isin: str = Field(pattern=r'^[0-9A-Z]{12}$')
    market: Literal['KOSPI', 'KOSDAQ']
    observedName: str = Field(min_length=1, max_length=300)
    observedFrom: str
    observedTo: str
    statusDate: str
    statusEventType: Literal['신규상장']
    statusReferenceId: str = Field(pattern=r'^[0-9a-f]{64}$')


class Config(engine.Config):
    schemaVersion: Literal['SAGOPALGO_NEW_LISTING_COVERAGE_PLAN_V1'] = SCHEMA
    inventorySha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    targets: list[Target] = Field(min_length=1, max_length=500)
    maxRequests: int = Field(default=1400, ge=4, le=3000)

    @model_validator(mode='after')
    def bounds(self):
        if (self.sourceKind not in {'SYNTHETIC', 'PROVIDER_OBSERVATIONS'}
                or (self.lookbackDays, self.maxAttemptsPerStage, self.minIntervalSeconds) != (45, 3, 1)
                or len({t.observationId for t in self.targets}) != len(self.targets) or self.maxRequests < len(self.targets) * 4
                or any(not day(self.startDate) <= day(t.observedFrom) < day(t.statusDate) <= day(t.observedTo) <= day(self.endDate) for t in self.targets)):
            raise ValueError('invalid bounded new listing scope')
        return self


def inventory(parent, parent_sha):
    if parent.get('schemaVersion') != 'SAGOPALGO_UNIVERSE_RECONCILIATION_V4':
        raise ResearchError('LISTING_COVERAGE_PARENT_INVALID')
    ids, verified, remaining = set(), {}, []
    for row in parent['rows']:
        o = row['observation']; identity = row['observationId']
        if identity != digest(canonical(o)) or identity in ids:
            raise ResearchError('LISTING_COVERAGE_PARENT_INVALID')
        ids.add(identity)
        if o['kind'] not in {'ADDED_OBSERVED', 'REMOVED_OBSERVED'}: continue
        issue = o['after'] or o['before']
        if row['resolution'] == 'DISCLOSURE_MATCH' and row['membershipDateConfirmedByDisclosure']:
            key = (o['kind'], issue['symbol'], issue['isin'], issue['market'], row['exchangeMembershipDate'])
            verified.setdefault(key, []).append(identity)
        if row['resolution'] != 'STATUS_LIST_MATCH': continue
        channel = 'LISTING' if o['kind'] == 'ADDED_OBSERVED' else 'DELISTING'
        refs = [e for e in row['evidence'] if e.get('kind') == channel]
        if (len(refs) != 1 or refs[0]['market'] != issue['market'] or not o['observedFrom'] < refs[0]['date'] <= o['observedTo']
                or issue['classification'] != 'COMMON_SHARE' or issue['isin'] != o['isin']):
            raise ResearchError('LISTING_COVERAGE_STATUS_SCOPE_CONFLICT')
        ref = refs[0]
        category = 'DELISTING' if channel == 'DELISTING' else {'신규상장': 'NEW_LISTING', '재상장': 'RELISTING', '이전상장': 'INBOUND_TRANSFER'}.get(ref['eventType'])
        if not category: raise ResearchError('LISTING_COVERAGE_EVENT_REVIEW_REQUIRED')
        remaining.append({'observationId': identity, 'kind': o['kind'], 'symbol': issue['symbol'], 'isin': issue['isin'],
            'market': issue['market'], 'observedName': issue['name'], 'observedFrom': o['observedFrom'], 'observedTo': o['observedTo'],
            'statusDate': ref['date'], 'statusEventType': ref['eventType'], 'statusReferenceId': ref['referenceId'], 'category': category})
    for target in remaining:
        key = (target['kind'], target['symbol'], target['isin'], target['market'], target['statusDate'])
        target['auditedReusableObservationIds'] = verified.get(key, [])
    if not remaining: raise ResearchError('LISTING_COVERAGE_EMPTY_SCOPE')
    return {'schemaVersion': 'SAGOPALGO_MEMBERSHIP_DISCLOSURE_INVENTORY_V1', 'parentSha256': parent_sha,
        'sourceKind': parent['sourceKind'], 'startDate': parent['startDate'], 'endDate': parent['endDate'], 'targets': remaining,
        'remaining': len(remaining), 'categoryCounts': dict(Counter(t['category'] for t in remaining)),
        'marketCounts': dict(Counter(t['market'] for t in remaining)),
        'auditedFactReuseAvailable': sum(bool(t['auditedReusableObservationIds']) for t in remaining),
        'reuseBasis': 'IDENTICAL_KIND_FULL_CODE_ISIN_MARKET_AND_EXCHANGE_DATE_IN_AUDITED_PARENT_FACT',
        'firstPhase': 'NEW_LISTING', 'usableForTraining': False, 'usableForTrading': False}


def phase_targets(report):
    return [{k: v for k, v in t.items() if k not in {'category', 'auditedReusableObservationIds'}}
            for t in report['targets'] if t['category'] == 'NEW_LISTING']


def prepare(folder, parent_path, inventory_path, max_requests=1400):
    raw = read_bytes(parent_path); parent = read_json(raw)
    report = inventory(parent, digest(raw))
    payload = Config(parentSha256=digest(raw), inventorySha256=digest(canonical(report)), sourceKind=parent['sourceKind'],
        startDate=parent['startDate'], endDate=parent['endDate'], targets=phase_targets(report), maxRequests=max_requests).model_dump(mode='json')
    immutable_json(inventory_path, report)
    plan = {**payload, 'planId': digest(canonical(payload))}
    folder.mkdir(parents=True, exist_ok=False); (folder / 'raw').mkdir()
    atomic_json(folder / 'plan.json', plan); atomic_json(folder / 'journal.json', {'planId': plan['planId'], 'attempts': []})
    return plan


def candidates(raw):
    root = engine.public.html(raw)
    info = [v for v in root.walk('div') if v.attrs.get('class') == 'info type-00']
    counts = re.findall(r'전체\s*([0-9,]+)\s*건\s*:\s*([0-9]+)\s*/\s*([0-9]+)', info[0].text()) if len(info) == 1 else []
    if len(counts) != 1: raise ResearchError('LISTING_COVERAGE_SEARCH_LAYOUT')
    total, page, pages = [int(v.replace(',', '')) for v in counts[0]]
    links = [v for v in root.walk('a') if v.attrs.get('href') == '#viewer']
    if total > 100 or page != 1 or pages not in ({0, 1} if total == 0 else {1}) or len(links) != total:
        raise ResearchError('LISTING_COVERAGE_SEARCH_INCOMPLETE')
    found = []
    for link in links:
        title = re.sub(r'\s+', '', link.text()); corrected = title.startswith('[정정]'); core = title.removeprefix('[정정]')
        if re.match(r'^신규상장(?:\(|$)', core): priority = 0
        elif re.match(r'^주권등신규상장.*기준가격.*안내', core): priority = 1
        else: continue
        receipt = re.fullmatch(r"openDisclsViewer\('([0-9]{14})',''\);?", link.attrs.get('onclick', ''))
        if not receipt: raise ResearchError('LISTING_COVERAGE_SEARCH_LINK_INVALID')
        found.append({'receipt': receipt[1], 'title': title, 'priority': priority, 'corrected': corrected})
    if not found: raise ResearchError('LISTING_COVERAGE_NO_REVIEWED_TITLE')
    result = sorted([v for v in found if v['priority'] == min(r['priority'] for r in found)], key=lambda v: v['receipt'])
    if not 1 <= len(result) <= 4 or len({v['receipt'] for v in result}) != len(result):
        raise ResearchError('LISTING_COVERAGE_CANDIDATE_REVIEW')
    return result


def viewer(raw, target, candidate):
    if not candidate['corrected']:
        try:
            result = engine.public.viewer_result(raw, target)
            return {**result, 'documents': [result['document']]}
        except ResearchError as exc:
            if str(exc) != 'MEMBERSHIP_EVIDENCE_CORRECTION_REVIEW': raise
    return engine.viewer(raw, target, {**candidate, 'viewerTitle': '신규상장'})


def requests_for(t, completed):
    params = {'method': 'searchDetailsSub', 'forward': 'details_sub', 'currentPageSize': '100', 'pageIndex': '1',
        'orderMode': '0', 'orderStat': 'D', 'fromDate': (day(t['observedFrom']) - timedelta(days=45)).isoformat(),
        'toDate': t['observedTo'], 'repIsuSrtCd': 'A' + t['symbol'], 'searchCodeType': 'number', 'searchCorpName': t['symbol'],
        'reportNm': '신규상장', 'reportCd': '', 'allRepIsuSrtCd': '', 'marketType': ''}
    yield 'SEARCH', {'url': engine.public.BASE + '/disclosure/details.do', 'method': 'POST', 'parameters': params}
    for index, candidate in enumerate(candidates(completed['SEARCH'])):
        label = 'V' + str(index)
        yield label + '_VIEWER', {'url': engine.public.BASE + '/common/disclsviewer.do?' + urlencode({'acptno': candidate['receipt'], 'method': 'search'}), 'method': 'GET', 'parameters': None}
        doc = viewer(completed[label + '_VIEWER'], t, candidate)['document']
        yield label + '_PATH', {'url': engine.public.BASE + '/common/disclsviewer.do', 'method': 'POST', 'parameters': {'method': 'searchContents', 'docNo': doc}}
        url = engine.public.path_result(completed[label + '_PATH'], candidate['receipt'], doc)
        yield label + '_BODY', {'url': url, 'method': 'GET', 'parameters': None}


def load(folder): return engine.load(folder, Config, requests_for)
def inspect(folder, target, latest): return engine.inspect(folder, target, latest, request_builder=requests_for)
def capture_summary(value):
    result = {k: v for k, v in value.items() if k != 'nameChangeConfirmed'}
    return {**result, 'membershipConfirmed': False, 'phase': 'NEW_LISTING'}
def collect(folder, transport, max_new_requests, retry_failed=False, **kwargs):
    return capture_summary(engine.collect(folder, transport, max_new_requests, retry_failed, config_type=Config, request_builder=requests_for, **kwargs))
def summary(folder): return capture_summary(engine.summary(folder, Config, requests_for))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command', required=True)
    for command in ['plan', 'collect', 'audit']:
        p = sub.add_parser(command); p.add_argument('--job', type=Path, required=True)
        if command == 'plan':
            p.add_argument('--parent', type=Path, required=True); p.add_argument('--inventory', type=Path, required=True); p.add_argument('--max-requests', type=int, default=1400)
        if command == 'collect': p.add_argument('--max-new-requests', type=int, required=True); p.add_argument('--retry-failed', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = prepare(args.job, args.parent, args.inventory, args.max_requests) if args.command == 'plan' else collect(args.job, engine.public.Transport(), args.max_new_requests, args.retry_failed) if args.command == 'collect' else summary(args.job)
        print(json.dumps({k: v for k, v in result.items() if k != 'targets'}, sort_keys=True), flush=True); return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'diagnostic': str(exc) if isinstance(exc, ResearchError) else 'LISTING_COVERAGE_INPUT_INVALID'})); return 2


if __name__ == '__main__': raise SystemExit(main())
