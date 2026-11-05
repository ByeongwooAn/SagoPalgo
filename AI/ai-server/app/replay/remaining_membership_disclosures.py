"""Bounded acquisition of the exact remaining V6 membership observations."""
import argparse
from datetime import timedelta
import json
from pathlib import Path
import re
from typing import Literal
from urllib.parse import urlencode

from pydantic import Field, model_validator

from . import name_disclosures as engine
from .dataset import canonical, digest, read_bytes, read_json
from .history import day
from .krx_storage import atomic_json
from .models import ResearchError, StrictModel


class Target(StrictModel):
    observationId: str = Field(pattern=r'^[0-9a-f]{64}$')
    kind: Literal['ADDED_OBSERVED', 'REMOVED_OBSERVED']
    symbol: str = Field(pattern=r'^[0-9A-Z]{6}$')
    isin: str = Field(pattern=r'^[0-9A-Z]{12}$')
    market: Literal['KOSPI', 'KOSDAQ']
    observedName: str
    observedFrom: str
    observedTo: str
    statusDate: str
    statusEventType: str
    statusReferenceId: str = Field(pattern=r'^[0-9a-f]{64}$')
    category: Literal['RELISTING', 'INBOUND_TRANSFER', 'DELISTING_REVIEW']
    searchThrough: str


class Config(engine.Config):
    schemaVersion: Literal['SAGOPALGO_REMAINING_MEMBERSHIP_PLAN_V1'] = 'SAGOPALGO_REMAINING_MEMBERSHIP_PLAN_V1'
    inventorySha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    targets: list[Target] = Field(min_length=1, max_length=100)
    maxRequests: int = Field(default=160, ge=4, le=1000)

    @model_validator(mode='after')
    def bounds(self):
        if (self.sourceKind not in {'SYNTHETIC', 'PROVIDER_OBSERVATIONS'}
                or (self.lookbackDays,self.maxAttemptsPerStage,self.minIntervalSeconds)!=(45,3,1)
                or len({t.observationId for t in self.targets})!=len(self.targets) or self.maxRequests<len(self.targets)*4
                or any(not day(self.startDate)<=day(t.observedFrom)<day(t.statusDate)<=day(t.observedTo)<=day(t.searchThrough)<=day(self.endDate)
                       or day(t.searchThrough)!=min(day(self.endDate),day(t.statusDate)+timedelta(days=30)) for t in self.targets)):
            raise ValueError('invalid bounded remaining membership scope')
        return self


def targets_from(parent, inventory):
    if parent.get('schemaVersion')!='SAGOPALGO_UNIVERSE_RECONCILIATION_V6': raise ResearchError('REMAINING_PARENT_INVALID')
    rows={}
    for r in parent['rows']:
        if r['observationId']!=digest(canonical(r['observation'])) or r['observationId'] in rows:
            raise ResearchError('REMAINING_PARENT_INVALID')
        rows[r['observationId']]=r
    pending={i:r for i,r in rows.items() if r['resolution']=='STATUS_LIST_MATCH'}
    entries=[t for t in inventory['targets'] if t['observationId'] in pending]
    if (not pending or len(entries)!=len(pending) or {t['observationId'] for t in entries}!=set(pending)
            or inventory['sourceKind']!=parent['sourceKind'] or (inventory['startDate'],inventory['endDate'])!=(parent['startDate'],parent['endDate'])):
        raise ResearchError('REMAINING_EXACT_SCOPE_REQUIRED')
    targets=[]
    for t in entries:
        r=pending[t['observationId']]; o=r['observation']; issue=o['after'] or o['before']
        category='DELISTING_REVIEW' if t['category']=='DELISTING' else t['category']
        expected_kind='REMOVED_OBSERVED' if category=='DELISTING_REVIEW' else 'ADDED_OBSERVED'
        refs=[e for e in r['evidence'] if e.get('kind')==('DELISTING' if expected_kind=='REMOVED_OBSERVED' else 'LISTING')]
        if (category not in {'RELISTING','INBOUND_TRANSFER','DELISTING_REVIEW'} or o['kind']!=expected_kind
                or issue['classification']!='COMMON_SHARE' or issue['isin']!=o['isin'] or len(refs)!=1
                or (t['kind'],t['symbol'],t['isin'],t['market'],t['observedName'],t['observedFrom'],t['observedTo'])
                   !=(o['kind'],issue['symbol'],issue['isin'],issue['market'],issue['name'],o['observedFrom'],o['observedTo'])
                or (t['statusDate'],t['statusEventType'],t['statusReferenceId'])!=(refs[0]['date'],refs[0]['eventType'],refs[0]['referenceId'])
                or category=='RELISTING' and t['statusEventType']!='재상장'
                or category=='INBOUND_TRANSFER' and t['statusEventType']!='이전상장'):
            raise ResearchError('REMAINING_IDENTITY_STATUS_CONFLICT')
        targets.append({**{k:v for k,v in t.items() if k not in {'category','auditedReusableObservationIds'}},'category':category,
            'searchThrough':min(day(parent['endDate']),day(t['statusDate'])+timedelta(days=30)).isoformat()})
    return targets


