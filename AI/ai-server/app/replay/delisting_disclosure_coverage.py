"""Exact V5 delisting subset of the original 514-item inventory and bounded KIND capture."""
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
    kind: Literal['REMOVED_OBSERVED']
    symbol: str = Field(pattern=r'^[0-9A-Z]{6}$')
    isin: str = Field(pattern=r'^[0-9A-Z]{12}$')
    market: Literal['KOSPI', 'KOSDAQ']
    observedName: str = Field(min_length=1, max_length=300)
    observedFrom: str
    observedTo: str
    statusDate: str
    statusEventType: str = Field(min_length=1, max_length=1000)
    statusReferenceId: str = Field(pattern=r'^[0-9a-f]{64}$')


class Config(engine.Config):
    schemaVersion: Literal['SAGOPALGO_DELISTING_COVERAGE_PLAN_V1'] = 'SAGOPALGO_DELISTING_COVERAGE_PLAN_V1'
    inventorySha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    targets: list[Target] = Field(min_length=1, max_length=500)
    maxRequests: int = Field(default=1000, ge=4, le=3000)

    @model_validator(mode='after')
    def bounds(self):
        if (self.sourceKind not in {'SYNTHETIC','PROVIDER_OBSERVATIONS'}
                or (self.lookbackDays,self.maxAttemptsPerStage,self.minIntervalSeconds)!=(45,3,1)
                or len({t.observationId for t in self.targets})!=len(self.targets) or self.maxRequests<len(self.targets)*4
                or any(not day(self.startDate)<=day(t.observedFrom)<day(t.statusDate)<=day(t.observedTo)<=day(self.endDate) for t in self.targets)):
            raise ValueError('invalid bounded delisting scope')
        return self


def targets_from(parent, inventory):
    if parent.get('schemaVersion')!='SAGOPALGO_UNIVERSE_RECONCILIATION_V5':
        raise ResearchError('DELISTING_PARENT_INVALID')
    rows={}
    for r in parent['rows']:
        identity=r['observationId']
        if identity!=digest(canonical(r['observation'])) or identity in rows: raise ResearchError('DELISTING_PARENT_INVALID')
        rows[identity]=r
    expected={k for k,r in rows.items() if r['resolution']=='STATUS_LIST_MATCH' and r['observation']['kind']=='REMOVED_OBSERVED'}
    entries=[t for t in inventory['targets'] if t['category']=='DELISTING']
    if (not expected or len(entries)!=len(expected) or {t['observationId'] for t in entries}!=expected
            or inventory['sourceKind']!=parent['sourceKind'] or (inventory['startDate'],inventory['endDate'])!=(parent['startDate'],parent['endDate'])):
        raise ResearchError('DELISTING_EXACT_INVENTORY_SCOPE_REQUIRED')
    targets=[]
    for t in entries:
        r=rows[t['observationId']]; o=r['observation']; issue=o['before']
        refs=[e for e in r['evidence'] if e.get('kind')=='DELISTING']
        if (o['after'] is not None or len(refs)!=1 or issue['classification']!='COMMON_SHARE'
                or (t['kind'],t['symbol'],t['isin'],t['market'],t['observedName'],t['observedFrom'],t['observedTo'])
                !=(o['kind'],issue['symbol'],issue['isin'],issue['market'],issue['name'],o['observedFrom'],o['observedTo'])
                or (t['statusDate'],t['statusEventType'],t['statusReferenceId'])!=(refs[0]['date'],refs[0]['eventType'],refs[0]['referenceId'])):
            raise ResearchError('DELISTING_INVENTORY_IDENTITY_OR_STATUS_CONFLICT')
        targets.append({k:v for k,v in t.items() if k not in {'category','auditedReusableObservationIds'}})
    return targets


def prepare(folder,parent_path,inventory_path,max_requests=1000):
    raw, inv_raw=read_bytes(parent_path),read_bytes(inventory_path)
    parent,inv=read_json(raw),read_json(inv_raw)
    if parent.get('listingInventorySha256')!=digest(inv_raw): raise ResearchError('DELISTING_INVENTORY_HASH_MISMATCH')
    payload=Config(parentSha256=digest(raw),inventorySha256=digest(inv_raw),sourceKind=parent['sourceKind'],
        startDate=parent['startDate'],endDate=parent['endDate'],targets=targets_from(parent,inv),maxRequests=max_requests).model_dump(mode='json')
    plan={**payload,'planId':digest(canonical(payload))}
    folder.mkdir(parents=True,exist_ok=False); (folder/'raw').mkdir()
    atomic_json(folder/'plan.json',plan); atomic_json(folder/'journal.json',{'planId':plan['planId'],'attempts':[]})
    return plan


