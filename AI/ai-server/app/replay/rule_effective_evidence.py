"""Resolve one historical rule using its archived body and an explicit delegated start date.

The earlier mismatching capture remains immutable. Ordinary hours still require
an exhaustive temporary-session notice review before becoming actual sessions.
"""
import argparse
from copy import deepcopy
from datetime import timedelta
from http.cookiejar import CookieJar
import json
from pathlib import Path
import re
import time
from typing import Literal
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPCookieProcessor, Request

from pydantic import Field, model_validator

from . import historical_session_rules as rules
from .dataset import digest, read_bytes, read_json
from .history import day, now, NoRedirect, job_lock
from .krx_baseline_validation import immutable_json
from .krx_storage import atomic_json
from .models import StrictModel, ResearchError, utc


class Source(StrictModel):
    sourceId: str = Field(pattern=r'^[a-z0-9-]{1,60}$')
    role: Literal['ARCHIVED_RULE', 'DELEGATING_BYLAW', 'CORROBORATING_BYLAW']
    bookId: str = Field(pattern=r'^[0-9]{6,10}$')
    oldyn: Literal['Y', 'N']
    title: str
    revision: int = Field(ge=1, le=300)
    ruleNumber: str = Field(pattern=r'^[0-9]{1,5}$')
    promulgatedDate: str
    headerEffectiveDate: str

    @model_validator(mode='after')
    def valid(self):
        day(self.promulgatedDate)
        if self.headerEffectiveDate != rules.PLACEHOLDER:
            day(self.headerEffectiveDate)
        title = rules.TITLES['KOSDAQ'] + ('' if self.role == 'ARCHIVED_RULE' else ' 시행세칙')
        if self.title != title or self.role != 'CORROBORATING_BYLAW' and self.oldyn != 'Y':
            raise ValueError('reviewed archived source required')
        return self

    def parameters(self):
        return {**rules.parameters(self.bookId), 'oldyn': self.oldyn}


class Scope(StrictModel):
    schemaVersion: Literal['SAGOPALGO_RULE_EFFECTIVE_SCOPE_V1']
    parentSha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    targetBookId: str = Field(pattern=r'^[0-9]{6,10}$')
    resolvedEffectiveDate: str
    sources: list[Source] = Field(min_length=3, max_length=3)

    @model_validator(mode='after')
    def valid(self):
        day(self.resolvedEffectiveDate)
        if ({s.role for s in self.sources} != {'ARCHIVED_RULE', 'DELEGATING_BYLAW', 'CORROBORATING_BYLAW'}
                or len({s.sourceId for s in self.sources}) != 3 or len({s.bookId for s in self.sources}) != 3):
            raise ValueError('three distinct reviewed sources required')
        target = next(s for s in self.sources if s.role == 'ARCHIVED_RULE')
        bylaw = next(s for s in self.sources if s.role == 'DELEGATING_BYLAW')
        if (target.bookId != self.targetBookId or target.headerEffectiveDate != rules.PLACEHOLDER
                or bylaw.headerEffectiveDate != self.resolvedEffectiveDate
                or target.promulgatedDate > self.resolvedEffectiveDate or bylaw.promulgatedDate > self.resolvedEffectiveDate):
            raise ValueError('invalid delegated effective date')
        return self


def load_scope(path):
    return Scope.model_validate(read_json(read_bytes(path)))


def allowed_parameters(source):
    values = [source.parameters()]
    if source.role == 'CORROBORATING_BYLAW' and source.oldyn == 'N':
        values.append(rules.parameters(source.bookId))
    return values


