"""Audited first-phase membership facts, retaining unsupported forms, revisions and conflicts."""
from collections import Counter
import re

from . import listing_disclosure_coverage as capture, membership_evidence_facts as parser
from .dataset import canonical, digest
from .models import ResearchError, utc
from .kind_cases import compact, iso_date, one_row, scalar_date
from .distribution_facts import Node


def parse_fact(raw, url, target, known, viewer_name, context, corrected=False):
    if not url.endswith('/68152.htm'):
        return parser.parse_fact(raw, url, target, known, viewer_name, context, corrected)
    capture.engine.public.validate_url(url)
    if (target['market'], target['kind']) != ('KOSPI', 'ADDED_OBSERVED'):
        raise ResearchError('LISTING_KOSPI_MARKET_OR_DIRECTION_CONFLICT')
    text = capture.engine.public.html(raw).text()
    if corrected or '정정신고' in compact(text) or '정정공시' in compact(text):
        raise ResearchError('LISTING_KOSPI_CORRECTION_REVIEW')
    reit_note = '◎ (동 주권은 부동산투자회사법에 의한 부동산투자회사 주권임)'
    reit_notice = reit_note in text
    if text.count(reit_note) > 1: raise ResearchError('LISTING_KOSPI_REIT_NOTE_AMBIGUOUS')
    text = text.replace(reit_note, '', 1)
    names = re.findall(r'^◎\s*(.+?)\s*(?:부동산투자회사\s+)?주권\s*신규상장\s*(?:상장)?내역\s*(?:◎\s*)?①\s*상장종목(?:명)?\s*-\s*한글종목명\s*:\s*(.+?)\s*-\s*영문종목명\s*:', text)
    dates = re.findall(r'②\s*상장일\s*:\s*([0-9]{4})년\s*([0-9]{1,2})월\s*([0-9]{1,2})일\s*③', text)
    identities = re.findall(r'④\s*표준코드\s*:\s*([A-Z]{2}[A-Z0-9]{10})\s*\(단축코드\s*:\s*A([A-Z0-9]{6})\)', text)
    shares = re.findall(r'⑤\s*주식의\s*종류와\s*수\s*(?::\s*(?:-\s*)?(?:기명식\s*)?보통주\s+[0-9,]+주|-\s*(?:기명식\s*)?보통주\s*(?::\s*)?[0-9,]+주)', text)
    if len(names) != 1 or len(dates) != 1 or len(identities) != 1 or len(shares) != 1 or identities[0] != (target['isin'], target['symbol']):
        raise ResearchError('LISTING_KOSPI_68152_IDENTITY_OR_LAYOUT_REVIEW')
    stamp = '%04d-%02d-%02d' % tuple(map(int, dates[0])); iso_date(stamp)
    if not target['observedFrom'] < stamp <= target['observedTo']:
        raise ResearchError('MEMBERSHIP_FACT_DATE_CONFLICT')
    return {'observationId': target['observationId'], 'kind': 'MEMBERSHIP_ENTRY', 'stockCode': target['symbol'],
        'historyIsin': target['isin'], 'sourceIsin': identities[0][0], 'isinProvided': True, 'market': 'KOSPI',
        'issuerName': names[0][0], 'sourceListingName': names[0][1], 'viewerIssuerName': viewer_name,
        'date': stamp, 'dateBasis': 'EXCHANGE_LISTING_DATE', 'marketBasis': 'REVIEWED_KOSPI_PLAIN_TEXT_FORM_CODE',
        'identityBasis': 'VIEWER_FULL_STOCK_CODE_AND_SOURCE_ISIN', 'form': '68152',
        'formPolicy': 'REVIEWED_KOSPI_68152_LAYOUT_VARIANTS_V1', 'reitNoticePresent': reit_notice, 'knownAt': known, 'knowledgeBasis': 'FETCH_TIME_ONLY',
        'sourceUrl': url, 'sourceSha256': digest(raw), 'sourceShareClass': '보통주', 'instrumentContext': context,
        'reviewedCorrection': False, 'legalMergerCompletionConfirmed': False, 'firstEverIpoConfirmed': False, 'exchangeRatio': None}


