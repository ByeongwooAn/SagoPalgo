"""Pagination, filter boundaries, immutable resumption and inherited HTTP accounting."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.replay import session_notice_inventory as n, session_notice_review as review
from app.replay.dataset import canonical, digest
from app.replay.models import ResearchError

RECEIPT = '20241217000106'
DOCUMENT = '20241216000001'
URL = 'https://kind.krx.co.kr/external/2024/12/17/000106/' + DOCUMENT + '/99303.htm'
TITLE = '기타시장안내(2024년 연말 시장운영 일정 및 2025년 연초 개장일 매매거래시간 안내)'


def parent_file(tmp_path):
    partitions = [{'market': m, 'startDate': max('2023-11-01', f'{y}-01-01'), 'endDate': min('2026-11-02', f'{y}-12-31'),
        'status': 'PENDING', 'knownExceptionDates': ['2025-01-02'] if (m, y) == ('KOSPI', 2025) else [],
        'ordinaryCandidateCount': 1, 'inventoryCompletenessConfirmed': False, 'paginationCoverageConfirmed': False,
        'correctionLineageConfirmed': False, 'intradayHaltIsSeparate': True} for m in ['KOSPI', 'KOSDAQ'] for y in range(2023, 2027)]
    p = {'schemaVersion': 'SAGOPALGO_SESSION_RULE_REPORT_V2', 'allOrdinaryRuleChainsConfirmed': True,
        'startDate': '2023-11-01', 'endDate': '2026-11-02', 'knownAt': '2026-11-01T00:00:00Z',
        'temporaryChangeReviewPlan': partitions, 'markets': {m: {'candidates': [{}]} for m in ['KOSPI', 'KOSDAQ']},
        'referencePacks': {'KOSPI': {'calendar': [{'businessDate': '2025-01-02', 'openDay': True}], 'sessions': [{
            'market': 'KOSPI', 'businessDate': '2025-01-02', 'openAt': '2025-01-02T10:00:00+09:00',
            'closeAt': '2025-01-02T15:30:00+09:00', 'knownAt': '2026-11-01T00:00:00Z'}], 'coverage': []},
            'KOSDAQ': {'calendar': [], 'sessions': [], 'coverage': []}}}
    path = tmp_path / 'parent.json'; path.write_bytes(canonical(p)); return path


def row(rank=1, receipt=RECEIPT, stamp='2024-12-17 10:40', issuer='', title=TITLE, submitter='유가증권시장본부', decorative=None):
    company = "<img alt='유가증권'><a onclick=\"companysummary_open('12345'); return false;\">" + issuer + '</a>' if issuer else ''
    decoration = " title='" + decorative + "'" if decorative else ''
    return (f'<tr><td>{rank}</td><td>{stamp}</td><td>{company}</td><td><a href="#viewer" '
        f'onclick="openDisclsViewer(\'{receipt}\',\'\')"{decoration}>{title}</a></td><td>{submitter}</td><td></td></tr>')


def page(rows='', total=0, current=1, pages=1):
    empty = '<tr><td>조회된 내용이 없습니다</td></tr>' if total == 0 else ''
    return (f'<table><tbody>{rows}{empty}</tbody></table><div class="info type-00">전체 {total}건 : {current}/{pages}</div>').encode()


def newyear_body(market='유가증권시장', opened='10:00'):
    return (f'<html><body>기타시장안내 2024년 연말 시장운영 일정 및 2025년 연초 개장일 '
        f'연말 휴장일(결제일에서도 제외) : 2024.12.31 '
        f'2. 2025년 연초 개장일(1.2, 목) 정규장은 개장시각만 1시간 연기 : {opened}~15:30 '
        f'3. 근거규정 {market}업무규정 제4조, 제5조</body></html>').encode()


class Client:
    source_kind = 'SYNTHETIC'
    def __init__(self, fail_stage=None): self.calls = []; self.fail_stage = fail_stage; self.raw = newyear_body()
    def fetch(self, spec):
        self.calls.append(deepcopy(spec)); url = spec['url']; params = spec['parameters']
        if url.endswith('/disclosure/details.do'):
            stage = 'LIST'
            raw = page(row(), 1) if params['marketType'] == '1' and params['fromDate'] == '2024-01-01' else page()
        elif spec['method'] == 'GET' and '/common/' in url:
            stage = 'VIEWER'; raw = (f'<select id="mainDoc"><option value="{DOCUMENT}|N">2024.12.17 기타시장안내</option></select>').encode()
        elif spec['method'] == 'POST':
            stage = 'PATH'; raw = (f"parent.setPath('','{URL}','','01','01');").encode()
        else: stage = 'BODY'; raw = self.raw
        if stage == self.fail_stage: raise ResearchError('TEST_PROVIDER_FAILED')
        return raw


def prepared(tmp_path, budget=64, collect=True):
    parent = parent_file(tmp_path); job = tmp_path / 'job'; client = Client()
    n.prepare(job, parent, '2026-11-05', budget, source_kind='SYNTHETIC')
    if collect: n.collect(job, client, budget, sleep=lambda _: None)
    return parent, job, client


def fixture_review(tmp_path, parent, job):
    inv = n.inventory(job, parent); path = tmp_path / 'inventory.json'; path.write_bytes(canonical(inv))
    v = next(r['versions'][0] for r in inv['rows'] if r['versions'])
    d = {'schemaVersion': 'SAGOPALGO_SESSION_NOTICE_REVIEW_SCOPE_V1', 'inventorySha256': digest(path.read_bytes()),
        'reviewedAt': n.now(), 'decisions': [{'market': 'KOSPI', 'document': v['document'], 'bodySha256': v['bodySha256'],
            'classification': 'REGULAR_SESSION_CHANGE', 'reason': '원문의 적용일과 정규장 시각을 확인해 기존 세션과 대조한다.'}]}
    review_path = tmp_path / 'review.json'; review_path.write_bytes(canonical(d))
    return path, review_path


def test_paginated_query_collects_all_pages_and_rejects_wrong_ranks():
    q = {'kind': 'FORM', 'market': 'KOSPI', 'fromDate': '2024-01-01', 'toDate': '2024-12-31'}
    rows = ''.join(row(rank=i, receipt=f'20241217{i:06d}') for i in range(101, 1, -1))
    assert len(n.page_rows(page(rows, 101, 1, 2), q, 1)['rows']) == 100
    assert n.page_rows(page(row(), 101, 2, 2), q, 2)['rows'][0]['rank'] == 1
    with pytest.raises(ResearchError): n.page_rows(page(row(rank=2), 101, 2, 2), q, 2)
    with pytest.raises(ResearchError): n.page_rows(page(row(), 101, 1, 1), q, 1)


@pytest.mark.parametrize('variant', ['date', 'receipt', 'submitter', 'title', 'duplicate', 'issuer_link'])
def test_invalid_list_rows_are_not_silently_skipped(variant):
    q = {'kind': 'FORM', 'market': 'KOSPI', 'fromDate': '2024-01-01', 'toDate': '2024-12-31'}
    value = row()
    if variant == 'date': value = row(stamp='2025-01-01 10:40')
    if variant == 'receipt': value = row(receipt='20241216000106')
    if variant == 'submitter': value = row(submitter='코스닥시장본부')
    if variant == 'title': value = row(title='ETF기타시장안내')
    if variant == 'duplicate': value += row()
    if variant == 'issuer_link': value = row(issuer='기업').replace("companysummary_open('12345')", "companysummary_open('invalid')")
    with pytest.raises(ResearchError): n.page_rows(page(value, 1), q, 1)


def test_old_disclosure_current_market_icon_is_retained_without_overriding_query_market():
    q = {'kind': 'FORM', 'market': 'KOSDAQ', 'fromDate': '2024-01-01', 'toDate': '2024-12-31'}
    value = row(issuer='이전상장 회사', title='기타시장안내(상장 관련)', submitter='코스닥시장본부')
    r = n.page_rows(page(value, 1), q, 1)['rows'][0]
    assert r['market'] == 'KOSDAQ' and r['issuerDisplayMarket'] == '유가증권'
    assert not r['requiresBodyReview'] and r['issuerKey'] == '12345'


def test_broken_decorative_title_is_ignored_but_duplicate_link_identity_is_rejected():
    q = {'kind': 'FORM', 'market': 'KOSPI', 'fromDate': '2024-01-01', 'toDate': '2024-12-31'}
    value = row(decorative="'22년 감사의견 관련 '23년 감사의견 안내")
    assert n.page_rows(page(value, 1), q, 1)['rows'][0]['title'] == TITLE
    with pytest.raises(ResearchError):
        n.page_rows(page(value.replace('href="#viewer"', 'href="#viewer" href="#viewer"'), 1), q, 1)


def test_query_does_not_select_latest_only_and_has_independent_title_control(tmp_path):
    parent, job, _ = prepared(tmp_path, collect=False); plan, *_ = n.load(job)
    assert len(plan['queries']) == 16
    for q in plan['queries']:
        params = n.query_spec(q, 1)['parameters']
        assert 'lastReport' not in params and not params['repIsuSrtCd']
        assert params['reportCd'] == (n.FORMS[q['market']] if q['kind'] == 'FORM' else '')
    assert min(q['fromDate'] for q in plan['queries']) == '2023-01-01'
    assert max(q['toDate'] for q in plan['queries']) == '2026-11-05'


def test_successful_capture_reuses_shared_body_and_offline_cache(tmp_path):
    parent, job, client = prepared(tmp_path); count = len(client.calls)
    assert count == 19 and n.status(job)['status'] == 'CAPTURED'
    with patch('socket.socket.connect', side_effect=AssertionError('offline')):
        report = n.inventory(job, parent); n.collect(job, client, 0)
    assert len(client.calls) == count
    assert len(report['rows']) == 1 and len(report['rows'][0]['queryIds']) == 2
    assert report['bodyReviewRequired'] == 1 and not report['fullTemporaryChangeInventoryComplete']
    assert report['referencePacks'] == json.loads(parent.read_bytes())['referencePacks']


def test_budget_extension_preserves_old_job_and_counts_inherited_requests(tmp_path):
    parent, job, client = prepared(tmp_path, budget=16); before = (job / 'journal.json').read_bytes()
    assert len(client.calls) == 16 and n.status(job)['status'] == 'PENDING'
    next_job = tmp_path / 'extended'; n.extend(next_job, job, 20)
    assert n.status(next_job)['newRequestsUsed'] == 16
    n.collect(next_job, client, 4, sleep=lambda _: None)
    assert len(client.calls) == 19 and n.status(next_job)['newRequestsUsed'] == 19
    assert n.status(next_job)['newRequestsInThisPlan'] == 3 and n.status(next_job)['status'] == 'CAPTURED'
    assert (job / 'journal.json').read_bytes() == before
    with pytest.raises(ResearchError): n.extend(tmp_path / 'bad', job, 16)
    (job / 'journal.json').write_bytes(before + b' ')
    with pytest.raises(ResearchError, match='LINEAGE_TAMPERED'): n.load(next_job)


@pytest.mark.parametrize('stage', ['LIST', 'VIEWER', 'PATH', 'BODY'])
def test_failed_stage_is_not_automatically_retried(tmp_path, stage):
    parent, job, _ = prepared(tmp_path, collect=False); client = Client(fail_stage=stage)
    n.collect(job, client, 64, sleep=lambda _: None); count = len(client.calls)
    assert n.status(job)['status'] == 'FAILED'
    n.collect(job, client, 64, sleep=lambda _: None)
    assert len(client.calls) == count
    with pytest.raises(ResearchError): n.extend(tmp_path / 'unsafe', job, 65)


@pytest.mark.parametrize('variant', ['raw', 'plan', 'journal', 'parameters', 'count', 'clock', 'parent'])
def test_input_and_evidence_tampering_are_rejected(tmp_path, variant):
    parent, job, client = prepared(tmp_path)
    if variant == 'raw': (job / 'raw' / '0001.bin').write_bytes(b'changed')
    elif variant == 'plan':
        p = job / 'plan.json'; d = json.loads(p.read_bytes()); d['pageSize'] = 200; p.write_bytes(canonical(d))
    elif variant == 'parent': parent.write_bytes(parent.read_bytes() + b' ')
    else:
        p = job / 'journal.json'; d = json.loads(p.read_bytes()); entry = d['attempts'][0]
        if variant == 'journal': entry['seq'] = True
        if variant == 'parameters': entry['request']['parameters']['pageIndex'] = '2'
        if variant == 'count': entry['newRequests'] = 0
        if variant == 'clock': entry['capturedAt'] = '2000-01-01T00:00:00Z'
        p.write_bytes(canonical(d))
    with pytest.raises(ResearchError): n.inventory(job, parent)
    if variant != 'parent':
        count = len(client.calls)
        with pytest.raises(ResearchError): n.collect(job, client, 64)
        assert len(client.calls) == count


def test_publication_guard_and_provider_kind_cannot_be_changed(tmp_path):
    parent = parent_file(tmp_path)
    with pytest.raises(ResearchError): n.prepare(tmp_path / 'future', parent, '2027-01-01')
    _, job, client = prepared(tmp_path, collect=False); client.source_kind = 'PROVIDER_OBSERVATIONS'
    with pytest.raises(ResearchError): n.collect(job, client, 64)
    assert not client.calls


def test_viewer_versions_and_document_paths_are_unique_and_bound():
    raw = (f'<select id="mainDoc"><option value="{DOCUMENT}|N">원문</option><option value="20241217000002|Y">정정</option></select>').encode()
    assert len(n.viewer_documents(raw)) == 2
    with pytest.raises(ResearchError): n.viewer_documents(raw.replace(b'20241217000002', DOCUMENT.encode()))
    path = (f"parent.setPath('','{URL}','','01','01');").encode()
    assert n.body_path(path, DOCUMENT) == URL
    with pytest.raises(ResearchError): n.body_path(path, '20241216000002')
    with pytest.raises(ResearchError): n.body_path(path + path, DOCUMENT)


def test_hash_bound_review_corroborates_cross_year_session_without_promoting_candidates(tmp_path):
    parent, job, _ = prepared(tmp_path); before = parent.read_bytes(); inv, manifest = fixture_review(tmp_path, parent, job)
    report = review.build(job, parent, inv, manifest)
    assert len(report['sessionCorroborations']) == 1 and report['sessionCorroborations'][0]['businessDate'] == '2025-01-02'
    assert report['referencePacks'] == json.loads(before)['referencePacks'] and parent.read_bytes() == before
    assert report['ordinaryCandidatesNotPromoted'] == 2 and len(report['partitions']) == 8
    assert report['scopedInventoryReviewComplete'] and not report['fullTemporaryChangeInventoryComplete']
    assert not report['allHistoricalSessionsComplete'] and not report['usableForTrading']
    p = next(p for p in report['partitions'] if p['market'] == 'KOSPI' and p['startDate'].startswith('2025'))
    assert p['corroboratedExceptionDates'] == ['2025-01-02']
    assert not p['inventoryCompletenessConfirmed'] and not p['correctionLineageConfirmed']


@pytest.mark.parametrize('variant', ['hash', 'missing', 'extra', 'duplicate', 'early_time', 'policy', 'wrong_subject'])
def test_review_decisions_cannot_skip_or_misclassify_bodies(tmp_path, variant):
    parent, job, _ = prepared(tmp_path); inv, manifest = fixture_review(tmp_path, parent, job)
    d = json.loads(manifest.read_bytes())
    if variant == 'hash': d['inventorySha256'] = '0' * 64
    if variant == 'missing': d['decisions'] = []
    if variant == 'extra':
        extra = deepcopy(d['decisions'][0]); extra['document'] = '20241216000002'; d['decisions'].append(extra)
    if variant == 'duplicate': d['decisions'].append(deepcopy(d['decisions'][0]))
    if variant == 'early_time': d['reviewedAt'] = '2020-01-01T00:00:00Z'
    if variant == 'policy': d['decisions'][0]['classification'] = 'MARKET_MAKING_POLICY'
    if variant == 'wrong_subject':
        d['decisions'][0].update(classification='ISSUER_SPECIFIC_HALT', subjectIssuer='임의 회사')
    manifest.write_bytes(canonical(d))
    with pytest.raises((ResearchError, ValueError)): review.build(job, parent, inv, manifest)


@pytest.mark.parametrize('variant', ['wrong_time', 'wrong_market', 'closed_day'])
def test_schedule_conflicts_do_not_override_existing_session(tmp_path, variant):
    parent, job, _ = prepared(tmp_path, collect=False)
    client = Client()
    if variant == 'wrong_time': client.raw = newyear_body(opened='11:00')
    if variant == 'wrong_market': client.raw = newyear_body(market='코스닥시장')
    if variant == 'closed_day':
        d = json.loads(parent.read_bytes()); d['referencePacks']['KOSPI']['calendar'][0]['openDay'] = False
        parent.write_bytes(canonical(d)); p = job / 'plan.json'; plan = json.loads(p.read_bytes()); plan['parentSha256'] = digest(parent.read_bytes())
        payload = {k:v for k,v in plan.items() if k != 'planId'}; plan['planId'] = digest(canonical(payload)); p.write_bytes(canonical(plan))
        (job / 'journal.json').write_bytes(canonical({'planId': plan['planId'], 'attempts': []}))
    n.collect(job, client, 64, sleep=lambda _: None); inv, manifest = fixture_review(tmp_path, parent, job)
    with pytest.raises(ResearchError): review.build(job, parent, inv, manifest)
