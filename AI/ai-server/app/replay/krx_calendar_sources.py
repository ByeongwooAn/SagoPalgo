"""Audited public KRX annual holiday queries; no KIS or authenticated API calls."""
import argparse
from datetime import timedelta
import json
from pathlib import Path
import re
import time
from urllib.parse import urlencode
from urllib.request import build_opener, Request

from .dataset import canonical,digest,read_bytes,read_json
from .history import day,job_lock,now,NoRedirect
from .krx_storage import atomic_json
from .models import ResearchError,utc

BASE='https://open.krx.co.kr'
PAGE='/contents/MKD/01/0110/01100305/MKD01100305.jsp'
BLD='MKD/01/0110/01100305/mkd01100305_01'
DATA=BASE+'/contents/OPN/99/OPN99000001.jspx'
OTP=BASE+'/contents/COM/GenerateOTP.jspx?'+urlencode({'name':'form','bld':BLD})
LIMIT=1024*1024


def spec(year,stage,otp=None):
    if stage=='OTP':return {'url':OTP,'method':'GET','parameters':None}
    token=otp.decode('ascii').strip()
    if not re.fullmatch(r'[A-Za-z0-9+/=_-]{16,4096}',token):raise ResearchError('KRX_CALENDAR_OTP_INVALID')
    return {'url':DATA,'method':'POST','parameters':{'search_bas_yy':str(year),'gridTp':'KRX','code':token,'pagePath':PAGE}}


def holidays(raw,year):
    value=read_json(raw)
    if not isinstance(value,dict) or set(value)!={'block1'} or not isinstance(value['block1'],list) or not 1<=len(value['block1'])<=50:
        raise ResearchError('KRX_HOLIDAY_ENVELOPE_REVIEW')
    result=[];seen=set();weekdays=['MON','TUE','WED','THU','FRI','SAT','SUN'];korean=['월요일','화요일','수요일','목요일','금요일','토요일','일요일']
    for row in value['block1']:
        if not isinstance(row,dict) or set(row)!={'calnd_dd','dy_tp_cd','calnd_dd_dy','kr_dy_tp','holdy_nm'}:
            raise ResearchError('KRX_HOLIDAY_ROW_REVIEW')
        date=day(row['calnd_dd'])
        if (date.year!=year or row['calnd_dd_dy']!=date.isoformat() or row['dy_tp_cd']!=weekdays[date.weekday()]
                or row['kr_dy_tp']!=korean[date.weekday()] or date.isoformat() in seen
                or not isinstance(row['holdy_nm'],str) or not 1<=len(row['holdy_nm'])<=100):
            raise ResearchError('KRX_HOLIDAY_DATE_OR_LABEL_CONFLICT')
        seen.add(date.isoformat());result.append({'date':date.isoformat(),'reason':row['holdy_nm']})
    # Reject obviously truncated annual responses rather than inferring all other days open.
    endings=[v['date'] for v in result if v['reason']=='연말휴장일']
    cursor=day(str(year)+'-12-31')
    while cursor.weekday()>=5 or cursor.isoformat() in {v['date'] for v in result if v['reason']!='연말휴장일'}:cursor-=timedelta(days=1)
    if endings!=[cursor.isoformat()] or not any(v['reason'] in {'근로자의날','노동절'} and v['date']==str(year)+'-05-01' for v in result):
        raise ResearchError('KRX_HOLIDAY_ANNUAL_ANCHORS_MISSING')
    return sorted(result,key=lambda v:v['date'])


def seed_capture(source,year):
    records={};bodies={}
    for stage in ['OTP','DATA']:
        name=f'year-{year}-'+stage.lower();raw=read_bytes(source/(name+'.bin'));m=read_json(read_bytes(source/(name+'.json')))
        expected=spec(year,stage,bodies.get('OTP'))
        if (m['url'],m['method'],m.get('parameters'))!=(expected['url'],expected['method'],expected['parameters']) or m['sha256']!=digest(raw):
            raise ResearchError('KRX_CALENDAR_SEED_TAMPERED')
        if utc(m['startedAt'])>utc(m['capturedAt']):raise ResearchError('KRX_CALENDAR_SEED_TIME_CONFLICT')
        records[stage]={'request':expected,'sha256':digest(raw),'startedAt':m['startedAt'],'capturedAt':m['capturedAt']};bodies[stage]=raw
    if utc(records['DATA']['startedAt'])<utc(records['OTP']['capturedAt']):raise ResearchError('KRX_CALENDAR_SEED_TIME_CONFLICT')
    holidays(bodies['DATA'],year)
    return {'year':year,'records':records},bodies


