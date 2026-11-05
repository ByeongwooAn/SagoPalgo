"""Capture viewer-linked older revisions with an independent immutable budget and audited seed reuse."""
import argparse
from datetime import timedelta
import json
from pathlib import Path
import re
import time

from . import delisting_disclosure_coverage as source
from .dataset import canonical,digest,read_bytes,read_json
from .history import job_lock,now,day
from .krx_storage import atomic_json
from .models import ResearchError,utc

SCHEMA='SAGOPALGO_DELISTING_REVISION_PLAN_V1'


def viewer_documents(raw,target):
    root=source.engine.public.html(raw)
    headers=[v.text() for v in root.walk('h1') if re.search(r'\([0-9A-Z]{6}\)$',v.text())]
    selectors=[v for v in root.walk('select') if v.attrs.get('id')=='mainDoc']
    options=[v for v in selectors[0].walk('option') if v.attrs.get('value')] if len(selectors)==1 else []
    if len(headers)!=1 or not headers[0].endswith('('+target['symbol']+')') or not 1<=len(options)<=20:
        raise ResearchError('DELISTING_REVISION_VIEWER_REVIEW')
    docs=[]
    for index,option in enumerate(options):
        value=re.fullmatch(r'([0-9]{14})\|([YN])',option.attrs['value'])
        title=re.fullmatch(r'(\[정정\])?상장폐지\(([0-9]{4})\.([0-9]{2})\.([0-9]{2})\)',re.sub(r'\s+','',option.text()))
        if not value or not title: raise ResearchError('DELISTING_REVISION_OPTION_REVIEW')
        stamp='-'.join(title.group(i) for i in [2,3,4]); day(stamp)
        docs.append({'document':value[1],'publicationDate':stamp,'corrected':bool(title[1]),'active':value[2]=='Y','ordinal':index})
    if len({d['document'] for d in docs})!=len(docs) or sum(d['active'] for d in docs)!=1:
        raise ResearchError('DELISTING_REVISION_LINEAGE_AMBIGUOUS')
    return docs


def targets_from(source_job,plan,journal,latest):
    result=[]
    for t in plan['targets']:
        viewers=[]; docs=None; seeds={}
        for label in ['V0','V1','V2','V3']:
            e=latest.get((t['observationId'],label+'_VIEWER'))
            if e and e['state']=='CAPTURED':
                current=viewer_documents(read_bytes(source_job/'raw'/f"{e['seq']:04d}.bin"),t)
                if docs is not None and docs!=current: raise ResearchError('DELISTING_REVISION_VIEWERS_CONFLICT')
                docs=current; viewers.append({'seq':e['seq'],'sha256':e['sha256'],'knownAt':e['capturedAt']})
            path=latest.get((t['observationId'],label+'_PATH')); body=latest.get((t['observationId'],label+'_BODY'))
            if path and body and path['state']==body['state']=='CAPTURED':
                document=path['request']['parameters']['docNo']
                seeds[document]={'pathSeq':path['seq'],'pathSha256':path['sha256'],'bodySeq':body['seq'],'bodySha256':body['sha256'],
                                 'knownAt':max([path['capturedAt'],body['capturedAt']],key=utc)}
        if docs is None or len(docs)==1: continue
        last_publication=(utc(max([v['knownAt'] for v in viewers],key=utc))+timedelta(hours=9)).date().isoformat()
        if any(d['publicationDate']>last_publication for d in docs): raise ResearchError('DELISTING_REVISION_PUBLICATION_AFTER_CAPTURE')
        result.append({**t,'viewerSources':viewers,'documents':[{**d,'seed':seeds.get(d['document'])} for d in docs]})
    if not result: raise ResearchError('DELISTING_REVISION_EMPTY_SCOPE')
    return result


def prepare(folder,source_job,max_requests=400):
    parent,journal,latest=source.load(source_job)
    targets=targets_from(source_job,parent,journal,latest)
    needed=2*sum(d['seed'] is None for t in targets for d in t['documents'])
    if type(max_requests) is not int or not needed<=max_requests<=1200:
        raise ResearchError('DELISTING_REVISION_BUDGET_INVALID')
    payload={'schemaVersion':SCHEMA,'sourcePlanId':parent['planId'],'parentSha256':parent['parentSha256'],'sourceKind':parent['sourceKind'],
        'targets':targets,'maxRequests':max_requests,'maxAttemptsPerStage':3,'minIntervalSeconds':1}
    plan={**payload,'planId':digest(canonical(payload))}
    folder.mkdir(parents=True,exist_ok=False); (folder/'raw').mkdir()
    atomic_json(folder/'plan.json',plan); atomic_json(folder/'journal.json',{'planId':plan['planId'],'attempts':[]})
    return plan


