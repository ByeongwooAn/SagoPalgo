"""Supplement notice searches and make explicit, evidence-bound session promotion decisions.

Expanded keyword searches do not establish exhaustive absence of other notices.
All captures are local research evidence, never a live trading permission.
"""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import timedelta
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import time
from typing import Literal

from pydantic import Field, model_validator

from . import session_notice_inventory as notices
from . import session_notice_review as review
from . import market_calendar_evidence as calendar
from .dataset import canonical, digest, read_bytes, read_json
from .history import day, job_lock, now
from .krx_storage import atomic_json
from .krx_baseline_validation import immutable_json
from .models import ResearchError, StrictModel, utc

TERMS = ('거래시간', '매매시간', '시장운영', '개장', '폐장', '임시변경', '매매거래중단', '서킷브레이커', '거래재개', '기타시장조치')
BASE = notices.BASE
NEEDS_BODY = re.compile(r'거래시간|매매시간|시장운영|개장|폐장|매매거래중단|일시중단|서킷브레이커|거래재개')


def queries(variant='TITLES_AND_BOUNDARY'):
    result = []
    if variant in {'HALT_AND_ACTION_CATEGORIES','HALT_AND_ACTION_CATEGORIES_V2'}:
        for market in notices.FORMS:
            for year in range(2022,2027):
                for category in ('0306','0346','0347'):
                    result.append({'id':f'{market}-{year}-CATEGORY-{category}','kind':'CATEGORY','market':market,'category':category,
                        'term':'','fromDate':f'{year}-01-01','toDate':min(f'{year}-12-31','2026-11-05')})
                result.append({'id':f'{market}-{year}-temporary-halt','kind':'TITLE','market':market,'term':'일시중단',
                    'fromDate':f'{year}-01-01','toDate':min(f'{year}-12-31','2026-11-05')})
            for category in ('0306','0346','0347'):
                result.append({'id':f'{market}-tail-CATEGORY-{category}','kind':'CATEGORY','market':market,'category':category,
                    'term':'','fromDate':'2026-11-06','toDate':'2026-11-06'})
        if variant.endswith('_V2'):
            for q in result:
                if q['kind']=='CATEGORY':q['filterEncoding']='SUBMITTED_FORM'
        return result
    if variant!='TITLES_AND_BOUNDARY':raise ResearchError('SESSION_COVERAGE_QUERY_VARIANT')
    for market in notices.FORMS:
        for year in range(2022, 2027):
            for term in TERMS:
                result.append({'id': f'{market}-{year}-{term}', 'kind': 'TITLE', 'market': market, 'term': term,
                    'fromDate': f'{year}-01-01', 'toDate': min(f'{year}-12-31', '2026-11-05')})
        result.append({'id': f'{market}-2022-FORM', 'kind': 'FORM', 'market': market, 'term': '기타시장안내',
                       'fromDate': '2022-01-01', 'toDate': '2022-12-31'})
        for term in (*TERMS, '기타시장안내'):
            result.append({'id': f'{market}-tail-{term}', 'kind': 'FORM' if term == '기타시장안내' else 'TITLE',
                'market': market, 'term': term, 'fromDate': '2026-11-06', 'toDate': '2026-11-06'})
    return result


def list_spec(query, page):
    # Preserve exact old request identity to reuse its eight title control pages.
    value = notices.query_spec({**query, 'kind': 'FORM' if query['kind'] == 'FORM' else 'TIME_TITLE_CONTROL'}, page)
    value['parameters']['reportNm'] = query['term']
    if query['kind']=='CATEGORY':value['parameters']['pDisclosureType02']=query['category']+'|'
    if query.get('filterEncoding')=='SUBMITTED_FORM':
        value['parameters']['disclosureType02']=query['category']+'|'
    return value


def rows(raw, query, page):
    parsed = notices.page_rows(raw, {**query, 'kind': 'FORM' if query['kind'] == 'FORM' else 'TIME_TITLE_CONTROL'}, page)
    for row in parsed['rows']:
        # The provider's submitter/market filters and title containment are checked
        # independently; do not trust a successful HTTP response to prove a filter.
        if query['kind'] == 'TITLE' and query['term'] not in re.sub(r'\s+', '', row['title']):
            raise ResearchError('SESSION_COVERAGE_TITLE_FILTER_MISMATCH')
        row['requiresBodyReview'] = not row['issuer'] or bool(NEEDS_BODY.search(row['title']))
        row['scopeDisposition'] = 'BODY_REVIEW_REQUIRED' if row['requiresBodyReview'] else 'ISSUER_SPECIFIC_OUTSIDE_MARKET_SCHEDULE_SCOPE'
    return parsed


