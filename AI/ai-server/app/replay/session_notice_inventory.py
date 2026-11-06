"""Bounded, paginated KIND notice inventory; scoped search is not full session completeness."""
import argparse
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import re
import time

from . import kind_membership_evidence as kind
from .distribution_facts import Node, XForms
from .dataset import canonical, digest, read_bytes, read_json
from .history import day, now, job_lock
from .krx_storage import atomic_json
from .krx_baseline_validation import immutable_json
from .models import ResearchError, utc
from .session_evidence import validate_url

BASE = kind.BASE
FORMS = {'KOSPI': '99303', 'KOSDAQ': '70780'}
SUBMITTERS = {'KOSPI': '유가증권시장본부', 'KOSDAQ': '코스닥시장본부'}
LIMIT = kind.LIMIT
SCHEMA = 'SAGOPALGO_SESSION_INVENTORY_PLAN_V1'


def query_spec(query, page):
    return {'url': BASE + '/disclosure/details.do', 'method': 'POST', 'parameters': {
        'method': 'searchDetailsSub', 'forward': 'details_sub', 'currentPageSize': '100', 'pageIndex': str(page),
        'orderMode': '1', 'orderStat': 'D', 'fromDate': query['fromDate'], 'toDate': query['toDate'],
        'repIsuSrtCd': '', 'searchCodeType': '', 'searchCorpName': '',
        'reportNm': '기타시장안내' if query['kind'] == 'FORM' else '거래시간',
        'reportCd': FORMS[query['market']] if query['kind'] == 'FORM' else '',
        'allRepIsuSrtCd': '', 'marketType': '1' if query['market'] == 'KOSPI' else '2'}}


def key(stage, spec):
    return digest(canonical({'stage': stage, 'request': spec}))


class ListHTML(XForms):
    def handle_starttag(self, tag, attrs):
        # KIND's decorative title attribute sometimes contains unescaped year
        # apostrophes. Only the visible text and unique validated viewer link
        # carry evidence. Never relax duplicate href/onclick identities.
        hrefs = [v for k, v in attrs if k == 'href']
        if tag == 'a' and '#viewer' in hrefs:
            clicks = [v for k, v in attrs if k == 'onclick']
            if hrefs != ['#viewer'] or len(clicks) != 1 or not re.fullmatch(r"openDisclsViewer\('[0-9]{14}',''\);?", clicks[0]):
                raise ResearchError('SESSION_INVENTORY_VIEWER_LINK_AMBIGUOUS')
            attrs = [('href', hrefs[0]), ('onclick', clicks[0])]
        super().handle_starttag(tag, attrs)


