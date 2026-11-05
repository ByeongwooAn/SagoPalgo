"""Annual source bounds, nonce binding, immutable seed reuse and failed reservations."""
from datetime import date,timedelta
import json
import pytest
from app.replay import krx_calendar_sources as source
from app.replay.dataset import canonical,digest
from app.replay.models import ResearchError


def response(year=2023):
    last=date(year,12,31)
    while last.weekday()>=5:last-=timedelta(days=1)
    rows=[]
    for d,label in [(date(year,5,1),'근로자의날'),(last,'연말휴장일')]:
        rows.append({'calnd_dd':d.isoformat(),'calnd_dd_dy':d.isoformat(),'dy_tp_cd':['MON','TUE','WED','THU','FRI','SAT','SUN'][d.weekday()],
            'kr_dy_tp':['월요일','화요일','수요일','목요일','금요일','토요일','일요일'][d.weekday()],'holdy_nm':label})
    return canonical({'block1':rows})


class Client:
    source_kind='SYNTHETIC'
    def __init__(self,fail=False):self.calls=[];self.fail=fail
    def fetch(self,s):
        self.calls.append(s)
        if self.fail:raise OSError('private error')
        return b'a'*32 if s['method']=='GET' else response(int(s['parameters']['search_bas_yy']))


def planned(tmp_path):
    job=tmp_path/'calendar';source.prepare(job,'2023-11-01','2024-02-29',4,source_kind='SYNTHETIC');return job


def test_resume_and_cache_do_not_repeat_completed_nonce_or_data(tmp_path):
    job=planned(tmp_path);c=Client()
    assert source.collect(job,c,1,sleep=lambda _:None)['states']=={'PENDING':2}
    assert source.collect(job,c,3,sleep=lambda _:None)['states']=={'CAPTURED':2}
    assert source.collect(job,Client(True),4)['attemptsUsed']==len(c.calls)==4


def test_failed_reservation_is_not_automatically_retried(tmp_path):
    job=planned(tmp_path);c=Client(True)
    source.collect(job,c,1);source.collect(job,c,0)
    assert len(c.calls)==1 and source.load(job)[1]['attempts'][0]['state']=='FAILED'


@pytest.mark.parametrize('variant',['raw','request','plan','orphan'])
def test_tampering_stops_before_new_network_calls(tmp_path,variant):
    job=planned(tmp_path);source.collect(job,Client(),4,sleep=lambda _:None)
    if variant=='raw':(job/'raw/0001.bin').write_bytes(b'changed')
    elif variant=='plan':
        p=json.loads((job/'plan.json').read_bytes());p['years']=[2024];(job/'plan.json').write_bytes(canonical(p))
    else:
        j=json.loads((job/'journal.json').read_bytes())
        if variant=='request':j['attempts'][1]['request']['parameters']['code']='different'
        else:j['attempts'][0]['stage']='DATA'
        (job/'journal.json').write_bytes(canonical(j))
    c=Client()
    with pytest.raises(ResearchError):source.collect(job,c,1)
    assert not c.calls


@pytest.mark.parametrize('variant',['year','weekday','date','duplicate','empty','truncated','extra'])
def test_annual_rows_require_year_weekday_unique_dates_and_completeness_anchors(variant):
    d=json.loads(response())
    if variant=='year':d=json.loads(response(2024))
    if variant=='weekday':d['block1'][0]['dy_tp_cd']='SUN'
    if variant=='date':d['block1'][0]['calnd_dd_dy']='2023-05-02'
    if variant=='duplicate':d['block1']*=2
    if variant=='empty':d['block1']=[]
    if variant=='truncated':d['block1']=d['block1'][:1]
    if variant=='extra':d['block1'][0]['unexpected']='x'
    with pytest.raises(ResearchError):source.holidays(canonical(d),2023)


def test_complete_discovery_seed_is_reused_and_reaudited(tmp_path):
    original=tmp_path/'original';source.prepare(original,'2026-01-01','2026-11-02',2,source_kind='SYNTHETIC')
    source.collect(original,Client(),2,sleep=lambda _:None);_,j,_=source.load(original)
    seed=tmp_path/'discovery';seed.mkdir()
    for e in j['attempts']:
        name='year-2026-'+e['stage'].lower();(seed/(name+'.bin')).write_bytes((original/'raw'/f"{e['seq']:04d}.bin").read_bytes())
        (seed/(name+'.json')).write_bytes(canonical({**e['request'],'sha256':e['sha256'],'startedAt':e['startedAt'],'capturedAt':e['capturedAt']}))
    job=tmp_path/'seeded';source.prepare(job,'2026-01-01','2026-11-02',0,seed,2026,'SYNTHETIC')
    c=Client(True);r=source.collect(job,c,0)
    assert r['states']=={'CAPTURED':1} and r['seededRequests']==2 and not c.calls
    (job/'seed/2026-DATA.bin').write_bytes(b'changed')
    with pytest.raises(ResearchError):source.load(job)


def test_invalid_scope_budget_and_wrong_source_kind_are_rejected(tmp_path):
    with pytest.raises(ResearchError):source.prepare(tmp_path/'bad','2022-01-01','2023-01-01',4)
    with pytest.raises(ResearchError):source.prepare(tmp_path/'small','2023-01-01','2024-01-01',3)
    job=planned(tmp_path);c=Client();c.source_kind='PROVIDER_OBSERVATIONS'
    with pytest.raises(ResearchError):source.collect(job,c,1)
    assert not c.calls
