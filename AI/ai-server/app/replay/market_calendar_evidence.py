"""Market-scoped holiday reconstruction and explicit session exceptions, without historical rule assumptions."""
import argparse
from collections import Counter
from datetime import timedelta
import json
from pathlib import Path
import re
import time
from typing import Literal
from urllib.parse import urlsplit,parse_qs
from urllib.request import Request,build_opener

from pydantic import Field,model_validator
from . import krx_calendar_sources as years,session_evidence as kind,kb_market_evidence as kb
from .dataset import canonical,digest,read_bytes,read_json
from .history import day,now,NoRedirect,job_lock
from .krx_baseline_validation import immutable_json
from .krx_storage import atomic_json
from .models import ResearchError,StrictModel,utc
from .reference import ReferencePack

RULES={'KOSPI_RULE':'https://regulation.krx.co.kr/contents/RGL/03/03010100/RGL03010100T1.jsp',
       'KOSDAQ_RULE':'https://regulation.krx.co.kr/contents/RGL/03/03020401/RGL03020401.jsp'}
LIMIT=1024*1024


class Source(StrictModel):
    sourceId:str=Field(pattern=r'^[a-z0-9-]{1,60}$')
    role:Literal['KOSPI_RULE','KOSDAQ_RULE','KIND_SESSION','KB_YEAR_END','MIRAE_EXAM','YUANTA_EXAM']
    url:str
    markets:list[Literal['KOSPI','KOSDAQ']]=Field(min_length=1,max_length=2)
    expectedDate:str|None=None

    @model_validator(mode='after')
    def valid(self):
        if len(set(self.markets))!=len(self.markets):raise ValueError('duplicate market')
        if self.role in RULES:
            if self.url!=RULES[self.role] or self.markets!=[self.role.split('_')[0]] or self.expectedDate is not None:raise ValueError('rule scope')
        else:
            day(self.expectedDate)
            if self.role=='KIND_SESSION':kind.validate_url(self.url)
            elif self.role=='KB_YEAR_END':
                if kb.canonical_url(self.url)!=self.url:raise ValueError('canonical KB URL required')
            else:
                p=urlsplit(self.url);q=parse_qs(p.query)
                if p.scheme!='https' or p.fragment:raise ValueError('public HTTPS source required')
                if self.role=='MIRAE_EXAM':
                    if (p.netloc!='securities.miraeasset.com' or p.path!='/bbs/board/message/view.do' or set(q)!={'categoryId','messageId'}
                            or q['categoryId']!=['66'] or len(q['messageId'])!=1 or not re.fullmatch(r'[0-9]{1,10}',q['messageId'][0])):raise ValueError('Mirae source URL')
                elif (p.netloc!='www.myasset.com' or p.path!='/myasset/customer/notice/CU_0201000_P2.cmd' or set(q)!={'SEQ','gubun'}
                        or q['gubun']!=['norNotice'] or len(q['SEQ'])!=1 or not re.fullmatch(r'[0-9]{22,26}',q['SEQ'][0])):raise ValueError('Yuanta source URL')
        return self


class Scope(StrictModel):
    schemaVersion:Literal['SAGOPALGO_MARKET_CALENDAR_SCOPE_V1']
    startDate:str
    endDate:str
    sources:list[Source]=Field(min_length=3,max_length=20)

    @model_validator(mode='after')
    def valid(self):
        if not day(self.startDate)<=day(self.endDate) or len({s.sourceId for s in self.sources})!=len(self.sources) or len({s.url for s in self.sources})!=len(self.sources):raise ValueError('invalid source scope')
        if any(s.expectedDate is not None and not self.startDate<=s.expectedDate<=self.endDate for s in self.sources):raise ValueError('exception outside scope')
        if any(sum(s.role==role for s in self.sources)!=1 for role in RULES):raise ValueError('both market rule sources required')
        return self