def page_rows(raw, query, page):
    if len(raw) > LIMIT: raise ResearchError('SESSION_INVENTORY_RESPONSE_LIMIT')
    parser = ListHTML(); parser.feed(raw.decode('utf-8-sig')); parser.close()
    if len(parser.stack) != 1: raise ResearchError('SESSION_INVENTORY_PAGE_LAYOUT')
    root = parser.root
    info = [v.text() for v in root.walk('div') if v.attrs.get('class') == 'info type-00']
    match = re.findall(r'전체\s*([0-9,]+)\s*건\s*:\s*([0-9]+)\s*/\s*([0-9]+)', info[0]) if len(info) == 1 else []
    if len(match) != 1:
        raise ResearchError('SESSION_INVENTORY_PAGE_LAYOUT')
    total, actual, pages = [int(v.replace(',', '')) for v in match[0]]
    if total > 2000 or actual != page or pages != max(1, (total + 99) // 100) or not 1 <= page <= pages:
        raise ResearchError('SESSION_INVENTORY_PAGE_RANGE')
    rows = []
    for tr in root.walk('tr'):
        cells = [c for c in tr.children if isinstance(c, Node) and c.tag == 'td']
        if not cells or total == 0 and len(cells) == 1 and '조회' in cells[0].text():
            continue
        if len(cells) != 6:
            raise ResearchError('SESSION_INVENTORY_ROW_LAYOUT')
        rank, stamp, issuer, title, submitter = [c.text() for c in cells[:5]]
        links = [v for v in cells[3].walk('a') if v.attrs.get('href') == '#viewer']
        receipt = re.fullmatch(r"openDisclsViewer\('([0-9]{14})',''\);?", links[0].attrs.get('onclick', '')) if len(links) == 1 else None
        if (not receipt or not rank.isdigit() or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}', stamp)
                or not query['fromDate'] <= stamp[:10] <= query['toDate'] or receipt[1][:8] != stamp[:10].replace('-', '')):
            raise ResearchError('SESSION_INVENTORY_ROW_IDENTITY')
        day(stamp[:10])
        if query['kind'] == 'FORM' and (submitter != SUBMITTERS[query['market']] or not re.fullmatch(r'(?:\[정정\]\s*)?기타시장안내(?:\(.*\))?', title)):
            raise ResearchError('SESSION_INVENTORY_FILTER_MISMATCH')
        issuer_keys = []; icons = []
        if issuer:
            companies = list(cells[2].walk('a'))
            for company in companies:
                m = re.fullmatch(r"companysummary_open\('([A-Z0-9]{5})'\);\s*return false;", company.attrs.get('onclick', ''))
                if m: issuer_keys.append(m[1])
            icons = [v.attrs.get('alt') for v in cells[2].walk('img') if v.attrs.get('alt') in {'유가증권', '코스닥', '코넥스'}]
            # KIND decorates old disclosures with the issuer's current market icon.
            # Preserve it as display metadata; it cannot override the historical query/form.
            if len(issuer_keys) != 1 or len(icons) != 1:
                raise ResearchError('SESSION_INVENTORY_ISSUER_IDENTITY')
        elif list(cells[2].walk('a')) or list(cells[2].walk('img')):
            raise ResearchError('SESSION_INVENTORY_EMPTY_ISSUER_AMBIGUOUS')
        needs_body = not issuer or bool(re.search(r'거래시간|매매시간|시장운영|개장|폐장', title))
        rows.append({'receipt': receipt[1], 'rank': int(rank), 'reportedAtKstText': stamp, 'issuer': issuer,
            'issuerKey': issuer_keys[0] if issuer_keys else None, 'title': title, 'submitter': submitter,
            'issuerDisplayMarket': icons[0] if icons else None,
            'market': query['market'], 'requiresBodyReview': needs_body,
            'scopeDisposition': 'BODY_REVIEW_REQUIRED' if needs_body else 'ISSUER_SPECIFIC_OUTSIDE_MARKET_SCHEDULE_SCOPE'})
    expected = list(range(total - (page - 1) * 100, max(0, total - page * 100), -1))
    if [v['rank'] for v in rows] != expected or len({v['receipt'] for v in rows}) != len(rows):
        raise ResearchError('SESSION_INVENTORY_ROW_COUNT_OR_RANK')
    return {'total': total, 'page': actual, 'pages': pages, 'rows': rows}


def viewer_documents(raw):
    root = kind.html(raw)
    selectors = [v for v in root.walk('select') if v.attrs.get('id') == 'mainDoc']
    options = [v for v in selectors[0].walk('option') if v.attrs.get('value')] if len(selectors) == 1 else []
    docs = []
    if not 1 <= len(options) <= 10:
        raise ResearchError('SESSION_INVENTORY_VIEWER_VERSIONS')
    for option in options:
        m = re.fullmatch(r'([0-9]{14})\|[YN]', option.attrs['value'])
        if not m or not option.text():
            raise ResearchError('SESSION_INVENTORY_VIEWER_DOCUMENT')
        docs.append({'document': m[1], 'label': option.text(), 'correctionMarked': '정정' in option.text()})
    if len({v['document'] for v in docs}) != len(docs):
        raise ResearchError('SESSION_INVENTORY_VIEWER_DUPLICATE')
    return docs


def body_path(raw, document):
    paths = re.findall(r"parent\.setPath\('[^']*','(https://kind\.krx\.co\.kr/external/[^']+)','[^']*','[0-9]{2}','[0-9]{2}'\);", raw.decode('utf-8-sig'))
    if len(paths) != 1:
        raise ResearchError('SESSION_INVENTORY_PATH_AMBIGUOUS')
    validate_url(paths[0])
    if paths[0].split('/')[-2] != document:
        raise ResearchError('SESSION_INVENTORY_DOCUMENT_PATH_MISMATCH')
    return paths[0]