def zero_duplicate_original(raw, corrected_raw, target, corrected_fact, url, corrected_document):
    """Only an original zero row removed in its fully validated correction can be bridged."""
    def main_rows(value):
        root = capture.engine.public.html(value); tables = []
        for table in root.walk('table'):
            rows = [[v.text() for v in tr.children if isinstance(v, Node) and v.tag in {'td', 'th'}] for tr in table.walk('tr')]
            if rows and rows[0] and compact(rows[0][0]) == '1.회사명':
                if list(table.walk('table')): raise ResearchError('LISTING_ZERO_DUPLICATE_LAYOUT_REVIEW')
                tables.append(rows)
        if len(tables) != 1: raise ResearchError('LISTING_ZERO_DUPLICATE_LAYOUT_REVIEW')
        return tables[0]
    if target['market'] != 'KOSDAQ' or corrected_fact['form'] != '70760' or not corrected_fact['reviewedCorrection']:
        raise ResearchError('LISTING_ZERO_DUPLICATE_SCOPE_REVIEW')
    before, after = main_rows(raw), main_rows(corrected_raw)
    code = 'A' + target['symbol']; old_rows = [r for r in before if code in r]; new_rows = [r for r in after if code in r]
    if (len(old_rows) != 2 or len(new_rows) != 1 or any(len(r) != 4 or r[:3] != ['보통주', target['isin'], code]
            or not re.fullmatch(r'[0-9,]+', r[3]) for r in old_rows + new_rows)):
        raise ResearchError('LISTING_ZERO_DUPLICATE_IDENTITY_REVIEW')
    zero = [r for r in old_rows if int(r[3].replace(',', '')) == 0]
    positive = [r for r in old_rows if int(r[3].replace(',', '')) > 0]
    if (len(zero) != 1 or len(positive) != 1 or positive != new_rows
            or one_row(before, '1.회사명') != one_row(after, '1.회사명')
            or scalar_date(before, '10.상장일(매매개시일)') != corrected_fact['date']
            or scalar_date(after, '10.상장일(매매개시일)') != corrected_fact['date']):
        raise ResearchError('LISTING_ZERO_DUPLICATE_CORRECTION_REVIEW')
    return {**corrected_fact, 'sourceUrl': url, 'sourceSha256': digest(raw), 'reviewedCorrection': False,
        'zeroDuplicateCommonShareRowReviewed': True, 'zeroDuplicateRowSha256': digest(canonical(zero[0])),
        'unchangedNonzeroStockRowSha256': digest(canonical(positive[0])), 'validatedAgainstCorrectionDocument': corrected_document,
        'zeroDuplicatePolicy': 'ORIGINAL_ZERO_ROW_REMOVED_WITH_IDENTICAL_NONZERO_ROW_AND_MEMBERSHIP_DATE'}


