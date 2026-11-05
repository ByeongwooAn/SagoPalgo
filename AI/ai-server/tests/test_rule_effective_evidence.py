"""An archived body plus a named delegated appendix resolves metadata, not actual sessions."""
from copy import deepcopy
from datetime import timedelta
from io import BytesIO
import json
from unittest.mock import patch
from urllib.parse import parse_qs

import pytest
from pydantic import ValidationError

from app.replay import rule_effective_evidence as e, historical_session_rules as r
from app.replay.dataset import canonical, digest
from app.replay.models import ResearchError, utc
from app.replay.krx_baseline_validation import immutable_json
from test_historical_session_rules import prepared as rule_prepared, body as rule_body

AT = '2026-11-05T12:00:00Z'


def sources():
    return [e.Source(sourceId='archive', role='ARCHIVED_RULE', bookId='200002', oldyn='Y', title=r.TITLES['KOSDAQ'],
        revision=2, ruleNumber='2002', promulgatedDate='2025-02-05', headerEffectiveDate=r.PLACEHOLDER),
        e.Source(sourceId='bylaw', role='DELEGATING_BYLAW', bookId='300001', oldyn='Y',
        title=r.TITLES['KOSDAQ'] + ' 시행세칙', revision=111, ruleNumber='2304', promulgatedDate='2025-02-27', headerEffectiveDate='2025-03-04'),
        e.Source(sourceId='corroboration', role='CORROBORATING_BYLAW', bookId='300002', oldyn='N',
        title=r.TITLES['KOSDAQ'] + ' 시행세칙', revision=119, ruleNumber='2500', promulgatedDate='2026-09-10', headerEffectiveDate='2026-09-14')]


def appendix(number, date, clause):
    return '<p class="buchik_title"><a name="appendix">부칙 &lt;제%s호, %s&gt;</a></p><div>%s</div>' % (number, date.replace('-', '. '), clause)


def delegation(target='2002', date='2025년 3월 4일'):
    return ('제1조(시행일)이 세칙은 ' + date + '부터 시행한다. '
        '제2조(코스닥시장 업무규정의 시행일)규정 제' + target + '호 코스닥시장 업무규정(2025년 2월 5일 개정) '
        '부칙의 "세칙으로 정하는 날"이란 ' + date + '을 말한다.')


def body(source):
    if source.role == 'ARCHIVED_RULE':
        version = r.Version(market='KOSDAQ', bookId=source.bookId, revision=source.revision, ruleNumber=source.ruleNumber,
            effectiveDate=source.headerEffectiveDate, title=source.title)
        value = rule_body(version, old_clock=True).decode().replace('2022. 12. 7', '2025. 2. 5')
        value += '<img onclick="printJo(\'%s\',\'1\',\'bon1\');"/>' % source.bookId
        value += appendix(source.ruleNumber, source.promulgatedDate,
            '이 규정은 전산프로그램 개발에 필요한 기간 등을 고려하여 세칙으로 정하는 날부터 시행한다.')
    else:
        value = ('<div class="lawbon"><p class="title">%s</p><p class="jang">[개정 %s 규정 제%s호 '
            '&lt;시행일 : %s&gt;]</p><p class="selBox">제%d차 개정</p>'
            '<img onclick="printJo(\'%s\',\'1\',\'bon1\');"/>' % (source.title, source.promulgatedDate.replace('-', '. '),
                source.ruleNumber, source.headerEffectiveDate.replace('-', '. '), source.revision, source.bookId))
        value += appendix('2304', '2025-02-27', delegation())
        value += '</div>'
    return value.encode()


def receipt(source, raw, implicit_current=False):
    return {'url': r.VIEW, 'method': 'POST', 'parameters': r.parameters(source.bookId) if implicit_current else source.parameters(),
        'status': 'COMPLETE', 'httpStatus': 200, 'startedAt': AT, 'capturedAt': AT, 'sha256': digest(raw)}


def prepared(tmp_path, mutate=None, parent_mutate=None):
    old_scope, old_cache, old_calendar = rule_prepared(tmp_path, mismatch=True)
    parent = r.build(old_scope, old_cache, old_calendar)
    if parent_mutate: parent_mutate(parent)
    parent_path = tmp_path / 'rules-v1.json'; parent_path.write_bytes(canonical(parent))
    scope = {'schemaVersion': 'SAGOPALGO_RULE_EFFECTIVE_SCOPE_V1', 'parentSha256': digest(parent_path.read_bytes()),
        'targetBookId': '200002', 'resolvedEffectiveDate': '2025-03-04', 'sources': [s.model_dump() for s in sources()]}
    path = tmp_path / 'effective-scope.json'; path.write_bytes(canonical(scope)); cache = tmp_path / 'effective-cache'
    for source in sources():
        raw = body(source)
        if mutate: raw = mutate(source, raw)
        e.seed_capture(cache, source, raw, receipt(source, raw))
    e.capture(path, cache, 0)
    return path, cache, parent_path


