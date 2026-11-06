"""Known-at restrictions, second boundaries and real-evidence export without session promotion."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.replay import intraday as i
from app.replay.dataset import canonical, digest, normalize, quality
from app.replay.engine import replay
from app.replay.models import DatasetSpec, ReplayConfig, ResearchError, utc
from app.replay.__main__ import main
from tests.test_replay import inputs, dataset

BEFORE='2026-11-01T00:00:00Z'
CREATED='2026-11-03T00:00:00Z'


def phase(kind='HALT',start='2026-11-02T00:02:00Z',end='2026-11-02T00:02:30Z',known=BEFORE,id='phase1',market='KOSPI'):
    return {'phaseId':id,'market':market,'businessDate':'2026-11-02','kind':kind,'startAt':start,'endAt':end,'knownAt':known,
            'evidence':['https://example.test/synthetic'],'bodySha256s':['1'*64]}


def timeline(phases=(),coverage='COMPLETE',known=BEFORE,provenance='SYNTHETIC',market='KOSPI'):
    return i.timeline_value({'schemaVersion':'SAGOPALGO_INTRADAY_TIMELINE_V1','sourceDecisionSha256':'2'*64,
        'provenance':provenance,'createdAt':CREATED,'days':[{'market':market,'businessDate':'2026-11-02','coverage':coverage,
            'knownAt':known,'openAt':'2026-11-02T00:00:00Z' if coverage=='COMPLETE' else None,
            'closeAt':'2026-11-02T06:30:00Z' if coverage=='COMPLETE' else None}],
        'phases':list(phases),'allIntradayInterruptionsComplete':False,'usableForTrading':False,'usableForStrategyValidation':False})


def policy(t,order='ORDINARY',market='KOSPI'):
    return i.ReplayIntraday.model_validate({'timeline':t.model_dump(mode='json'),'timelineSha256':digest(canonical(t.model_dump(mode='json'))),'market':market,'orderClass':order})


def engine_inputs():
    # Engine unit cases do not require publishing a filesystem bundle. The CLI
    # integration below still exercises the real build/load/hash path.
    spec,rows,_=inputs();ds=DatasetSpec.model_validate(spec)
    raw=b''.join(canonical(r)+b'\n' for r in rows);records=normalize(raw,ds)
    manifest={'datasetId':digest(canonical({'syntheticSpec':spec,'rawSha256':digest(raw)}))}
    return manifest,ds,records,quality(records,ds,len(rows))


def run(tmp_path,t,order='ORDINARY',config=None):
    loaded=engine_inputs()
    cfg=inputs()[2];cfg['intents']=[cfg['intents'][0]];cfg.update(config or {})
    return replay(*loaded,ReplayConfig.model_validate(cfg),policy(t,order))


@pytest.mark.parametrize('at,status',[
    ('2026-11-02T00:01:59.999999Z',None),('2026-11-02T00:02:00Z','MARKET_HALTED'),
    ('2026-11-02T00:02:29.999999Z','MARKET_HALTED'),('2026-11-02T00:02:30Z','REOPENING_AUCTION_UNSUPPORTED'),
    ('2026-11-02T00:03:29.999999Z','REOPENING_AUCTION_UNSUPPORTED'),('2026-11-02T00:03:30Z',None)])
def test_half_open_halt_auction_and_continuous_boundaries(at,status):
    t=timeline([phase(),phase('REOPENING_AUCTION','2026-11-02T00:02:30Z','2026-11-02T00:03:30Z',id='auction')])
    start=utc(at);actual=i.gate(policy(t),start,start+i.timedelta(microseconds=1),'BUY')
    assert (actual['status'] if actual else None)==status


@pytest.mark.parametrize('kind,status',[('HALT','MARKET_HALTED'),('REOPENING_AUCTION','REOPENING_AUCTION_UNSUPPORTED')])
def test_tradable_bar_does_not_override_known_market_phase(tmp_path,kind,status):
    report=run(tmp_path,timeline([phase(kind)]))
    assert not report['fills'] and report['finalCash']=='10000' and report['holdings']==[]
    assert report['outcomes'][0]['status']==status and report['outcomes'][0]['stage']=='EXECUTION'


def test_new_intent_during_halt_is_blocked_at_decision(tmp_path):
    report=run(tmp_path,timeline([phase(start='2026-11-02T00:01:00Z')]))
    assert report['outcomes'][0]['status']=='MARKET_HALTED' and report['outcomes'][0]['stage']=='DECISION'
    assert not report['fills']


def test_bar_crossing_later_known_boundary_is_not_estimated(tmp_path):
    report=run(tmp_path,timeline([phase(start='2026-11-02T00:02:30Z',end='2026-11-02T00:03:30Z')]))
    assert report['outcomes'][0]['status']=='INTRADAY_BAR_CROSSES_PHASE_BOUNDARY' and not report['fills']


def test_bar_ending_at_halt_start_is_allowed(tmp_path):
    report=run(tmp_path,timeline([phase(start='2026-11-02T00:03:00Z',end='2026-11-02T00:03:30Z')]))
    assert len(report['fills'])==1 and report['fills'][0]['at']=='2026-11-02T00:02:00+00:00'


def test_first_full_bar_after_auction_can_fill_when_day_is_confirmed(tmp_path):
    # Phase ends before decision and next bar; no synthetic auction execution.
    t=timeline([phase('REOPENING_AUCTION','2026-11-02T00:00:00Z','2026-11-02T00:01:00Z')])
    report=run(tmp_path,t)
    assert len(report['fills'])==1 and report['engineVersion']=='R5_FOUNDATION_3'
    assert report['intradayPolicy']['auctionMatching']=='UNSUPPORTED'


def test_new_decision_after_second_boundary_uses_next_full_minute(tmp_path):
    cfg=inputs()[2];buy=cfg['intents'][0]
    buy.update(decisionAt='2026-11-02T00:02:31Z',expiresAt='2026-11-02T00:04:00Z',evidence=['demo/BAR/m2/1'])
    t=timeline([phase('REOPENING_AUCTION','2026-11-02T00:02:00Z','2026-11-02T00:02:30Z')])
    report=run(tmp_path,t,config={'intents':[buy]})
    assert len(report['fills'])==1 and report['fills'][0]['at']=='2026-11-02T00:03:00+00:00'


@pytest.mark.parametrize('order,side,expected',[
    ('ORDINARY','BUY',None),('ORDINARY','SELL',None),('PROGRAM','BUY','PROGRAM_BUY_PAUSED'),('PROGRAM','SELL',None)])
def test_sidecar_only_blocks_matching_program_order_side(order,side,expected):
    t=timeline([phase('PROGRAM_BUY_PAUSE')]);start=utc('2026-11-02T00:02:00Z')
    value=i.gate(policy(t,order),start,start+i.timedelta(seconds=1),side)
    assert (value['status'] if value else None)==expected


def test_program_pause_and_market_halt_can_overlap_without_becoming_same_scope():
    t=timeline([phase(),phase('PROGRAM_BUY_PAUSE',id='sidecar')]);start=utc('2026-11-02T00:02:00Z')
    assert i.gate(policy(t,'PROGRAM'),start,start+i.timedelta(seconds=1),'BUY')['status']=='MARKET_HALTED'


def test_program_pause_wires_to_engine_but_ordinary_order_can_fill(tmp_path):
    t=timeline([phase('PROGRAM_BUY_PAUSE')])
    ordinary=run(tmp_path,t)
    assert len(ordinary['fills'])==1
    other=tmp_path/'program';other.mkdir();program=run(other,t,'PROGRAM')
    assert not program['fills'] and program['outcomes'][0]['status']=='PROGRAM_BUY_PAUSED'


def test_future_phase_cannot_change_earlier_outcome_or_reveal_phase_id(tmp_path):
    late='2026-11-02T00:04:00Z'
    t=timeline([phase(known=late)],known=late)
    first=run(tmp_path,t)
    t2=timeline([phase('PROGRAM_SELL_PAUSE',start='2026-11-02T00:03:00Z',end='2026-11-02T00:03:30Z',known=late,id='secret-future')],known=late)
    other=tmp_path/'changed';other.mkdir();second=run(other,t2)
    assert first['outcomes']==second['outcomes']
    assert first['outcomes'][0]['status']=='INTRADAY_COVERAGE_UNCONFIRMED'
    assert first['outcomes'][0]['phaseIds']==[] and not first['fills'] and not second['fills']


def test_partial_real_evidence_never_authorizes_unknown_continuous_time(tmp_path):
    report=run(tmp_path,timeline(coverage='PARTIAL',provenance='EVIDENCED_PARTIAL'))
    assert report['outcomes'][0]['status']=='INTRADAY_COVERAGE_UNCONFIRMED' and not report['fills']


def test_late_historical_capture_is_not_backdated(tmp_path):
    t=timeline([phase(known=CREATED)],coverage='PARTIAL',known=CREATED,provenance='EVIDENCED_PARTIAL')
    report=run(tmp_path,t)
    assert report['outcomes'][0]['status']=='INTRADAY_COVERAGE_UNCONFIRMED' and report['outcomes'][0]['phaseIds']==[]


def test_visibility_activates_at_exact_known_at_and_cannot_infer_missing_day():
    known='2026-11-02T00:02:00Z';p=policy(timeline([phase(known=known)],known=known))
    before=utc('2026-11-02T00:01:59.999999Z');at=utc(known)
    assert i.gate(p,before,at,'BUY')=={'status':'INTRADAY_COVERAGE_UNCONFIRMED','phaseIds':[]}
    assert i.gate(p,at,at+i.timedelta(microseconds=1),'BUY')['status']=='MARKET_HALTED'
    other=utc('2026-11-03T00:02:00Z')
    assert i.gate(p,other,other+i.timedelta(seconds=1),'BUY')['status']=='INTRADAY_COVERAGE_UNCONFIRMED'


@pytest.mark.parametrize('variant',['overlap','duplicate','reversed','wrong_date','future','day_before_phase','real_complete','hash'])
def test_invalid_phase_model_or_identity_is_rejected(variant):
    t=timeline([phase()]).model_dump(mode='json');t.pop('timelineId')
    if variant=='overlap':t['phases'].append(phase('REOPENING_AUCTION',id='overlap'))
    elif variant=='duplicate':t['phases']*=2
    elif variant=='reversed':t['phases'][0]['endAt']=t['phases'][0]['startAt']
    elif variant=='wrong_date':t['phases'][0]['businessDate']='2026-11-01'
    elif variant=='future':t['phases'][0]['knownAt']='2026-11-04T00:00:00Z'
    elif variant=='day_before_phase':t['phases'][0]['knownAt']='2026-11-02T00:01:00Z'
    elif variant=='real_complete':t['provenance']='EVIDENCED_PARTIAL'
    else:
        t['timelineId']='0'*64
        with pytest.raises(ValueError):i.Timeline.model_validate(t)
        return
    with pytest.raises(ValueError):i.timeline_value(t)


def test_other_market_never_inherits_a_market_halt():
    t=timeline([phase()]).model_dump(mode='json');t.pop('timelineId')
    t['days'].append({**t['days'][0],'market':'KOSDAQ'})
    p=policy(i.timeline_value(t),market='KOSDAQ');start=utc('2026-11-02T00:02:00Z')
    assert i.gate(p,start,start+i.timedelta(seconds=1),'BUY') is None


def test_timeline_file_hash_market_and_synthetic_opt_in_are_required(tmp_path):
    t=timeline();path=tmp_path/'timeline.json';path.write_bytes(canonical(t.model_dump(mode='json')))
    with pytest.raises(ResearchError,match='HASH_MISMATCH'):i.load_policy(path,'0'*64,'KOSPI','ORDINARY')
    with pytest.raises(ValueError):i.load_policy(path,digest(path.read_bytes()),'KOSDAQ','ORDINARY')
    # Dataset provenance can be real while the timeline itself remains synthetic.
    spec,rows,config=inputs();spec['sources'][0]['provenance']='OBSERVED';config['allowSynthetic']=False
    _,loaded=dataset(tmp_path,spec,rows)
    with pytest.raises(ResearchError,match='SYNTHETIC_INTRADAY'):replay(*loaded,ReplayConfig.model_validate(config),policy(t))


def test_legacy_replay_is_byte_identical_without_timeline(tmp_path):
    _,loaded=dataset(tmp_path);cfg=ReplayConfig.model_validate(inputs()[2])
    assert canonical(replay(*loaded,cfg))==canonical(replay(*loaded,cfg,None))
    assert replay(*loaded,cfg)['engineVersion']=='R5_FOUNDATION_2'


def test_cli_loads_hash_bound_timeline_and_runs_offline(tmp_path,capsys):
    target,_=dataset(tmp_path);cfg=tmp_path/'config.json';cfg.write_bytes(canonical(inputs()[2]))
    t=timeline([phase()]);path=tmp_path/'timeline.json';path.write_bytes(canonical(t.model_dump(mode='json')))
    output=tmp_path/'report.json'
    with patch('socket.socket.connect',side_effect=AssertionError('offline')):
        assert main(['replay','--dataset',str(target),'--config',str(cfg),'--output',str(output),
            '--intraday-timeline',str(path),'--timeline-sha256',digest(path.read_bytes()),'--market','KOSPI','--order-class','ORDINARY'])==0
    result=json.loads(output.read_bytes());assert result['intradayPolicy']['timelineSha256']==digest(path.read_bytes())
    assert not result['fills']
    with pytest.raises(SystemExit):main(['replay','--dataset',str(target),'--config',str(cfg),'--output',str(output),'--market','KOSPI'])


@pytest.mark.parametrize('form,market,side',[('99404','KOSPI','BUY'),('99405','KOSPI','SELL'),('70711','KOSDAQ','BUY'),('70710','KOSDAQ','SELL')])
def test_official_program_templates_extract_direction_date_and_five_minutes(form,market,side):
    stamp='2. 발동일시 2024년08월05일 09시06분02초' if market=='KOSPI' else '1. 일자 및 시각 2024-08-05 09:06:02'
    raw=(stamp+' 프로그램'+('매수' if side=='BUY' else '매도')+'호가의 효력이 향후 5분간 정지됨').encode()
    row={'market':market,'document':'20240805000001','url':'https://kind.krx.co.kr/external/2024/08/05/000001/20240805000001/'+form+'.htm','bodySha256':digest(raw)}
    result=i.program_phase(row,raw,CREATED)
    assert result['kind']=='PROGRAM_'+side+'_PAUSE' and result['businessDate']=='2024-08-05'
    assert utc(result['endAt'])-utc(result['startAt'])==i.timedelta(minutes=5)


@pytest.mark.parametrize('variant',['form','market','side','duration','date'])
def test_program_template_requires_exact_market_scope_and_time(variant):
    raw='2. 발동일시 2024년08월05일 09시06분02초 프로그램매수호가 향후 5분간 효력정지'
    row={'market':'KOSPI','document':'20240805000001','url':'https://kind.krx.co.kr/external/2024/08/05/000001/20240805000001/99404.htm','bodySha256':'1'*64}
    if variant=='form':row['url']=row['url'].replace('99404','99303')
    elif variant=='market':row['market']='KOSDAQ'
    elif variant=='side':raw=raw.replace('매수','매도')
    elif variant=='duration':raw=raw.replace('5분','20분')
    else:raw=raw.replace('08월05일','13월05일')
    with pytest.raises((ValueError,ResearchError)):i.program_phase(row,raw.encode(),CREATED)
