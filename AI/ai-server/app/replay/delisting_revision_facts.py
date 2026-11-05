"""Viewer-linked announcements preserve superseded dates without asserting that they occurred."""
from collections import Counter
import re

from . import delisting_revision_capture as archive, delisting_disclosure_facts as facts
from .dataset import digest
from .distribution_facts import XForms
from .kind_cases import compact, one_row, iso_date
from .models import ResearchError, utc


def announcement(raw, url, target, known, context, corrected):
    """Validate source identity independently of the observation window for historical plans."""
    archive.source.engine.public.validate_url(url); utc(known)
    form = url.rsplit('/', 1)[-1].removesuffix('.htm')
    if form not in {'70769', '68051'} or len(raw) > archive.source.engine.public.LIMIT:
        raise ResearchError('DELISTING_REVISION_FORM_REVIEW')
    expected_market = 'KOSDAQ' if form == '70769' else 'KOSPI'
    if (target['market'], target['kind']) != (expected_market, 'REMOVED_OBSERVED'):
        raise ResearchError('DELISTING_REVISION_MARKET_MISMATCH')
    text = raw.decode('utf-8-sig')
    text = re.sub(r'\A\s*<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1\.0 Transitional//EN" '
                  r'"http://www\.w3\.org/TR/xhtml1/DTD/xhtml1-transitional\.dtd">', '', text, count=1)
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)', text, re.I): raise ResearchError('DELISTING_REVISION_DECLARATION_REVIEW')
    x = XForms(); x.feed(text); x.close()
    if len(x.stack) != 1 or len(list(x.root.walk('html'))) != 1: raise ResearchError('DELISTING_REVISION_HTML_INVALID')
    titles = [v.text() for v in x.root.walk('a') if v.attrs.get('name') == '#2']
    titles += [v.text() for v in x.root.walk('div') if v.attrs.get('class') == 'xforms_title']
    if corrected:
        if sum(compact(v) == '정정신고(보고)' for v in titles) != 1: raise ResearchError('DELISTING_REVISION_CORRECTION_HEADER')
        titles = [v for v in titles if compact(v) != '정정신고(보고)']
    elif any(v in compact(x.root.text()) for v in ['정정신고', '정정공시']):
        raise ResearchError('DELISTING_REVISION_UNDECLARED_CORRECTION')
    if titles != ['상장폐지']: raise ResearchError('DELISTING_REVISION_TITLE_MISMATCH')
    rows = facts.main_rows(raw); issuer = rows[0][1]
    coded = [r for r in rows if 'A' + target['symbol'] in r]
    if not issuer or len(issuer) > 200 or len(coded) != 1 or coded[0][0] not in {'보통주', '보통주식', 'KDR'}:
        raise ResearchError('DELISTING_REVISION_IDENTITY_REVIEW')
    codes = re.findall(r'(?<![A-Za-z0-9])A([A-Z0-9]{6})(?![A-Za-z0-9])', ' '.join(' '.join(r) for r in rows))
    if codes.count(target['symbol']) != 1: raise ResearchError('DELISTING_REVISION_FULL_CODE_REVIEW')
    isins = [v for v in coded[0] if re.fullmatch(r'[A-Z]{2}[A-Z0-9]{10}', v)]
    if len(isins) > 1 or isins and isins[0] != target['isin']: raise ResearchError('DELISTING_REVISION_ISIN_MISMATCH')
    if coded[0][0] == 'KDR' and (context.get('symbol'), context.get('isin'), context.get('securityType'), context.get('shareType')) != (
            target['symbol'], target['isin'], '주식예탁증권', '보통주'):
        raise ResearchError('DELISTING_REVISION_KDR_CONTEXT_REQUIRED')
    rule = one_row(rows, '8.근거규정' if form == '70769' else '7.근거규정')
    if ('코스닥시장' if form == '70769' else '유가증권시장') not in compact(' '.join(rule[1:])):
        raise ResearchError('DELISTING_REVISION_MARKET_RULE_MISMATCH')
    date_row = one_row(rows, '7.상장폐지일' if form == '70769' else '6.상장폐지일')
    if len(date_row) != 2: raise ResearchError('DELISTING_REVISION_DATE_LAYOUT')
    stamp = None if date_row[1] in {'-', '미정', '추후결정', '추후공지'} else iso_date(date_row[1])
    reason = one_row(rows, '5.상장폐지사유' if form == '70769' else '3.상장폐지사유')
    if len(reason) != 2 or not reason[1]: raise ResearchError('DELISTING_REVISION_REASON_REVIEW')
    period = facts.declared_period(rows, form, stamp)
    return {'stockCode': target['symbol'], 'historyIsin': target['isin'], 'sourceIsin': isins[0] if isins else None,
            'market': expected_market, 'form': form, 'sourceShareClass': coded[0][0], 'issuerName': issuer,
            'announcedDelistingDate': stamp, 'sourceDelistingReason': reason[1], 'liquidationTradingPeriod': period,
            'sourceUrl': url, 'sourceSha256': digest(raw), 'knownAt': known,
            'announcedDateOccurredConfirmed': False, 'legalMergerCompletionConfirmed': False}