def load_scope(path):return Scope.model_validate(read_json(read_bytes(path)))


def audit_capture(cache,url):
    folder=cache/digest(url.encode());e=read_json(read_bytes(folder/'receipt.json'))
    if not isinstance(e,dict) or e.get('status')!='COMPLETE':raise ResearchError('MARKET_SOURCE_CAPTURE_RESERVED')
    raw=read_bytes(folder/'body.html')
    required={'schemaVersion','url','status','startedAt','capturedAt','bodySha256','newGetRequests','knowledgeBasis'}
    if (set(e)!=required or e['schemaVersion']!='SAGOPALGO_PUBLIC_MARKET_SOURCE_V1' or e['url']!=url or e['status']!='COMPLETE'
            or type(e['newGetRequests']) is not int or e['newGetRequests'] not in {0,1} or e['knowledgeBasis']!='FETCH_TIME_ONLY'
            or utc(e['startedAt'])>utc(e['capturedAt']) or len(raw)>LIMIT or digest(raw)!=e['bodySha256']):
        raise ResearchError('MARKET_SOURCE_CAPTURE_TAMPERED')
    return e,raw


def seed_capture(cache,url,raw,origin):
    # Source URL validation remains the caller's reviewed Scope responsibility.
    if origin['url']!=url or (origin.get('bodySha256') or origin.get('sha256'))!=digest(raw) or len(raw)>LIMIT:
        raise ResearchError('MARKET_SOURCE_SEED_INVALID')
    if utc(origin['startedAt'])>utc(origin['capturedAt']):raise ResearchError('MARKET_SOURCE_SEED_INVALID')
    folder=cache/digest(url.encode());folder.mkdir(parents=True,exist_ok=False)
    (folder/'body.html').write_bytes(raw)
    atomic_json(folder/'receipt.json',{'schemaVersion':'SAGOPALGO_PUBLIC_MARKET_SOURCE_V1','url':url,'status':'COMPLETE',
        'startedAt':origin['startedAt'],'capturedAt':origin['capturedAt'],'bodySha256':digest(raw),'newGetRequests':0,'knowledgeBasis':'FETCH_TIME_ONLY'})
    return audit_capture(cache,url)[0]


def capture(scope_path,cache,budget,opener=None,sleep=time.sleep):
    scope=load_scope(scope_path)
    if type(budget) is not int or not 0<=budget<=20:raise ResearchError('MARKET_SOURCE_BUDGET_INVALID')
    cache.mkdir(parents=True,exist_ok=True)
    with job_lock(cache):
        index={'schemaVersion':'SAGOPALGO_PUBLIC_MARKET_CAPTURE_PLAN_V1','scopeSha256':digest(read_bytes(scope_path)),
               'sources':[s.model_dump(mode='json') for s in scope.sources]}
        immutable_json(cache/'index.json',index)
        missing=[];receipts=[]
        # Audit every existing source before any new network request.
        for s in scope.sources:
            folder=cache/digest(s.url.encode())
            if folder.exists():receipts.append(audit_capture(cache,s.url)[0])
            else:missing.append(s)
        if len(missing)>budget:raise ResearchError('MARKET_SOURCE_BUDGET_TOO_SMALL')
        client=opener or build_opener(NoRedirect());previous=None
        for s in missing:
            if previous:
                elapsed=(utc(now())-utc(previous)).total_seconds()
                if elapsed<0:raise ResearchError('MARKET_SOURCE_CLOCK_REGRESSION')
                if elapsed<1:sleep(1-elapsed)
            folder=cache/digest(s.url.encode());folder.mkdir()
            receipt={'url':s.url,'status':'RESERVED','startedAt':now()};previous=receipt['startedAt'];atomic_json(folder/'receipt.json',receipt)
            try:
                with client.open(Request(s.url,headers={'User-Agent':'SagoPalgo-local-research/1'},method='GET'),timeout=20) as response:raw=response.read(LIMIT+1)
                if len(raw)>LIMIT:raise ResearchError('MARKET_SOURCE_SIZE_LIMIT')
                (folder/'body.html').write_bytes(raw)
                receipt.update(schemaVersion='SAGOPALGO_PUBLIC_MARKET_SOURCE_V1',status='COMPLETE',capturedAt=now(),bodySha256=digest(raw),newGetRequests=1,knowledgeBasis='FETCH_TIME_ONLY')
            except Exception as exc:
                receipt.update(status='FAILED',diagnostic=str(exc) if isinstance(exc,ResearchError) else 'MARKET_SOURCE_CAPTURE_FAILED',finishedAt=now())
                atomic_json(folder/'receipt.json',receipt);raise ResearchError(receipt['diagnostic']) from None
            atomic_json(folder/'receipt.json',receipt);receipts.append(receipt)
        return {'sources':len(receipts),'newRequests':len(missing),'reused':len(scope.sources)-len(missing)}


