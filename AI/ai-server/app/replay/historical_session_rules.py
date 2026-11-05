"""Audit KRX historical rule identities before using ordinary session hours.

Nominal rule continuity is separate from an exhaustive temporary-change review.
This supplement never promotes ordinary candidates to actual session evidence.
"""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import re
import time
from typing import Literal
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar

from pydantic import Field, model_validator

from . import market_calendar_evidence as calendar
from .dataset import canonical, digest, read_bytes, read_json
from .history import day, now, NoRedirect, job_lock
from .krx_baseline_validation import immutable_json
from .krx_storage import atomic_json
from .models import ResearchError, StrictModel, utc

INDEX = 'https://rule.krx.co.kr/out/index.do'
VIEW = 'https://rule.krx.co.kr/out/regulation/regulationViewPop.do'
LIMIT = 3 * 1024 * 1024
TITLES = {'KOSPI': '유가증권시장 업무규정', 'KOSDAQ': '코스닥시장 업무규정'}
PLACEHOLDER = '9999-12-31'


class Version(StrictModel):
    market: Literal['KOSPI', 'KOSDAQ']
    bookId: str = Field(pattern=r'^[0-9]{6,10}$')
    revision: int = Field(ge=1, le=300)
    ruleNumber: str = Field(pattern=r'^[0-9]{1,5}$')
    effectiveDate: str
    title: str

    @model_validator(mode='after')
    def valid(self):
        if self.title != TITLES[self.market]:
            raise ValueError('market title mismatch')
        if self.effectiveDate != PLACEHOLDER:
            day(self.effectiveDate)
        return self


class Scope(StrictModel):
    schemaVersion: Literal['SAGOPALGO_SESSION_RULE_SCOPE_V1']
    startDate: str
    endDate: str
    parentSha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    anchors: dict[str, str]
    versions: list[Version] = Field(min_length=2, max_length=40)

    @model_validator(mode='after')
    def valid(self):
        if day(self.startDate) > day(self.endDate) or set(self.anchors) != set(TITLES):
            raise ValueError('invalid rule scope')
        if len({v.bookId for v in self.versions}) != len(self.versions):
            raise ValueError('duplicate book identity')
        for market in TITLES:
            rows = sorted([v for v in self.versions if v.market == market], key=lambda v: v.revision)
            if not rows or [v.revision for v in rows] != list(range(rows[0].revision, rows[-1].revision + 1)):
                raise ValueError('revision chain gap')
            if self.anchors[market] != rows[-1].bookId or not rows[0].effectiveDate <= self.startDate:
                raise ValueError('missing baseline or latest anchor')
            if any(v.effectiveDate > self.endDate and v.effectiveDate != PLACEHOLDER for v in rows):
                raise ValueError('rule outside reviewed period')
        return self


def load_scope(path):
    return Scope.model_validate(read_json(read_bytes(path)))


def parameters(book):
    return {'bookid': book, 'noformyn': 'N'}


def audit_capture(cache, book):
    folder = cache / book
    e = read_json(read_bytes(folder / 'receipt.json'))
    if e.get('status') != 'COMPLETE':
        raise ResearchError('RULE_CAPTURE_INCOMPLETE')
    raw = read_bytes(folder / 'body.html')
    fields = {'schemaVersion', 'url', 'method', 'parameters', 'status', 'startedAt', 'capturedAt',
              'bodySha256', 'newRequests', 'knowledgeBasis'}
    if (set(e) != fields or e['schemaVersion'] != 'SAGOPALGO_RULE_CAPTURE_V1' or e['url'] != VIEW
            or e['method'] != 'POST' or e['parameters'] != parameters(book)
            or type(e['newRequests']) is not int or e['newRequests'] not in {0, 1}
            or e['knowledgeBasis'] != 'FETCH_TIME_ONLY' or utc(e['startedAt']) > utc(e['capturedAt'])
            or len(raw) > LIMIT or digest(raw) != e['bodySha256']):
        raise ResearchError('RULE_CAPTURE_TAMPERED')
    return e, raw


