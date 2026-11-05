"""The delisting subset must match V5 and its hash-bound original inventory exactly."""
import json

import pytest

from app.replay import delisting_disclosure_coverage as coverage
from app.replay.dataset import canonical,digest,read_bytes,read_json
from app.replay.krx_storage import atomic_json
from app.replay.models import ResearchError
from test_listing_disclosure_coverage import planned as listing_plan
from test_kind_membership_evidence import Client,search,viewer,path


def planned(tmp_path):
    _,p,inv=listing_plan(tmp_path)
    parent=json.loads(p.read_bytes()); parent['schemaVersion']='SAGOPALGO_UNIVERSE_RECONCILIATION_V5'
    parent['listingInventorySha256']=digest(inv.read_bytes())
    p.write_bytes(canonical(parent)); job=tmp_path/'delisting'
    coverage.prepare(job,p,inv,8)
    return job,p,inv


class DelistingClient(Client):
    def fetch(self,spec):
        raw=super().fetch(spec)
        if 'details.do' in spec['url']: return search('상장폐지')
        if 'acptno=' in spec['url']: return viewer('000030',title='상장폐지')
        return raw


def test_only_removals_are_planned_and_cache_resume_is_offline(tmp_path):
    job,_,_=planned(tmp_path); plan,_,_=coverage.load(job)
    assert len(plan['targets'])==1 and plan['targets'][0]['symbol']=='000030'
    c=DelistingClient()
    assert coverage.collect(job,c,2,sleep=lambda _:None)['states']=={'PENDING':1}
    assert coverage.collect(job,c,2,sleep=lambda _:None)['states']=={'BODIES_CAPTURED':1}
    assert coverage.collect(job,Client(fail=1),8)['attemptsUsed']==len(c.calls)==4


@pytest.mark.parametrize('variant',['inventory_hash','subset','stock','status_date','schema'])
def test_parent_or_inventory_conflict_blocks_planning(tmp_path,variant):
    _,p,inv=planned(tmp_path); parent=read_json(read_bytes(p)); original=read_json(read_bytes(inv))
    if variant=='inventory_hash': parent['listingInventorySha256']='a'*64
    if variant=='subset': original['targets']=[v for v in original['targets'] if v['category']!='DELISTING']
    if variant=='stock': next(t for t in original['targets'] if t['category']=='DELISTING')['symbol']='999999'
    if variant=='status_date': parent['rows'][-1]['evidence'][0]['date']='2024-01-04'
    if variant=='schema': parent['schemaVersion']='SAGOPALGO_UNIVERSE_RECONCILIATION_V4'
    if variant not in {'inventory_hash'}: parent['listingInventorySha256']=digest(canonical(original))
    atomic_json(p,parent); atomic_json(inv,original)
    with pytest.raises((ResearchError,ValueError)): coverage.prepare(tmp_path/'other',p,inv,8)


@pytest.mark.parametrize('variant',['raw','request','orphan'])
def test_cache_tampering_is_detected_before_network(tmp_path,variant):
    job,_,_=planned(tmp_path); coverage.collect(job,DelistingClient(),4,sleep=lambda _:None)
    if variant=='raw': (job/'raw/0001.bin').write_bytes(b'changed')
    else:
        j=read_json(read_bytes(job/'journal.json'))
        if variant=='request': j['attempts'][0]['request']['parameters']['repIsuSrtCd']='A999999'
        else: j['attempts'][0]['stage']='V3_BODY'
        atomic_json(job/'journal.json',j)
    c=Client(fail=1)
    with pytest.raises(ResearchError): coverage.collect(job,c,1)
    assert not c.calls


def test_failure_requires_explicit_retry_and_preserves_receipt(tmp_path):
    job,_,_=planned(tmp_path)
    assert coverage.collect(job,Client(fail=1),8)['attemptsUsed']==1
    assert coverage.collect(job,Client(fail=1),8)['attemptsUsed']==1
    assert coverage.collect(job,DelistingClient(),8,True,sleep=lambda _:None)['states']=={'BODIES_CAPTURED':1}
    assert coverage.load(job)[1]['attempts'][0]['state']=='FAILED'


def test_company_delisting_decision_is_not_exchange_delisting_notice():
    with pytest.raises(ResearchError): coverage.candidates(search('상장폐지결정'))
    with pytest.raises(ResearchError): coverage.candidates(search('상장폐지',pages=2))


def test_insufficient_budget_does_not_create_job(tmp_path):
    _,p,inv=planned(tmp_path)
    with pytest.raises(ValueError): coverage.prepare(tmp_path/'small',p,inv,3)
    assert not (tmp_path/'small').exists()
