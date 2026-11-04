"""Explicit trading aliases and bilingual issuer fields, never guessed transliterations or legal dates."""
from collections import Counter
import re

from . import name_alias_evidence as capture, name_facts, krx_universe_history as history
from .dataset import canonical, digest, read_bytes
from .distribution_facts import Node
from .kind_cases import compact, one_row, iso_date
from .models import ResearchError, utc


def tables(raw, title):
    root = capture.engine.public.html(raw)
    titles = [v.text() for v in root.walk('div') if v.attrs.get('class') == 'xforms_title']
    titles += [v.text() for v in root.walk('a') if v.attrs.get('name') == '#2']
    values = list(root.walk('table'))
    if [compact(v) for v in titles] != [compact(title)] or len(values) != 1 or '정정신고' in compact(root.text()):
        raise ResearchError('NAME_ALIAS_TITLE_OR_VERSION_REVIEW')
    rows = [[v.text() for v in tr.children if isinstance(v, Node) and v.tag in {'td', 'th'}] for tr in values[0].walk('tr')]
    return rows


def parse_alias(raw):
    rows = tables(raw, '기타시장안내(약명 및 영문명)')
    issuer, stamp = one_row(rows, '1.종목명'), one_row(rows, '3.상장일')
    changes = [r for r in rows if len(r) == 4 and r[:2] == ['보통주', '한글약명']]
    english = [r for r in rows if len(r) == 4 and r[:2] == ['보통주', '영문약명']]
    headers = [r for r in rows if r == ['주권종류', '변경대상', '변경전', '변경후']]
    if len(issuer) != 2 or len(stamp) != 2 or len(changes) != 1 or len(english) > 1 or len(headers) != 1:
        raise ResearchError('NAME_ALIAS_TABLE_REVIEW')
    if not all(changes[0][2:]) or changes[0][2] == changes[0][3]:
        raise ResearchError('NAME_ALIAS_NO_EXPLICIT_CHANGE')
    return {'form': '70792', 'issuerName': issuer[1], 'beforeAlias': changes[0][2], 'afterAlias': changes[0][3],
            'date': iso_date(stamp[1]), 'dateBasis': 'EXCHANGE_TRADING_ALIAS_LISTING_DATE',
            'englishAliasChange': {'before': english[0][2], 'after': english[0][3]} if english else None,
            'englishAliasChangeVerified': False, 'corporateLegalEffectiveDate': None}


def parse_issuer(raw):
    rows = tables(raw, '상호변경안내')
    if (len(rows) < 4 or len(rows[0]) != 4 or [compact(v) for v in rows[0][:3]] != ['1.변경내용', '가.변경전', '국문']
            or len(rows[1]) != 2 or rows[1][0] != '영문' or len(rows[2]) != 3 or rows[2][:2] != ['나. 변경후', '국문']
            or len(rows[3]) != 2 or rows[3][0] != '영문'
            or len([r for r in rows if r and compact(r[0]) == '1.변경내용']) != 1
            or len([r for r in rows if r and compact(r[0]) == '나.변경후']) != 1):
        raise ResearchError('NAME_ALIAS_ISSUER_LAYOUT_REVIEW')
    meeting = one_row(rows, '3.주주총회일')
    if len(meeting) != 2: raise ResearchError('NAME_ALIAS_MEETING_DATE_REVIEW')
    return {'form': '70659', 'beforeKorean': rows[0][3], 'beforeEnglish': rows[1][1], 'afterKorean': rows[2][2], 'afterEnglish': rows[3][1],
            'shareholderMeetingDate': iso_date(meeting[1]), 'shareholderMeetingDateIsListingDate': False,
            'corporateLegalEffectiveDate': None}


def english_key(value):
    if not isinstance(value, str) or not value.strip() or not value.isascii():
        raise ResearchError('NAME_ALIAS_ENGLISH_FIELD_REQUIRED')
    value = re.sub(r'\s+', ' ', value.strip()).upper()
    # Only the explicit English corporate suffix observed in the reviewed form is removed.
    return re.sub(r'\s+INC\.?$', '', value)


