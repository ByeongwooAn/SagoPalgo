"""Historical rule-body binding, incomplete chains and actual-session promotion gates."""
from copy import deepcopy
from datetime import timedelta
from io import BytesIO
from pathlib import Path
import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.replay import historical_session_rules as r
from app.replay.dataset import canonical, digest
from app.replay.krx_baseline_validation import immutable_json
from app.replay.models import ResearchError, utc

AT = '2026-11-05T10:00:00Z'


def versions():
    return [r.Version(market=market, bookId=book, revision=rev, ruleNumber=str(2000 + rev),
                      effectiveDate='2023-01-01' if rev == 1 else '2025-01-01', title=r.TITLES[market])
            for market, books in [('KOSPI', ['100001', '100002']), ('KOSDAQ', ['200001', '200002'])]
            for rev, book in enumerate(books, 1)]


def body(v, listed=None, old_clock=False, delegated=False):
    listed = listed or [p for p in versions() if p.market == v.market]
    menu = ''.join('<div onclick=" goRegulationView(\'%s\',\'N\', \'제%d차\')">'
        '<div><b>%s</b></div><div style="color:rgba(1);">제%d차 개정 %s. 규정 제%s호</div></div>'
        % (p.bookId, p.revision, p.title, p.revision, p.effectiveDate.replace('-', '. '), p.ruleNumber) for p in listed)
    clock = '오전 9시부터 오후 3시 30분' if old_clock else '9시부터 15시 30분'
    date = v.effectiveDate.replace('-', '. ')
    return ('<div class="layerViewW">' + menu + '</div><div class="lawbon" id="regulCont">'
        '<p class="title">%s</p><p class="jang">[일부개정 2022. 12. 7 규정 제%s호 &lt;시행일 : %s&gt;]</p>'
        '<p class="selBox">%s제%d차 개정</p>'
        '<img onclick="printJo(\'%s\',\'101\',\'bon4\');"/><a name="bon4"><strong>제4조(시장의 구분 및 매매거래시간)</strong></a>'
        '③ 매매거래시간 1. 정규시장 : %s(장종료시의 가격을 결정하는 경우에는 당해 가격이 결정되는 시점)까지로 한다. '
        '장중경쟁대량매매는 9시부터 15시까지. 시간외시장 15시 40분부터 20시까지. 임시로 변경할 수 있다.'
        '<a name="bon5">제5조</a></div>' % (v.title, v.ruleNumber, date, '(타)' if delegated else '',
                                             v.revision, v.bookId, clock)).encode()


def origin(v, raw):
    return {'url': r.VIEW, 'method': 'POST', 'parameters': r.parameters(v.bookId), 'status': 'COMPLETE',
            'httpStatus': 200, 'startedAt': AT, 'capturedAt': AT, 'sha256': digest(raw)}


def prepared(tmp_path, mismatch=False):
    parent = {'schemaVersion': 'SAGOPALGO_MARKET_CALENDAR_REPORT_V1', 'startDate': '2023-11-01', 'endDate': '2026-11-02',
        'sessionCandidates': {market: [{'businessDate': '2023-11-01', 'open': '09:00', 'close': '15:30',
            'knownAt': '2026-11-04T00:00:00Z', 'includedInReferencePack': False}] for market in r.TITLES},
        'referencePacks': {market: {'sessions': [{'market': market, 'businessDate': '2024-01-02',
            'knownAt': '2026-11-04T00:00:00Z'}], 'coverage': []} for market in r.TITLES}}
    parent_path = tmp_path / 'parent.json'; parent_path.write_bytes(canonical(parent))
    vs = versions()
    if mismatch:
        vs[-1] = vs[-1].model_copy(update={'effectiveDate': r.PLACEHOLDER})
    scope = {'schemaVersion': 'SAGOPALGO_SESSION_RULE_SCOPE_V1', 'startDate': parent['startDate'], 'endDate': parent['endDate'],
        'parentSha256': digest(parent_path.read_bytes()), 'anchors': {'KOSPI': '100002', 'KOSDAQ': '200002'},
        'versions': [v.model_dump() for v in vs]}
    scope_path = tmp_path / 'scope.json'; scope_path.write_bytes(canonical(scope)); cache = tmp_path / 'cache'
    for v in vs:
        observed = versions()[-2] if mismatch and v.bookId == '200002' else v
        raw = body(observed, [p for p in vs if p.market == v.market])
        r.seed_capture(cache, v.bookId, raw, origin(v, raw))
    r.capture(scope_path, cache, 0)
    return scope_path, cache, parent_path