def test_archived_identity_and_explicit_delegation_resolve_only_the_previous_case(tmp_path):
    scope, cache, parent_path = prepared(tmp_path); before = parent_path.read_bytes(); prior = json.loads(before)
    with patch('socket.socket.connect', side_effect=AssertionError('offline')):
        report = e.build(scope, cache, parent_path)
    assert parent_path.read_bytes() == before
    assert report['schemaVersion'] == 'SAGOPALGO_SESSION_RULE_REPORT_V2'
    assert report['resolution']['effectiveDate'] == '2025-03-04'
    assert report['resolution']['targetRuleNumber'] == '2002' and report['resolution']['delegatingRuleNumber'] == '2304'
    assert not report['issueCounts'] and report['resolvedPriorIssueCounts'] == prior['issueCounts']
    assert report['metadataWarnings'] == {'EFFECTIVE_DATE_PLACEHOLDER_PRESERVED': 1}
    assert all(v['identityConfirmed'] for v in report['versions'])
    target = next(v for v in report['versions'] if v['expected']['bookId'] == '200002')
    assert target['observed']['effectiveDate'] == r.PLACEHOLDER
    assert target['expected']['effectiveDate'] == r.PLACEHOLDER
    assert target['resolvedEffectiveDate'] == '2025-03-04' and target['effectiveDateConfirmed']
    assert target['sourceIssues'] == ['EFFECTIVE_DATE_PLACEHOLDER']
    state = report['markets']['KOSDAQ']
    assert state['historicalRuleContinuityConfirmed'] and state['verifiedVersionCount'] == 2
    assert state['rulePeriods'][0]['endDate'] == '2025-03-03'
    assert state['rulePeriods'][1]['startDate'] == '2025-03-04'
    assert report['markets']['KOSPI'] == prior['markets']['KOSPI']
    assert report['referencePacks'] == prior['referencePacks']
    assert not report['allHistoricalSessionsComplete'] and not report['usableForTraining'] and not report['usableForTrading']
    assert all(not c['actualSessionConfirmed'] and not c['includedInReferencePack'] for c in state['candidates'])


def test_review_plan_has_market_year_partitions_and_never_assumes_complete_inventory(tmp_path):
    scope, cache, parent = prepared(tmp_path); report = e.build(scope, cache, parent)
    plan = report['temporaryChangeReviewPlan']
    assert len(plan) == 8 and {p['market'] for p in plan} == {'KOSPI', 'KOSDAQ'}
    assert sum(p['ordinaryCandidateCount'] for p in plan) == 2
    assert sum(len(p['knownExceptionDates']) for p in plan) == 2
    assert all(p['status'] == 'PENDING' and not p['inventoryCompletenessConfirmed']
        and not p['paginationCoverageConfirmed'] and not p['correctionLineageConfirmed'] for p in plan)
    assert all(p['intradayHaltIsSeparate'] for p in plan)
    assert min(p['startDate'] for p in plan) == '2023-11-01' and max(p['endDate'] for p in plan) == '2026-11-02'


@pytest.mark.parametrize('variant', ['target_number', 'target_promulgation', 'start_date', 'foreign_appendix',
    'appendix_promulgation', 'duplicate_appendix', 'conditional_date', 'missing_clause', 'fake_toc'])
def test_wrong_or_ambiguous_delegation_never_clears_the_gap(tmp_path, variant):
    def mutate(source, raw):
        if source.role != 'DELEGATING_BYLAW': return raw
        if variant == 'target_number': return raw.replace('규정 제2002호'.encode(), '규정 제2099호'.encode())
        if variant == 'target_promulgation': return raw.replace('2025년 2월 5일 개정'.encode(), '2025년 2월 6일 개정'.encode())
        if variant == 'start_date': return raw.replace('2025년 3월 4일'.encode(), '2025년 3월 5일'.encode())
        if variant == 'foreign_appendix': return raw.replace('부칙 &lt;제2304호'.encode(), '부칙(다른 규정) &lt;제2304호'.encode())
        if variant == 'appendix_promulgation': return raw.replace('제2304호, 2025. 02. 27'.encode(), '제2304호, 2025. 02. 28'.encode())
        if variant == 'duplicate_appendix': return raw + appendix('2304', '2025-02-27', delegation()).encode()
        if variant == 'conditional_date': return raw.replace('을 말한다.'.encode(), '을 말한다. 다만, 별도로 정하는 경우는 제외한다.'.encode())
        if variant == 'missing_clause': return raw.replace('제2조(코스닥시장 업무규정의 시행일)'.encode(), '제3조(기타)'.encode())
        if variant == 'fake_toc': return raw.replace('이란 2025년 3월 4일을 말한다.'.encode(), '이란 미정이다.'.encode()) + delegation().encode()
        raise AssertionError(variant)
    scope, cache, parent = prepared(tmp_path, mutate=mutate)
    with pytest.raises(ResearchError): e.build(scope, cache, parent)