def prepare(folder, parent, rules, old_job, max_requests=400, variant='TITLES_AND_BOUNDARY'):
    p = read_json(read_bytes(parent)); r = read_json(read_bytes(rules))
    if (p.get('schemaVersion') != 'SAGOPALGO_SESSION_EXCEPTION_REVIEW_V1'
            or r.get('schemaVersion') != 'SAGOPALGO_SESSION_RULE_REPORT_V2'
            or p['parentSha256'] != digest(read_bytes(rules))
            or p['referencePacks'] != r['referencePacks'] or not r['allOrdinaryRuleChainsConfirmed']
            or type(max_requests) is not int or not 1 <= max_requests <= 512):
        raise ResearchError('SESSION_COVERAGE_PARENT_SCOPE')
    old, _, _, _ = notices.load(old_job)
    if p.get('sourceKind') != old['sourceKind'] or r.get('sourceKind',old['sourceKind']) != old['sourceKind']:
        raise ResearchError('SESSION_COVERAGE_PARENT_SOURCE_KIND')
    payload = {'schemaVersion': 'SAGOPALGO_SESSION_COVERAGE_PLAN_V1', 'parentSha256': digest(read_bytes(parent)),
        'rulesSha256': digest(read_bytes(rules)), 'sourceJob': str(old_job.resolve()),
        'sourcePlanSha256': digest(read_bytes(old_job/'plan.json')), 'sourceJournalSha256': digest(read_bytes(old_job/'journal.json')),
        'startDate': r['startDate'], 'endDate': r['endDate'], 'queries': queries(variant), 'maxRequests': max_requests,
        'publicationStart': '2022-01-01', 'publicationThrough': '2026-11-06', 'minIntervalSeconds': 1}
    if variant!='TITLES_AND_BOUNDARY':payload['queryVariant']=variant
    folder.mkdir(parents=True, exist_ok=False); (folder/'captures').mkdir()
    immutable_json(folder/'plan.json', {**payload, 'planId': digest(canonical(payload))})
    return load_plan(folder)


def load_plan(folder):
    p = read_json(read_bytes(folder/'plan.json')); value = {k:v for k,v in p.items() if k != 'planId'}
    fields = {'schemaVersion','parentSha256','rulesSha256','sourceJob','sourcePlanSha256','sourceJournalSha256',
              'startDate','endDate','queries','maxRequests','publicationStart','publicationThrough','minIntervalSeconds','planId'}
    if 'queryVariant' in p:fields.add('queryVariant')
    if 'reuseSources' in p:fields|={'reuseSources','inheritedRequests'}
    if (set(p) != fields or p['schemaVersion'] != 'SAGOPALGO_SESSION_COVERAGE_PLAN_V1'
            or p['planId'] != digest(canonical(value)) or p['queries'] != queries(p.get('queryVariant','TITLES_AND_BOUNDARY'))
            or p['publicationStart'] != '2022-01-01' or p['publicationThrough'] != '2026-11-06'
            or p['minIntervalSeconds'] != 1 or type(p['maxRequests']) is not int or not 1 <= p['maxRequests'] <= 1024):
        raise ResearchError('SESSION_COVERAGE_PLAN_TAMPERED')
    old = Path(p['sourceJob'])
    if digest(read_bytes(old/'plan.json')) != p['sourcePlanSha256'] or digest(read_bytes(old/'journal.json')) != p['sourceJournalSha256']:
        raise ResearchError('SESSION_COVERAGE_SOURCE_TAMPERED')
    return p


def capture_index(folder):
    return digest(canonical({p.parent.name:digest(read_bytes(p)) for p in sorted((folder/'captures').glob('*/receipt.json'))}))


def extend(folder, prior_folder, reuse_folder, max_requests):
    if any((p/'.collect.lock').exists() for p in [prior_folder,reuse_folder]):
        raise ResearchError('SESSION_COVERAGE_SOURCE_ACTIVE')
    prior=Cache(prior_folder);reuse=Cache(reuse_folder)
    if any(e['state']!='CAPTURED' for source in [prior,reuse] for e in source.entries.values()):
        raise ResearchError('SESSION_COVERAGE_SOURCE_UNRESOLVED')
    if type(max_requests) is not int or not prior.plan['maxRequests']<max_requests<=1024:
        raise ResearchError('SESSION_COVERAGE_EXTENSION_BUDGET')
    if any(prior.plan[k]!=reuse.plan[k] for k in ['parentSha256','rulesSha256','startDate','endDate','sourceJob']):
        raise ResearchError('SESSION_COVERAGE_REUSE_SCOPE_CONFLICT')
    value={k:deepcopy(v) for k,v in prior.plan.items() if k not in {'planId','reuseSources','inheritedRequests'}}
    value.update(maxRequests=max_requests,inheritedRequests=prior.total,reuseSources=[
        {'job':str(p.resolve()),'planSha256':digest(read_bytes(p/'plan.json')),'captureIndexSha256':capture_index(p),
         'inheritBudget':p==prior_folder} for p in [reuse_folder,prior_folder]])
    folder.mkdir(parents=True,exist_ok=False);(folder/'captures').mkdir()
    immutable_json(folder/'plan.json',{**value,'planId':digest(canonical(value))})
    return load_plan(folder)


