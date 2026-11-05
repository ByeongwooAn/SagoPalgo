"""Explicit exception rows, conservative historical-rule candidates and immutable source provenance."""
from copy import deepcopy
from datetime import timezone,timedelta
from pathlib import Path
import pytest

from app.replay import market_calendar_evidence as m,krx_calendar_sources as y
from app.replay.dataset import canonical,digest
from app.replay.models import ResearchError
from test_krx_calendar_sources import Client

AT='2026-11-05T12:00:00Z'
MIRAE='https://securities.miraeasset.com/bbs/board/message/view.do?categoryId=66&messageId=2312542'
YUANTA='https://www.myasset.com/myasset/customer/notice/CU_0201000_P2.cmd?SEQ=202411061044540000000004&gubun=norNotice'


def source(role='MIRAE_EXAM'):
    return m.Source(sourceId='exam',role=role,url=MIRAE if role=='MIRAE_EXAM' else YUANTA,
                    markets=['KOSPI','KOSDAQ'],expectedDate='2023-11-16')


def exam(role='MIRAE_EXAM',competition=False):
    date='대학수학능력시험(2023.11.16)' if role=='MIRAE_EXAM' else '대학수학능력시험 변경일 : 2023년 11월 16일'
    text='유가증권시장, 코스닥시장 '+date+' 정규시장 (대량·바스켓매매 포함) 09:00 ~ 15:30 '
    text+='(경쟁대량매매는 15:00까지) ' if competition else ''
    return ('<html><body>'+text+'10:00 ~ 16:30</body></html>').encode()


def receipt(s,raw):
    return {'url':s.url,'sha256':digest(raw),'startedAt':AT,'capturedAt':AT,'bodySha256':digest(raw)}


@pytest.mark.parametrize('role,competition',[('MIRAE_EXAM',False),('YUANTA_EXAM',False),('YUANTA_EXAM',True)])
def test_exam_uses_regular_after_change_time_not_competitive_block_close(role,competition):
    s=source(role);raw=exam(role,competition);values=m.broker_exam(s,receipt(s,raw),raw)
    assert {v['market'] for v in values}=={'KOSPI','KOSDAQ'}
    assert all(v['openAt'].endswith('T10:00:00+09:00') and v['closeAt'].endswith('T16:30:00+09:00') for v in values)
    assert all(v['knownAt']==AT for v in values)


@pytest.mark.parametrize('variant',['date','market','time','duplicate','wrong_label'])
def test_ambiguous_or_wrong_exam_date_market_and_session_are_rejected(variant):
    s=source();raw=exam()
    if variant=='date':s=s.model_copy(update={'expectedDate':'2023-11-17'})
    if variant=='market':raw=raw.replace('유가증권시장'.encode(),'파생상품시장'.encode())
    if variant=='time':raw=raw.replace(b'16:30',b'16:00')
    if variant=='duplicate':raw+=exam()
    if variant=='wrong_label':raw=raw.replace('정규시장'.encode(),'당사주문접수시간'.encode())
    with pytest.raises(ResearchError):m.broker_exam(s,receipt(s,raw),raw)


def newyear(market='KOSPI'):
    label='유가증권시장' if market=='KOSPI' else '코스닥시장'
    return ('<html><body>기타시장안내 2023년 연말 시장운영 일정 및 2024년 연초 개장일 '
        '연말 휴장일(결제일에서도 제외) : 2023.12.29 '
        '2. 2024년 연초 개장일(1.2, 화) 정규장*은 개장시각만 1시간 연기 : 10:00~15:30 '
        '3. 근거규정 '+label+'업무규정 제4조, 제5조</body></html>').encode()


def newyear_source(market):
    form='99303' if market=='KOSPI' else '70780'
    return m.Source(sourceId='newyear',role='KIND_SESSION',url='https://kind.krx.co.kr/external/2023/12/14/000173/20231213000752/'+form+'.htm',markets=[market],expectedDate='2024-01-02')