def seed_capture(cache, book, raw, origin):
    """Import an existing public POST receipt, preserving the original fetch time."""
    if (origin.get('url') != VIEW or origin.get('method') != 'POST' or origin.get('parameters') != parameters(book)
            or origin.get('status') != 'COMPLETE' or origin.get('httpStatus') != 200
            or origin.get('sha256') != digest(raw) or len(raw) > LIMIT
            or utc(origin['startedAt']) > utc(origin['capturedAt'])):
        raise ResearchError('RULE_SEED_INVALID')
    folder = cache / book
    folder.mkdir(parents=True, exist_ok=False)
    (folder / 'body.html').write_bytes(raw)
    atomic_json(folder / 'receipt.json', {
        'schemaVersion': 'SAGOPALGO_RULE_CAPTURE_V1', 'url': VIEW, 'method': 'POST', 'parameters': parameters(book),
        'status': 'COMPLETE', 'startedAt': origin['startedAt'], 'capturedAt': origin['capturedAt'],
        'bodySha256': digest(raw), 'newRequests': 0, 'knowledgeBasis': 'FETCH_TIME_ONLY'})
    return audit_capture(cache, book)[0]


def capture(scope_path, cache, budget, opener=None, sleep=time.sleep):
    """Bounded public form acquisition. A failed reservation is never auto-retried."""
    scope = load_scope(scope_path)
    if type(budget) is not int or not 0 <= budget <= 41:
        raise ResearchError('RULE_CAPTURE_BUDGET_INVALID')
    cache.mkdir(parents=True, exist_ok=True)
    with job_lock(cache):
        immutable_json(cache / 'index.json', {'schemaVersion': 'SAGOPALGO_RULE_CAPTURE_PLAN_V1',
            'scopeSha256': digest(read_bytes(scope_path)), 'books': [v.bookId for v in scope.versions]})
        missing = []
        for v in scope.versions:
            if (cache / v.bookId).exists():
                audit_capture(cache, v.bookId)
            else:
                missing.append(v.bookId)
        if not missing:
            return {'sources': len(scope.versions), 'newRequests': 0, 'reused': len(scope.versions)}
        if budget < len(missing) + 1:
            raise ResearchError('RULE_CAPTURE_BUDGET_TOO_SMALL')
        bootstrap = cache / 'public-form.json'
        if bootstrap.exists():
            raise ResearchError('RULE_CAPTURE_ATTEMPT_EXISTS')
        client = opener or build_opener(HTTPCookieProcessor(CookieJar()), NoRedirect())
        # Cookies and the public form nonce live in memory, never in receipts or logs.
        started = now()
        atomic_json(bootstrap, {'url': INDEX, 'status': 'RESERVED', 'startedAt': started})
        try:
            with client.open(Request(INDEX, headers={'User-Agent': 'SagoPalgo-Personal-Research/1.0'}), timeout=20) as response:
                raw = response.read(LIMIT + 1)
                if response.status != 200 or len(raw) > LIMIT:
                    raise ResearchError('RULE_FORM_RESPONSE_INVALID')
            nonce = re.findall(rb'<meta id="_csrf" name="_csrf" content="([a-zA-Z0-9-]{1,100})">', raw)
            if len(nonce) != 1:
                raise ResearchError('RULE_FORM_LAYOUT_UNSUPPORTED')
            atomic_json(bootstrap, {'url': INDEX, 'status': 'COMPLETE', 'startedAt': started,
                'capturedAt': now(), 'bodySha256': digest(raw), 'newRequests': 1})
        except Exception:
            raise ResearchError('RULE_FORM_CAPTURE_FAILED') from None
        previous = started
        for book in missing:
            elapsed = (utc(now()) - utc(previous)).total_seconds()
            if elapsed < 0:
                raise ResearchError('RULE_CAPTURE_CLOCK_REGRESSION')
            if elapsed < 1:
                sleep(1 - elapsed)
            started = now()
            folder = cache / book
            folder.mkdir()
            atomic_json(folder / 'receipt.json', {'status': 'RESERVED', 'startedAt': started, 'parameters': parameters(book)})
            data = urlencode({**parameters(book), '_csrf': nonce[0].decode()}).encode()
            try:
                request = Request(VIEW, data=data, headers={'User-Agent': 'SagoPalgo-Personal-Research/1.0',
                    'Content-Type': 'application/x-www-form-urlencoded', 'Referer': INDEX})
                with client.open(request, timeout=20) as response:
                    raw = response.read(LIMIT + 1)
                    if response.status != 200 or len(raw) > LIMIT:
                        raise ResearchError('RULE_RESPONSE_INVALID')
                captured = now()
                (folder / 'body.html').write_bytes(raw)
                atomic_json(folder / 'receipt.json', {'schemaVersion': 'SAGOPALGO_RULE_CAPTURE_V1',
                    'url': VIEW, 'method': 'POST', 'parameters': parameters(book), 'status': 'COMPLETE',
                    'startedAt': started, 'capturedAt': captured, 'bodySha256': digest(raw),
                    'newRequests': 1, 'knowledgeBasis': 'FETCH_TIME_ONLY'})
                audit_capture(cache, book)
                previous = started
            except Exception:
                raise ResearchError('RULE_SOURCE_CAPTURE_FAILED') from None
        return {'sources': len(scope.versions), 'newRequests': len(missing) + 1, 'reused': len(scope.versions) - len(missing)}