def audit_capture(cache, source):
    folder = cache / source.sourceId
    receipt = read_json(read_bytes(folder / 'receipt.json'))
    if receipt.get('status') != 'COMPLETE':
        raise ResearchError('RULE_EFFECTIVE_CAPTURE_INCOMPLETE')
    raw = read_bytes(folder / 'body.html')
    expected = {'schemaVersion', 'url', 'method', 'parameters', 'status', 'startedAt', 'capturedAt',
                'bodySha256', 'newRequests', 'knowledgeBasis'}
    if (set(receipt) != expected or receipt['schemaVersion'] != 'SAGOPALGO_RULE_EFFECTIVE_CAPTURE_V1'
            or receipt['url'] != rules.VIEW or receipt['method'] != 'POST' or receipt['parameters'] not in allowed_parameters(source)
            or type(receipt['newRequests']) is not int or receipt['newRequests'] not in {0, 1}
            or receipt['knowledgeBasis'] != 'FETCH_TIME_ONLY'
            or utc(receipt['startedAt']) > utc(receipt['capturedAt'])
            or len(raw) > rules.LIMIT or digest(raw) != receipt['bodySha256']):
        raise ResearchError('RULE_EFFECTIVE_CAPTURE_TAMPERED')
    return receipt, raw


def seed_capture(cache, source, raw, origin):
    # The current-body corroboration can reuse the original no-oldyn request;
    # archived sources must explicitly bind oldyn=Y in their original receipt.
    if (origin.get('url') != rules.VIEW or origin.get('method') != 'POST' or origin.get('parameters') not in allowed_parameters(source)
            or origin.get('status') != 'COMPLETE' or origin.get('httpStatus') != 200
            or origin.get('sha256') != digest(raw) or len(raw) > rules.LIMIT
            or utc(origin['startedAt']) > utc(origin['capturedAt'])):
        raise ResearchError('RULE_EFFECTIVE_SEED_INVALID')
    folder = cache / source.sourceId
    folder.mkdir(parents=True, exist_ok=False)
    (folder / 'body.html').write_bytes(raw)
    atomic_json(folder / 'receipt.json', {'schemaVersion': 'SAGOPALGO_RULE_EFFECTIVE_CAPTURE_V1',
        'url': rules.VIEW, 'method': 'POST', 'parameters': origin['parameters'], 'status': 'COMPLETE',
        'startedAt': origin['startedAt'], 'capturedAt': origin['capturedAt'], 'bodySha256': digest(raw),
        'newRequests': 0, 'knowledgeBasis': 'FETCH_TIME_ONLY'})
    return audit_capture(cache, source)[0]