def queries(parent, through):
    day(through)
    if not parent['endDate'] <= through <= (day(parent['endDate']) + timedelta(days=31)).isoformat():
        raise ResearchError('SESSION_INVENTORY_PUBLICATION_WINDOW')
    return [{'id': p['market'].lower() + '-' + p['startDate'][:4] + '-' + kind_, 'kind': kind_, 'market': p['market'],
        'fromDate': p['startDate'][:4] + '-01-01', 'toDate': min(p['endDate'][:4] + '-12-31', through)}
        for p in parent['temporaryChangeReviewPlan'] for kind_ in ['FORM', 'TIME_TITLE_CONTROL']]


def prepare(folder, parent_path, through, max_requests=256, source_kind='PROVIDER_OBSERVATIONS', seeds=()):
    parent = read_json(read_bytes(parent_path))
    if (parent.get('schemaVersion') != 'SAGOPALGO_SESSION_RULE_REPORT_V2' or not parent.get('allOrdinaryRuleChainsConfirmed')
            or len(parent.get('temporaryChangeReviewPlan', [])) != 8 or type(max_requests) is not int or not 16 <= max_requests <= 512
            or source_kind not in {'PROVIDER_OBSERVATIONS', 'SYNTHETIC'}):
        raise ResearchError('SESSION_INVENTORY_PARENT_OR_BUDGET')
    query_list = queries(parent, through)
    if len({q['id'] for q in query_list}) != 16:
        raise ResearchError('SESSION_INVENTORY_QUERY_SCOPE')
    expected_seeds = {key('LIST', query_spec(q, 1)): query_spec(q, 1) for q in query_list}
    seed_records = []
    for origin, raw in seeds:
        spec = {k: origin[k] for k in ['url', 'method', 'parameters']}
        k = key('LIST', spec)
        if (k not in expected_seeds or expected_seeds[k] != spec or origin.get('status') != 'COMPLETE'
                or origin.get('httpStatus') != 200 or digest(raw) != origin.get('bodySha256') or len(raw) > LIMIT
                or utc(origin['startedAt']) > utc(origin['capturedAt'])):
            raise ResearchError('SESSION_INVENTORY_SEED_INVALID')
        seed_records.append({'key': k, 'stage': 'LIST', 'request': spec, 'sha256': digest(raw),
            'startedAt': origin['startedAt'], 'capturedAt': origin['capturedAt']})
    if len({s['key'] for s in seed_records}) != len(seed_records):
        raise ResearchError('SESSION_INVENTORY_SEED_DUPLICATE')
    payload = {'schemaVersion': SCHEMA, 'parentSha256': digest(read_bytes(parent_path)), 'sourceKind': source_kind,
        'startDate': parent['startDate'], 'endDate': parent['endDate'], 'publicationThrough': through,
        'partitions': parent['temporaryChangeReviewPlan'], 'queries': query_list, 'pageSize': 100,
        'maxRequests': max_requests, 'minIntervalSeconds': 1, 'seeds': seed_records}
    plan = {**payload, 'planId': digest(canonical(payload))}
    folder.mkdir(parents=True, exist_ok=False); (folder / 'raw').mkdir()
    atomic_json(folder / 'plan.json', plan)
    entries = []
    for i, ((_, raw), record) in enumerate(zip(seeds, seed_records), 1):
        (folder / 'raw' / f'{i:04d}.bin').write_bytes(raw)
        entries.append({**record, 'seq': i, 'state': 'CAPTURED', 'newRequests': 0})
    atomic_json(folder / 'journal.json', {'planId': plan['planId'], 'attempts': entries})
    return plan