@pytest.mark.parametrize('market,old_clock,delegated', [('KOSPI', False, False), ('KOSPI', False, True),
    ('KOSDAQ', True, False), ('KOSDAQ', False, False), ('KOSDAQ', True, True)])
def test_verified_body_identity_uses_nominal_regular_hours_and_fetch_time(market, old_clock, delegated):
    v = next(v for v in versions() if v.market == market)
    raw = body(v, old_clock=old_clock, delegated=delegated)
    fact = r.parse_version(v, {'bodySha256': digest(raw), 'capturedAt': AT}, raw)
    assert fact['identityConfirmed'] and not fact['issues']
    assert (fact['nominalOpen'], fact['nominalClose']) == ('09:00', '15:30')
    assert fact['temporaryChangesPermitted'] and fact['closingAuctionMayExtend']
    assert fact['knownAt'] == AT and not fact['historicalPublicationTimeConfirmed']


def test_successful_http_wrong_old_body_is_not_the_requested_revision():
    requested = versions()[-1].model_copy(update={'effectiveDate': r.PLACEHOLDER})
    raw = body(versions()[-2], listed=[requested])
    fact = r.parse_version(requested, {'bodySha256': digest(raw), 'capturedAt': AT}, raw)
    assert not fact['identityConfirmed']
    assert fact['issues'] == ['EFFECTIVE_DATE_PLACEHOLDER', 'RULE_VERSION_MISMATCH']
    assert fact['observed']['ruleNumber'] == '2001' and fact['expected']['ruleNumber'] == '2002'


@pytest.mark.parametrize('variant', ['wrong_market', 'wrong_number', 'wrong_date', 'wrong_revision', 'wrong_body_id'])
def test_body_identity_is_bound_to_all_expected_fields(variant):
    v = versions()[0]; raw = body(v)
    if variant == 'wrong_market': raw = raw.replace(v.title.encode(), r.TITLES['KOSDAQ'].encode())
    if variant == 'wrong_number': raw = raw.replace(b'2001', b'3001')
    if variant == 'wrong_date': raw = raw.replace(b'2023. 01. 01', b'2023. 01. 02')
    if variant == 'wrong_revision': raw = raw.replace('제1차'.encode(), '제2차'.encode())
    if variant == 'wrong_body_id': raw = raw.replace(b"printJo('100001'", b"printJo('100002'")
    fact = r.parse_version(v, {'bodySha256': digest(raw), 'capturedAt': AT}, raw)
    assert 'RULE_VERSION_MISMATCH' in fact['issues'] and not fact['identityConfirmed']


@pytest.mark.parametrize('variant', ['hours', 'orders', 'article', 'duplicate_header', 'missing_permission', 'after_hours_only'])
def test_unsupported_or_ambiguous_layouts_fail_closed(variant):
    v = versions()[0]; raw = body(v)
    if variant == 'hours': raw = raw.replace('15시 30분('.encode(), '15시 00분('.encode())
    if variant == 'orders': raw = raw.replace('1. 정규시장 :'.encode(), '1. 호가접수시간 :'.encode())
    if variant == 'article': raw = raw.replace(b'bon4', b'bon6')
    if variant == 'duplicate_header': raw += b'<p class="title">duplicate</p>'
    if variant == 'missing_permission': raw = raw.replace('임시로 변경'.encode(), '다른 조항'.encode())
    if variant == 'after_hours_only': raw = raw.replace('정규시장 : 9시부터 15시 30분('.encode(), '정규시장 : 8시부터 15시 30분('.encode())
    with pytest.raises(ResearchError): r.parse_version(v, {'bodySha256': digest(raw), 'capturedAt': AT}, raw)