def contexts(job, parent, plan):
    config, _, _, latest = history.load_job(job)
    rows = {r['observationId']: r['observation'] for r in parent['rows']}
    result = {}
    for t in plan['targets']:
        result[t['observationId']] = {}
        obs = rows[t['observationId']]
        for side, date_key in [('before', 'observedFrom'), ('after', 'observedTo')]:
            issue = obs[side]
            entry = history.observations(job, config, latest, obs[date_key])[issue['market']]
            selected = [r for r in history.envelope(history.entry_raw(job, entry, entry['seed'])) if r['ISU_CD'] == issue['isin']]
            if (len(selected) != 1 or digest(canonical(selected[0])) != issue['sourceRowSha256']
                    or selected[0]['ISU_SRT_CD'] != issue['symbol'] or selected[0]['ISU_NM'] != issue['name']):
                raise ResearchError('NAME_ALIAS_KRX_CONTEXT_MISMATCH')
            r = selected[0]
            result[t['observationId']][side] = {'symbol': issue['symbol'], 'isin': issue['isin'], 'market': issue['market'],
                'name': r['ISU_NM'], 'abbreviatedName': r['ISU_ABBRV'], 'englishName': r['ISU_ENG_NM'],
                'shareType': r['KIND_STKCERT_TP_NM'], 'securityType': r['SECUGRP_NM'], 'date': obs[date_key],
                'sourceRowSha256': issue['sourceRowSha256'], 'sourceSha256': entry['sha256'], 'knownAt': entry['capturedAt']}
    return result


def check_context(t, context):
    for side in ['before', 'after']:
        c = context[side]
        if ((c['symbol'], c['isin'], c['market'], c['name'], c['date'], c['shareType'], c['securityType'])
                != (t['symbol'], t['isin'], t[side + 'Market'], t[side + 'Name'], t['observedFrom' if side == 'before' else 'observedTo'], '보통주', '주권')):
            raise ResearchError('NAME_ALIAS_KRX_CONTEXT_MISMATCH')
        utc(c['knownAt'])


def alias_fact(parsed, t, context):
    check_context(t, context)
    if not t['observedFrom'] < parsed['date'] <= t['observedTo']:
        raise ResearchError('NAME_ALIAS_LISTING_DATE_CONFLICT')
    issuer = name_facts.name_key(parsed['issuerName'])
    if issuer not in {name_facts.name_key(context[s]['name']) for s in ['before', 'after']}:
        raise ResearchError('NAME_ALIAS_ISSUER_NAME_CONFLICT')
    bindings = {}
    for side in ['before', 'after']:
        alias = name_facts.name_key(parsed[side + 'Alias']); c = context[side]
        if alias != name_facts.name_key(c['abbreviatedName']):
            raise ResearchError('NAME_ALIAS_KRX_ABBREVIATION_CONFLICT')
        if name_facts.name_key(c['name']) not in {issuer, alias}:
            raise ResearchError('NAME_ALIAS_KRX_FULL_NAME_CONFLICT')
        bindings[side] = 'DECLARED_KOREAN_ALIAS' if name_facts.name_key(c['name']) == alias else 'DECLARED_ISSUER_FORMAL_NAME'
    return {**parsed, 'classification': 'EXCHANGE_TRADING_ALIAS_CHANGE', 'nameMatchBasis': bindings,
            'beforeName': t['beforeName'], 'afterName': t['afterName'], 'corporateNameChangeConfirmed': False}