def text(raw):
    try:html=raw.decode('utf-8-sig')
    except UnicodeError:html=raw.decode('cp949')
    articles=re.findall(r'<article\b[^>]*>(.*?)</article>',html,re.S|re.I)
    if len(articles)>1:raise ResearchError('MARKET_SOURCE_ARTICLE_AMBIGUOUS')
    p=kind.NoticeText();p.feed(articles[0] if articles else html)
    return re.sub(r'\s+',' ',' '.join(p.parts)).strip()


def rule(source,receipt,raw):
    value=text(raw);compact=re.sub(r'\s+','',value)
    if source.role=='KOSPI_RULE':
        if not all(v in compact for v in ['휴장일','매매거래일은월요일부터금요일까지','토요일','공휴일']):raise ResearchError('MARKET_WEEKDAY_RULE_REVIEW')
        matches=re.findall(r'정규장\s*([0-9]{2}:[0-9]{2})\s*~\s*([0-9]{2}:[0-9]{2})\s*([0-9]{2}:[0-9]{2})\s*~\s*([0-9]{2}:[0-9]{2})',value)
    else:
        if (not re.search(r'<title>[^<]*코스닥시장[^<]*</title>',raw.decode('utf-8-sig'))
                or not all(v in compact for v in ['휴장일','토요일','공휴일'])):raise ResearchError('MARKET_WEEKDAY_RULE_REVIEW')
        matches=re.findall(r'정규시장\s*호가접수시간\s*([0-9]{2}:[0-9]{2})\s*~\s*([0-9]{2}:[0-9]{2})\s*매매거래시간\s*([0-9]{2}:[0-9]{2})\s*~\s*([0-9]{2}:[0-9]{2})',value)
    if len(matches)!=1:raise ResearchError('MARKET_REGULAR_SESSION_RULE_REVIEW')
    opened,closed=(matches[0][:2] if source.role=='KOSPI_RULE' else matches[0][2:])
    if (opened,closed)!=('09:00','15:30'):raise ResearchError('MARKET_CURRENT_RULE_CHANGED_REVIEW')
    return {'market':source.markets[0],'open':opened,'close':closed,'sourceId':source.sourceId,'sourceUrl':source.url,
        'sourceSha256':receipt['bodySha256'],'knownAt':receipt['capturedAt'],'historicalRuleContinuityConfirmed':False}