class Cache:
    def __init__(self, folder, budget=0, transport=None, sleep=time.sleep, _seen=()):
        identity=str(folder.resolve())
        if identity in _seen or len(_seen)>=4:raise ResearchError('SESSION_COVERAGE_REUSE_CYCLE')
        self.folder=folder; self.plan=load_plan(folder); self.budget=budget; self.transport=transport; self.sleep=sleep
        if type(budget) is not int or not 0 <= budget <= 512:
            raise ResearchError('SESSION_COVERAGE_RUN_BUDGET')
        self.old_plan, _, self.old_raws, self.old_entries = notices.load(Path(self.plan['sourceJob']))
        self.seed_entries={k:(e,self.old_raws[k],None) for k,e in self.old_entries.items() if e['state']=='CAPTURED'}
        inherited=0
        for source in self.plan.get('reuseSources',[]):
            p=Path(source['job'])
            if (set(source)!={'job','planSha256','captureIndexSha256','inheritBudget'} or type(source['inheritBudget']) is not bool
                    or digest(read_bytes(p/'plan.json'))!=source['planSha256'] or capture_index(p)!=source['captureIndexSha256']):
                raise ResearchError('SESSION_COVERAGE_REUSE_TAMPERED')
            other=Cache(p,_seen=(*_seen,identity))
            if any(other.plan[k]!=self.plan[k] for k in ['parentSha256','rulesSha256','startDate','endDate','sourceJob']):
                raise ResearchError('SESSION_COVERAGE_REUSE_SCOPE_CONFLICT')
            inherited+=other.total if source['inheritBudget'] else 0
            for k,e in other.entries.items():
                if e['state']!='CAPTURED':raise ResearchError('SESSION_COVERAGE_SOURCE_UNRESOLVED')
                if k not in self.seed_entries:self.seed_entries[k]=(e,read_bytes(p/'captures'/k/'body.bin'),str(p.resolve()))
        if type(self.plan.get('inheritedRequests',0)) is not int or inherited!=self.plan.get('inheritedRequests',0):
            raise ResearchError('SESSION_COVERAGE_INHERITED_BUDGET_TAMPERED')
        self.used=0; self.total=inherited; self.previous=None; self.entries={}; self.visited=set()
        for file in sorted((folder/'captures').glob('*/receipt.json')):
            e = read_json(read_bytes(file)); self.validate(e, file.parent)
            if e['key'] in self.entries: raise ResearchError('SESSION_COVERAGE_DUPLICATE_CAPTURE')
            self.entries[e['key']]=e; self.total+=e['newRequests']
            if e['newRequests'] and (self.previous is None or utc(e['startedAt'])>utc(self.previous)):
                self.previous=e['startedAt']
        if self.total>self.plan['maxRequests']: raise ResearchError('SESSION_COVERAGE_BUDGET_TAMPERED')

    def validate(self, e, path):
        fields={'planId','key','stage','request','state','startedAt','newRequests'}
        if e.get('state') == 'CAPTURED': fields|={'capturedAt','sha256'}
        if e.get('state') == 'FAILED': fields|={'finishedAt','diagnostic'}
        if e.get('newRequests') == 0: fields|={'originKey'}
        if 'originJob' in e:fields.add('originJob')
        if (set(e)!=fields or e['planId']!=self.plan['planId'] or e['key']!=notices.key(e['stage'],e['request'])
                or path.name!=e['key'] or e['stage'] not in {'LIST','VIEWER','PATH','BODY'}
                or e['state'] not in {'RESERVED','FAILED','CAPTURED'} or type(e['newRequests']) is not int or e['newRequests'] not in {0,1}):
            raise ResearchError('SESSION_COVERAGE_RECEIPT_TAMPERED')
        utc(e['startedAt'])
        if e['state']=='CAPTURED':
            raw=read_bytes(path/'body.bin')
            if len(raw)>notices.LIMIT or digest(raw)!=e['sha256'] or utc(e['capturedAt'])<utc(e['startedAt']):
                raise ResearchError('SESSION_COVERAGE_RAW_TAMPERED')
        if e['newRequests']==0:
            item=self.seed_entries.get(e.get('originKey'));old=item[0] if item else None
            if (not old or e.get('originJob')!=item[2] or e['state']!='CAPTURED' or e['key']!=old['key']
                    or any(e[k]!=old[k] for k in ['stage','request','startedAt','capturedAt','sha256'])):
                raise ResearchError('SESSION_COVERAGE_SEED_TAMPERED')

    def get(self, stage, request):
        k=notices.key(stage,request); self.visited.add(k); path=self.folder/'captures'/k
        if k in self.entries:
            e=self.entries[k]
            if e['request']!=request or e['stage']!=stage: raise ResearchError('SESSION_COVERAGE_REQUEST_CONFLICT')
            if e['state']!='CAPTURED': raise ResearchError('SESSION_COVERAGE_UNRESOLVED_REQUEST')
            return read_bytes(path/'body.bin'), e
        item=self.seed_entries.get(k);origin=item[0] if item else None
        if origin and origin['state']=='CAPTURED':
            if not self.transport: raise ResearchError('SESSION_COVERAGE_MISSING_SEED')
            path.mkdir(); raw=item[1]; (path/'body.bin').write_bytes(raw)
            e={**{f:origin[f] for f in ['key','stage','request','startedAt','capturedAt','sha256']},
               'planId':self.plan['planId'],'newRequests':0,'originKey':k,'state':'CAPTURED'}
            if item[2] is not None:e['originJob']=item[2]
            immutable_json(path/'receipt.json',e); self.entries[k]=e
            return raw,e
        if not self.transport or self.used>=self.budget or self.total>=self.plan['maxRequests']:
            raise ResearchError('SESSION_COVERAGE_PENDING')
        if self.transport.source_kind!=self.old_plan['sourceKind']: raise ResearchError('SESSION_COVERAGE_SOURCE_KIND')
        if self.previous:
            elapsed=(utc(now())-utc(self.previous)).total_seconds()
            if elapsed<0: raise ResearchError('SESSION_COVERAGE_CLOCK_REGRESSION')
            if elapsed<1:self.sleep(1-elapsed)
        e={'planId':self.plan['planId'],'key':k,'stage':stage,'request':request,'state':'RESERVED','startedAt':now(),'newRequests':1}
        path.mkdir(); atomic_json(path/'receipt.json',e); self.previous=e['startedAt']; self.used+=1; self.total+=1
        try:
            raw=self.transport.fetch(request)
            if len(raw)>notices.LIMIT:raise ResearchError('SESSION_COVERAGE_RESPONSE_LIMIT')
            (path/'body.bin').write_bytes(raw);e.update(state='CAPTURED',capturedAt=now(),sha256=digest(raw))
        except Exception:
            e.update(state='FAILED',finishedAt=now(),diagnostic='SESSION_COVERAGE_CAPTURE_FAILED')
        atomic_json(path/'receipt.json',e);self.entries[k]=e
        if e['state']!='CAPTURED':raise ResearchError('SESSION_COVERAGE_UNRESOLVED_REQUEST')
        if self.used%10==0:print(json.dumps({'progress':True,'newRequests':self.total,'stage':stage}),flush=True)
        return raw,e