def bridge_fact(parsed, t, context, parent_row):
    check_context(t, context)
    candidates = parent_row['nameReview'].get('candidateVersions', [])
    eligible = [v for v in candidates if v['parsed']['form'] == '70765'
        and t['observedFrom'] < v['parsed']['date'] <= t['observedTo']
        and all(name_facts.name_key(v['parsed'][s + 'Name']) == name_facts.name_key(parsed[s + 'Korean']) for s in ['before', 'after'])]
    if len(eligible) != 1:
        raise ResearchError('NAME_ALIAS_EXISTING_LISTING_EVIDENCE_REQUIRED')
    for side in ['before', 'after']:
        if english_key(context[side]['englishName']) != english_key(parsed[side + 'English']):
            raise ResearchError('NAME_ALIAS_ENGLISH_IDENTITY_CONFLICT')
    if (name_facts.name_key(parsed['afterKorean']) != name_facts.name_key(t['afterName'])
            or parsed['shareholderMeetingDate'] > eligible[0]['parsed']['date']):
        raise ResearchError('NAME_ALIAS_FORMAL_NAME_OR_DATE_CONFLICT')
    return {**parsed, 'classification': 'EXCHANGE_FORMAL_NAME_IDENTITY_BRIDGE', 'beforeName': t['beforeName'], 'afterName': t['afterName'],
        'date': eligible[0]['parsed']['date'], 'dateBasis': 'EXISTING_AUDITED_EXCHANGE_NAME_LISTING_DATE',
        'existingListingEvidence': eligible[0], 'identityBasis': 'TWO_FULL_CODE_VIEWERS_AND_BILINGUAL_NAMES_AND_BOTH_KRX_ENGLISH_FIELDS',
        'englishNormalization': 'ASCII_CASE_WHITESPACE_AND_EXPLICIT_INC_SUFFIX_ONLY', 'corporateLegalEffectiveDate': None}


def build(folder, parent, source_contexts):
    plan, journal, latest = capture.load(folder)
    rows = {r['observationId']: r for r in parent['rows']}
    if set(source_contexts) != {t['observationId'] for t in plan['targets']}:
        raise ResearchError('NAME_ALIAS_CONTEXT_SCOPE_MISMATCH')
    facts, reviews = [], []
    for t in plan['targets']:
        identity = t['observationId']; context = source_contexts[identity]
        _, _, completed, state = capture.inspect(folder, t, latest)
        times = [rows[identity]['knownAt'], *[context[s]['knownAt'] for s in ['before', 'after']]]
        times += [e.get('finishedAt', e.get('capturedAt', e['startedAt'])) for e in journal['attempts'] if e['targetId'] == identity]
        known = max(times, key=utc)
        try:
            if state != 'BODIES_CAPTURED': raise ResearchError(state)
            entry = latest[(identity, 'V0_BODY')]
            if t['mode'] == 'TRADING_ALIAS_NOTICE':
                fact = alias_fact(parse_alias(completed['V0_BODY']), t, context)
            else:
                fact = bridge_fact(parse_issuer(completed['V0_BODY']), t, context, rows[identity])
            facts.append({**fact, 'observationId': identity, 'stockCode': t['symbol'], 'historyIsin': t['isin'], 'market': t['afterMarket'],
                'knownAt': known, 'knowledgeBasis': 'FETCH_TIME_ONLY', 'instrumentContext': context, 'receipt': t['receipt'],
                'sourceUrl': entry['request']['url'], 'sourceSha256': entry['sha256'],
                'acquisitionHashes': {s: latest[(identity, s)]['sha256'] for s in ['V0_VIEWER', 'V0_PATH', 'V0_BODY']},
                'legalMergerCompletionConfirmed': False, 'exchangeRatio': None})
        except (ValueError, KeyError, TypeError) as exc:
            reviews.append({'observationId': identity, 'symbol': t['symbol'], 'knownAt': known,
                            'diagnostic': str(exc) if isinstance(exc, ResearchError) else 'NAME_ALIAS_FACT_INPUT_REVIEW'})
    return {'schemaVersion': 'SAGOPALGO_NAME_ALIAS_FACTS_V1', 'parentSha256': plan['parentSha256'], 'sourceKind': plan['sourceKind'],
            'planId': plan['planId'], 'targets': len(plan['targets']), 'facts': facts, 'reviews': reviews, 'verified': len(facts),
            'reviewRequired': len(reviews), 'classificationCounts': dict(Counter(f['classification'] for f in facts)),
            'allCorporateLegalDatesConfirmed': False, 'usableForTraining': False, 'usableForTrading': False}