def prepare(folder,start,end,max_requests=16,seed_source=None,seed_year=None,source_kind='PROVIDER_OBSERVATIONS'):
    first,last=day(start),day(end)
    if not 2023<=first.year<=last.year<=2026 or first>last or source_kind not in {'PROVIDER_OBSERVATIONS','SYNTHETIC'}:raise ResearchError('KRX_CALENDAR_SCOPE_INVALID')
    years=list(range(first.year,last.year+1));seeds=[];seed_raw={}
    if seed_source is not None:
        if seed_year not in years:raise ResearchError('KRX_CALENDAR_SEED_SCOPE_INVALID')
        seed,bodies=seed_capture(seed_source,seed_year);seeds=[seed];seed_raw[seed_year]=bodies
    if type(max_requests) is not int or not 2*(len(years)-len(seeds))<=max_requests<=32:raise ResearchError('KRX_CALENDAR_BUDGET_INVALID')
    payload={'schemaVersion':'SAGOPALGO_KRX_CALENDAR_PLAN_V1','startDate':start,'endDate':end,'years':years,'seeds':seeds,
        'maxRequests':max_requests,'minIntervalSeconds':1,'sourceKind':source_kind}
    plan={**payload,'planId':digest(canonical(payload))};folder.mkdir(parents=True,exist_ok=False);(folder/'raw').mkdir();(folder/'seed').mkdir()
    for year,bodies in seed_raw.items():
        for stage,raw in bodies.items():(folder/'seed'/f'{year}-{stage}.bin').write_bytes(raw)
    atomic_json(folder/'plan.json',plan);atomic_json(folder/'journal.json',{'planId':plan['planId'],'attempts':[]})
    return plan


def inspect(folder,plan,latest,year,expected=None):
    done={};seed=next((s for s in plan['seeds'] if s['year']==year),None)
    for stage in ['OTP','DATA']:
        request=spec(year,stage,done.get('OTP'));key=(year,stage)
        if expected is not None:expected[key]=request
        e=seed['records'][stage] if seed else latest.get(key)
        if not e:return stage,request,done,'PENDING'
        if e['request']!=request:raise ResearchError('KRX_CALENDAR_REQUEST_TAMPERED')
        if not seed and e['state']!='CAPTURED':return stage,request,done,e['state']
        raw=read_bytes(folder/('seed' if seed else 'raw')/(f'{year}-{stage}.bin' if seed else f"{e['seq']:04d}.bin"))
        if digest(raw)!=e['sha256']:raise ResearchError('KRX_CALENDAR_RAW_TAMPERED')
        done[stage]=raw
    holidays(done['DATA'],year)
    return None,None,done,'CAPTURED'


def load(folder):
    plan=read_json(read_bytes(folder/'plan.json'));payload={k:v for k,v in plan.items() if k!='planId'}
    if (set(plan)!={'schemaVersion','startDate','endDate','years','seeds','maxRequests','minIntervalSeconds','sourceKind','planId'}
            or plan['schemaVersion']!='SAGOPALGO_KRX_CALENDAR_PLAN_V1' or plan['planId']!=digest(canonical(payload))
            or not 2023<=day(plan['startDate']).year<=day(plan['endDate']).year<=2026 or plan['startDate']>plan['endDate']
            or plan['years']!=list(range(day(plan['startDate']).year,day(plan['endDate']).year+1))
            or plan['minIntervalSeconds']!=1 or plan['sourceKind'] not in {'PROVIDER_OBSERVATIONS','SYNTHETIC'}
            or len(plan['seeds'])>1 or any(s['year'] not in plan['years'] or set(s)!= {'year','records'} or set(s['records'])!={'OTP','DATA'} for s in plan['seeds'])
            or type(plan['maxRequests']) is not int or not 2*(len(plan['years'])-len(plan['seeds']))<=plan['maxRequests']<=32):
        raise ResearchError('KRX_CALENDAR_PLAN_INVALID')
    journal=read_json(read_bytes(folder/'journal.json'));latest={}
    if set(journal)!={'planId','attempts'} or journal['planId']!=plan['planId'] or len(journal['attempts'])>plan['maxRequests']:
        raise ResearchError('KRX_CALENDAR_JOURNAL_INVALID')
    seed_years={s['year'] for s in plan['seeds']}
    for seq,e in enumerate(journal['attempts'],1):
        key=(e['year'],e['stage']);fields={'seq','year','stage','request','state','startedAt'}
        if (type(e['seq']) is not int or e['seq']!=seq or e['year'] not in plan['years'] or e['year'] in seed_years
                or key in latest or e['stage'] not in {'OTP','DATA'} or e['state'] not in {'RESERVED','CAPTURED','FAILED'}):
            raise ResearchError('KRX_CALENDAR_JOURNAL_INVALID')
        utc(e['startedAt'])
        if e['state']=='CAPTURED':
            fields|={'sha256','capturedAt'}
            if utc(e['capturedAt'])<utc(e['startedAt']):raise ResearchError('KRX_CALENDAR_JOURNAL_INVALID')
        if e['state']=='FAILED':
            fields|={'diagnostic','finishedAt'}
            if utc(e['finishedAt'])<utc(e['startedAt']):raise ResearchError('KRX_CALENDAR_JOURNAL_INVALID')
        if set(e)!=fields:raise ResearchError('KRX_CALENDAR_JOURNAL_INVALID')
        latest[key]=e
    expected={}
    for year in plan['years']:inspect(folder,plan,latest,year,expected)
    if any(e['request']!=expected.get((e['year'],e['stage'])) for e in journal['attempts']):raise ResearchError('KRX_CALENDAR_REQUEST_TAMPERED')
    for seed in plan['seeds']:
        for e in seed['records'].values():
            if set(e)!={'request','sha256','startedAt','capturedAt'} or utc(e['startedAt'])>utc(e['capturedAt']):raise ResearchError('KRX_CALENDAR_SEED_INVALID')
        if utc(seed['records']['DATA']['startedAt'])<utc(seed['records']['OTP']['capturedAt']):raise ResearchError('KRX_CALENDAR_SEED_INVALID')
    return plan,journal,latest