def path_url(raw,doc):
    text=raw.decode('utf-8-sig')
    paths=re.findall(r"parent\.setPath\('[^']*','(https://kind\.krx\.co\.kr/external/[^']+)','[^']*','[0-9]{2}','[0-9]{2}'\);",text)
    if len(paths)!=1: raise ResearchError('DELISTING_REVISION_PATH_AMBIGUOUS')
    url=paths[0]; source.engine.public.validate_url(url); parts=url.split('/')
    if ''.join(parts[4:7])!=doc['publicationDate'].replace('-','') or parts[-2]!=doc['document']:
        raise ResearchError('DELISTING_REVISION_DOCUMENT_OR_DATE_MISMATCH')
    return url


def inspect(folder,source_job,t,doc,latest,expected=None):
    completed={}; identity=t['observationId']; document=doc['document']
    if doc['seed'] is not None:
        for stage,key in [('PATH','pathSeq'),('BODY','bodySeq')]: completed[stage]=read_bytes(source_job/'raw'/f"{doc['seed'][key]:04d}.bin")
        url=path_url(completed['PATH'],doc)
        return None,None,completed,'CAPTURED',url
    path_spec={'url':source.engine.public.BASE+'/common/disclsviewer.do','method':'POST','parameters':{'method':'searchContents','docNo':document}}
    for stage in ['PATH','BODY']:
        spec=path_spec if stage=='PATH' else {'url':path_url(completed['PATH'],doc),'method':'GET','parameters':None}
        key=(identity,document,stage)
        if expected is not None: expected[key]=spec
        entry=latest.get(key)
        if not entry: return stage,spec,completed,'PENDING',None
        if entry['request']!=spec: raise ResearchError('DELISTING_REVISION_REQUEST_TAMPERED')
        if entry['state']!='CAPTURED': return stage,spec,completed,entry['state'],None
        completed[stage]=read_bytes(folder/'raw'/f"{entry['seq']:04d}.bin")
    return None,None,completed,'CAPTURED',path_url(completed['PATH'],doc)


def load(folder,source_job):
    parent,sources,source_latest=source.load(source_job)
    plan=read_json(read_bytes(folder/'plan.json')); payload={k:v for k,v in plan.items() if k!='planId'}
    targets=targets_from(source_job,parent,sources,source_latest)
    if (set(plan)!={'schemaVersion','sourcePlanId','parentSha256','sourceKind','targets','maxRequests','maxAttemptsPerStage','minIntervalSeconds','planId'}
            or plan.get('schemaVersion')!=SCHEMA or plan.get('planId')!=digest(canonical(payload)) or plan['sourcePlanId']!=parent['planId']
            or plan['parentSha256']!=parent['parentSha256'] or plan['sourceKind']!=parent['sourceKind'] or plan['targets']!=targets
            or (plan['maxAttemptsPerStage'],plan['minIntervalSeconds'])!=(3,1)
            or type(plan['maxRequests']) is not int or not 2*sum(d['seed'] is None for t in targets for d in t['documents'])<=plan['maxRequests']<=1200):
        raise ResearchError('DELISTING_REVISION_PLAN_INVALID')
    journal=read_json(read_bytes(folder/'journal.json'))
    if set(journal)!={'planId','attempts'} or journal['planId']!=plan['planId'] or len(journal['attempts'])>plan['maxRequests']:
        raise ResearchError('DELISTING_REVISION_JOURNAL_INVALID')
    permitted={(t['observationId'],d['document']) for t in targets for d in t['documents'] if d['seed'] is None}
    latest,counts={},{}
    for seq,e in enumerate(journal['attempts'],1):
        key=(e['targetId'],e['document'],e['stage'])
        if (type(e['seq']) is not int or e['seq']!=seq or key[:2] not in permitted or key[2] not in {'PATH','BODY'}
                or e['state'] not in {'RESERVED','CAPTURED','FAILED'} or key in latest and latest[key]['state']=='CAPTURED'):
            raise ResearchError('DELISTING_REVISION_JOURNAL_INVALID')
        counts[key]=counts.get(key,0)+1
        if counts[key]>3: raise ResearchError('DELISTING_REVISION_STAGE_BUDGET')
        utc(e['startedAt']); fields={'seq','targetId','document','stage','state','startedAt','request'}
        if 'sha256' in e:
            fields|={'sha256','capturedAt'}
            if utc(e['capturedAt'])<utc(e['startedAt']) or digest(read_bytes(folder/'raw'/f'{seq:04d}.bin'))!=e['sha256']:
                raise ResearchError('DELISTING_REVISION_RAW_TAMPERED')
        if e['state']=='CAPTURED': fields|={'sha256','capturedAt'}
        if e['state']=='FAILED':
            fields|={'diagnostic','finishedAt'}
            if utc(e['finishedAt'])<utc(e['startedAt']): raise ResearchError('DELISTING_REVISION_JOURNAL_INVALID')
        if set(e)!=fields: raise ResearchError('DELISTING_REVISION_JOURNAL_INVALID')
        latest[key]=e
    expected={}
    for t in targets:
        for d in t['documents']: inspect(folder,source_job,t,d,latest,expected)
    if any(e['request']!=expected.get((e['targetId'],e['document'],e['stage'])) for e in journal['attempts']):
        raise ResearchError('DELISTING_REVISION_REQUEST_TAMPERED')
    return plan,journal,latest