def html_text(value):
    parser = calendar.kind.NoticeText()
    parser.feed(value)
    return re.sub(r'\s+', ' ', ' '.join(parser.parts)).strip()


def history(raw):
    """Read the complete version list, not dates embedded in navigation or URLs."""
    s = raw.decode('utf-8-sig')
    try:
        s = s[s.rindex('layerViewW'):s.index('class="lawbon"')]
    except ValueError:
        raise ResearchError('RULE_HISTORY_LAYOUT_UNSUPPORTED') from None
    pattern = (r"goRegulationView\('([0-9]+)','N', '제([0-9]+)차'\).*?<b[^>]*>(.*?)</b>"
               r'.*?<div style="color:rgba.*?">(.*?)</div>')
    rows = []
    for book, rev, title, label in re.findall(pattern, s, re.S):
        stamp = re.findall(r'([0-9]{4})\.\s*([0-9]{1,2})\.\s*([0-9]{1,2})\.', label)
        number = re.findall(r'제([0-9]+)호', label)
        if len(stamp) != 1 or len(number) != 1:
            raise ResearchError('RULE_HISTORY_IDENTITY_AMBIGUOUS')
        effective = '%04d-%02d-%02d' % tuple(map(int, stamp[0]))
        rows.append({'bookId': book, 'revision': int(rev), 'ruleNumber': number[0],
                     'effectiveDate': effective, 'title': html_text(title)})
    if not rows or len({r['bookId'] for r in rows}) != len(rows) or len({r['revision'] for r in rows}) != len(rows):
        raise ResearchError('RULE_HISTORY_IDENTITY_AMBIGUOUS')
    return rows


def parse_version(version, receipt, raw):
    s = raw.decode('utf-8-sig')
    # Exclude the history menu: it lists every requested title/date even if the body is wrong.
    try:
        body = s[s.index('class="lawbon"'):]
    except ValueError:
        raise ResearchError('RULE_BODY_LAYOUT_UNSUPPORTED') from None
    titles = re.findall(r'<p class="title">(.*?)</p>', body, re.S)
    headers = re.findall(r'<p class="jang"[^>]*>\[(.*?)</p>', body, re.S)
    revisions = re.findall(r'<p class="selBox"[^>]*>(?:\(타\))?제([0-9]+)차', body)
    if len(titles) != 1 or len(headers) != 1 or len(revisions) != 1:
        raise ResearchError('RULE_BODY_IDENTITY_AMBIGUOUS')
    header = html_text(headers[0])
    metadata = re.fullmatch(r'.*?([0-9]{4})\.\s*([0-9]{1,2})\.\s*([0-9]{1,2})\.? 규정 제([0-9]+)호 <시행일\s*:\s*([0-9]{4})\.\s*([0-9]{1,2})\.\s*([0-9]{1,2})\.?\s*>\]', header)
    if not metadata:
        raise ResearchError('RULE_BODY_HEADER_UNSUPPORTED')
    y, m, d, number, ey, em, ed = metadata.groups()
    observed = {'title': html_text(titles[0]), 'revision': int(revisions[0]), 'ruleNumber': number,
        'promulgatedDate': '%04d-%02d-%02d' % (int(y), int(m), int(d)),
        'effectiveDate': '%04d-%02d-%02d' % (int(ey), int(em), int(ed))}
    issues = []
    if version.effectiveDate == PLACEHOLDER:
        issues.append('EFFECTIVE_DATE_PLACEHOLDER')
    if any(observed[k] != getattr(version, k) for k in ['title', 'revision', 'ruleNumber', 'effectiveDate']):
        issues.append('RULE_VERSION_MISMATCH')
    # Inspect exactly article 4 before article 5. No menu, appendix, order-acceptance or after-hours match.
    articles = re.findall(r'<a name="bon4".*?(?=<a name="bon5")', body, re.S)
    if len(articles) != 1:
        raise ResearchError('RULE_ARTICLE_AMBIGUOUS')
    article = html_text(articles[0])
    pattern = (r'1\. 정규시장\s*:\s*9시부터\s*15시\s*30분(?=\()' if version.market == 'KOSPI' else
               r'1\. 정규시장\s*:\s*(?:오전 9시부터 오후 3시\s*30분|9시부터\s*15시\s*30분)(?=\()')
    matches = re.findall(pattern, article)
    if len(matches) != 1 or '임시로 변경' not in article or not article.startswith('제4조(시장의 구분 및 매매거래시간)'):
        raise ResearchError('RULE_REGULAR_HOURS_UNSUPPORTED')
    books = re.findall(r"printJo\('([0-9]+)','[0-9]+','bon4'\)", body)
    if books != [version.bookId] and 'RULE_VERSION_MISMATCH' not in issues:
        issues.append('RULE_VERSION_MISMATCH')
    if observed['effectiveDate'] != PLACEHOLDER:
        day(observed['effectiveDate'])
    day(observed['promulgatedDate'])
    if observed['promulgatedDate'] > observed['effectiveDate']:
        issues.append('RULE_EFFECTIVE_DATE_CONFLICT')
    return {'expected': version.model_dump(), 'observed': observed, 'identityConfirmed': not issues,
        'issues': issues, 'nominalOpen': '09:00', 'nominalClose': '15:30',
        'temporaryChangesPermitted': True, 'closingAuctionMayExtend': '당해 가격이 결정되는 시점' in article,
        'article4Sha256': digest(article.encode()), 'sourceUrl': VIEW, 'requestParameters': parameters(version.bookId),
        'bodySha256': receipt['bodySha256'], 'knownAt': receipt['capturedAt'],
        'effectiveDateBasis': 'PORTAL_BODY_HEADER', 'historicalPublicationTimeConfirmed': False}