def inventory(folder, cache):
    found={}; searches=[]
    for q in cache.plan['queries']:
        raw,e=cache.get('LIST',list_spec(q,1)); first=rows(raw,q,1); all_rows=[]; proofs=[]
        for page in range(1,first['pages']+1):
            raw,e=cache.get('LIST',list_spec(q,page)); parsed=rows(raw,q,page)
            if (parsed['total'],parsed['pages'])!=(first['total'],first['pages']):raise ResearchError('SESSION_COVERAGE_TOTAL_CHANGED')
            all_rows+=parsed['rows'];proofs.append({'page':page,'key':e['key'],'sha256':e['sha256']})
        if len(all_rows)!=first['total'] or len({r['receipt'] for r in all_rows})!=len(all_rows):raise ResearchError('SESSION_COVERAGE_PAGE_GAP')
        searches.append({'query':q,'total':first['total'],'pages':first['pages'],'proofs':proofs})
        for r in all_rows:
            k=(r['market'],r['receipt'])
            if k in found:
                if any(found[k][f]!=r[f] for f in ['title','issuer','submitter','reportedAtKstText']):raise ResearchError('SESSION_COVERAGE_CROSS_QUERY_CONFLICT')
            else:found[k]={**r,'queryIds':[]}
            found[k]['queryIds'].append(q['id'])
    for r in found.values():
        r['versions']=[]
        if not r['requiresBodyReview']:continue
        spec={'url':BASE+'/common/disclsviewer.do?acptno='+r['receipt']+'&method=search','method':'GET','parameters':None}
        raw,_=cache.get('VIEWER',spec)
        for v in notices.viewer_documents(raw):
            spec={'url':BASE+'/common/disclsviewer.do','method':'POST','parameters':{'method':'searchContents','docNo':v['document']}}
            raw,_=cache.get('PATH',spec);url=notices.body_path(raw,v['document'])
            raw,e=cache.get('BODY',{'url':url,'method':'GET','parameters':None})
            r['versions'].append({**v,'url':url,'bodySha256':e['sha256'],'sourceKnownAt':e['capturedAt'],'rawFile':f"captures/{e['key']}/body.bin"})
    if set(cache.entries)-cache.visited:raise ResearchError('SESSION_COVERAGE_UNEXPECTED_CAPTURE')
    return {'schemaVersion':'SAGOPALGO_SESSION_COVERAGE_INVENTORY_V1','planId':cache.plan['planId'],
        'parentSha256':cache.plan['parentSha256'],'rulesSha256':cache.plan['rulesSha256'],
        'startDate':cache.plan['startDate'],'endDate':cache.plan['endDate'],'sourceKind':cache.old_plan['sourceKind'],
        'queries':searches,'rows':list(found.values()),
        'queryVariant':cache.plan.get('queryVariant','TITLES_AND_BOUNDARY'),
        'knownAt':max((v['capturedAt'] for v in cache.entries.values()),key=utc),'newRequests':cache.total,
        'reusedRequests':sum(v['newRequests']==0 for v in cache.entries.values()),
        'fullTemporaryChangeInventoryComplete':False,'usableForTraining':False,'usableForTrading':False}


class Decision(StrictModel):
    market: Literal['KOSPI','KOSDAQ']
    document: str = Field(pattern=r'^[0-9]{14}$')
    bodySha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    classification: Literal['REGULAR_SESSION_CHANGE','MARKET_MAKING_POLICY','SHORT_SELLING_POLICY',
        'LOCKUP_POLICY','ISSUER_SPECIFIC_HALT','MARKET_WIDE_HALT','MARKET_WIDE_RESUMPTION','PROGRAM_ORDER_PAUSE','OTHER_MARKET_POLICY']
    reason: str = Field(min_length=10,max_length=500)
    subjectIssuer: str | None = Field(default=None,min_length=1,max_length=100)

    @model_validator(mode='after')
    def valid(self):
        if (self.classification=='ISSUER_SPECIFIC_HALT') != (self.subjectIssuer is not None):
            raise ValueError('issuer-specific classification needs its subject')
        return self


class Correction(StrictModel):
    market: Literal['KOSPI','KOSDAQ']
    originalDocument: str = Field(pattern=r'^[0-9]{14}$')
    correctedDocument: str = Field(pattern=r'^[0-9]{14}$')
    reason: str = Field(min_length=10,max_length=500)