def summary(folder,source_job):
    plan,journal,latest=load(folder,source_job); states={}
    for t in plan['targets']:
        for doc in t['documents']:
            state=inspect(folder,source_job,t,doc,latest)[3]; states[state]=states.get(state,0)+1
    return {'planId':plan['planId'],'targets':len(plan['targets']),'documents':sum(len(t['documents']) for t in plan['targets']),
        'seededDocuments':sum(d['seed'] is not None for t in plan['targets'] for d in t['documents']),
        'states':states,'attemptsUsed':len(journal['attempts']),'maxRequests':plan['maxRequests'],'usableForTrading':False}


def collect(folder,source_job,transport,max_new_requests,retry_failed=False,sleep=time.sleep):
    if type(max_new_requests) is not int or not 0<=max_new_requests<=1200: raise ResearchError('DELISTING_REVISION_RUN_BUDGET_INVALID')
    with job_lock(folder):
        plan,journal,latest=load(folder,source_job)
        if transport.source_kind!=plan['sourceKind']: raise ResearchError('DELISTING_REVISION_SOURCE_KIND_MISMATCH')
        used=0
        for index,t in enumerate(plan['targets'],1):
            for doc in t['documents']:
                while True:
                    stage,spec,_,state,_=inspect(folder,source_job,t,doc,latest)
                    if not stage or state in {'RESERVED','FAILED'} and not retry_failed: break
                    key=(t['observationId'],doc['document'],stage)
                    if sum((e['targetId'],e['document'],e['stage'])==key for e in journal['attempts'])>=3: break
                    if used>=max_new_requests or len(journal['attempts'])>=plan['maxRequests']: return summary(folder,source_job)
                    if journal['attempts']:
                        elapsed=(utc(now())-utc(journal['attempts'][-1]['startedAt'])).total_seconds()
                        if elapsed<0: raise ResearchError('DELISTING_REVISION_CLOCK_REGRESSION')
                        if elapsed<1: sleep(1-elapsed)
                    seq=len(journal['attempts'])+1
                    e={'seq':seq,'targetId':key[0],'document':key[1],'stage':stage,'state':'RESERVED','startedAt':now(),'request':spec}
                    journal['attempts'].append(e); atomic_json(folder/'journal.json',journal)
                    try:
                        raw=transport.fetch(spec); (folder/'raw'/f'{seq:04d}.bin').write_bytes(raw)
                        e.update(state='CAPTURED',sha256=digest(raw),capturedAt=now()); atomic_json(folder/'journal.json',journal)
                    except Exception as exc:
                        e.update(state='FAILED',diagnostic=str(exc) if isinstance(exc,ResearchError) else 'DELISTING_REVISION_CAPTURE_FAILED',finishedAt=now())
                        atomic_json(folder/'journal.json',journal)
                    latest[key]=e; used+=1
                    if e['state']=='FAILED': break
            if index%5==0: print(json.dumps({'progress':True,'targetsVisited':index,'attemptsUsed':len(journal['attempts'])}),flush=True)
        return summary(folder,source_job)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='command',required=True)
    for command in ['plan','collect','audit']:
        p=sub.add_parser(command); p.add_argument('--job',type=Path,required=True); p.add_argument('--source-job',type=Path,required=True)
        if command=='plan': p.add_argument('--max-requests',type=int,default=400)
        if command=='collect': p.add_argument('--max-new-requests',type=int,required=True); p.add_argument('--retry-failed',action='store_true')
    args=parser.parse_args(argv)
    try:
        result=prepare(args.job,args.source_job,args.max_requests) if args.command=='plan' else collect(args.job,args.source_job,source.engine.public.Transport(),args.max_new_requests,args.retry_failed) if args.command=='collect' else summary(args.job,args.source_job)
        print(json.dumps({k:v for k,v in result.items() if k!='targets'},sort_keys=True),flush=True); return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'diagnostic':str(exc) if isinstance(exc,ResearchError) else 'DELISTING_REVISION_INPUT_INVALID'})); return 2


if __name__=='__main__': raise SystemExit(main())