def capture(scope_path, cache, budget, opener=None, sleep=time.sleep):
    scope = load_scope(scope_path)
    if type(budget) is not int or not 0 <= budget <= 4:
        raise ResearchError('RULE_EFFECTIVE_BUDGET_INVALID')
    cache.mkdir(parents=True, exist_ok=True)
    with job_lock(cache):
        immutable_json(cache / 'index.json', {'schemaVersion': 'SAGOPALGO_RULE_EFFECTIVE_CAPTURE_PLAN_V1',
            'scopeSha256': digest(read_bytes(scope_path)), 'sources': [s.model_dump() for s in scope.sources]})
        missing = []
        for source in scope.sources:
            if (cache / source.sourceId).exists():
                audit_capture(cache, source)
            else:
                missing.append(source)
        if not missing:
            return {'sources': 3, 'newRequests': 0, 'reused': 3}
        if budget < len(missing) + 1:
            raise ResearchError('RULE_EFFECTIVE_BUDGET_TOO_SMALL')
        form = cache / 'public-form.json'
        if form.exists():
            raise ResearchError('RULE_EFFECTIVE_ATTEMPT_EXISTS')
        client = opener or build_opener(HTTPCookieProcessor(CookieJar()), NoRedirect())
        started = now()
        atomic_json(form, {'url': rules.INDEX, 'status': 'RESERVED', 'startedAt': started})
        try:
            with client.open(Request(rules.INDEX, headers={'User-Agent': 'SagoPalgo-Personal-Research/1.0'}), timeout=20) as response:
                raw = response.read(rules.LIMIT + 1)
                if response.status != 200 or len(raw) > rules.LIMIT:
                    raise ResearchError('RULE_EFFECTIVE_FORM_INVALID')
            nonce = re.findall(rb'<meta id="_csrf" name="_csrf" content="([a-zA-Z0-9-]{1,100})">', raw)
            if len(nonce) != 1:
                raise ResearchError('RULE_EFFECTIVE_FORM_INVALID')
            atomic_json(form, {'url': rules.INDEX, 'status': 'COMPLETE', 'startedAt': started, 'capturedAt': now(),
                'newRequests': 1, 'bodySha256': digest(raw)})
        except Exception:
            raise ResearchError('RULE_EFFECTIVE_FORM_FAILED') from None
        previous = started
        for source in missing:
            elapsed = (utc(now()) - utc(previous)).total_seconds()
            if elapsed < 0:
                raise ResearchError('RULE_EFFECTIVE_CLOCK_REGRESSION')
            if elapsed < 1:
                sleep(1 - elapsed)
            started = now()
            folder = cache / source.sourceId
            folder.mkdir()
            atomic_json(folder / 'receipt.json', {'status': 'RESERVED', 'startedAt': started, 'parameters': source.parameters()})
            data = urlencode({**source.parameters(), '_csrf': nonce[0].decode()}).encode()
            try:
                with client.open(Request(rules.VIEW, data=data, headers={'User-Agent': 'SagoPalgo-Personal-Research/1.0',
                    'Content-Type': 'application/x-www-form-urlencoded', 'Referer': rules.INDEX}), timeout=20) as response:
                    raw = response.read(rules.LIMIT + 1)
                    if response.status != 200 or len(raw) > rules.LIMIT:
                        raise ResearchError('RULE_EFFECTIVE_RESPONSE_INVALID')
                (folder / 'body.html').write_bytes(raw)
                atomic_json(folder / 'receipt.json', {'schemaVersion': 'SAGOPALGO_RULE_EFFECTIVE_CAPTURE_V1',
                    'url': rules.VIEW, 'method': 'POST', 'parameters': source.parameters(), 'status': 'COMPLETE',
                    'startedAt': started, 'capturedAt': now(), 'bodySha256': digest(raw),
                    'newRequests': 1, 'knowledgeBasis': 'FETCH_TIME_ONLY'})
                audit_capture(cache, source)
                previous = started
            except Exception:
                raise ResearchError('RULE_EFFECTIVE_SOURCE_FAILED') from None
        return {'sources': 3, 'newRequests': len(missing) + 1, 'reused': 3 - len(missing)}


def body(raw):
    try:
        s = raw.decode('utf-8-sig')
        s = s[s.index('class="lawbon"'):]
        # Exclude the side navigation, which repeats appendix headings without clauses.
        s = s.split('class="slawbon"')[0]
    except (ValueError, UnicodeError):
        raise ResearchError('RULE_EFFECTIVE_BODY_LAYOUT') from None
    return s


def identity(source, receipt, raw):
    s = body(raw)
    title = re.findall(r'<p class="title">(.*?)</p>', s, re.S)
    header = re.findall(r'<p class="jang"[^>]*>\[(.*?)</p>', s, re.S)
    revision = re.findall(r'<p class="selBox"[^>]*>(?:\(타\))?제([0-9]+)차', s)
    if len(title) != 1 or len(header) != 1 or revision != [str(source.revision)]:
        raise ResearchError('RULE_EFFECTIVE_BODY_IDENTITY')
    value = rules.html_text(header[0])
    match = re.fullmatch(r'.*?([0-9]{4})\.\s*([0-9]{1,2})\.\s*([0-9]{1,2})\.? 규정 제([0-9]+)호 <시행일\s*:\s*([0-9]{4})\.\s*([0-9]{1,2})\.\s*([0-9]{1,2})\.?\s*>\]', value)
    if not match:
        raise ResearchError('RULE_EFFECTIVE_BODY_HEADER')
    y, m, d, number, ey, em, ed = match.groups()
    observed = {'title': rules.html_text(title[0]), 'ruleNumber': number, 'revision': int(revision[0]),
        'promulgatedDate': '%04d-%02d-%02d' % (int(y), int(m), int(d)),
        'headerEffectiveDate': '%04d-%02d-%02d' % (int(ey), int(em), int(ed))}
    if any(observed[k] != getattr(source, k) for k in observed):
        raise ResearchError('RULE_EFFECTIVE_BODY_IDENTITY')
    # Bind the main body, independently of a menu/request ID, using article 1's print identity.
    if re.findall(r"printJo\('([0-9]+)','[0-9]+','bon1'\)", s) != [source.bookId]:
        raise ResearchError('RULE_EFFECTIVE_BODY_IDENTITY')
    return {'sourceId': source.sourceId, 'role': source.role, 'bookId': source.bookId,
        'observed': observed, 'requestParameters': receipt['parameters'], 'bodySha256': receipt['bodySha256'],
        'knownAt': receipt['capturedAt'], 'sourceUrl': rules.VIEW, 'bodyIdentityConfirmed': True,
        'historicalPublicationTimeConfirmed': False}