def walk_requests(plan, raws):
    rows_by_receipt = {}
    for query in plan['queries']:
        all_rows = []; first = None
        for page in range(1, 21):
            spec = query_spec(query, page); k = key('LIST', spec)
            yield 'LIST', spec
            if k not in raws: return
            parsed = page_rows(raws[k], query, page)
            if first is None: first = parsed
            elif (parsed['total'], parsed['pages']) != (first['total'], first['pages']):
                raise ResearchError('SESSION_INVENTORY_TOTAL_CHANGED')
            all_rows.extend(parsed['rows'])
            if page == parsed['pages']: break
        if len(all_rows) != first['total'] or len({r['receipt'] for r in all_rows}) != len(all_rows):
            raise ResearchError('SESSION_INVENTORY_PAGINATION_GAP')
        for row in all_rows:
            identity = (row['market'], row['receipt'])
            if identity in rows_by_receipt and any(rows_by_receipt[identity][v] != row[v] for v in ['title', 'issuer', 'submitter', 'reportedAtKstText']):
                raise ResearchError('SESSION_INVENTORY_CROSS_QUERY_CONFLICT')
            rows_by_receipt[identity] = row
    for identity, row in sorted(rows_by_receipt.items()):
        if not row['requiresBodyReview']: continue
        spec = {'url': BASE + '/common/disclsviewer.do?acptno=' + row['receipt'] + '&method=search', 'method': 'GET', 'parameters': None}
        yield 'VIEWER', spec
        if key('VIEWER', spec) not in raws: return
        docs = viewer_documents(raws[key('VIEWER', spec)])
        for doc in docs:
            spec = {'url': BASE + '/common/disclsviewer.do', 'method': 'POST', 'parameters': {'method': 'searchContents', 'docNo': doc['document']}}
            yield 'PATH', spec
            if key('PATH', spec) not in raws: return
            url = body_path(raws[key('PATH', spec)], doc['document'])
            spec = {'url': url, 'method': 'GET', 'parameters': None}
            yield 'BODY', spec
            if key('BODY', spec) not in raws: return


def extend(folder, source_folder, max_requests):
    if (source_folder / '.collect.lock').exists():
        raise ResearchError('SESSION_INVENTORY_SOURCE_JOB_ACTIVE')
    prior, journal, raws, entries = load(source_folder)
    inherited = prior.get('inheritedRequests', 0) + sum(e['newRequests'] for e in entries.values())
    if type(max_requests) is not int or not prior['maxRequests'] < max_requests <= 512:
        raise ResearchError('SESSION_INVENTORY_EXTENSION_BUDGET')
    if any(e['state'] != 'CAPTURED' for e in entries.values()):
        raise ResearchError('SESSION_INVENTORY_UNRESOLVED_RESERVATION')
    records = [{k: e[k] for k in ['key', 'stage', 'request', 'sha256', 'startedAt', 'capturedAt']} for e in journal['attempts']]
    payload = {k: deepcopy(v) for k, v in prior.items() if k not in {'planId', 'seeds', 'lineage', 'inheritedRequests'}}
    payload.update(maxRequests=max_requests, seeds=records, inheritedRequests=inherited,
        lineage={'sourceJob': str(source_folder.resolve()), 'planSha256': digest(read_bytes(source_folder / 'plan.json')),
                 'journalSha256': digest(read_bytes(source_folder / 'journal.json'))})
    plan = {**payload, 'planId': digest(canonical(payload))}
    folder.mkdir(parents=True, exist_ok=False); (folder / 'raw').mkdir()
    new_entries = []
    for i, record in enumerate(records, 1):
        (folder / 'raw' / f'{i:04d}.bin').write_bytes(raws[record['key']])
        new_entries.append({**record, 'seq': i, 'state': 'CAPTURED', 'newRequests': 0})
    atomic_json(folder / 'plan.json', plan)
    atomic_json(folder / 'journal.json', {'planId': plan['planId'], 'attempts': new_entries})
    return plan