class Transport:
    source_kind='PROVIDER_OBSERVATIONS'
    def fetch(self,s):
        if s['url'] not in {OTP,DATA}:raise ResearchError('KRX_CALENDAR_URL_INVALID')
        req=Request(s['url'],data=urlencode(s['parameters']).encode() if s['parameters'] is not None else None,
                    headers={'User-Agent':'SagoPalgo-local-research/1','Referer':BASE+PAGE},method=s['method'])
        with build_opener(NoRedirect()).open(req,timeout=20) as response:raw=response.read(LIMIT+1)
        if len(raw)>LIMIT:raise ResearchError('KRX_CALENDAR_RESPONSE_LIMIT')
        return raw


def collect(folder,transport,budget,sleep=time.sleep):
    if type(budget) is not int or not 0<=budget<=32:raise ResearchError('KRX_CALENDAR_RUN_BUDGET_INVALID')
    with job_lock(folder):
        plan,journal,latest=load(folder);used=0
        if transport.source_kind!=plan['sourceKind']:raise ResearchError('KRX_CALENDAR_SOURCE_KIND_CONFLICT')
        for year in plan['years']:
            while True:
                stage,request,_,state=inspect(folder,plan,latest,year)
                if stage is None or state in {'FAILED','RESERVED'}:break
                if used>=budget or len(journal['attempts'])>=plan['maxRequests']:return summary(folder)
                if journal['attempts']:
                    elapsed=(utc(now())-utc(journal['attempts'][-1]['startedAt'])).total_seconds()
                    if elapsed<0:raise ResearchError('KRX_CALENDAR_CLOCK_REGRESSION')
                    if elapsed<1:sleep(1-elapsed)
                e={'seq':len(journal['attempts'])+1,'year':year,'stage':stage,'request':request,'state':'RESERVED','startedAt':now()}
                journal['attempts'].append(e);atomic_json(folder/'journal.json',journal)
                try:
                    raw=transport.fetch(request);(folder/'raw'/f"{e['seq']:04d}.bin").write_bytes(raw)
                    e.update(state='CAPTURED',sha256=digest(raw),capturedAt=now())
                except Exception as exc:e.update(state='FAILED',diagnostic=str(exc) if isinstance(exc,ResearchError) else 'KRX_CALENDAR_CAPTURE_FAILED',finishedAt=now())
                atomic_json(folder/'journal.json',journal);latest[(year,stage)]=e;used+=1
        return summary(folder)


def summary(folder):
    p,j,l=load(folder);states={}
    for year in p['years']:
        state=inspect(folder,p,l,year)[3];states[state]=states.get(state,0)+1
    return {'planId':p['planId'],'years':p['years'],'states':states,'attemptsUsed':len(j['attempts']),'seededRequests':2*len(p['seeds']),
            'maxRequests':p['maxRequests'],'usableForTraining':False,'usableForTrading':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for command in ['plan','collect','audit']:
        q=sub.add_parser(command);q.add_argument('--job',type=Path,required=True)
        if command=='plan':
            q.add_argument('--start',required=True);q.add_argument('--end',required=True);q.add_argument('--max-requests',type=int,default=16)
            q.add_argument('--seed-source',type=Path);q.add_argument('--seed-year',type=int)
            q.add_argument('--source-kind',choices=['PROVIDER_OBSERVATIONS','SYNTHETIC'],default='PROVIDER_OBSERVATIONS')
        if command=='collect':q.add_argument('--max-new-requests',type=int,required=True)
    a=p.parse_args(argv)
    try:
        result=prepare(a.job,a.start,a.end,a.max_requests,a.seed_source,a.seed_year,a.source_kind) if a.command=='plan' else collect(a.job,Transport(),a.max_new_requests) if a.command=='collect' else summary(a.job)
        print(json.dumps({k:v for k,v in result.items() if k not in {'seeds'}},sort_keys=True));return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'diagnostic':str(exc) if isinstance(exc,ResearchError) else 'KRX_CALENDAR_INPUT_INVALID'}));return 2


if __name__=='__main__':raise SystemExit(main())
