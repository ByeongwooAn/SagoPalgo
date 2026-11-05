"""V6 may upgrade only hash-bound removal observations, with conservative knowledge times."""
import json
import pytest

from app.replay import delisting_coverage_reconciliation as ledger, delisting_disclosure_coverage as capture
from app.replay.dataset import canonical
from app.replay.models import ResearchError
from app.replay.universe_reconciliation import as_of
from test_delisting_disclosure_coverage import planned

AT = '2026-11-05T00:00:00Z'


def inputs(tmp_path):
    _, p, inv = planned(tmp_path); parent = json.loads(p.read_bytes()); inventory = json.loads(inv.read_bytes())
    parent.update(disclosureMatched=355, membershipAwaitingIndividualDisclosure=3, membershipMatched=577,
                  nameDisclosureMatched=288, nameReviewRequired=0, usableForTraining=False, newListingReviewRequired=0)
    t = capture.targets_from(parent, inventory)[0]
    f = {'observationId':t['observationId'], 'kind':'MEMBERSHIP_EXIT', 'stockCode':t['symbol'], 'historyIsin':t['isin'],
         'sourceIsin':None, 'market':t['market'], 'date':t['statusDate'], 'statusDate':t['statusDate'],
         'dateBasis':'EXCHANGE_DELISTING_DATE', 'statusReferenceId':t['statusReferenceId'], 'statusEventType':t['statusEventType'], 'knownAt':AT}
    return parent, {'parentSha256':'f'*64,'sourceKind':'SYNTHETIC','targets':1,'facts':[f],'reviews':[]}, inventory


def test_only_removal_row_changes_and_future_capture_time_is_not_backdated(tmp_path):
    p, s, inv = inputs(tmp_path); frozen = canonical(p); r = ledger.overlay(p,s,inv,'f'*64)
    assert canonical(p) == frozen and r['rows'][:-1] == p['rows'][:-1]
    assert r['rows'][-1]['observation'] == p['rows'][-1]['observation']
    assert r['disclosureMatched'] == 356 and r['membershipAwaitingIndividualDisclosure'] == 2
    assert r['nameDisclosureMatched'] == 288 and not r['usableForTraining']
    assert r['rows'][-1]['knownAt'] == AT and len(as_of(r,'2026-11-04T23:59:59Z')['rows']) == 2


@pytest.mark.parametrize('field,value', [('stockCode','999999'),('historyIsin','KR9999999999'),('sourceIsin','KR9999999999'),
    ('market','KOSPI'),('date','2024-01-02'),('statusDate','2024-01-04'),('statusEventType','다른사유'),
    ('statusReferenceId','b'*64),('kind','MEMBERSHIP_ENTRY'),('dateBasis','LIQUIDATION_END')])
def test_all_identity_status_date_and_direction_bindings_are_required(tmp_path, field, value):
    p,s,inv = inputs(tmp_path); s['facts'][0][field] = value
    with pytest.raises(ResearchError): ledger.overlay(p,s,inv,'f'*64)


@pytest.mark.parametrize('variant',['duplicate','missing','overlap','parent','source','other_phase'])
def test_exact_scope_is_required(tmp_path, variant):
    p,s,inv = inputs(tmp_path)
    if variant == 'duplicate': s['facts'] *= 2
    if variant == 'missing': s['facts'] = []
    if variant == 'overlap': s['reviews'] = [{'observationId':s['facts'][0]['observationId'],'knownAt':AT}]
    if variant == 'parent': s['parentSha256'] = 'a'*64
    if variant == 'source': s['sourceKind'] = 'PROVIDER_OBSERVATIONS'
    if variant == 'other_phase': s['facts'][0]['observationId'] = p['rows'][0]['observationId']
    with pytest.raises(ResearchError): ledger.overlay(p,s,inv,'f'*64)


def test_review_does_not_upgrade_status_match(tmp_path):
    p,s,inv = inputs(tmp_path); identity=s['facts'][0]['observationId']; s['facts']=[]
    s['reviews']=[{'observationId':identity,'knownAt':AT,'diagnostic':'UNVERIFIED'}]
    r=ledger.overlay(p,s,inv,'f'*64)
    assert r['delistingReviewRequired']==1 and r['membershipAwaitingIndividualDisclosure']==3
    assert r['rows'][-1]['resolution']=='STATUS_LIST_MATCH'