def load(folder, seen=None):
    seen = set(seen or ())
    if str(folder.resolve()) in seen or len(seen) >= 4:
        raise ResearchError('SESSION_INVENTORY_LINEAGE_CYCLE')
    seen.add(str(folder.resolve()))
    plan = read_json(read_bytes(folder / 'plan.json')); payload = {k: v for k, v in plan.items() if k != 'planId'}
    fields = {'schemaVersion', 'parentSha256', 'sourceKind', 'startDate', 'endDate', 'publicationThrough', 'partitions',
              'queries', 'pageSize', 'maxRequests', 'minIntervalSeconds', 'seeds', 'planId'}
    if 'lineage' in plan: fields |= {'inheritedRequests', 'lineage'}
    if (set(plan) != fields or plan.get('schemaVersion') != SCHEMA or plan.get('planId') != digest(canonical(payload))
            or len(plan['queries']) != 16 or len(plan['partitions']) != 8
            or plan.get('queries') != queries({'endDate': plan['endDate'], 'temporaryChangeReviewPlan': plan['partitions']}, plan['publicationThrough'])
            or plan.get('pageSize') != 100 or plan.get('minIntervalSeconds') != 1
            or type(plan.get('maxRequests')) is not int or not 16 <= plan['maxRequests'] <= 512
            or plan.get('sourceKind') not in {'PROVIDER_OBSERVATIONS', 'SYNTHETIC'}):
        raise ResearchError('SESSION_INVENTORY_PLAN_TAMPERED')
    inherited = plan.get('inheritedRequests', 0)
    if 'lineage' in plan:
        lineage = plan['lineage']; prior_folder = Path(lineage['sourceJob'])
        if (digest(read_bytes(prior_folder / 'plan.json')) != lineage['planSha256']
                or digest(read_bytes(prior_folder / 'journal.json')) != lineage['journalSha256']):
            raise ResearchError('SESSION_INVENTORY_LINEAGE_TAMPERED')
        prior, prior_journal, _, prior_entries = load(prior_folder, seen)
        expected_records = [{k: e[k] for k in ['key', 'stage', 'request', 'sha256', 'startedAt', 'capturedAt']}
                            for e in prior_journal['attempts'] if e['state'] == 'CAPTURED']
        if (type(inherited) is not int or inherited != prior.get('inheritedRequests', 0) + sum(e['newRequests'] for e in prior_entries.values())
                or plan['seeds'] != expected_records or not prior['maxRequests'] < plan['maxRequests']
                or any(plan[k] != prior[k] for k in ['parentSha256', 'sourceKind', 'startDate', 'endDate', 'publicationThrough', 'partitions', 'queries'])):
            raise ResearchError('SESSION_INVENTORY_LINEAGE_TAMPERED')
    elif inherited != 0:
        raise ResearchError('SESSION_INVENTORY_INHERITED_BUDGET_WITHOUT_LINEAGE')
    journal = read_json(read_bytes(folder / 'journal.json'))
    if set(journal) != {'planId', 'attempts'} or journal['planId'] != plan['planId'] or not isinstance(journal['attempts'], list):
        raise ResearchError('SESSION_INVENTORY_JOURNAL_TAMPERED')
    raws = {}; entries = {}; used = 0
    for i, entry in enumerate(journal['attempts'], 1):
        fields = {'seq', 'key', 'stage', 'request', 'state', 'startedAt', 'newRequests'}
        if entry.get('state') == 'CAPTURED': fields |= {'sha256', 'capturedAt'}
        elif entry.get('state') == 'FAILED': fields |= {'finishedAt', 'diagnostic'}
        if (set(entry) != fields or type(entry.get('seq')) is not int or entry.get('seq') != i
                or entry.get('key') != key(entry['stage'], entry['request']) or entry['key'] in entries
                or entry.get('stage') not in {'LIST', 'VIEWER', 'PATH', 'BODY'} or entry.get('state') not in {'RESERVED', 'FAILED', 'CAPTURED'}
                or type(entry.get('newRequests')) is not int or entry['newRequests'] not in {0, 1}):
            raise ResearchError('SESSION_INVENTORY_JOURNAL_TAMPERED')
        utc(entry['startedAt']); entries[entry['key']] = entry; used += entry['newRequests']
        if entry['newRequests'] == 0:
            seed = {k: v for k, v in entry.items() if k not in {'seq', 'state', 'newRequests'}}
            if seed not in plan['seeds'] or entry['state'] != 'CAPTURED':
                raise ResearchError('SESSION_INVENTORY_SEED_TAMPERED')
        if entry['state'] == 'CAPTURED':
            raw = read_bytes(folder / 'raw' / f'{i:04d}.bin')
            if len(raw) > LIMIT or digest(raw) != entry['sha256'] or utc(entry['capturedAt']) < utc(entry['startedAt']):
                raise ResearchError('SESSION_INVENTORY_RAW_TAMPERED')
            raws[entry['key']] = raw
    if inherited + used > plan['maxRequests'] or len(journal['attempts']) > plan['maxRequests'] - inherited + len(plan['seeds']):
        raise ResearchError('SESSION_INVENTORY_BUDGET_TAMPERED')
    expected = {key(stage, spec) for stage, spec in walk_requests(plan, raws)}
    if set(entries) - expected - {s['key'] for s in plan['seeds']}:
        raise ResearchError('SESSION_INVENTORY_REQUEST_TAMPERED')
    return plan, journal, raws, entries


