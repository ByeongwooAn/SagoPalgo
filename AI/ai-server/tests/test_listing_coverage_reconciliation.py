"""V5 preserves the original 514 inventory and only upgrades verified new-listing rows."""
from copy import deepcopy
import json

import pytest

from app.replay import listing_coverage_reconciliation as ledger, listing_disclosure_coverage as capture
from app.replay.dataset import digest,canonical
from app.replay.models import ResearchError
from app.replay.universe_reconciliation import as_of
from test_listing_disclosure_coverage import planned

AT='2026-11-05T00:00:00Z'


def inputs(tmp_path):
    _,p,inv=planned(tmp_path); parent=json.loads(p.read_bytes())
    parent.update(disclosureMatched=63,membershipAwaitingIndividualDisclosure=3,membershipMatched=3,
        nameDisclosureMatched=288,transferNameLabelsExplained=3,nameReviewRequired=0,unresolvedObservations=0,usableForTraining=False)
    inventory=json.loads(inv.read_bytes()); t=capture.phase_targets(inventory)[0]
    f={'observationId':t['observationId'],'kind':'MEMBERSHIP_ENTRY','stockCode':t['symbol'],'historyIsin':t['isin'],
       'sourceIsin':t['isin'],'market':t['market'],'date':t['statusDate'],'statusDate':t['statusDate'],
       'dateBasis':'EXCHANGE_LISTING_DATE','statusReferenceId':t['statusReferenceId'],'statusEventType':'신규상장','knownAt':AT}
    s={'parentSha256':'f'*64,'sourceKind':'SYNTHETIC','targets':1,'facts':[f],'reviews':[]}
    return parent,s,inventory


def test_overlay_preserves_prior_rows_observations_name_results_and_legal_limits(tmp_path):
    p,s,inv=inputs(tmp_path); frozen=canonical(p); r=ledger.overlay(p,s,inv,'f'*64)
    assert canonical(p)==frozen and r['rows'][1:]==p['rows'][1:]
    assert r['rows'][0]['observation']==p['rows'][0]['observation']
    assert r['disclosureMatched']==64 and r['membershipAwaitingIndividualDisclosure']==2
    assert r['membershipMatched']==3 and r['nameDisclosureMatched']==288 and r['nameReviewRequired']==0
    assert not r['usableForTraining'] and not r['rows'][0]['allLegalEffectsConfirmed']
    assert r['rows'][0]['knownAt']==AT and len(as_of(r,'2026-11-04T23:59:59Z')['rows'])==2
    assert inv['remaining']==3 and r['laterPhasePending']==2


@pytest.mark.parametrize('field,value',[('stockCode','999999'),('historyIsin','KR9999999999'),('sourceIsin','KR9999999999'),
    ('market','KOSPI'),('date','2024-01-02'),('statusDate','2024-01-04'),('statusEventType','재상장'),('statusReferenceId','b'*64),('kind','MEMBERSHIP_EXIT')])
def test_identity_date_and_status_binding_are_all_required(tmp_path,field,value):
    p,s,inv=inputs(tmp_path); s['facts'][0][field]=value
    with pytest.raises(ResearchError): ledger.overlay(p,s,inv,'f'*64)


@pytest.mark.parametrize('variant',['duplicate','missing','overlap','parent','source','later_phase'])
def test_exact_phase_scope_is_not_silently_expanded(tmp_path,variant):
    p,s,inv=inputs(tmp_path)
    if variant=='duplicate': s['facts']*=2
    if variant=='missing': s['facts']=[]
    if variant=='overlap': s['reviews']=[{'observationId':s['facts'][0]['observationId'],'knownAt':AT}]
    if variant=='parent': s['parentSha256']='a'*64
    if variant=='source': s['sourceKind']='PROVIDER_OBSERVATIONS'
    if variant=='later_phase': s['facts'][0]['observationId']=p['rows'][1]['observationId']
    with pytest.raises(ResearchError): ledger.overlay(p,s,inv,'f'*64)


def test_unverified_source_keeps_status_match_and_is_counted_as_pending_disclosure(tmp_path):
    p,s,inv=inputs(tmp_path); identity=s['facts'][0]['observationId']; s['facts']=[]
    s['reviews']=[{'observationId':identity,'knownAt':AT,'diagnostic':'LISTING_FACT_CORRECTION_CONFLICT'}]
    r=ledger.overlay(p,s,inv,'f'*64)
    assert r['membershipAwaitingIndividualDisclosure']==3 and r['newListingReviewRequired']==1
    assert r['rows'][0]['resolution']=='STATUS_LIST_MATCH' and r['rows'][0]['individualDisclosureStatus']=='REVIEW_REQUIRED'
    assert len(as_of(r,'2026-11-04T23:59:59Z')['rows'])==2
