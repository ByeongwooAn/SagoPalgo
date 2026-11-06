"""Expanded query boundaries, cache provenance and date-specific refusal to overclaim sessions."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.replay import session_coverage_review as c, session_notice_inventory as n, session_notice_review as r
from app.replay.dataset import canonical,digest
from app.replay.models import ResearchError
from tests.test_session_notice_inventory import parent_file,Client,fixture_review,page,row


def write(path,value):path.write_bytes(canonical(value))


def case(tmp_path,monkeypatch,fresh=False):
    q={'id':'kospi-title','market':'KOSPI','kind':'TITLE','term':'거래시간','fromDate':'2024-01-01','toDate':'2024-12-31'}
    if fresh:q['term']='개장'
    monkeypatch.setattr(c,'queries',lambda variant='TITLES_AND_BOUNDARY':[q])
    parent=parent_file(tmp_path);rules=json.loads(parent.read_bytes());rules['sourceKind']='SYNTHETIC'
    for market in n.FORMS:
        rules['referencePacks'][market]['calendar'].append({'businessDate':'2025-01-03','openDay':True})
        rules['markets'][market].update(candidates=[{'businessDate':'2025-01-03'}],rulePeriods=[{
            'startDate':'2023-11-01','endDate':'2026-11-02','continuityConfirmed':True,
            'nominalOpen':'09:00','nominalClose':'15:30','bookIds':['synthetic']}])
    write(parent,rules)
    old=tmp_path/'old';n.prepare(old,parent,'2026-11-05',64,source_kind='SYNTHETIC')
    client=Client();n.collect(old,client,64,sleep=lambda _:None)
    inv,scope=fixture_review(tmp_path,parent,old)
    previous=r.build(old,parent,inv,scope);previous_path=tmp_path/'previous.json';write(previous_path,previous)
    folder=tmp_path/'expanded';c.prepare(folder,previous_path,parent,old,64)
    cache=c.Cache(folder,64,client,sleep=lambda _:None);expanded=c.inventory(folder,cache)
    path=tmp_path/'expanded.json';write(path,expanded)
    review_path=tmp_path/'expanded-review.json'
    old_scope=json.loads(scope.read_bytes())
    write(review_path,{'schemaVersion':'SAGOPALGO_SESSION_COVERAGE_REVIEW_SCOPE_V1','inventorySha256':digest(path.read_bytes()),
        'parentReviewSha256':digest(previous_path.read_bytes()),'reviewedAt':n.now(),'decisions':old_scope['decisions'],'corrections':[]})
    return folder,previous_path,parent,path,review_path,client


def test_fixed_search_has_pre_window_tail_and_independent_halt_categories():
    qs=c.queries();halts=c.queries('HALT_AND_ACTION_CATEGORIES')
    assert len(qs)==124 and len(halts)==46
    assert min(q['fromDate'] for q in qs)=='2022-01-01'
    assert max(q['toDate'] for q in qs)=='2026-11-06'
    assert {q['category'] for q in halts if q['kind']=='CATEGORY'}=={'0306','0346','0347'}
    assert all(q['fromDate'][:4]==q['toDate'][:4] for q in qs+halts)
    spec=c.list_spec(next(q for q in halts if q.get('category')=='0347'),1)
    assert spec['parameters']['pDisclosureType02']=='0347|' and not spec['parameters']['reportCd']
    assert 'lastReport' not in spec['parameters'] and not spec['parameters']['searchCorpName']
    submitted=c.list_spec(next(q for q in c.queries('HALT_AND_ACTION_CATEGORIES_V2') if q.get('category')=='0347'),1)
    assert submitted['parameters']['disclosureType02']=='0347|'


def test_title_filter_rejects_server_ignoring_term_and_requires_issuer_resumption_body():
    q={'id':'q','kind':'TITLE','market':'KOSPI','term':'거래재개','fromDate':'2024-01-01','toDate':'2024-12-31'}
    with pytest.raises(ResearchError,match='TITLE_FILTER'):c.rows(page(row(),1),q,1)
    result=c.rows(page(row(title='매매거래재개 안내',issuer='시험회사'),1),q,1)
    assert result['rows'][0]['requiresBodyReview']


def test_old_capture_reuse_is_offline_and_does_not_reset_or_consume_budget(tmp_path,monkeypatch):
    folder,prior,rules,inv,scope,client=case(tmp_path,monkeypatch)
    calls=len(client.calls)
    with patch('socket.socket.connect',side_effect=AssertionError('offline')):
        cache=c.Cache(folder);rebuilt=c.inventory(folder,cache)
        result=c.build_review(folder,prior,rules,inv,scope)
    assert len(client.calls)==calls and cache.total==0 and rebuilt['reusedRequests']==4
    assert result['referencePacks']==json.loads(prior.read_bytes())['referencePacks']
    assert result['promotionCounts']=={'DEFERRED':2}
    assert all(not x['actualSessionConfirmed'] and not x['includedInReferencePack'] for x in result['promotionDecisions'])
    assert all(len(x['blockers'])==3 for x in result['promotionDecisions'])
    assert not result['allHistoricalSessionsComplete'] and not result['usableForTraining']


@pytest.mark.parametrize('variant',['plan','origin','receipt','raw','budget','unexpected'])
def test_cache_tampering_fails_before_any_request(tmp_path,monkeypatch,variant):
    folder,prior,rules,inv,scope,client=case(tmp_path,monkeypatch)
    receipt=next((folder/'captures').glob('*/receipt.json'));e=json.loads(receipt.read_bytes())
    if variant=='plan':
        p=folder/'plan.json';v=json.loads(p.read_bytes());v['queries'][0]['term']='거래';write(p,v)
    elif variant=='origin':
        p=Path(json.loads((folder/'plan.json').read_bytes())['sourceJob'])/'journal.json';p.write_bytes(p.read_bytes()+b' ')
    elif variant=='receipt':e['request']['parameters']={'injected':'x'};write(receipt,e)
    elif variant=='raw':(receipt.parent/'body.bin').write_bytes(b'changed')
    elif variant=='budget':e['newRequests']=True;write(receipt,e)
    else:
        # A hash-valid unrelated request must still fail derived request coverage.
        spec={'url':'https://kind.krx.co.kr/external/2024/12/17/000001/20241217000001/99303.htm','method':'GET','parameters':None}
        k=n.key('BODY',spec);p=folder/'captures'/k;p.mkdir();raw=b'unexpected';(p/'body.bin').write_bytes(raw)
        write(p/'receipt.json',{'planId':e['planId'],'key':k,'stage':'BODY','request':spec,'state':'CAPTURED',
            'startedAt':n.now(),'capturedAt':n.now(),'sha256':digest(raw),'newRequests':1})
    calls=len(client.calls)
    with pytest.raises(ResearchError):c.inventory(folder,c.Cache(folder))
    assert len(client.calls)==calls


@pytest.mark.parametrize('variant',['missing','hash','duplicate','early','parent','classification'])
def test_review_binding_and_knowledge_are_checked(tmp_path,monkeypatch,variant):
    folder,prior,rules,inv,scope,client=case(tmp_path,monkeypatch)
    s=json.loads(scope.read_bytes())
    if variant=='missing':s['decisions']=[]
    elif variant=='hash':s['inventorySha256']='0'*64
    elif variant=='duplicate':s['decisions']*=2
    elif variant=='early':s['reviewedAt']='2020-01-01T00:00:00Z'
    elif variant=='parent':s['parentReviewSha256']='0'*64
    else:s['decisions'][0]['classification']='OTHER_MARKET_POLICY'
    write(scope,s)
    with pytest.raises((ResearchError,ValueError)):c.build_review(folder,prior,rules,inv,scope)


@pytest.mark.parametrize('variant',['duplicate','closed','rule_gap','existing','outside'])
def test_promotion_requires_unique_open_day_and_one_verified_rule_period(tmp_path,monkeypatch,variant):
    _,_,path,_,_,_=case(tmp_path,monkeypatch);rules=json.loads(path.read_bytes())
    market=rules['markets']['KOSPI']
    if variant=='duplicate':market['candidates']*=2
    elif variant=='closed':rules['referencePacks']['KOSPI']['calendar'][-1]['openDay']=False
    elif variant=='rule_gap':market['rulePeriods']=[]
    elif variant=='existing':rules['referencePacks']['KOSPI']['sessions'].append({'businessDate':'2025-01-03'})
    else:market['candidates']=[{'businessDate':'2020-01-01'}]
    with pytest.raises(ResearchError):c.promotion_decisions(rules,n.now(),set())


def test_halt_is_a_date_specific_blocker_not_changed_open_or_close(tmp_path,monkeypatch):
    _,_,path,_,_,_=case(tmp_path,monkeypatch)
    result=c.promotion_decisions(json.loads(path.read_bytes()),n.now(),{('KOSPI','2025-01-03')})
    kospi=next(v for v in result if v['market']=='KOSPI');kosdaq=next(v for v in result if v['market']=='KOSDAQ')
    assert len(kospi['blockers'])==4 and len(kosdaq['blockers'])==3
    assert kospi['nominalOpen']=='09:00' and kospi['nominalClose']=='15:30'


def test_correction_text_diff_preserves_changed_date_and_time():
    changes=c.text_changes(b'<p>2025-01-02 09:00</p>',b'<p>2025-01-03 10:00</p>')
    assert changes and any('2' in x['before'] for x in changes)
    assert any(x['after'] for x in changes)


def test_new_request_is_reserved_and_failed_capture_is_not_retried(tmp_path,monkeypatch):
    folder,_,_,_,_,client=case(tmp_path,monkeypatch)
    class Failed:
        source_kind='SYNTHETIC'
        calls=0
        def fetch(self,spec):
            self.calls+=1
            e=list((folder/'captures').glob('*/receipt.json'))
            assert any(json.loads(p.read_bytes())['state']=='RESERVED' for p in e)
            raise OSError('private transport error')
    failed=Failed();cache=c.Cache(folder,1,failed,sleep=lambda _:None)
    spec={'url':c.BASE+'/disclosure/details.do','method':'POST','parameters':{'new':'request'}}
    with pytest.raises(ResearchError,match='UNRESOLVED'):cache.get('LIST',spec)
    assert failed.calls==1 and cache.total==1
    with pytest.raises(ResearchError,match='UNRESOLVED'):c.Cache(folder,1,failed).get('LIST',spec)
    assert failed.calls==1
    assert b'private transport error' not in b''.join(p.read_bytes() for p in (folder/'captures').glob('*/receipt.json'))


def test_run_budget_zero_prevents_reservation_for_new_request(tmp_path,monkeypatch):
    folder,_,_,_,_,client=case(tmp_path,monkeypatch);cache=c.Cache(folder,0,client)
    before=len(cache.entries);calls=len(client.calls)
    with pytest.raises(ResearchError,match='PENDING'):
        cache.get('LIST',{'url':c.BASE+'/disclosure/details.do','method':'POST','parameters':{'new':'request'}})
    assert len(list((folder/'captures').glob('*/receipt.json')))==before and len(client.calls)==calls


def test_extension_inherits_spent_budget_and_binds_other_source_snapshots(tmp_path,monkeypatch):
    folder,prior,rules,_,_,client=case(tmp_path,monkeypatch,fresh=True)
    second=tmp_path/'second';c.prepare(second,prior,rules,tmp_path/'old',32)
    c.inventory(second,c.Cache(second,32,client,sleep=lambda _:None))
    extended=tmp_path/'extended';c.extend(extended,second,folder,64)
    result=c.inventory(extended,c.Cache(extended,64,client,sleep=lambda _:None))
    assert result['newRequests']==1 and c.Cache(extended).plan['inheritedRequests']==1
    e=next((second/'captures').glob('*/receipt.json'));e.write_bytes(e.read_bytes()+b' ')
    with pytest.raises(ResearchError,match='REUSE_TAMPERED'):c.Cache(extended)


@pytest.mark.parametrize('variant',['issuer','market','date','duration'])
def test_halt_facts_reject_wrong_scope_date_or_duration(variant):
    row={'market':'KOSPI','issuer':'','reportedAtKstText':'2024-08-05 14:14'}
    raw='유가증권시장 매매거래 일시중단(1단계 CB 발동) 1. 일자 및 시각 2024-08-05 14:14:30 향후 20분간 매매거래 중단'
    if variant=='issuer':row['issuer']='개별 종목'
    elif variant=='market':row['market']='KOSDAQ'
    elif variant=='date':raw=raw.replace('2024-08-05','2024-08-06')
    else:raw=raw.replace('20분간','5분간')
    v={'document':'20240805000001','bodySha256':'1'*64,'url':'https://kind.krx.co.kr/external/test.htm'}
    with pytest.raises(ResearchError):c.halt_fact(row,v,raw.encode(),n.now())


def test_halt_and_resumption_pair_preserves_auction_and_rejects_wrong_gap():
    event={'market':'KOSPI','businessDate':'2024-08-05','knownAt':n.now()}
    halt={**event,'eventType':'HALT','eventAt':'2024-08-05T14:14:30+09:00','document':'1'}
    resume={**event,'eventType':'RESUMPTION','eventAt':'2024-08-05T14:34:30+09:00','document':'2'}
    value=c.pair_interruptions([halt,resume])[0]
    assert value['status']=='PAIRED' and value['continuousTradingResumesAt']=='2024-08-05T05:44:30+00:00'
    assert not value['allIntradayInterruptionsComplete']
    assert c.pair_interruptions([resume])[0]['status']=='UNPAIRED'
    resume['eventAt']='2024-08-05T14:35:30+09:00'
    with pytest.raises(ResearchError,match='TIME_CONFLICT'):c.pair_interruptions([halt,resume])


@pytest.mark.parametrize('variant',['parent','body','rule_hash'])
def test_combined_decision_rejects_conflicting_provenance(tmp_path,monkeypatch,variant):
    folder,prior,rules,inv,scope,_=case(tmp_path,monkeypatch)
    result=c.build_review(folder,prior,rules,inv,scope);other=deepcopy(result)
    if variant=='parent':other['parentReviewSha256']='0'*64
    elif variant=='body':other['reviewedBodies'][0]['bodySha256']='0'*64
    else:result['rulesSha256']='0'*64;other['rulesSha256']='0'*64
    with pytest.raises(ResearchError):c.combine_reports([result,other],json.loads(rules.read_bytes()))


def test_cli_asof_reaudits_sources_and_hides_decisions_before_review(tmp_path,monkeypatch,capsys):
    folder,prior,rules,inv,scope,_=case(tmp_path,monkeypatch)
    result=c.build_review(folder,prior,rules,inv,scope);output=tmp_path/'report.json';write(output,result)
    import sys
    monkeypatch.setattr(sys,'argv',['coverage','as-of','--job',str(folder),'--parent',str(prior),'--rules',str(rules),
        '--inventory',str(inv),'--review',str(scope),'--output',str(output),'--at','2000-01-01T00:00:00Z','--market','KOSPI'])
    capsys.readouterr()
    with patch('socket.socket.connect',side_effect=AssertionError('offline')):assert c.main()==0
    assert json.loads(capsys.readouterr().out)['promotionDecisions']==[]
    output.write_bytes(output.read_bytes()+b' ')
    assert c.main()==2