def broker_exam(source,receipt,raw):
    value=text(raw)
    if not all(v in value for v in ['유가증권시장','코스닥시장','대학수학능력시험']):raise ResearchError('MARKET_EXAM_SCOPE_REVIEW')
    if source.role=='MIRAE_EXAM':dates=re.findall(r'대학수학능력시험\(([0-9]{4})\.([0-9]{1,2})\.([0-9]{1,2})\)',value)
    else:dates=re.findall(r'변경일\s*:\s*([0-9]{4})년\s*([0-9]{1,2})월\s*([0-9]{1,2})일',value)
    if len(set(dates))!=1:raise ResearchError('MARKET_EXAM_DATE_REVIEW')
    stamp='%04d-%02d-%02d'%tuple(map(int,dates[0]))
    ranges=re.findall(r'정규시장\s*(?:\(대량\s*[•·․,]\s*바스켓매매\s*포함\))?\s*([0-9]{2}:[0-9]{2})\s*~\s*([0-9]{2}:[0-9]{2})\s*(?:\(경쟁대량매매는\s*[0-9]{2}:[0-9]{2}까지\)\s*)?([0-9]{2}:[0-9]{2})\s*~\s*([0-9]{2}:[0-9]{2})',value)
    if len(ranges)!=1 or ranges[0]!=('09:00','15:30','10:00','16:30') or stamp!=source.expectedDate:
        raise ResearchError('MARKET_EXAM_REGULAR_ROW_REVIEW')
    return [{'market':m,'businessDate':stamp,'openAt':stamp+'T10:00:00+09:00','closeAt':stamp+'T16:30:00+09:00',
        'knownAt':receipt['capturedAt'],'evidence':source.url+'; raw-sha256:'+receipt['bodySha256']+'; knowledge=FETCH_TIME_ONLY'} for m in source.markets]


def kind_newyear(source,receipt,raw):
    """Reviewed year-end variant identifies its market in the explicit regulatory citation."""
    value=text(raw);compact=re.sub(r'\s+','',value)
    venues={m for label,m in [('유가증권시장','KOSPI'),('코스닥시장','KOSDAQ')] if label+'업무규정' in compact}
    expected={'99303':'KOSPI','70780':'KOSDAQ'}.get(source.url.rsplit('/',1)[1].removesuffix('.htm'))
    intro=re.findall(r'([0-9]{4})년 연말 시장운영 일정 및 ([0-9]{4})년 연초 개장일',value)
    date=re.findall(r'2\.\s*([0-9]{4})년 연초 개장일\s*\(([0-9]{1,2})\.([0-9]{1,2})\s*,',value)
    times=re.findall(r'정규장\*?은 개장시각만 1시간 연기\s*:\s*([0-9]{2}:[0-9]{2})\s*~\s*([0-9]{2}:[0-9]{2})',value)
    closures=re.findall(r'연말 휴장일\(결제일에서도 제외\)\s*:\s*([0-9]{4})\.\s*([0-9]{1,2})\.\s*([0-9]{1,2})',value)
    if (venues!={expected} or source.markets!=[expected] or len(intro)!=1 or len(date)!=1 or len(times)!=1 or len(closures)!=1
            or int(intro[0][0])+1!=int(intro[0][1]) or date[0][0]!=intro[0][1] or closures[0][0]!=intro[0][0]
            or '기타시장안내' not in value or '정정' in value):raise ResearchError('MARKET_KIND_NEWYEAR_LAYOUT_REVIEW')
    stamp='%04d-%02d-%02d'%tuple(map(int,date[0]));closure='%04d-%02d-%02d'%tuple(map(int,closures[0]));day(closure)
    if stamp!=source.expectedDate or closure>=stamp or times[0]!=('10:00','15:30'):raise ResearchError('MARKET_KIND_NEWYEAR_DATE_OR_TIME_CONFLICT')
    evidence=source.url+'; raw-sha256:'+receipt['bodySha256']+'; knowledge=FETCH_TIME_ONLY'
    return ReferencePack.model_validate({'schemaVersion':'SAGOPALGO_MARKET_REFERENCE_V1','provider':'KRX_KIND_YEAR_END_NOTICE',
        'provenance':'PROVIDER_OBSERVATIONS','reference':evidence,'observedAt':receipt['capturedAt'],
        'calendar':[{'businessDate':closure,'openDay':False,'businessDay':None,'tradingDay':None,'settlementDay':False}],
        'sessions':[{'market':expected,'businessDate':stamp,'openAt':stamp+'T10:00:00+09:00','closeAt':stamp+'T15:30:00+09:00',
            'knownAt':receipt['capturedAt'],'evidence':evidence}]})