@pytest.mark.parametrize('market',['KOSPI','KOSDAQ'])
def test_year_opening_market_comes_from_regulatory_citation_and_reviewed_form(market):
    s=newyear_source(market);raw=newyear(market);p=m.kind_newyear(s,receipt(s,raw),raw)
    assert p.sessions[0].market==market and p.sessions[0].closeAt.astimezone(timezone(timedelta(hours=9))).hour==15
    assert p.calendar[0].settlementDay is False and p.sessions[0].businessDate=='2024-01-02'


@pytest.mark.parametrize('variant',['market','date','close','year','correction'])
def test_year_opening_conflicts_are_rejected(variant):
    s=newyear_source('KOSPI');raw=newyear()
    if variant=='market':raw=newyear('KOSDAQ')
    if variant=='date':s=s.model_copy(update={'expectedDate':'2024-01-03'})
    if variant=='close':raw=raw.replace(b'15:30',b'16:30')
    if variant=='year':raw=raw.replace(b'2023',b'2022')
    if variant=='correction':raw+= '정정'.encode()
    with pytest.raises(ResearchError):m.kind_newyear(s,receipt(s,raw),raw)


def rules(market):
    if market=='KOSPI':value='휴장일 매매거래일은 월요일부터 금요일까지 토요일 공휴일 정규장 09:00~15:30 08:30~15:30'
    else:value='<title>코스닥시장</title><article>휴장일 토요일 공휴일 정규시장 호가접수시간 08:30~15:30 매매거래시간 09:00~15:30</article>'
    return value.encode()


def prepared(tmp_path,seed=True):
    sources=[m.Source(sourceId=market.lower()+'-rule',role=market+'_RULE',url=m.RULES[market+'_RULE'],markets=[market]) for market in ['KOSPI','KOSDAQ']]+[source()]
    scope={'schemaVersion':'SAGOPALGO_MARKET_CALENDAR_SCOPE_V1','startDate':'2023-11-01','endDate':'2023-12-31','sources':[s.model_dump(mode='json') for s in sources]}
    path=tmp_path/'scope.json';path.write_bytes(canonical(scope));cache=tmp_path/'cache'
    bodies={s.url:rules(s.markets[0]) if s.role in m.RULES else exam() for s in sources}
    if seed:
        for s in sources:m.seed_capture(cache,s.url,bodies[s.url],receipt(s,bodies[s.url]))
        m.capture(path,cache,0)
    job=tmp_path/'years';y.prepare(job,scope['startDate'],scope['endDate'],2,source_kind='SYNTHETIC')
    y.collect(job,Client(),2,sleep=lambda _:None)
    return path,cache,job,bodies


def test_reconstruction_preserves_unknown_flags_and_excludes_general_session_candidates(tmp_path):
    path,cache,job,_=prepared(tmp_path);r=m.build(path,cache,job)
    assert len(r['days'])==61 and r['days'][-1]['openDay'] is False
    assert next(v for v in r['days'] if v['businessDate']=='2023-12-29')['basis']=='ANNUAL_HOLIDAY'
    for market in ['KOSPI','KOSDAQ']:
        p=r['referencePacks'][market]
        assert len(p['sessions'])==1 and p['sessions'][0]['businessDate']=='2023-11-16'
        assert all(d['businessDay'] is None and d['tradingDay'] is None and d['settlementDay'] is None for d in p['calendar'])
        assert all(not c['includedInReferencePack'] for c in r['sessionCandidates'][market])
        assert not r['currentRules'][market]['historicalRuleContinuityConfirmed']
    assert not r['allHistoricalSessionsComplete'] and not r['allCalendarFlagsComplete'] and not r['usableForTraining']
    assert not m.as_of(r,'2023-12-01T00:00:00Z','KOSPI')['sessions']
    assert not m.as_of(r,'2023-12-01T00:00:00Z','KOSPI')['calendar']
    assert len(m.as_of(r,r['knownAt'],'KOSPI')['calendar'])==61


def test_current_rule_change_is_a_review_instead_of_silent_historical_fill():
    s=m.Source(sourceId='rule',role='KOSPI_RULE',url=m.RULES['KOSPI_RULE'],markets=['KOSPI'])
    raw=rules('KOSPI').replace(b'09:00',b'08:00')
    with pytest.raises(ResearchError):m.rule(s,receipt(s,raw),raw)