def test_rule_continuity_does_not_promote_any_actual_session_or_coverage(tmp_path):
    scope, cache, parent = prepared(tmp_path)
    before = parent.read_bytes()
    with patch('socket.socket.connect', side_effect=AssertionError('offline')):
        report = r.build(scope, cache, parent)
    assert parent.read_bytes() == before
    for market, value in report['markets'].items():
        assert value['historicalRuleContinuityConfirmed'] and value['ruleSupportedCandidateCount'] == 1
        assert not value['temporaryChangeInventoryComplete']
        candidate = value['candidates'][0]
        assert candidate['ordinaryRuleConfirmed'] and not candidate['actualSessionConfirmed']
        assert not candidate['includedInReferencePack']
        assert candidate['basis'] == 'TEMPORARY_CHANGE_INVENTORY_UNVERIFIED'
        assert len(report['referencePacks'][market]['sessions']) == 1
        assert not report['referencePacks'][market]['coverage']
        assert value['rulePeriods'][0]['startDate'] == '2023-11-01'
    assert not report['allHistoricalSessionsComplete'] and not report['usableForTraining'] and not report['usableForTrading']


def test_one_wrong_version_blocks_only_its_market_chain_and_keeps_both_raw_identities(tmp_path):
    scope, cache, parent = prepared(tmp_path, mismatch=True)
    report = r.build(scope, cache, parent)
    assert report['markets']['KOSPI']['historicalRuleContinuityConfirmed']
    assert not report['markets']['KOSDAQ']['historicalRuleContinuityConfirmed']
    assert report['markets']['KOSDAQ']['ruleSupportedCandidateCount'] == 0
    assert report['issueCounts'] == {'EFFECTIVE_DATE_PLACEHOLDER': 1, 'RULE_VERSION_MISMATCH': 1}
    assert all(not p['continuityConfirmed'] for p in report['markets']['KOSDAQ']['rulePeriods'])


def test_as_of_never_backdates_periods_or_exposes_candidates_as_actual_sessions(tmp_path):
    scope, cache, parent = prepared(tmp_path); report = r.build(scope, cache, parent)
    at = (utc(AT) - timedelta(microseconds=1)).isoformat()
    before = r.as_of(report, at, 'KOSPI')
    assert not before['rulePeriods'] and not before['ordinaryCandidates']
    assert len(before['actualSessions']) == 1
    current = r.as_of(report, AT, 'KOSPI')
    assert len(current['ordinaryCandidates']) == 1 and len(current['actualSessions']) == 1
    current['ordinaryCandidates'][0]['basis'] = 'changed'
    assert report['markets']['KOSPI']['candidates'][0]['basis'] != 'changed'
    with pytest.raises(ResearchError): r.as_of(report, AT, 'NXT')


def test_parent_hash_changes_are_rejected_before_build(tmp_path):
    scope, cache, parent = prepared(tmp_path); parent.write_bytes(parent.read_bytes() + b' ')
    with pytest.raises(ResearchError, match='RULE_PARENT_HASH_MISMATCH'): r.build(scope, cache, parent)


def test_manifest_cannot_silently_skip_a_listed_revision(tmp_path):
    scope, cache, parent = prepared(tmp_path)
    d = json.loads(scope.read_bytes()); d['versions'] = [v for v in d['versions'] if v['bookId'] != '100002']; d['anchors']['KOSPI'] = '100001'
    scope.write_bytes(canonical(d))
    # A different valid plan is needed to isolate the history-list check.
    index = {'schemaVersion': 'SAGOPALGO_RULE_CAPTURE_PLAN_V1', 'scopeSha256': digest(scope.read_bytes()),
             'books': [v['bookId'] for v in d['versions']]}
    (cache / 'index.json').write_bytes(canonical(index))
    with pytest.raises(ResearchError, match='RULE_HISTORY_SCOPE_GAP'): r.build(scope, cache, parent)


@pytest.mark.parametrize('variant', ['raw', 'receipt_hash', 'receipt_url', 'receipt_parameters', 'time', 'reserved'])
def test_seed_capture_and_receipt_tampering_are_detected(tmp_path, variant):
    scope, cache, _ = prepared(tmp_path); folder = cache / '100001'; p = folder / 'receipt.json'; e = json.loads(p.read_bytes())
    if variant == 'raw': (folder / 'body.html').write_bytes(b'changed')
    if variant == 'receipt_hash': e['bodySha256'] = '0' * 64
    if variant == 'receipt_url': e['url'] = 'https://example.com'
    if variant == 'receipt_parameters': e['parameters']['bookid'] = '100002'
    if variant == 'time': e['startedAt'] = '2026-11-06T00:00:00Z'
    if variant == 'reserved': e['status'] = 'RESERVED'
    p.write_bytes(canonical(e))
    with pytest.raises(ResearchError): r.capture(scope, cache, 0)


