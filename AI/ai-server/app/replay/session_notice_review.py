"""Hash-bound decisions for a scoped notice inventory, without promoting ordinary sessions."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import Field, model_validator

from . import session_notice_inventory as inventory, session_evidence, market_calendar_evidence as market
from .dataset import canonical, digest, read_bytes, read_json
from .krx_baseline_validation import immutable_json
from .models import StrictModel, ResearchError, utc


class Decision(StrictModel):
    market: Literal['KOSPI', 'KOSDAQ']
    document: str = Field(pattern=r'^[0-9]{14}$')
    bodySha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    classification: Literal['REGULAR_SESSION_CHANGE', 'MARKET_MAKING_POLICY', 'SHORT_SELLING_POLICY',
                            'LOCKUP_POLICY', 'ISSUER_SPECIFIC_HALT']
    reason: str = Field(min_length=10, max_length=300)
    subjectIssuer: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode='after')
    def valid(self):
        if (self.classification == 'ISSUER_SPECIFIC_HALT') != (self.subjectIssuer is not None):
            raise ValueError('issuer-specific halt requires its reviewed subject')
        return self


class Review(StrictModel):
    schemaVersion: Literal['SAGOPALGO_SESSION_NOTICE_REVIEW_SCOPE_V1']
    inventorySha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    reviewedAt: str
    decisions: list[Decision] = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def valid(self):
        utc(self.reviewedAt)
        if len({(d.market, d.document) for d in self.decisions}) != len(self.decisions):
            raise ValueError('duplicate document decision')
        return self


def scheduled_session(row, version, raw):
    if version['url'].rsplit('/', 1)[1] != inventory.FORMS[row['market']] + '.htm':
        raise ResearchError('SESSION_REVIEW_SCHEDULE_FORM_MISMATCH')
    value = market.text(raw)
    if '대학수학능력시험일' in value:
        pack = session_evidence.notice_reference(raw, version['url'], version['knownAt'])
        result = pack.model_dump(mode='json')['sessions'][0]
        # Verify both before/after regular rows, not just a competitive block closing time.
        before = re.split(r'나\.\s*변경\s*후', value)[0]
        if not re.search(r'정규시장\s*:\s*09:00\s*~\s*15:30', before):
            raise ResearchError('SESSION_REVIEW_BEFORE_TIME_MISMATCH')
        if not result['openAt'].endswith('01:00:00Z') or not result['closeAt'].endswith('07:30:00Z'):
            raise ResearchError('SESSION_REVIEW_EXAM_TIME_MISMATCH')
    elif '연말 시장운영 일정' in value and '연초 개장일' in value:
        found = re.findall(r'2\.\s*([0-9]{4})년 연초 개장일\s*\(([0-9]{1,2})\.([0-9]{1,2})\s*,', value)
        if len(found) != 1:
            raise ResearchError('SESSION_REVIEW_NEWYEAR_DATE_AMBIGUOUS')
        stamp = '%04d-%02d-%02d' % tuple(map(int, found[0]))
        source = market.Source(sourceId='inventory-year-open', role='KIND_SESSION', url=version['url'], markets=[row['market']], expectedDate=stamp)
        pack = market.kind_newyear(source, {'bodySha256': version['bodySha256'], 'capturedAt': version['knownAt']}, raw)
        result = pack.model_dump(mode='json')['sessions'][0]
    else:
        raise ResearchError('SESSION_REVIEW_SCHEDULE_LAYOUT_UNSUPPORTED')
    if result['market'] != row['market']:
        raise ResearchError('SESSION_REVIEW_SCHEDULE_MARKET_MISMATCH')
    return result


def build(job, parent_path, inventory_path, review_path):
    report = inventory.inventory(job, parent_path)
    immutable_json(inventory_path, report, True)
    review = Review.model_validate(read_json(read_bytes(review_path)))
    if review.inventorySha256 != digest(read_bytes(inventory_path)):
        raise ResearchError('SESSION_REVIEW_INVENTORY_HASH_MISMATCH')
    if utc(review.reviewedAt) < utc(report['knownAt']):
        raise ResearchError('SESSION_REVIEW_KNOWLEDGE_BEFORE_CAPTURE')
    decisions = {(d.market, d.document, d.bodySha256): d for d in review.decisions}
    observed = {(r['market'], v['document'], v['bodySha256']) for r in report['rows'] for v in r['versions']}
    if set(decisions) != observed:
        raise ResearchError('SESSION_REVIEW_DECISION_COVERAGE_MISMATCH')
    parent = read_json(read_bytes(parent_path)); reviewed = {}; sessions = {}; outside = []; links = []
    for row in report['rows']:
        if len(row['versions']) > 1:
            links.append({'market': row['market'], 'receipt': row['receipt'], 'versions': deepcopy(row['versions']),
                          'basis': 'VIEWER_OPTIONS_ONLY', 'fullCorrectionLineageConfirmed': False})
        for version in row['versions']:
            k = (row['market'], version['document'], version['bodySha256'])
            if k in reviewed: continue
            decision = decisions[k]; raw = read_bytes(job / version['rawFile']); value = market.text(raw)
            if digest(raw) != decision.bodySha256:
                raise ResearchError('SESSION_REVIEW_RAW_HASH_MISMATCH')
            if version['url'].rsplit('/', 1)[1] != inventory.FORMS[row['market']] + '.htm':
                raise ResearchError('SESSION_REVIEW_FORM_REQUIRES_ADDITIONAL_REVIEW')
            classification = decision.classification
            if classification == 'REGULAR_SESSION_CHANGE':
                session = scheduled_session(row, version, raw)
                session.update(sourceKnownAt=version['knownAt'], knownAt=review.reviewedAt, document=version['document'])
                if not report['startDate'] <= session['businessDate'] <= report['endDate']:
                    outside.append(session)
                else:
                    prior = [s for s in parent['referencePacks'][row['market']]['sessions'] if s['businessDate'] == session['businessDate']]
                    dates = [d for d in parent['referencePacks'][row['market']]['calendar'] if d['businessDate'] == session['businessDate']]
                    if len(dates) != 1 or not dates[0]['openDay']:
                        raise ResearchError('SESSION_REVIEW_CLOSED_OR_UNKNOWN_DAY')
                    if len(prior) != 1 or any(utc(prior[0][t]) != utc(session[t]) for t in ['openAt', 'closeAt']):
                        raise ResearchError('SESSION_REVIEW_EXISTING_SESSION_CONFLICT')
                    session['corroboratesExistingSession'] = True
                    session_key = (session['market'], session['businessDate'])
                    if session_key in sessions:
                        raise ResearchError('SESSION_REVIEW_MULTIPLE_SESSION_VERSIONS')
                    sessions[session_key] = session
            else:
                required = {'MARKET_MAKING_POLICY': ['시장조성', '계약'], 'SHORT_SELLING_POLICY': ['공매도'],
                            'LOCKUP_POLICY': ['의무보유'], 'ISSUER_SPECIFIC_HALT': [decision.subjectIssuer]}[classification]
                halt_supported = classification != 'ISSUER_SPECIFIC_HALT' or ('매매거래정지' in value or '종목의 거래' in value and '재개' in value)
                if not all(term in value for term in required) or not halt_supported or re.search(r'정규시장\s*:\s*[0-9]{2}:[0-9]{2}', value):
                    raise ResearchError('SESSION_REVIEW_NON_SESSION_DECISION_CONFLICT')
            reviewed[k] = {**decision.model_dump(), 'url': version['url'], 'sourceKnownAt': version['knownAt'], 'knownAt': review.reviewedAt}
    expected_dates = {(p['market'], date) for p in parent['temporaryChangeReviewPlan'] for date in p['knownExceptionDates']}
    if not expected_dates <= set(sessions):
        raise ResearchError('SESSION_REVIEW_KNOWN_EXCEPTION_MISSING')
    partitions = []
    for p in parent['temporaryChangeReviewPlan']:
        matching = sorted(s['businessDate'] for s in sessions.values() if s['market'] == p['market'] and p['startDate'] <= s['businessDate'] <= p['endDate'])
        partitions.append({**deepcopy(p), 'status': 'SCOPED_INVENTORY_REVIEWED', 'scopedPaginationConfirmed': True,
            'scopedBodyReviewConfirmed': True, 'corroboratedExceptionDates': matching,
            'inventoryCompletenessConfirmed': False, 'correctionLineageConfirmed': False})
    counts = dict(Counter(v['classification'] for v in reviewed.values()))
    return {'schemaVersion': 'SAGOPALGO_SESSION_EXCEPTION_REVIEW_V1', 'inventorySha256': digest(read_bytes(inventory_path)),
        'reviewScopeSha256': digest(read_bytes(review_path)), 'parentSha256': report['parentSha256'],
        'startDate': report['startDate'], 'endDate': report['endDate'], 'knownAt': review.reviewedAt,
        'sourceKind': report['sourceKind'], 'inventoryScope': report['inventoryScope'], 'uniqueListRows': len(report['rows']),
        'reviewedNotices': report['bodyReviewRequired'], 'reviewedUniqueBodies': len(reviewed),
        'versionReferences': sum(len(r['versions']) for r in report['rows']), 'classificationCounts': counts,
        'reviewedBodies': list(reviewed.values()), 'sessionCorroborations': list(sessions.values()), 'outsideScopeSessions': outside,
        'viewerVersionLinks': links, 'partitions': partitions, 'scopedInventoryReviewComplete': True,
        'fullTemporaryChangeInventoryComplete': False, 'fullCorrectionLineageComplete': False,
        'additionalFormAndPublicationBoundaryReviewRequired': True, 'ordinaryCandidatesNotPromoted':
            sum(len(m['candidates']) for m in parent['markets'].values()),
        'referencePacks': deepcopy(parent['referencePacks']), 'allHistoricalSessionsComplete': False,
        'usableForTraining': False, 'usableForStrategyValidation': False, 'usableForTrading': False}


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('command', choices=['build', 'audit', 'as-of'])
    p.add_argument('--job', type=Path); p.add_argument('--parent', type=Path); p.add_argument('--inventory', type=Path)
    p.add_argument('--review', type=Path); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--at'); p.add_argument('--market', choices=['KOSPI', 'KOSDAQ']); a = p.parse_args()
    try:
        if a.command == 'as-of':
            if not a.at or not a.market: p.error('--at --market required')
            report = read_json(read_bytes(a.output)); cutoff = utc(a.at)
            result = {'market': a.market, 'sessionCorroborations': [s for s in report['sessionCorroborations'] if s['market'] == a.market and utc(s['knownAt']) <= cutoff],
                'allHistoricalSessionsComplete': False}
        else:
            if not all([a.job, a.parent, a.inventory, a.review]): p.error('--job --parent --inventory --review required')
            report = build(a.job, a.parent, a.inventory, a.review); immutable_json(a.output, report, a.command == 'audit')
            result = {'status': 'SCOPED_REVIEW_COMPLETE_FULL_SESSION_COVERAGE_PENDING', 'reviewedUniqueBodies': report['reviewedUniqueBodies'],
                'corroboratedMarketDates': len(report['sessionCorroborations']), 'outsideScopeSessions': len(report['outsideScopeSessions']),
                'sha256': digest(read_bytes(a.output)), 'allHistoricalSessionsComplete': False}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except (ResearchError, ValueError, KeyError, OSError) as exc:
        print(json.dumps({'error': str(exc) if isinstance(exc, ResearchError) else 'SESSION_REVIEW_INPUT_INVALID'})); return 2
    return 0


if __name__ == '__main__': raise SystemExit(main())