class Opener:
    def __init__(self,bodies,fail=False):self.bodies=bodies;self.calls=[];self.fail=fail
    def open(self,req,timeout):
        from io import BytesIO
        self.calls.append(req.full_url)
        if self.fail:raise OSError('private failure')
        return BytesIO(self.bodies[req.full_url])


def test_budget_is_preflighted_and_cache_reuse_never_fetches(tmp_path):
    path,cache,_,bodies=prepared(tmp_path,False);client=Opener(bodies)
    with pytest.raises(ResearchError):m.capture(path,cache,2,client)
    assert not client.calls
    assert m.capture(path,cache,3,client,sleep=lambda _:None)['newRequests']==3
    c=Opener(bodies,True);assert m.capture(path,cache,0,c)['reused']==3 and not c.calls


def test_failed_source_is_preserved_and_not_automatically_retried(tmp_path):
    path,cache,_,bodies=prepared(tmp_path,False);c=Opener(bodies,True)
    with pytest.raises(ResearchError):m.capture(path,cache,3,c)
    with pytest.raises(ResearchError):m.capture(path,cache,3,c)
    assert len(c.calls)==1


def test_all_cached_sources_are_audited_before_any_new_request(tmp_path):
    path,cache,_,bodies=prepared(tmp_path);url=next(iter(bodies));(cache/digest(url.encode())/'body.html').write_bytes(b'changed')
    c=Opener(bodies)
    with pytest.raises(ResearchError):m.capture(path,cache,3,c)
    assert not c.calls


@pytest.mark.parametrize('variant',['host','query','http','market','duplicate','outside'])
def test_reviewed_source_scope_rejects_untrusted_or_conflicting_configuration(tmp_path,variant):
    path,_,_,_=prepared(tmp_path);import json
    d=json.loads(path.read_bytes());s=d['sources'][-1]
    if variant=='host':s['url']=s['url'].replace('securities.miraeasset.com','example.com')
    if variant=='query':s['url']+='&token=private'
    if variant=='http':s['url']=s['url'].replace('https:','http:')
    if variant=='market':s['markets']=['KONEX']
    if variant=='duplicate':d['sources'].append(s)
    if variant=='outside':s['expectedDate']='2024-01-01'
    path.write_bytes(canonical(d))
    with pytest.raises(ValueError):m.load_scope(path)


def test_membership_calendar_context_does_not_explain_away_a_conflicting_date(tmp_path):
    path,cache,job,_=prepared(tmp_path);r=m.build(path,cache,job)
    from test_universe_reconciliation import observation,issue
    o=observation('REMOVED_OBSERVED',before=issue());o.update(observedFrom='2023-11-12',observedTo='2023-11-13')
    row={'observation':o,'observationId':digest(canonical(o)),'resolution':'STATUS_LIST_MATCH','individualDisclosureStatus':'REVIEW_REQUIRED',
        'knownAt':AT,'membershipDisclosureReview':{'candidateVersions':[{'announcement':{'announcedDelistingDate':'2023-11-10'}}]}}
    p={'schemaVersion':'SAGOPALGO_UNIVERSE_RECONCILIATION_V7','startDate':r['startDate'],'endDate':r['endDate'],
       'disclosureMatched':576,'membershipAwaitingIndividualDisclosure':1,'rows':[row]}
    frozen=canonical(p);result=m.membership_context(r,p,'a'*64);v=result['rows'][0]
    assert canonical(p)==frozen and v['nextReconstructedOpenDay']=='2023-11-13'
    assert v['removalObservedOnNextReconstructedOpenDay'] and not v['causalExplanationConfirmed'] and not v['exchangeDelistingDateOverridden']
    assert result['membershipReviewsUnchanged']==1 and result['membershipDisclosuresUnchanged']==576


def test_cli_build_audit_and_asof_are_offline(tmp_path,capsys):
    path,cache,job,_=prepared(tmp_path);out=tmp_path/'report.json'
    args=['--scope',str(path),'--cache',str(cache),'--year-job',str(job),'--output',str(out)]
    assert m.main(['build',*args])==0 and m.main(['audit',*args])==0
    assert m.main(['as-of',*args,'--at','2023-12-01T00:00:00Z','--market','KOSPI'])==0
    assert '"calendar": []' in capsys.readouterr().out