class ReviewScope(StrictModel):
    schemaVersion: Literal['SAGOPALGO_SESSION_COVERAGE_REVIEW_SCOPE_V1']
    inventorySha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    parentReviewSha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    reviewedAt: str
    decisions: list[Decision] = Field(min_length=1,max_length=1000)
    corrections: list[Correction] = Field(default_factory=list,max_length=200)

    @model_validator(mode='after')
    def valid(self):
        utc(self.reviewedAt)
        if len({(v.market,v.document) for v in self.decisions})!=len(self.decisions):raise ValueError('duplicate decision')
        if len({(v.market,v.originalDocument,v.correctedDocument) for v in self.corrections})!=len(self.corrections):raise ValueError('duplicate correction')
        return self


def text_changes(before, after):
    a=calendar.text(before);b=calendar.text(after)
    return [{'before':a[i:j],'after':b[k:l]} for op,i,j,k,l in SequenceMatcher(None,a,b,autojunk=False).get_opcodes() if op!='equal']


def halt_fact(row, version, raw, reviewed_at, resumption=False):
    value=calendar.text(raw)
    label={'KOSPI':'유가증권시장','KOSDAQ':'코스닥시장'}[row['market']]
    action=r'재개' if resumption else r'(?:일시)?중단'
    if row['issuer'] or not re.search(label+r'\s*매매거래\s*'+action,value):
        raise ResearchError('SESSION_COVERAGE_HALT_SCOPE_CONFLICT')
    if not re.search(r'CB\s*해제' if resumption else r'서킷브레이커|CB\s*발동',value):raise ResearchError('SESSION_COVERAGE_HALT_EVIDENCE_MISSING')
    match=re.findall(r'1\.\s*일자 및 시각\s*([0-9]{4}-[0-9]{2}-[0-9]{2})\s*([0-9]{2}:[0-9]{2}:[0-9]{2})',value)
    if len(match)!=1 or match[0][0]!=row['reportedAtKstText'][:10]:raise ResearchError('SESSION_COVERAGE_HALT_DATE_CONFLICT')
    stamp=match[0][0]+'T'+match[0][1]+'+09:00';utc(stamp)
    required=r'재개시\s*10분간\s*호가' if resumption else r'향후\s*20분간'
    if not re.search(required,value):raise ResearchError('SESSION_COVERAGE_HALT_DURATION_UNSUPPORTED')
    return {'market':row['market'],'businessDate':match[0][0],'eventAt':stamp,'eventType':'RESUMPTION' if resumption else 'HALT',
        'effectiveDateBasis':'BODY_DATE_AND_PUBLICATION_DATE_AGREE','document':version['document'],
        'bodySha256':version['bodySha256'],'url':version['url'],'knownAt':reviewed_at,
        'fullIntradayTimelineConfirmed':False}


def promotion_decisions(rules, review_at, halt_dates):
    decisions=[]
    for market,value in rules['markets'].items():
        pack=rules['referencePacks'][market]
        days={v['businessDate']:v for v in pack['calendar']}
        existing={v['businessDate'] for v in pack['sessions']}
        seen=set()
        for row in value['candidates']:
            date=row['businessDate'];day(date)
            if date in seen or date in existing or date not in days or not days[date]['openDay']:
                raise ResearchError('SESSION_COVERAGE_CANDIDATE_CALENDAR_CONFLICT')
            if not rules['startDate']<=date<=rules['endDate']:raise ResearchError('SESSION_COVERAGE_CANDIDATE_OUTSIDE_SCOPE')
            periods=[p for p in value['rulePeriods'] if p['startDate']<=date<=p['endDate']]
            if len(periods)!=1 or not periods[0]['continuityConfirmed']:
                raise ResearchError('SESSION_COVERAGE_CANDIDATE_RULE_GAP')
            seen.add(date);period=periods[0]
            blockers=['NOTICE_SCOPE_NOT_EXHAUSTIVE','PUBLICATION_PREHISTORY_UNBOUNDED','CORRECTION_PUBLICATION_HISTORY_UNCONFIRMED']
            if (market,date) in halt_dates:blockers.append('MARKET_WIDE_INTRADAY_HALT_REQUIRES_INTERVAL_MODEL')
            decisions.append({'market':market,'businessDate':date,'decision':'DEFERRED','knownAt':review_at,
                'nominalOpen':period['nominalOpen'],'nominalClose':period['nominalClose'],'ruleBookIds':period['bookIds'],
                'blockers':blockers,'actualSessionConfirmed':False,'includedInReferencePack':False})
    return decisions


def pair_interruptions(events):
    by_date={}
    for e in events:
        by_date.setdefault((e['market'],e['businessDate']),[]).append(e)
    result=[]
    for (market,date),values in sorted(by_date.items()):
        starts=[e for e in values if e['eventType']=='HALT'];ends=[e for e in values if e['eventType']=='RESUMPTION']
        if len(starts)!=1 or len(ends)!=1:
            result.append({'market':market,'businessDate':date,'status':'UNPAIRED','documents':[e['document'] for e in values]})
            continue
        a,b=starts[0],ends[0]
        if utc(b['eventAt'])-utc(a['eventAt'])!=timedelta(minutes=20):
            raise ResearchError('SESSION_COVERAGE_HALT_RESUMPTION_TIME_CONFLICT')
        result.append({'market':market,'businessDate':date,'status':'PAIRED',
            'haltAt':a['eventAt'],'quoteAcceptanceResumesAt':b['eventAt'],
            'continuousTradingResumesAt':(utc(b['eventAt'])+timedelta(minutes=10)).isoformat(),
            'haltDocument':a['document'],'resumptionDocument':b['document'],
            'knownAt':max(a['knownAt'],b['knownAt'],key=utc),
            'basis':'TWO_OFFICIAL_NOTICES_AND_EXPLICIT_TEN_MINUTE_AUCTION','allIntradayInterruptionsComplete':False})
    return result