def build(folder, source_job, contexts, base):
    plan, journal, latest = archive.load(folder, source_job)
    primary, _, primary_latest = archive.source.load(source_job)
    if base['planId'] != primary['planId'] or base['parentSha256'] != plan['parentSha256']:
        raise ResearchError('DELISTING_REVISION_FACT_PARENT_MISMATCH')
    by_id = {f['observationId']: f for f in base['facts']}
    reviews = {r['observationId']: r for r in base['reviews']}
    for t in plan['targets']:
        identity = t['observationId']; context = contexts[identity]
        times = [context['knownAt']] + [v['knownAt'] for v in t['viewerSources']]
        times += [d['seed']['knownAt'] for d in t['documents'] if d['seed']]
        times += [e.get('finishedAt', e.get('capturedAt', e['startedAt'])) for e in journal['attempts'] if e['targetId'] == identity]
        known = max(times, key=utc); versions = []
        try:
            docs = t['documents']
            if docs[0]['corrected'] or any(not d['corrected'] for d in docs[1:]) or not docs[-1]['active']:
                raise ResearchError('DELISTING_REVISION_ORDER_REVIEW')
            if any(a['publicationDate'] > b['publicationDate'] for a, b in zip(docs, docs[1:])):
                raise ResearchError('DELISTING_REVISION_PUBLICATION_ORDER_REVIEW')
            for d in docs:
                _, _, completed, state, url = archive.inspect(folder, source_job, t, d, latest)
                if state != 'CAPTURED': raise ResearchError('DELISTING_REVISION_' + state)
                notice = announcement(completed['BODY'], url, t, known, context, d['corrected'])
                versions.append({**d, 'announcement': notice,
                    'dateRole': 'CURRENT_ANNOUNCEMENT' if d['active'] else 'SUPERSEDED_ANNOUNCEMENT'})
            keys = ['stockCode', 'historyIsin', 'sourceIsin', 'market', 'form', 'sourceShareClass']
            if any(any(v['announcement'][k] != versions[0]['announcement'][k] for k in keys) for v in versions):
                raise ResearchError('DELISTING_REVISION_IDENTITY_CHANGED')
            current = docs[-1]; _, _, completed, _, url = archive.inspect(folder, source_job, t, current, latest)
            viewer = archive.source.engine.public.html(archive.read_bytes(source_job/'raw'/f"{t['viewerSources'][0]['seq']:04d}.bin"))
            name = next(v.text() for v in viewer.walk('h1') if v.text().endswith('('+t['symbol']+')'))
            fact = facts.parse_fact(completed['BODY'], url, t, known, name, context, current['corrected'])
            if fact['date'] != t['statusDate']: raise ResearchError('DELISTING_REVISION_CURRENT_STATUS_DATE_CONFLICT')
            by_id[identity] = {**fact, 'statusDate': t['statusDate'], 'statusReferenceId': t['statusReferenceId'],
                'statusEventType': t['statusEventType'], 'versions': versions, 'revisionPlanId': plan['planId'],
                'viewerSources': t['viewerSources'], 'currentDocument': current['document'],
                'correctionPolicy': 'VIEWER_LINKED_COMPLETE_CHAIN_ACTIVE_Y_CURRENT_DATE_MATCHES_OBSERVED_REMOVAL',
                'announcedDateChangedByCorrection': any(v['announcement']['announcedDelistingDate'] != fact['date'] for v in versions),
                'supersededDatesOccurredConfirmed': False, 'otherCorrectionContentInterpreted': False}
            reviews.pop(identity, None)
        except (ValueError, KeyError, TypeError, StopIteration) as exc:
            by_id.pop(identity, None)
            reviews[identity] = {'observationId': identity, 'symbol': t['symbol'], 'market': t['market'], 'knownAt': known,
                'candidateVersions': versions, 'diagnostic': str(exc) if isinstance(exc, ResearchError) else 'DELISTING_REVISION_FACT_INPUT_REVIEW'}
    ordered_facts = [by_id[t['observationId']] for t in primary['targets'] if t['observationId'] in by_id]
    ordered_reviews = [reviews[t['observationId']] for t in primary['targets'] if t['observationId'] in reviews]
    return {**base, 'revisionPlanId': plan['planId'], 'facts': ordered_facts, 'reviews': ordered_reviews,
            'verified': len(ordered_facts), 'reviewRequired': len(ordered_reviews),
            'formCounts': dict(Counter(f['form'] for f in ordered_facts)),
            'liquidationPeriodCounts': dict(Counter(f['liquidationTradingPeriod']['status'] for f in ordered_facts)),
            'revisionTargets': len(plan['targets']), 'revisionVerified': sum('revisionPlanId' in f for f in ordered_facts)}