@pytest.mark.parametrize('role,variant', [('ARCHIVED_RULE', 'revision'), ('ARCHIVED_RULE', 'body_id'),
    ('ARCHIVED_RULE', 'time'), ('ARCHIVED_RULE', 'delegation'), ('DELEGATING_BYLAW', 'title'),
    ('DELEGATING_BYLAW', 'body_id'), ('CORROBORATING_BYLAW', 'conflict')])
def test_all_three_source_identities_and_their_clauses_are_required(tmp_path, role, variant):
    def mutate(source, raw):
        if source.role != role: return raw
        if variant == 'revision': return raw.replace('제2차 개정</p>'.encode(), '제1차 개정</p>'.encode())
        if variant == 'body_id': return raw.replace(('printJo(\'%s\',\'1\'' % source.bookId).encode(), b"printJo('999999','1'")
        if variant == 'time': return raw.replace('오후 3시 30분('.encode(), '오후 3시 00분('.encode())
        if variant == 'delegation': return raw.replace('세칙으로 정하는 날부터'.encode(), '공포일부터'.encode())
        if variant == 'title': return raw.replace(source.title.encode(), '파생상품시장 업무규정 시행세칙'.encode())
        if variant == 'conflict': return raw.replace('규정 제2002호'.encode(), '규정 제2003호'.encode())
        raise AssertionError(variant)
    scope, cache, parent = prepared(tmp_path, mutate=mutate)
    with pytest.raises(ResearchError): e.build(scope, cache, parent)


def test_current_body_implicit_oldyn_is_preserved_but_archived_sources_require_explicit_y(tmp_path):
    archive, _, current = sources(); raw = body(current)
    e.seed_capture(tmp_path, current, raw, receipt(current, raw, implicit_current=True))
    captured, _ = e.audit_capture(tmp_path, current)
    assert captured['parameters'] == r.parameters(current.bookId)
    assert 'oldyn' not in captured['parameters']
    with pytest.raises(ResearchError, match='SEED_INVALID'):
        raw = body(archive); e.seed_capture(tmp_path, archive, raw, receipt(archive, raw, implicit_current=True))


def test_new_knowledge_is_not_backdated_and_actual_sessions_are_unchanged(tmp_path):
    scope, cache, parent = prepared(tmp_path); report = e.build(scope, cache, parent)
    before = (utc(AT) - timedelta(microseconds=1)).isoformat()
    assert not r.as_of(report, before, 'KOSDAQ')['rulePeriods']
    assert len(r.as_of(report, before, 'KOSDAQ')['actualSessions']) == 1
    after = r.as_of(report, AT, 'KOSDAQ')
    assert len(after['ordinaryCandidates']) == 1 and len(after['actualSessions']) == 1
    assert all(c['knownAt'] == AT for c in after['ordinaryCandidates'])


def test_existing_later_candidate_knowledge_time_is_preserved(tmp_path):
    later = '2026-11-06T00:00:00Z'
    def mutate(parent): parent['markets']['KOSDAQ']['candidates'][0]['knownAt'] = later
    scope, cache, parent = prepared(tmp_path, parent_mutate=mutate); report = e.build(scope, cache, parent)
    assert report['markets']['KOSDAQ']['knownAt'] == later
    assert not r.as_of(report, AT, 'KOSDAQ')['ordinaryCandidates']


@pytest.mark.parametrize('variant', ['hash', 'schema', 'target', 'review', 'other_gap'])
def test_parent_identity_and_unrelated_gaps_cannot_be_overwritten(tmp_path, variant):
    def mutate(parent):
        if variant == 'schema': parent['schemaVersion'] = 'unsupported'
        if variant == 'target': parent['versions'][-1]['expected']['ruleNumber'] = '2099'
        if variant == 'review': parent['versions'][-1]['issues'] = ['different']
        if variant == 'other_gap': parent['versions'][0]['identityConfirmed'] = False
    scope, cache, parent = prepared(tmp_path, parent_mutate=mutate)
    if variant == 'hash': parent.write_bytes(parent.read_bytes() + b' ')
    with pytest.raises(ResearchError): e.build(scope, cache, parent)