def build_review(folder, parent_path, rules_path, inventory_path, scope_path):
    inv=inventory(folder,Cache(folder));immutable_json(inventory_path,inv,True)
    plan=load_plan(folder);parent=read_json(read_bytes(parent_path));rules=read_json(read_bytes(rules_path))
    if (digest(read_bytes(parent_path))!=plan['parentSha256'] or digest(read_bytes(rules_path))!=plan['rulesSha256']
            or parent['parentSha256']!=plan['rulesSha256'] or parent['referencePacks']!=rules['referencePacks']
            or (rules['startDate'],rules['endDate'])!=(plan['startDate'],plan['endDate'])):
        raise ResearchError('SESSION_COVERAGE_REVIEW_PARENT_CONFLICT')
    scope=ReviewScope.model_validate(read_json(read_bytes(scope_path)))
    if scope.inventorySha256!=digest(read_bytes(inventory_path)) or scope.parentReviewSha256!=plan['parentSha256']:
        raise ResearchError('SESSION_COVERAGE_REVIEW_HASH')
    if utc(scope.reviewedAt)<max(utc(inv['knownAt']),utc(parent['knownAt'])):
        raise ResearchError('SESSION_COVERAGE_REVIEW_BEFORE_CAPTURE')
    observed={};links=[]
    for row in inv['rows']:
        if len(row['versions'])>1:links.append({'market':row['market'],'receipt':row['receipt'],'versions':row['versions']})
        for v in row['versions']:
            k=(row['market'],v['document'],v['bodySha256'])
            if k in observed and observed[k][1]['url']!=v['url']:raise ResearchError('SESSION_COVERAGE_DOCUMENT_PATH_CONFLICT')
            observed[k]=(row,v)
    wanted={(d.market,d.document,d.bodySha256):d for d in scope.decisions}
    if set(wanted)!=set(observed):raise ResearchError('SESSION_COVERAGE_REVIEW_DECISION_COVERAGE')
    bodies=[];sessions=[];halts=[];raws={}
    parent_bodies={(r['market'],r['document'],r['bodySha256']):r for r in parent['reviewedBodies']}
    for k,(row,v) in observed.items():
        d=wanted[k];raw=read_bytes(folder/v['rawFile']);value=calendar.text(raw)
        if digest(raw)!=d.bodySha256:raise ResearchError('SESSION_COVERAGE_REVIEW_BODY_HASH')
        prior=parent_bodies.get(k)
        if prior and (d.classification!=prior['classification'] or d.subjectIssuer!=prior.get('subjectIssuer')):
            raise ResearchError('SESSION_COVERAGE_PRIOR_DECISION_CONFLICT')
        if d.classification=='REGULAR_SESSION_CHANGE':
            session=review.scheduled_session(row,{**v,'knownAt':v['sourceKnownAt']},raw)
            session.update(knownAt=scope.reviewedAt,sourceKnownAt=v['sourceKnownAt'],document=d.document)
            session['insideEffectiveScope']=inv['startDate']<=session['businessDate']<=inv['endDate']
            if session['insideEffectiveScope']:
                existing=[s for s in rules['referencePacks'][d.market]['sessions'] if s['businessDate']==session['businessDate']]
                if len(existing)!=1 or any(utc(existing[0][t])!=utc(session[t]) for t in ['openAt','closeAt']):
                    raise ResearchError('SESSION_COVERAGE_SCHEDULE_CONFLICT')
            sessions.append(session)
        elif d.classification in {'MARKET_WIDE_HALT','MARKET_WIDE_RESUMPTION'}:
            halts.append(halt_fact(row,v,raw,scope.reviewedAt,d.classification=='MARKET_WIDE_RESUMPTION'))
        else:
            terms={'MARKET_MAKING_POLICY':['시장조성','계약'],'SHORT_SELLING_POLICY':['공매도'],
                   'LOCKUP_POLICY':['의무보유'],'ISSUER_SPECIFIC_HALT':[d.subjectIssuer],
                   'PROGRAM_ORDER_PAUSE':['프로그램','호가','효력'],
                   'OTHER_MARKET_POLICY':['시장']}[d.classification]
            if not all(t in value for t in terms) or re.search(r'정규시장\s*:\s*[0-9]{2}:[0-9]{2}',value):
                raise ResearchError('SESSION_COVERAGE_POLICY_CLASSIFICATION_CONFLICT')
            if d.classification=='OTHER_MARKET_POLICY' and re.search(r'매매거래\s*(?:일시)?중단|서킷브레이커|연초 개장일|CB\s*해제',value):
                raise ResearchError('SESSION_COVERAGE_POLICY_REQUIRES_SPECIFIC_REVIEW')
        raws[(d.market,d.document)]=raw
        bodies.append({**d.model_dump(),'url':v['url'],'sourceKnownAt':v['sourceKnownAt'],'knownAt':scope.reviewedAt})
    groups={}
    for link in links:
        versions=link['versions']
        if len(versions)!=2 or versions[0]['correctionMarked'] or not versions[1]['correctionMarked']:
            raise ResearchError('SESSION_COVERAGE_UNSUPPORTED_CORRECTION_CHAIN')
        k=(link['market'],versions[0]['document'],versions[1]['document'])
        groups.setdefault(k,[]).append(link['receipt'])
    corrections={(c.market,c.originalDocument,c.correctedDocument):c for c in scope.corrections}
    if set(groups)!=set(corrections):raise ResearchError('SESSION_COVERAGE_CORRECTION_COVERAGE')
    correction_results=[]
    for k,receipts in groups.items():
        a=raws[k[:2]];b=raws[(k[0],k[2])]
        correction_results.append({**corrections[k].model_dump(),'receipts':sorted(receipts),
            'originalBodySha256':digest(a),'correctedBodySha256':digest(b),'textChanges':text_changes(a,b),
            'knownAt':scope.reviewedAt,'historicalFirstAvailabilityConfirmed':False})
    halt_dates={(h['market'],h['businessDate']) for h in halts if inv['startDate']<=h['businessDate']<=inv['endDate']}
    if inv['queryVariant']=='HALT_AND_ACTION_CATEGORIES_V2':
        controls={(m,'2024-08-05',kind) for m in notices.FORMS for kind in ['HALT','RESUMPTION']}
        if not controls<={(h['market'],h['businessDate'],h['eventType']) for h in halts}:
            raise ResearchError('SESSION_COVERAGE_CATEGORY_POSITIVE_CONTROL_MISSING')
    for market,date in halt_dates:
        dates=[d for d in rules['referencePacks'][market]['calendar'] if d['businessDate']==date]
        if len(dates)!=1 or not dates[0]['openDay']:raise ResearchError('SESSION_COVERAGE_HALT_CALENDAR_CONFLICT')
    decisions=promotion_decisions(rules,scope.reviewedAt,halt_dates)
    before=[r for r in inv['rows'] if r['reportedAtKstText'][:10]<'2023-01-01']
    after=[r for r in inv['rows'] if r['reportedAtKstText'][:10]>'2026-11-05']
    return {'schemaVersion':'SAGOPALGO_SESSION_COVERAGE_REVIEW_V1','inventorySha256':scope.inventorySha256,
        'reviewScopeSha256':digest(read_bytes(scope_path)),'parentReviewSha256':scope.parentReviewSha256,'rulesSha256':plan['rulesSha256'],
        'startDate':inv['startDate'],'endDate':inv['endDate'],'knownAt':scope.reviewedAt,'sourceKind':inv['sourceKind'],
        'queryCount':len(inv['queries']),'pageCount':sum(q['pages'] for q in inv['queries']),'listRows':len(inv['rows']),
        'bodyCount':len(bodies),'classificationCounts':dict(Counter(d['classification'] for d in bodies)),
        'reviewedBodies':bodies,'scheduledSessions':sessions,'marketWideHalts':halts,'correctionGroups':correction_results,
        'interruptionPairing':pair_interruptions(halts),
        'publicationBoundaryReview':{'start':'2022-01-01','through':'2026-11-06','earlierListRows':len(before),
            'laterListRows':len(after),'prehistoryBefore2022Exhaustive':False,'futureCorrectionsExhaustive':False},
        'promotionDecisions':decisions,'promotionCounts':dict(Counter(d['decision'] for d in decisions)),
        'blockerCounts':dict(Counter(b for d in decisions for b in d['blockers'])),
        'referencePacks':deepcopy(parent['referencePacks']),'scopedExpandedSearchReviewed':True,
        'scopedViewerCorrectionGroupsReviewed':True,'fullTemporaryChangeInventoryComplete':False,
        'fullCorrectionLineageComplete':False,'allHistoricalSessionsComplete':False,
        'usableForTraining':False,'usableForStrategyValidation':False,'usableForTrading':False}