def build(scope_path, cache, parent_path):
    scope = load_scope(scope_path)
    parent = read_json(read_bytes(parent_path))
    if digest(read_bytes(parent_path)) != scope.parentSha256:
        raise ResearchError('RULE_PARENT_HASH_MISMATCH')
    if (parent.get('schemaVersion') != 'SAGOPALGO_MARKET_CALENDAR_REPORT_V1'
            or parent.get('startDate') != scope.startDate or parent.get('endDate') != scope.endDate):
        raise ResearchError('RULE_PARENT_SCOPE_MISMATCH')
    index = read_json(read_bytes(cache / 'index.json'))
    if index != {'schemaVersion': 'SAGOPALGO_RULE_CAPTURE_PLAN_V1', 'scopeSha256': digest(read_bytes(scope_path)),
                 'books': [v.bookId for v in scope.versions]}:
        raise ResearchError('RULE_CAPTURE_SCOPE_MISMATCH')
    receipts = {v.bookId: audit_capture(cache, v.bookId) for v in scope.versions}
    parsed = [parse_version(v, *receipts[v.bookId]) for v in scope.versions]
    markets = {}
    for market in TITLES:
        expected = [v for v in scope.versions if v.market == market]
        baseline = min(v.revision for v in expected)
        listed = history(receipts[scope.anchors[market]][1])
        chain = [v for v in listed if v['revision'] >= baseline]
        wanted = [{k: v.model_dump()[k] for k in ['bookId', 'revision', 'ruleNumber', 'effectiveDate', 'title']} for v in expected]
        if sorted(chain, key=lambda v: v['revision']) != sorted(wanted, key=lambda v: v['revision']):
            raise ResearchError('RULE_HISTORY_SCOPE_GAP')
        # Baseline must be the latest listed revision effective before the requested start.
        if any(v['revision'] > baseline and v['effectiveDate'] <= scope.startDate for v in listed):
            raise ResearchError('RULE_HISTORY_BASELINE_INVALID')
        facts = [v for v in parsed if v['expected']['market'] == market]
        confirmed = all(v['identityConfirmed'] for v in facts)
        dates = sorted({v.effectiveDate for v in expected if v.effectiveDate != PLACEHOLDER})
        periods = []
        for i, start in enumerate(dates):
            end = (day(dates[i + 1]) - timedelta(days=1)).isoformat() if i + 1 < len(dates) else scope.endDate
            start = max(start, scope.startDate)
            if end < start:
                continue
            ids = [v.bookId for v in expected if v.effectiveDate == dates[i]]
            periods.append({'startDate': start, 'endDate': end, 'bookIds': ids,
                'nominalOpen': '09:00', 'nominalClose': '15:30', 'continuityConfirmed': confirmed,
                'basis': 'VERIFIED_REVISION_CHAIN' if confirmed else 'UNCONFIRMED_REVISION_CHAIN'})
        known = max((v['knownAt'] for v in facts), key=utc)
        candidates = deepcopy(parent['sessionCandidates'][market])
        for candidate in candidates:
            candidate.update(ordinaryRuleConfirmed=confirmed, knownAt=max([candidate['knownAt'], known], key=utc),
                basis='TEMPORARY_CHANGE_INVENTORY_UNVERIFIED' if confirmed else 'RULE_REVISION_REVIEW_REQUIRED',
                actualSessionConfirmed=False, includedInReferencePack=False)
        markets[market] = {'versionCount': len(facts), 'verifiedVersionCount': sum(v['identityConfirmed'] for v in facts),
            'historicalRuleContinuityConfirmed': confirmed, 'rulePeriods': periods, 'knownAt': known,
            'ordinaryCandidateCount': len(candidates), 'ruleSupportedCandidateCount': len(candidates) if confirmed else 0,
            'temporaryChangeInventoryComplete': False, 'candidates': candidates,
            'explicitSessionsUnchanged': len(parent['referencePacks'][market]['sessions'])}
    return {'schemaVersion': 'SAGOPALGO_SESSION_RULE_REPORT_V1', 'startDate': scope.startDate, 'endDate': scope.endDate,
        'scopeSha256': digest(read_bytes(scope_path)), 'parentSha256': digest(read_bytes(parent_path)),
        'knownAt': max((v['knownAt'] for v in parsed), key=utc), 'versions': parsed, 'markets': markets,
        'issueCounts': dict(Counter(issue for v in parsed for issue in v['issues'])),
        'referencePacks': deepcopy(parent['referencePacks']), 'allHistoricalSessionsComplete': False,
        'allCalendarFlagsComplete': False, 'usableForTraining': False, 'usableForStrategyValidation': False, 'usableForTrading': False}