@pytest.mark.parametrize('variant', ['raw', 'hash', 'parameters', 'clock', 'reserved'])
def test_source_tampering_is_rejected_before_reuse(tmp_path, variant):
    scope, cache, _ = prepared(tmp_path); p = cache / 'archive' / 'receipt.json'; rec = json.loads(p.read_bytes())
    if variant == 'raw': (p.parent / 'body.html').write_bytes(b'changed')
    if variant == 'hash': rec['bodySha256'] = '0' * 64
    if variant == 'parameters': rec['parameters']['oldyn'] = 'N'
    if variant == 'clock': rec['startedAt'] = '2026-11-06T00:00:00Z'
    if variant == 'reserved': rec['status'] = 'RESERVED'
    p.write_bytes(canonical(rec))
    with pytest.raises(ResearchError): e.capture(scope, cache, 0)


class Response(BytesIO):
    status = 200


class Client:
    def __init__(self, fail=False, bad_form=False): self.requests = []; self.fail = fail; self.bad_form = bad_form
    def open(self, request, timeout):
        self.requests.append(request)
        if request.full_url == r.INDEX:
            return Response(b'<html/>' if self.bad_form else b'<meta id="_csrf" name="_csrf" content="public-form-nonce">')
        if self.fail: raise TimeoutError('private detail not in error')
        params = parse_qs(request.data.decode()); source = next(s for s in sources() if s.bookId == params['bookid'][0])
        assert params['oldyn'] == [source.oldyn]
        return Response(body(source))


def test_bounded_public_capture_and_offline_reuse(tmp_path):
    scope, cache, parent = prepared(tmp_path); fresh = tmp_path / 'fresh'; client = Client(); sleeps = []
    assert e.capture(scope, fresh, 4, client, sleep=sleeps.append) == {'sources': 3, 'newRequests': 4, 'reused': 0}
    assert len(client.requests) == 4 and sleeps
    count = len(client.requests)
    assert e.capture(scope, fresh, 0, client)['newRequests'] == 0 and len(client.requests) == count
    assert all(e.audit_capture(fresh, s)[0]['newRequests'] == 1 for s in sources())
    assert 'public-form-nonce' not in (fresh / 'archive' / 'receipt.json').read_text()


def test_insufficient_budget_does_not_start_a_request(tmp_path):
    scope, _, _ = prepared(tmp_path); client = Client(); fresh = tmp_path / 'fresh'
    with pytest.raises(ResearchError, match='BUDGET_TOO_SMALL'): e.capture(scope, fresh, 3, client)
    assert not client.requests and not (fresh / 'public-form.json').exists()


@pytest.mark.parametrize('bad_form,fail', [(True, False), (False, True)])
def test_failed_form_or_source_reservation_is_never_retried(tmp_path, bad_form, fail):
    scope, _, _ = prepared(tmp_path); client = Client(fail=fail, bad_form=bad_form); fresh = tmp_path / 'fresh'
    with pytest.raises(ResearchError): e.capture(scope, fresh, 4, client, sleep=lambda _: None)
    count = len(client.requests)
    with pytest.raises(ResearchError): e.capture(scope, fresh, 4, client)
    assert len(client.requests) == count


def test_scope_rejects_mixed_market_duplicate_sources_and_unsafe_parameters(tmp_path):
    scope, _, _ = prepared(tmp_path); data = json.loads(scope.read_bytes())
    for variant in ['duplicate', 'title', 'current_archive', 'date', 'unsafe_id']:
        d = deepcopy(data)
        if variant == 'duplicate': d['sources'][1]['sourceId'] = 'archive'
        if variant == 'title': d['sources'][0]['title'] = r.TITLES['KOSPI']
        if variant == 'current_archive': d['sources'][0]['oldyn'] = 'N'
        if variant == 'date': d['resolvedEffectiveDate'] = '2025-03-05'
        if variant == 'unsafe_id': d['sources'][0]['sourceId'] = '../escape'
        with pytest.raises((ValueError, ValidationError)): e.Scope.model_validate(d)


def test_audit_recomputes_the_entire_v2_report(tmp_path):
    scope, cache, parent = prepared(tmp_path); report = e.build(scope, cache, parent); path = tmp_path / 'v2.json'
    immutable_json(path, report); immutable_json(path, e.build(scope, cache, parent), True)
    changed = deepcopy(report); changed['resolution']['effectiveDate'] = '2025-03-05'
    with pytest.raises(ResearchError): immutable_json(path, changed, True)