def status(folder):
    plan, journal, raws, entries = load(folder)
    requests = list(walk_requests(plan, raws))
    missing = [(stage, spec) for stage, spec in requests if key(stage, spec) not in raws]
    return {'planId': plan['planId'], 'capturedRequests': len(raws),
        'newRequestsUsed': plan.get('inheritedRequests', 0) + sum(e['newRequests'] for e in entries.values()),
        'newRequestsInThisPlan': sum(e['newRequests'] for e in entries.values()), 'maxRequests': plan['maxRequests'],
        'status': 'CAPTURED' if not missing else entries.get(key(*missing[0]), {}).get('state', 'PENDING'),
        'nextStage': missing[0][0] if missing else None, 'allHistoricalSessionsComplete': False,
        'usableForTraining': False, 'usableForTrading': False}


def collect(folder, transport, budget, sleep=time.sleep):
    if type(budget) is not int or not 0 <= budget <= 512:
        raise ResearchError('SESSION_INVENTORY_RUN_BUDGET')
    with job_lock(folder):
        plan, journal, raws, entries = load(folder)
        if transport.source_kind != plan['sourceKind']:
            raise ResearchError('SESSION_INVENTORY_SOURCE_KIND')
        used = 0; total = plan.get('inheritedRequests', 0) + sum(e['newRequests'] for e in entries.values())
        for stage, spec in walk_requests(plan, raws):
            k = key(stage, spec)
            if k in raws: continue
            if k in entries or used >= budget or total >= plan['maxRequests']: break
            if journal['attempts']:
                elapsed = (utc(now()) - utc(journal['attempts'][-1]['startedAt'])).total_seconds()
                if elapsed < 0: raise ResearchError('SESSION_INVENTORY_CLOCK_REGRESSION')
                if elapsed < 1: sleep(1 - elapsed)
            entry = {'seq': len(journal['attempts']) + 1, 'key': k, 'stage': stage, 'request': spec,
                'state': 'RESERVED', 'startedAt': now(), 'newRequests': 1}
            journal['attempts'].append(entry); atomic_json(folder / 'journal.json', journal)
            try:
                raw = transport.fetch(spec)
                if len(raw) > LIMIT: raise ResearchError('SESSION_INVENTORY_RESPONSE_LIMIT')
                (folder / 'raw' / f"{entry['seq']:04d}.bin").write_bytes(raw)
                entry.update(state='CAPTURED', capturedAt=now(), sha256=digest(raw)); raws[k] = raw
            except Exception as exc:
                entry.update(state='FAILED', finishedAt=now(), diagnostic=str(exc) if isinstance(exc, ResearchError) else 'SESSION_INVENTORY_CAPTURE_FAILED')
            atomic_json(folder / 'journal.json', journal); entries[k] = entry; used += 1; total += 1
            if used % 10 == 0: print(json.dumps({'progress': True, 'newRequestsUsed': total, 'stage': stage}), flush=True)
            if entry['state'] == 'FAILED': break
    return status(folder)