def build(scope_path,cache,year_job):
    report, _, _ = rebuild_with_notice_rows(scope_path, cache, year_job)
    return report


def rebuild_with_notice_rows(scope_path, cache, year_job):
    """Rebuild the existing report and retain which market and notice supplied each calendar row."""
    scope_bytes=read_bytes(scope_path)
    scope=Scope.model_validate(read_json(scope_bytes));plan,journal,latest=years.load(year_job)
    if (scope.startDate,scope.endDate)!=(plan['startDate'],plan['endDate']):raise ResearchError('MARKET_CALENDAR_SCOPE_CONFLICT')
    immutable_json(cache/'index.json',{'schemaVersion':'SAGOPALGO_PUBLIC_MARKET_CAPTURE_PLAN_V1','scopeSha256':digest(scope_bytes),
        'sources':[s.model_dump(mode='json') for s in scope.sources]},True)
    closed={};year_sources=[];known=[]
    for year in plan['years']:
        _,_,done,state=years.inspect(year_job,plan,latest,year)
        if state!='CAPTURED':raise ResearchError('MARKET_CALENDAR_YEAR_INCOMPLETE')
        seed=next((s for s in plan['seeds'] if s['year']==year),None)
        entries=seed['records'].values() if seed else [e for e in journal['attempts'] if e['year']==year]
        at=max([e['capturedAt'] for e in entries],key=utc);known.append(at)
        closed.update({v['date']:v['reason'] for v in years.holidays(done['DATA'],year)})
        year_sources.append({'year':year,'sourceUrl':years.BASE+years.PAGE,'sourceSha256':digest(done['DATA']),'knownAt':at})
    rules={};sessions={};sources=[];notice_calendars=[]
    for source in scope.sources:
        receipt,raw=audit_capture(cache,source.url);known.append(receipt['capturedAt']);sources.append({'sourceId':source.sourceId,'role':source.role,
            'url':source.url,'sha256':receipt['bodySha256'],'knownAt':receipt['capturedAt']})
        if source.role in RULES:rules[source.markets[0]]=rule(source,receipt,raw);continue
        if source.role=='KIND_SESSION':
            packs={source.markets[0]:kind_newyear(source,receipt,raw)}
        elif source.role=='KB_YEAR_END':
            packs={market:kb.notice_pack(receipt,raw,market,'OBSERVED_AT') for market in source.markets}
        else:
            packs={}
        if packs:
            values=[session.model_dump(mode='json') for pack in packs.values() for session in pack.sessions]
            for market,pack in packs.items():
                notice_calendars.extend((market,source.sourceId,row.model_dump(mode='json')) for row in pack.calendar)
        else:
            values=broker_exam(source,receipt,raw)
        if len(values)!=len(source.markets) or {v['market'] for v in values}!=set(source.markets) or any(v['businessDate']!=source.expectedDate for v in values):
            raise ResearchError('MARKET_NOTICE_EXPECTED_SCOPE_CONFLICT')
        for v in values:
            key=(v['market'],v['businessDate'])
            if key in sessions:raise ResearchError('MARKET_DUPLICATE_SESSION_SOURCE')
            sessions[key]=v
    known_at=max(known,key=utc);days=[];cursor=day(scope.startDate)
    while cursor<=day(scope.endDate):
        stamp=cursor.isoformat();reason=closed.get(stamp);basis='ANNUAL_HOLIDAY' if reason else 'WEEKEND_RULE' if cursor.weekday()>=5 else 'WEEKDAY_OPEN_RECONSTRUCTION'
        days.append({'businessDate':stamp,'openDay':not reason and cursor.weekday()<5,'businessDay':None,'tradingDay':None,'settlementDay':None,
                     'basis':basis,'holidayReason':reason,'knownAt':known_at,'yearSourceSha256':next(s['sourceSha256'] for s in year_sources if s['year']==cursor.year)})
        cursor+=timedelta(days=1)
    by_date={v['businessDate']:v for v in days}
    if any(not by_date[v['businessDate']]['openDay'] for v in sessions.values()):raise ResearchError('MARKET_CLOSED_DAY_SESSION_CONFLICT')
    for _,_,v in notice_calendars:
        if v['businessDate'] in by_date and v['openDay']!=by_date[v['businessDate']]['openDay']:raise ResearchError('MARKET_NOTICE_CALENDAR_CONFLICT')
    packs={};candidates={};market_counts={}
    for market in ['KOSPI','KOSDAQ']:
        selected=[v for (m,_),v in sorted(sessions.items()) if m==market]
        packs[market]=ReferencePack.model_validate({'schemaVersion':'SAGOPALGO_MARKET_REFERENCE_V1','provider':'KRX_RECONSTRUCTED_CALENDAR_'+market,
            'provenance':plan['sourceKind'],'reference':'KRX annual holidays + reviewed weekday rules; calendar basis=OPEN_DAY_RECONSTRUCTION; market='+market,
            'observedAt':known_at,'calendar':[{k:v[k] for k in ['businessDate','businessDay','tradingDay','openDay','settlementDay']} for v in days],
            'sessions':selected,'listings':[],'actions':[],'coverage':[]}).model_dump(mode='json')
        candidates[market]=[{'businessDate':v['businessDate'],'open':rules[market]['open'],'close':rules[market]['close'],
            'knownAt':known_at,'basis':'CURRENT_RULE_HISTORICAL_CONTINUITY_UNVERIFIED','includedInReferencePack':False}
            for v in days if v['openDay'] and (market,v['businessDate']) not in sessions]
        market_counts[market]={'calendarDates':len(days),'openDays':sum(v['openDay'] for v in days),'closedDays':sum(not v['openDay'] for v in days),
            'explicitSessionDates':len(selected),'generalSessionReviewRequired':len(candidates[market]),'partialCalendarFlags':len(days)}
    report = {'schemaVersion':'SAGOPALGO_MARKET_CALENDAR_REPORT_V1','scopeSha256':digest(scope_bytes),'yearPlanId':plan['planId'],
        'startDate':scope.startDate,'endDate':scope.endDate,'sourceKind':plan['sourceKind'],'knownAt':known_at,'knowledgeBasis':'FETCH_TIME_ONLY',
        'calendarBasis':'KRX_ANNUAL_HOLIDAYS_AND_REVIEWED_WEEKEND_RULES','historicalRuleContinuityConfirmed':False,
        'days':days,'yearSources':year_sources,'sources':sources,'currentRules':rules,'referencePacks':packs,'sessionCandidates':candidates,
        'marketCounts':market_counts,'calendarReasonCounts':dict(Counter(v['basis'] for v in days)),
        'allCalendarFlagsComplete':False,'allHistoricalSessionsComplete':False,'marketUniverseComplete':False,'usableForTraining':False,'usableForTrading':False}
    return report, notice_calendars, scope