def as_of(report, at, market):
    cutoff = utc(at)
    if market not in TITLES:
        raise ResearchError('RULE_MARKET_INVALID')
    m = report['markets'][market]
    return {'market': market, 'rulePeriods': deepcopy(m['rulePeriods']) if utc(m['knownAt']) <= cutoff else [],
        'ordinaryCandidates': [deepcopy(v) for v in m['candidates'] if utc(v['knownAt']) <= cutoff],
        'actualSessions': [deepcopy(v) for v in report['referencePacks'][market]['sessions'] if utc(v['knownAt']) <= cutoff],
        'allHistoricalSessionsComplete': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['capture', 'build', 'audit', 'as-of'])
    p.add_argument('--scope', type=Path)
    p.add_argument('--cache', type=Path)
    p.add_argument('--parent', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--max-new-requests', type=int, default=0)
    p.add_argument('--at')
    p.add_argument('--market', choices=list(TITLES))
    a = p.parse_args()
    try:
        if a.command == 'as-of':
            if not a.output or not a.at or not a.market:
                p.error('as-of requires --output --at --market')
            result = as_of(read_json(read_bytes(a.output)), a.at, a.market)
        else:
            if not a.scope or not a.cache:
                p.error('--scope --cache required')
            if a.command == 'capture':
                result = capture(a.scope, a.cache, a.max_new_requests)
            else:
                if not a.parent or not a.output:
                    p.error('--parent --output required')
                result = build(a.scope, a.cache, a.parent)
                immutable_json(a.output, result, a.command == 'audit')
                result = {'status': 'VERIFIED_WITH_GAPS', 'sha256': digest(read_bytes(a.output)),
                    'verifiedVersions': sum(v['identityConfirmed'] for v in result['versions']),
                    'issues': result['issueCounts'], 'allHistoricalSessionsComplete': False}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except (ResearchError, ValueError, OSError, KeyError) as exc:
        code = str(exc) if isinstance(exc, ResearchError) else 'RULE_INPUT_INVALID'
        print(json.dumps({'error': code})); return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