def prepare(folder, parent_path, inventory_path, max_requests=160):
    raw, inv_raw=read_bytes(parent_path),read_bytes(inventory_path); p,inv=read_json(raw),read_json(inv_raw)
    if p.get('listingInventorySha256')!=digest(inv_raw): raise ResearchError('REMAINING_INVENTORY_HASH_MISMATCH')
    payload=Config(parentSha256=digest(raw),inventorySha256=digest(inv_raw),sourceKind=p['sourceKind'],startDate=p['startDate'],endDate=p['endDate'],
                   targets=targets_from(p,inv),maxRequests=max_requests).model_dump(mode='json')
    plan={**payload,'planId':digest(canonical(payload))}
    folder.mkdir(parents=True,exist_ok=False);(folder/'raw').mkdir()
    atomic_json(folder/'plan.json',plan);atomic_json(folder/'journal.json',{'planId':plan['planId'],'attempts':[]})
    return plan


def candidates(raw, target):
    root=engine.public.html(raw); info=[v for v in root.walk('div') if v.attrs.get('class')=='info type-00']
    counts=re.findall(r'전체\s*([0-9,]+)\s*건\s*:\s*([0-9]+)\s*/\s*([0-9]+)',info[0].text()) if len(info)==1 else []
    if len(counts)!=1: raise ResearchError('REMAINING_SEARCH_LAYOUT')
    total,page,pages=[int(v.replace(',','')) for v in counts[0]];links=[v for v in root.walk('a') if v.attrs.get('href')=='#viewer']
    if total>100 or page!=1 or pages not in ({0,1} if total==0 else {1}) or len(links)!=total:
        raise ResearchError('REMAINING_SEARCH_INCOMPLETE')
    found=[]
    for link in links:
        title=re.sub(r'\s+','',link.text());core=title.removeprefix('[정정]')
        match=re.match(r'^(상장폐지)(?:\(|$)',core) if target['kind']=='REMOVED_OBSERVED' else re.match(r'^(주권재상장|재상장|주권신규상장|신규상장)(?:\(|$)',core)
        if not match: continue
        receipt=re.fullmatch(r"openDisclsViewer\('([0-9]{14})',''\);?",link.attrs.get('onclick',''))
        if not receipt: raise ResearchError('REMAINING_SEARCH_LINK_INVALID')
        found.append({'receipt':receipt[1],'title':title,'corrected':title.startswith('[정정]'),'viewerTitle':match[1]})
    if not 1<=len(found)<=4 or len({v['receipt'] for v in found})!=len(found): raise ResearchError('REMAINING_CANDIDATE_REVIEW')
    return sorted(found,key=lambda v:v['receipt'])


def viewer(raw, target, candidate):
    return engine.viewer(raw,target,candidate)


def requests_for(t, completed):
    params={'method':'searchDetailsSub','forward':'details_sub','currentPageSize':'100','pageIndex':'1','orderMode':'0','orderStat':'D',
        'fromDate':(day(t['observedFrom'])-timedelta(days=45)).isoformat(),'toDate':t['searchThrough'],'repIsuSrtCd':'A'+t['symbol'],
        'searchCodeType':'number','searchCorpName':t['symbol'],'reportNm':'상장','reportCd':'','allRepIsuSrtCd':'','marketType':''}
    yield 'SEARCH',{'url':engine.public.BASE+'/disclosure/details.do','method':'POST','parameters':params}
    for i,c in enumerate(candidates(completed['SEARCH'],t)):
        label='V'+str(i)
        yield label+'_VIEWER',{'url':engine.public.BASE+'/common/disclsviewer.do?'+urlencode({'acptno':c['receipt'],'method':'search'}),'method':'GET','parameters':None}
        doc=viewer(completed[label+'_VIEWER'],t,c)['document']
        yield label+'_PATH',{'url':engine.public.BASE+'/common/disclsviewer.do','method':'POST','parameters':{'method':'searchContents','docNo':doc}}
        yield label+'_BODY',{'url':engine.public.path_result(completed[label+'_PATH'],c['receipt'],doc),'method':'GET','parameters':None}


def load(folder): return engine.load(folder,Config,requests_for)
def inspect(folder,target,latest): return engine.inspect(folder,target,latest,request_builder=requests_for)
def capture_summary(value):
    return {**{k:v for k,v in value.items() if k!='nameChangeConfirmed'},'membershipConfirmed':False,'phase':'REMAINING_MEMBERSHIP'}
def summary(folder): return capture_summary(engine.summary(folder,Config,requests_for))
def collect(folder,transport,budget,retry_failed=False,**kwargs):
    return capture_summary(engine.collect(folder,transport,budget,retry_failed,config_type=Config,request_builder=requests_for,**kwargs))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for command in ['plan','collect','audit']:
        q=sub.add_parser(command);q.add_argument('--job',type=Path,required=True)
        if command=='plan':
            q.add_argument('--parent',type=Path,required=True);q.add_argument('--inventory',type=Path,required=True);q.add_argument('--max-requests',type=int,default=160)
        if command=='collect':q.add_argument('--max-new-requests',type=int,required=True);q.add_argument('--retry-failed',action='store_true')
    args=p.parse_args(argv)
    try:
        result=prepare(args.job,args.parent,args.inventory,args.max_requests) if args.command=='plan' else collect(args.job,engine.public.Transport(),args.max_new_requests,args.retry_failed) if args.command=='collect' else summary(args.job)
        print(json.dumps({k:v for k,v in result.items() if k!='targets'},sort_keys=True));return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'diagnostic':str(exc) if isinstance(exc,ResearchError) else 'REMAINING_INPUT_INVALID'}));return 2


if __name__=='__main__':raise SystemExit(main())