def as_of(report,at,market):
    cutoff=utc(at)
    if market not in {'KOSPI','KOSDAQ'}:raise ResearchError('MARKET_SCOPE_INVALID')
    p=report['referencePacks'][market]
    return {'market':market,'calendar':p['calendar'] if utc(report['knownAt'])<=cutoff else [],
        'sessions':[s for s in p['sessions'] if utc(s['knownAt'])<=cutoff],'usableForTraining':False,'usableForTrading':False}


def membership_context(report,parent,parent_sha):
    """Calendar adjacency is context, not proof of a disclosure/data-update date convention."""
    if parent.get('schemaVersion')!='SAGOPALGO_UNIVERSE_RECONCILIATION_V7' or (parent['startDate'],parent['endDate'])!=(report['startDate'],report['endDate']):
        raise ResearchError('CALENDAR_MEMBERSHIP_PARENT_CONFLICT')
    days={v['businessDate']:v for v in report['days']};rows=[]
    for row in parent['rows']:
        o=row['observation']
        if row['observationId']!=digest(canonical(o)):raise ResearchError('CALENDAR_MEMBERSHIP_OBSERVATION_TAMPERED')
        if row['resolution']!='STATUS_LIST_MATCH' or o['kind']!='REMOVED_OBSERVED':continue
        versions=row['membershipDisclosureReview']['candidateVersions']
        dates={v['announcement']['announcedDelistingDate'] for v in versions if 'announcement' in v}
        if len(dates)!=1 or None in dates:raise ResearchError('CALENDAR_MEMBERSHIP_DATE_REVIEW')
        announced=next(iter(dates))
        if announced not in days or o['observedFrom'] not in days or o['observedTo'] not in days:raise ResearchError('CALENDAR_MEMBERSHIP_DATE_OUTSIDE_SCOPE')
        later=[v for v in report['days'] if v['businessDate']>announced and v['openDay']]
        next_open=later[0]['businessDate'] if later else None
        rows.append({'observationId':row['observationId'],'symbol':o['before']['symbol'],'isin':o['isin'],'market':o['before']['market'],
            'announcedDelistingDate':announced,'announcedDateCalendar':days[announced],
            'observedFromCalendar':days[o['observedFrom']],'observedToCalendar':days[o['observedTo']],
            'interveningCalendarDates':[v for v in report['days'] if announced<v['businessDate']<o['observedTo']],
            'nextReconstructedOpenDay':next_open,'removalObservedOnNextReconstructedOpenDay':next_open==o['observedTo'],
            'resolution':row['resolution'],'individualDisclosureStatus':row['individualDisclosureStatus'],
            'knownAt':max([row['knownAt'],report['knownAt']],key=utc),'causalExplanationConfirmed':False,
            'exchangeDelistingDateOverridden':False,'historicalRuleContinuityConfirmed':False})
    return {'schemaVersion':'SAGOPALGO_CALENDAR_MEMBERSHIP_CONTEXT_V1','parentV7Sha256':parent_sha,'calendarReportSha256':digest(canonical(report)),
        'membershipDisclosuresUnchanged':parent['disclosureMatched'],'membershipReviewsUnchanged':parent['membershipAwaitingIndividualDisclosure'],
        'rows':rows,'usableForTraining':False,'usableForTrading':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for command in ['capture','build','audit','as-of']:
        q=sub.add_parser(command);q.add_argument('--scope',type=Path,required=True);q.add_argument('--cache',type=Path,required=True)
        if command=='capture':q.add_argument('--max-new-requests',type=int,required=True)
        else:q.add_argument('--year-job',type=Path,required=True);q.add_argument('--output',type=Path,required=True)
        if command=='as-of':q.add_argument('--at',required=True);q.add_argument('--market',choices=['KOSPI','KOSDAQ'],required=True)
    a=p.parse_args(argv)
    try:
        if a.command=='capture':result=capture(a.scope,a.cache,a.max_new_requests)
        else:
            result=build(a.scope,a.cache,a.year_job);immutable_json(a.output,result,a.command!='build')
            if a.command=='as-of':result=as_of(result,a.at,a.market)
            else:result={k:v for k,v in result.items() if k not in {'days','sources','yearSources','referencePacks','sessionCandidates'}}
        print(json.dumps(result,sort_keys=True));return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'diagnostic':str(exc) if isinstance(exc,ResearchError) else 'MARKET_CALENDAR_INPUT_INVALID'}));return 2


if __name__=='__main__':raise SystemExit(main())