def appendix(raw, number, promulgated):
    """Select only the named enactment's appendix, never another rule or the TOC."""
    s = body(raw)
    chunks = re.split(r'<p class="buchik_title"', s)[1:]
    matches = []
    for chunk in chunks:
        chunk = chunk.split('조문목록')[0]
        heading = re.match(r'[^>]*>\s*<a\b[^>]*>(.*?)</a></p>', chunk, re.S)
        if not heading:
            continue
        label = rules.html_text(heading[1])
        stamp = re.fullmatch(r'부칙 <제([0-9]+)호, ([0-9]{4})\.\s*([0-9]{1,2})\.\s*([0-9]{1,2})\.?\s*>', label)
        if stamp and stamp[1] == number:
            date = '%04d-%02d-%02d' % tuple(map(int, stamp.groups()[1:]))
            if date != promulgated:
                raise ResearchError('RULE_EFFECTIVE_APPENDIX_DATE_CONFLICT')
            matches.append(rules.html_text(chunk[heading.end():]).split('별표 및 서식')[0].strip())
    if len(matches) != 1:
        raise ResearchError('RULE_EFFECTIVE_APPENDIX_AMBIGUOUS')
    return matches[0]


def delegated_date(raw, bylaw, target, date):
    clause = appendix(raw, bylaw.ruleNumber, bylaw.promulgatedDate)
    y, m, d = map(int, date.split('-'))
    ty, tm, td = map(int, target.promulgatedDate.split('-'))
    # Ignore spaces inserted by official cross-reference anchors, preserving all other wording.
    compact = re.sub(r'\s+', '', clause)
    expected = (f'제2조(코스닥시장업무규정의시행일)규정제{target.ruleNumber}호코스닥시장업무규정'
        f'({ty}년{tm}월{td}일개정)부칙의"세칙으로정하는날"이란{y}년{m}월{d}일을말한다.')
    own = f'제1조(시행일)이세칙은{y}년{m}월{d}일부터시행한다.'
    if compact != own + expected:
        raise ResearchError('RULE_EFFECTIVE_DELEGATION_CONFLICT')
    return {'effectiveDate': date, 'clauseSha256': digest(clause.encode()),
        'targetRuleNumber': target.ruleNumber, 'targetPromulgatedDate': target.promulgatedDate,
        'delegatingRuleNumber': bylaw.ruleNumber, 'delegatingPromulgatedDate': bylaw.promulgatedDate,
        'targetArticle': '부칙', 'delegatingArticle': '부칙 제2조'}


def review_plan(report):
    plan = []
    for market, value in report['markets'].items():
        for year in range(day(report['startDate']).year, day(report['endDate']).year + 1):
            start = max(report['startDate'], f'{year}-01-01')
            end = min(report['endDate'], f'{year}-12-31')
            dates = [s['businessDate'] for s in report['referencePacks'][market]['sessions'] if start <= s['businessDate'] <= end]
            count = sum(start <= s['businessDate'] <= end for s in value['candidates'])
            plan.append({'market': market, 'startDate': start, 'endDate': end, 'status': 'PENDING',
                'knownExceptionDates': sorted(dates), 'ordinaryCandidateCount': count,
                'inventoryCompletenessConfirmed': False, 'paginationCoverageConfirmed': False,
                'correctionLineageConfirmed': False, 'intradayHaltIsSeparate': True})
    return plan