def inventory(folder, parent_path):
    plan, journal, raws, entries = load(folder)
    if digest(read_bytes(parent_path)) != plan['parentSha256']:
        raise ResearchError('SESSION_INVENTORY_PARENT_HASH')
    parent = read_json(read_bytes(parent_path))
    if parent.get('schemaVersion') != 'SAGOPALGO_SESSION_RULE_REPORT_V2' or plan['partitions'] != parent.get('temporaryChangeReviewPlan'):
        raise ResearchError('SESSION_INVENTORY_PARENT_SCOPE')
    if status(folder)['status'] != 'CAPTURED':
        raise ResearchError('SESSION_INVENTORY_INCOMPLETE')
    query_results = []; rows = {}
    for query in plan['queries']:
        first = page_rows(raws[key('LIST', query_spec(query, 1))], query, 1); all_rows = []; proofs = []
        for page in range(1, first['pages'] + 1):
            k = key('LIST', query_spec(query, page)); parsed = page_rows(raws[k], query, page)
            all_rows.extend(parsed['rows']); proofs.append({'page': page, 'sha256': entries[k]['sha256'], 'knownAt': entries[k]['capturedAt']})
        query_results.append({'query': query, 'total': first['total'], 'pages': first['pages'], 'pageProofs': proofs, 'paginationConfirmed': True})
        for row in all_rows:
            identity = (row['market'], row['receipt'])
            if identity not in rows: rows[identity] = {**row, 'queryIds': []}
            rows[identity]['queryIds'].append(query['id'])
    for row in rows.values():
        row['versions'] = []
        if not row['requiresBodyReview']: continue
        spec = {'url': BASE + '/common/disclsviewer.do?acptno=' + row['receipt'] + '&method=search', 'method': 'GET', 'parameters': None}
        for doc in viewer_documents(raws[key('VIEWER', spec)]):
            p = {'url': BASE + '/common/disclsviewer.do', 'method': 'POST', 'parameters': {'method': 'searchContents', 'docNo': doc['document']}}
            url = body_path(raws[key('PATH', p)], doc['document']); b = {'url': url, 'method': 'GET', 'parameters': None}
            entry = entries[key('BODY', b)]
            row['versions'].append({**doc, 'url': url, 'bodySha256': entry['sha256'], 'knownAt': entry['capturedAt'], 'rawFile': f"raw/{entry['seq']:04d}.bin"})
    known = max([parent['knownAt'], *(e['capturedAt'] for e in entries.values())], key=utc)
    return {'schemaVersion': 'SAGOPALGO_SESSION_NOTICE_INVENTORY_V1', 'planId': plan['planId'], 'parentSha256': plan['parentSha256'],
        'startDate': plan['startDate'], 'endDate': plan['endDate'], 'publicationThrough': plan['publicationThrough'],
        'sourceKind': plan['sourceKind'], 'inventoryScope': 'REVIEWED_KIND_FORMS_PLUS_TIME_TITLE_CONTROL',
        'queries': query_results, 'rows': list(rows.values()), 'knownAt': known,
        'scopedPaginationComplete': True, 'bodyReviewRequired': sum(r['requiresBodyReview'] for r in rows.values()),
        'fullTemporaryChangeInventoryComplete': False, 'allHistoricalSessionsComplete': False,
        'referencePacks': deepcopy(parent['referencePacks']), 'usableForTraining': False, 'usableForTrading': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['plan', 'extend', 'collect', 'status', 'build', 'audit'])
    p.add_argument('--job', type=Path, required=True); p.add_argument('--parent', type=Path)
    p.add_argument('--through'); p.add_argument('--max-requests', type=int, default=256); p.add_argument('--from-job', type=Path)
    p.add_argument('--max-new-requests', type=int, default=0); p.add_argument('--output', type=Path)
    a = p.parse_args()
    try:
        if a.command == 'plan':
            if not a.parent or not a.through: p.error('--parent --through required')
            result = prepare(a.job, a.parent, a.through, a.max_requests)
        elif a.command == 'extend':
            if not a.from_job: p.error('--from-job required')
            result = extend(a.job, a.from_job, a.max_requests)
        elif a.command == 'collect': result = collect(a.job, kind.Transport(), a.max_new_requests)
        elif a.command == 'status': result = status(a.job)
        else:
            if not a.parent or not a.output: p.error('--parent --output required')
            report = inventory(a.job, a.parent); immutable_json(a.output, report, a.command == 'audit')
            result = {'status': 'SCOPED_INVENTORY_CAPTURED_REVIEW_PENDING', 'rows': len(report['rows']),
                'bodyReviewRequired': report['bodyReviewRequired'], 'sha256': digest(read_bytes(a.output)), 'allHistoricalSessionsComplete': False}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except (ResearchError, ValueError, OSError, KeyError) as exc:
        print(json.dumps({'error': str(exc) if isinstance(exc, ResearchError) else 'SESSION_INVENTORY_INPUT_INVALID'})); return 2
    return 0


if __name__ == '__main__': raise SystemExit(main())