def combine_reports(reports, rules):
    if len(reports)!=2 or {r['schemaVersion'] for r in reports}!={'SAGOPALGO_SESSION_COVERAGE_REVIEW_V1'}:
        raise ResearchError('SESSION_COVERAGE_COMBINED_INPUT')
    first=reports[0];events={};bodies={};groups={}
    for r in reports:
        if any(r[k]!=first[k] for k in ['parentReviewSha256','rulesSha256','startDate','endDate','sourceKind','referencePacks']):
            raise ResearchError('SESSION_COVERAGE_COMBINED_SCOPE_CONFLICT')
        for b in r['reviewedBodies']:
            k=(b['market'],b['document'])
            if k in bodies and any(b[f]!=bodies[k][f] for f in ['bodySha256','classification','subjectIssuer']):
                raise ResearchError('SESSION_COVERAGE_COMBINED_BODY_CONFLICT')
            bodies[k]=b
        for e in r['marketWideHalts']:
            k=(e['market'],e['document'])
            if k in events and any(e[f]!=events[k][f] for f in ['bodySha256','businessDate','eventAt','eventType']):
                raise ResearchError('SESSION_COVERAGE_COMBINED_EVENT_CONFLICT')
            events[k]=e
        for g in r['correctionGroups']:groups[(g['market'],g['originalDocument'],g['correctedDocument'])]=g
    if digest(canonical(rules))!=first['rulesSha256']:
        raise ResearchError('SESSION_COVERAGE_COMBINED_RULE_HASH')
    known=max((r['knownAt'] for r in reports),key=utc)
    halt_dates={(e['market'],e['businessDate']) for e in events.values() if first['startDate']<=e['businessDate']<=first['endDate']}
    decisions=promotion_decisions(rules,known,halt_dates)
    return {'schemaVersion':'SAGOPALGO_SESSION_COVERAGE_DECISION_V1',
        'reviewReportSha256s':[digest(canonical(r)) for r in reports],'rulesSha256':first['rulesSha256'],
        'parentReviewSha256':first['parentReviewSha256'],'startDate':first['startDate'],'endDate':first['endDate'],
        'knownAt':known,'sourceKind':first['sourceKind'],'reviewedUniqueBodies':len(bodies),
        'classificationCounts':dict(Counter(b['classification'] for b in bodies.values())),
        'marketEvents':list(events.values()),'interruptionPairing':pair_interruptions(list(events.values())),
        'correctionGroups':list(groups.values()),'promotionDecisions':decisions,
        'promotionCounts':dict(Counter(d['decision'] for d in decisions)),
        'blockerCounts':dict(Counter(b for d in decisions for b in d['blockers'])),
        'referencePacks':deepcopy(first['referencePacks']),'allHistoricalSessionsComplete':False,
        'fullTemporaryChangeInventoryComplete':False,'fullCorrectionLineageComplete':False,
        'usableForTraining':False,'usableForStrategyValidation':False,'usableForTrading':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['plan','extend','collect','build','audit','review','audit-review','as-of','decide','audit-decision'])
    p.add_argument('--job',type=Path,required=True);p.add_argument('--parent',type=Path);p.add_argument('--rules',type=Path);p.add_argument('--source-job',type=Path)
    p.add_argument('--max-requests',type=int,default=400);p.add_argument('--max-new-requests',type=int,default=0);p.add_argument('--output',type=Path)
    p.add_argument('--variant',choices=['TITLES_AND_BOUNDARY','HALT_AND_ACTION_CATEGORIES_V2'],default='TITLES_AND_BOUNDARY')
    p.add_argument('--inventory',type=Path);p.add_argument('--review',type=Path);p.add_argument('--at');p.add_argument('--market',choices=['KOSPI','KOSDAQ'])
    p.add_argument('--from-job',type=Path);p.add_argument('--reuse-job',type=Path)
    p.add_argument('--other-job',type=Path);p.add_argument('--other-inventory',type=Path);p.add_argument('--other-review',type=Path)
    a=p.parse_args()
    try:
        if a.command=='plan':
            if not all([a.parent,a.rules,a.source_job]):p.error('plan requires --parent --rules --source-job')
            result=prepare(a.job,a.parent,a.rules,a.source_job,a.max_requests,a.variant)
            result={'planId':result['planId'],'queries':len(result['queries']),'maxRequests':result['maxRequests']}
        elif a.command=='extend':
            if not a.from_job or not a.reuse_job:p.error('extend requires --from-job --reuse-job')
            result=extend(a.job,a.from_job,a.reuse_job,a.max_requests)
            result={'planId':result['planId'],'inheritedRequests':result['inheritedRequests'],'maxRequests':result['maxRequests']}
        elif a.command=='collect':
            with job_lock(a.job):
                cache=Cache(a.job,a.max_new_requests,notices.kind.Transport())
                try:
                    result=inventory(a.job,cache);result={'status':'CAPTURED','rows':len(result['rows']),'newRequests':cache.total}
                except ResearchError as ex:
                    if str(ex)!='SESSION_COVERAGE_PENDING':raise
                    result={'status':'PENDING','newRequests':cache.total,'newRequestsThisRun':cache.used}
        elif a.command in {'build','audit'}:
            if not a.output:p.error('build/audit requires --output')
            result=inventory(a.job,Cache(a.job));immutable_json(a.output,result,a.command=='audit')
            result={'status':'EXPANDED_SEARCH_CAPTURED','queries':len(result['queries']),'rows':len(result['rows']),'sha256':digest(read_bytes(a.output))}
        else:
            if not all([a.parent,a.rules,a.inventory,a.review,a.output]):p.error('review requires --parent --rules --inventory --review --output')
            result=build_review(a.job,a.parent,a.rules,a.inventory,a.review)
            if a.command in {'decide','audit-decision'}:
                if not all([a.other_job,a.other_inventory,a.other_review]):p.error('decision requires --other-job --other-inventory --other-review')
                other=build_review(a.other_job,a.parent,a.rules,a.other_inventory,a.other_review)
                result=combine_reports([result,other],read_json(read_bytes(a.rules)))
            immutable_json(a.output,result,a.command not in {'review','decide'})
            if a.command=='as-of':
                if not a.at or not a.market:p.error('as-of requires --at --market')
                cutoff=utc(a.at)
                result={'market':a.market,'promotionDecisions':[d for d in result['promotionDecisions'] if d['market']==a.market and utc(d['knownAt'])<=cutoff],
                    'usableForTraining':False,'usableForTrading':False}
            else:result={'status':'REVIEWED_PROMOTION_DEFERRED','bodies':result.get('bodyCount',result.get('reviewedUniqueBodies')),'promotionCounts':result['promotionCounts'],'sha256':digest(read_bytes(a.output))}
        print(json.dumps(result,ensure_ascii=False,sort_keys=True));return 0
    except (ResearchError,ValueError,KeyError,TypeError,OSError) as ex:
        print(json.dumps({'error':str(ex) if isinstance(ex,ResearchError) else 'SESSION_COVERAGE_INPUT_INVALID'}));return 2


if __name__=='__main__':raise SystemExit(main())