def build(scope_path, cache, parent_path):
    scope = load_scope(scope_path)
    if digest(read_bytes(parent_path)) != scope.parentSha256:
        raise ResearchError('RULE_EFFECTIVE_PARENT_HASH')
    parent = read_json(read_bytes(parent_path))
    if parent.get('schemaVersion') != 'SAGOPALGO_SESSION_RULE_REPORT_V1':
        raise ResearchError('RULE_EFFECTIVE_PARENT_SCHEMA')
    if read_json(read_bytes(cache / 'index.json')) != {
            'schemaVersion': 'SAGOPALGO_RULE_EFFECTIVE_CAPTURE_PLAN_V1', 'scopeSha256': digest(read_bytes(scope_path)),
            'sources': [s.model_dump() for s in scope.sources]}:
        raise ResearchError('RULE_EFFECTIVE_CAPTURE_SCOPE')
    raws = {s.role: audit_capture(cache, s) for s in scope.sources}
    facts = [identity(s, *raws[s.role]) for s in scope.sources]
    target = next(s for s in scope.sources if s.role == 'ARCHIVED_RULE')
    bylaw = next(s for s in scope.sources if s.role == 'DELEGATING_BYLAW')
    candidates = [v for v in parent['versions'] if v['expected']['bookId'] == scope.targetBookId]
    if len(candidates) != 1:
        raise ResearchError('RULE_EFFECTIVE_TARGET_MISSING')
    prior = candidates[0]
    expected = prior['expected']
    if (expected != {'market': 'KOSDAQ', 'bookId': target.bookId, 'revision': target.revision,
            'ruleNumber': target.ruleNumber, 'effectiveDate': rules.PLACEHOLDER, 'title': target.title}
            or prior['identityConfirmed'] or set(prior['issues']) != {'EFFECTIVE_DATE_PLACEHOLDER', 'RULE_VERSION_MISMATCH'}
            or not parent['startDate'] <= scope.resolvedEffectiveDate <= parent['endDate']):
        raise ResearchError('RULE_EFFECTIVE_PARENT_TARGET_CONFLICT')
    rule_receipt, rule_raw = raws['ARCHIVED_RULE']
    version = rules.Version.model_validate(expected)
    checked = rules.parse_version(version, rule_receipt, rule_raw)
    if checked['issues'] != ['EFFECTIVE_DATE_PLACEHOLDER']:
        raise ResearchError('RULE_EFFECTIVE_TARGET_STILL_MISMATCHED')
    target_appendix = appendix(rule_raw, target.ruleNumber, target.promulgatedDate)
    if re.sub(r'\s+', '', target_appendix) != '이규정은전산프로그램개발에필요한기간등을고려하여세칙으로정하는날부터시행한다.':
        raise ResearchError('RULE_EFFECTIVE_TARGET_DELEGATION')
    resolved = delegated_date(raws['DELEGATING_BYLAW'][1], bylaw, target, scope.resolvedEffectiveDate)
    # A later official edition must independently preserve the same named appendix.
    corroboration = delegated_date(raws['CORROBORATING_BYLAW'][1], bylaw, target, scope.resolvedEffectiveDate)
    if resolved != corroboration:
        raise ResearchError('RULE_EFFECTIVE_CORROBORATION_CONFLICT')
    prior_market = parent['markets']['KOSDAQ']
    known = max([parent['knownAt'], prior_market['knownAt'], *(c['knownAt'] for c in prior_market['candidates']),
                 *(f['knownAt'] for f in facts)], key=utc)
    report = deepcopy(parent)
    report.update(schemaVersion='SAGOPALGO_SESSION_RULE_REPORT_V2', parentRuleReportSha256=scope.parentSha256,
        effectiveScopeSha256=digest(read_bytes(scope_path)), knownAt=known, effectiveEvidence=facts,
        resolvedPriorIssueCounts=deepcopy(parent['issueCounts']), issueCounts={},
        metadataWarnings={'EFFECTIVE_DATE_PLACEHOLDER_PRESERVED': 1},
        resolution={**resolved, 'targetAppendixSha256': digest(target_appendix.encode()),
            'priorBodySha256': prior['bodySha256'], 'correctedBodySha256': rule_receipt['bodySha256'],
            'priorObservationPreserved': True, 'knownAt': known})
    for i, value in enumerate(report['versions']):
        if value['expected']['bookId'] == scope.targetBookId:
            report['versions'][i] = {**checked, 'identityConfirmed': True, 'bodyIdentityConfirmed': True,
                'effectiveDateConfirmed': True, 'resolvedEffectiveDate': scope.resolvedEffectiveDate,
                'sourceIssues': checked['issues'], 'issues': [], 'knownAt': known,
                'effectiveDateBasis': 'ARCHIVED_RULE_AND_DELEGATING_BYLAW_APPENDIX'}
    state = report['markets']['KOSDAQ']
    if any(not v['identityConfirmed'] for v in report['versions']):
        raise ResearchError('RULE_EFFECTIVE_OTHER_REVISION_GAPS')
    versions = [v for v in report['versions'] if v['expected']['market'] == 'KOSDAQ']
    effective = lambda v: v.get('resolvedEffectiveDate', v['expected']['effectiveDate'])
    dates = sorted({effective(v) for v in versions})
    periods = []
    for i, date in enumerate(dates):
        start = max(report['startDate'], date)
        end = (day(dates[i + 1]) - timedelta(days=1)).isoformat() if i + 1 < len(dates) else report['endDate']
        if start <= end:
            periods.append({'startDate': start, 'endDate': end,
                'bookIds': [v['expected']['bookId'] for v in versions if effective(v) == date],
                'nominalOpen': '09:00', 'nominalClose': '15:30', 'continuityConfirmed': True,
                'basis': 'VERIFIED_REVISION_CHAIN_WITH_DELEGATED_DATE'})
    state.update(verifiedVersionCount=len(versions), historicalRuleContinuityConfirmed=True,
        ruleSupportedCandidateCount=len(state['candidates']), rulePeriods=periods, knownAt=known)
    for candidate in state['candidates']:
        candidate.update(ordinaryRuleConfirmed=True, knownAt=known, basis='TEMPORARY_CHANGE_INVENTORY_UNVERIFIED',
            actualSessionConfirmed=False, includedInReferencePack=False)
    report['allOrdinaryRuleChainsConfirmed'] = True
    report['temporaryChangeReviewPlan'] = review_plan(report)
    report.update(allHistoricalSessionsComplete=False, allCalendarFlagsComplete=False,
        usableForTraining=False, usableForStrategyValidation=False, usableForTrading=False)
    # Actual sessions, coverage and calendar evidence remain exactly as observed in V1.
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['capture', 'build', 'audit', 'as-of'])
    p.add_argument('--scope', type=Path)
    p.add_argument('--cache', type=Path)
    p.add_argument('--parent', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--max-new-requests', type=int, default=0)
    p.add_argument('--at')
    p.add_argument('--market', choices=list(rules.TITLES))
    a = p.parse_args()
    try:
        if a.command == 'as-of':
            if not a.output or not a.at or not a.market:
                p.error('--output --at --market required')
            result = rules.as_of(read_json(read_bytes(a.output)), a.at, a.market)
        else:
            if not a.scope or not a.cache:
                p.error('--scope --cache required')
            if a.command == 'capture':
                result = capture(a.scope, a.cache, a.max_new_requests)
            else:
                if not a.parent or not a.output:
                    p.error('--parent --output required')
                report = build(a.scope, a.cache, a.parent)
                immutable_json(a.output, report, a.command == 'audit')
                result = {'status': 'ORDINARY_RULES_CONFIRMED_SESSIONS_PENDING',
                    'sha256': digest(read_bytes(a.output)), 'verifiedVersions': sum(v['identityConfirmed'] for v in report['versions']),
                    'ordinaryRuleChainsConfirmed': True, 'allHistoricalSessionsComplete': False,
                    'temporaryReviewPartitions': len(report['temporaryChangeReviewPlan'])}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except (ResearchError, ValueError, OSError, KeyError) as exc:
        print(json.dumps({'error': str(exc) if isinstance(exc, ResearchError) else 'RULE_EFFECTIVE_INPUT_INVALID'})); return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