def test_cache_reuse_is_zero_network_and_budget_checked_before_bootstrap(tmp_path):
    scope, cache, _ = prepared(tmp_path)
    class NoNetwork:
        def open(self, *a, **k): raise AssertionError('unexpected request')
    assert r.capture(scope, cache, 0, NoNetwork()) == {'sources': 4, 'newRequests': 0, 'reused': 4}
    empty = tmp_path / 'empty'
    with pytest.raises(ResearchError, match='BUDGET_TOO_SMALL'): r.capture(scope, empty, 4, NoNetwork())
    assert not (empty / 'public-form.json').exists()


class Response(BytesIO):
    status = 200


class Client:
    def __init__(self, bad_form=False, fail=False): self.requests = []; self.bad_form = bad_form; self.fail = fail
    def open(self, request, timeout):
        self.requests.append(request)
        if request.full_url == r.INDEX:
            return Response(b'<html/>' if self.bad_form else b'<meta id="_csrf" name="_csrf" content="public-form-nonce">')
        if self.fail: raise TimeoutError('must not leak this text')
        from urllib.parse import parse_qs
        book = parse_qs(request.data.decode())['bookid'][0]
        return Response(body(next(v for v in versions() if v.bookId == book)))


def test_capture_form_and_each_source_are_bounded_and_auditable(tmp_path):
    scope, _, _ = prepared(tmp_path); cache = tmp_path / 'new'; client = Client(); sleeps = []
    result = r.capture(scope, cache, 5, client, sleep=sleeps.append)
    assert result == {'sources': 4, 'newRequests': 5, 'reused': 0}
    assert len(client.requests) == 5 and len(sleeps) >= 1
    for v in versions(): assert r.audit_capture(cache, v.bookId)[0]['newRequests'] == 1
    assert 'public-form-nonce' not in (cache / '100001' / 'receipt.json').read_text()
    assert client.requests[1].full_url == r.VIEW and client.requests[1].get_method() == 'POST'


@pytest.mark.parametrize('bad_form,fail', [(True, False), (False, True)])
def test_failed_public_form_or_reserved_source_is_not_automatically_retried(tmp_path, bad_form, fail):
    scope, _, _ = prepared(tmp_path); cache = tmp_path / 'new'; client = Client(bad_form=bad_form, fail=fail)
    with pytest.raises(ResearchError): r.capture(scope, cache, 5, client, sleep=lambda _: None)
    count = len(client.requests)
    with pytest.raises(ResearchError): r.capture(scope, cache, 5, client, sleep=lambda _: None)
    assert len(client.requests) == count


def test_scope_rejects_duplicate_ids_bad_market_and_revision_gaps(tmp_path):
    scope, _, _ = prepared(tmp_path); data = json.loads(scope.read_bytes())
    for mutation in ['duplicate', 'title', 'gap', 'anchor', 'date']:
        d = deepcopy(data)
        if mutation == 'duplicate': d['versions'][1]['bookId'] = d['versions'][0]['bookId']
        if mutation == 'title': d['versions'][0]['title'] = '파생상품시장 업무규정'
        if mutation == 'gap': d['versions'][1]['revision'] = 3
        if mutation == 'anchor': d['anchors']['KOSPI'] = '000000'
        if mutation == 'date': d['versions'][0]['effectiveDate'] = '2023-02-30'
        with pytest.raises((ValidationError, ValueError)): r.Scope.model_validate(d)


def test_audit_compares_the_entire_frozen_report(tmp_path):
    scope, cache, parent = prepared(tmp_path); output = tmp_path / 'report.json'; report = r.build(scope, cache, parent)
    immutable_json(output, report); immutable_json(output, r.build(scope, cache, parent), True)
    altered = deepcopy(report); altered['markets']['KOSDAQ']['historicalRuleContinuityConfirmed'] = False
    with pytest.raises(ResearchError): immutable_json(output, altered, True)