def build(folder, contexts):
    plan, journal, latest = capture.load(folder)
    if set(contexts) != {t['observationId'] for t in plan['targets']}:
        raise ResearchError('LISTING_FACT_CONTEXT_SCOPE_MISMATCH')
    facts, reviews = [], []
    for t in plan['targets']:
        identity = t['observationId']; context = contexts[identity]
        times = [context['knownAt']]
        times += [e.get('finishedAt', e.get('capturedAt', e['startedAt'])) for e in journal['attempts'] if e['targetId'] == identity]
        known = max(times, key=utc)
        _, _, completed, state = capture.inspect(folder, t, latest)
        versions = []
        try:
            if state != 'BODIES_CAPTURED': raise ResearchError(state)
            for index, candidate in enumerate(capture.candidates(completed['SEARCH'])):
                label = 'V' + str(index); v = capture.viewer(completed[label + '_VIEWER'], t, candidate)
                entry = latest[(identity, label + '_BODY')]
                version = {**candidate, **v, 'stageLabel': label, 'sourceUrl': entry['request']['url'], 'sourceSha256': entry['sha256'],
                    'acquisitionHashes': {s: latest[(identity, s)]['sha256'] for s in ['SEARCH', label + '_VIEWER', label + '_PATH', label + '_BODY']}}
                try:
                    p = parse_fact(completed[label + '_BODY'], entry['request']['url'], t, known, v['viewerIssuerName'], context, candidate['corrected'])
                    if p['date'] != t['statusDate']: raise ResearchError('LISTING_FACT_STATUS_DATE_CONFLICT')
                    version['fact'] = p
                except (ValueError, KeyError, TypeError) as exc:
                    version['diagnostic'] = str(exc) if isinstance(exc, ResearchError) else 'LISTING_FACT_FORM_INPUT_REVIEW'
                versions.append(version)
            valid = [v for v in versions if 'fact' in v]
            if not valid:
                diagnostics = {v['diagnostic'] for v in versions}
                raise ResearchError(next(iter(diagnostics)) if len(diagnostics) == 1 else 'LISTING_FACT_CANDIDATE_REVIEW')
            histories = {tuple(sorted(v['documents'])) for v in valid}
            if len(histories) != 1: raise ResearchError('LISTING_FACT_MULTIPLE_VALID_DISCLOSURES')
            docs = set(next(iter(histories))); chain = [v for v in versions if v['document'] in docs]
            if (set(v['document'] for v in chain) != docs or len(chain) != len(docs)
                    or any(set(v['documents']) != docs for v in chain)
                    or len([v for v in chain if not v['corrected']]) != 1
                    or chain[0]['corrected'] or any(not v['corrected'] for v in chain[1:])):
                raise ResearchError('LISTING_FACT_VERSION_LINEAGE_REVIEW')
            if (len(chain) == 2 and 'fact' not in chain[0] and 'fact' in chain[1]
                    and chain[0].get('diagnostic') == 'MEMBERSHIP_FACT_FULL_CODE_OR_SHARE_CLASS_MISMATCH'):
                try:
                    chain[0]['fact'] = zero_duplicate_original(completed[chain[0]['stageLabel'] + '_BODY'],
                        completed[chain[1]['stageLabel'] + '_BODY'], t, chain[1]['fact'], chain[0]['sourceUrl'], chain[1]['document'])
                    chain[0].pop('diagnostic')
                except ResearchError:
                    pass
            if any('fact' not in v for v in chain): raise ResearchError('LISTING_FACT_CORRECTION_CONFLICT')
            fields = ['stockCode', 'historyIsin', 'sourceIsin', 'market', 'date', 'dateBasis', 'form', 'sourceShareClass']
            if any(any(v['fact'][key] != chain[0]['fact'][key] for key in fields) for v in chain):
                raise ResearchError('LISTING_FACT_CORRECTION_IDENTITY_OR_DATE_CONFLICT')
            fact = chain[-1]['fact']
            facts.append({**fact, 'statusReferenceId': t['statusReferenceId'], 'statusDate': t['statusDate'],
                'statusEventType': t['statusEventType'], 'knownAt': known, 'versions': chain,
                'otherCandidateReceipts': [v['receipt'] for v in versions if v not in chain],
                'correctionPolicy': 'EXCHANGE_DATE_FULL_CODE_ISIN_MARKET_AND_SHARE_CLASS_EQUAL',
                'otherCorrectionContentInterpreted': False if len(chain) > 1 else None})
        except (ValueError, KeyError, TypeError) as exc:
            reviews.append({'observationId': identity, 'symbol': t['symbol'], 'market': t['market'], 'statusDate': t['statusDate'],
                'knownAt': known, 'candidateVersions': versions, 'diagnostic': str(exc) if isinstance(exc, ResearchError) else 'LISTING_FACT_INPUT_REVIEW'})
    return {'schemaVersion': 'SAGOPALGO_NEW_LISTING_FACTS_V1', 'planId': plan['planId'], 'parentSha256': plan['parentSha256'],
        'inventorySha256': plan['inventorySha256'], 'sourceKind': plan['sourceKind'], 'targets': len(plan['targets']), 'facts': facts,
        'reviews': reviews, 'verified': len(facts), 'reviewRequired': len(reviews), 'formCounts': dict(Counter(f['form'] for f in facts)),
        'firstEverIpoConfirmed': False, 'allLegalEffectsConfirmed': False, 'usableForTraining': False, 'usableForTrading': False}