def candidates(raw):
    root=engine.public.html(raw)
    info=[v for v in root.walk('div') if v.attrs.get('class')=='info type-00']
    counts=re.findall(r'전체\s*([0-9,]+)\s*건\s*:\s*([0-9]+)\s*/\s*([0-9]+)',info[0].text()) if len(info)==1 else []
    if len(counts)!=1: raise ResearchError('DELISTING_SEARCH_LAYOUT')
    total,page,pages=[int(v.replace(',','')) for v in counts[0]]
    links=[v for v in root.walk('a') if v.attrs.get('href')=='#viewer']
    if total>100 or page!=1 or pages not in ({0,1} if total==0 else {1}) or len(links)!=total:
        raise ResearchError('DELISTING_SEARCH_INCOMPLETE')
    result=[]
    for link in links:
        title=re.sub(r'\s+','',link.text()); core=title.removeprefix('[정정]')
        if not re.match(r'^상장폐지(?:\(|$)',core): continue
        receipt=re.fullmatch(r"openDisclsViewer\('([0-9]{14})',''\);?",link.attrs.get('onclick',''))
        if not receipt: raise ResearchError('DELISTING_SEARCH_LINK_INVALID')
        result.append({'receipt':receipt[1],'title':title,'corrected':title.startswith('[정정]')})
    if not 1<=len(result)<=4 or len({v['receipt'] for v in result})!=len(result):
        raise ResearchError('DELISTING_NO_UNIQUE_REVIEWED_CANDIDATES')
    return sorted(result,key=lambda v:v['receipt'])


def viewer(raw,target,candidate):
    if not candidate['corrected']:
        try:
            result=engine.public.viewer_result(raw,target)
            return {**result,'documents':[result['document']]}
        except ResearchError as exc:
            if str(exc)!='MEMBERSHIP_EVIDENCE_CORRECTION_REVIEW': raise
    return engine.viewer(raw,target,{**candidate,'viewerTitle':'상장폐지'})


def requests_for(t,completed):
    params={'method':'searchDetailsSub','forward':'details_sub','currentPageSize':'100','pageIndex':'1','orderMode':'0','orderStat':'D',
        'fromDate':(day(t['observedFrom'])-timedelta(days=45)).isoformat(),'toDate':t['observedTo'],
        'repIsuSrtCd':'A'+t['symbol'],'searchCodeType':'number','searchCorpName':t['symbol'],'reportNm':'상장폐지',
        'reportCd':'','allRepIsuSrtCd':'','marketType':''}
    yield 'SEARCH',{'url':engine.public.BASE+'/disclosure/details.do','method':'POST','parameters':params}
    for index,candidate in enumerate(candidates(completed['SEARCH'])):
        label='V'+str(index)
        yield label+'_VIEWER',{'url':engine.public.BASE+'/common/disclsviewer.do?'+urlencode({'acptno':candidate['receipt'],'method':'search'}),'method':'GET','parameters':None}
        doc=viewer(completed[label+'_VIEWER'],t,candidate)['document']
        yield label+'_PATH',{'url':engine.public.BASE+'/common/disclsviewer.do','method':'POST','parameters':{'method':'searchContents','docNo':doc}}
        url=engine.public.path_result(completed[label+'_PATH'],candidate['receipt'],doc)
        yield label+'_BODY',{'url':url,'method':'GET','parameters':None}


def load(folder): return engine.load(folder,Config,requests_for)
def inspect(folder,target,latest): return engine.inspect(folder,target,latest,request_builder=requests_for)
def capture_summary(value): return {**{k:v for k,v in value.items() if k!='nameChangeConfirmed'},'membershipConfirmed':False,'phase':'DELISTING'}
def collect(folder,transport,max_new_requests,retry_failed=False,**kwargs):
    return capture_summary(engine.collect(folder,transport,max_new_requests,retry_failed,config_type=Config,request_builder=requests_for,**kwargs))
def summary(folder): return capture_summary(engine.summary(folder,Config,requests_for))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='command',required=True)
    for command in ['plan','collect','audit']:
        p=sub.add_parser(command); p.add_argument('--job',type=Path,required=True)
        if command=='plan':
            p.add_argument('--parent',type=Path,required=True); p.add_argument('--inventory',type=Path,required=True); p.add_argument('--max-requests',type=int,default=1000)
        if command=='collect': p.add_argument('--max-new-requests',type=int,required=True); p.add_argument('--retry-failed',action='store_true')
    args=parser.parse_args(argv)
    try:
        result=prepare(args.job,args.parent,args.inventory,args.max_requests) if args.command=='plan' else collect(args.job,engine.public.Transport(),args.max_new_requests,args.retry_failed) if args.command=='collect' else summary(args.job)
        print(json.dumps({k:v for k,v in result.items() if k!='targets'},sort_keys=True),flush=True); return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'diagnostic':str(exc) if isinstance(exc,ResearchError) else 'DELISTING_INPUT_INVALID'})); return 2


if __name__=='__main__': raise SystemExit(main())
