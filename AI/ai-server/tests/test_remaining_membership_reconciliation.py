"""V7 upgrades exact phase rows without backdating knowledge or dropping earlier reviews."""
import json
import pytest
from app.replay import remaining_membership_reconciliation as ledger,remaining_membership_disclosures as capture
from app.replay.dataset import canonical
from app.replay.models import ResearchError
from app.replay.universe_reconciliation import as_of
from test_remaining_membership_disclosures import planned

AT='2026-11-06T00:00:00Z'


def inputs(tmp_path):
    _,p,inv=planned(tmp_path);parent=json.loads(p.read_bytes());inventory=json.loads(inv.read_bytes())
    parent.update(disclosureMatched=560,membershipAwaitingIndividualDisclosure=2,delistingVerified=205,
        nameDisclosureMatched=288,nameReviewRequired=0,usableForTraining=False)
    a,b=capture.targets_from(parent,inventory)
    parent['rows'][-1]['membershipDisclosureReview']={'diagnostic':'EARLIER_CONFLICT','knownAt':'2026-11-04T12:00:00Z'}
    f={'observationId':a['observationId'],'category':a['category'],'kind':'MEMBERSHIP_ENTRY','stockCode':a['symbol'],
       'historyIsin':a['isin'],'sourceIsin':a['isin'],'market':a['market'],'date':a['statusDate'],'statusDate':a['statusDate'],
       'statusReferenceId':a['statusReferenceId'],'statusEventType':a['statusEventType'],'dateBasis':'EXCHANGE_RELISTING_DATE','knownAt':AT}
    review={'observationId':b['observationId'],'category':b['category'],'knownAt':AT,'diagnostic':'DATE_CONFLICT'}
    return parent,{'parentSha256':'f'*64,'sourceKind':'SYNTHETIC','targets':2,'facts':[f],'reviews':[review]},inventory


def test_preserves_observations_other_rows_legal_flags_and_earlier_review(tmp_path):
    p,s,inv=inputs(tmp_path);frozen=canonical(p);r=ledger.overlay(p,s,inv,'f'*64)
    assert canonical(p)==frozen and r['rows'][0]==p['rows'][0]
    assert [v['observation'] for v in r['rows']]==[v['observation'] for v in p['rows']]
    assert r['rows'][-1]['previousMembershipDisclosureReview']==p['rows'][-1]['membershipDisclosureReview']
    assert r['disclosureMatched']==561 and r['membershipAwaitingIndividualDisclosure']==1
    assert r['nameDisclosureMatched']==288 and not r['usableForTraining']
    assert r['relistingVerified']==1 and r['delistingReviewRequired']==1
    assert len(as_of(r,'2026-11-05T23:59:59Z')['rows'])==1


@pytest.mark.parametrize('field,value',[('kind','MEMBERSHIP_EXIT'),('category','INBOUND_TRANSFER'),('stockCode','999999'),
    ('historyIsin','KR9999999999'),('sourceIsin','KR9999999999'),('market','KOSPI'),('date','2024-01-02'),
    ('statusDate','2024-01-04'),('statusReferenceId','a'*64),('statusEventType','이전상장'),('dateBasis','LEGAL_DEMERGER_DATE')])
def test_identity_status_and_date_bindings_are_mandatory(tmp_path,field,value):
    p,s,inv=inputs(tmp_path);s['facts'][0][field]=value
    with pytest.raises(ResearchError):ledger.overlay(p,s,inv,'f'*64)


@pytest.mark.parametrize('variant',['duplicate','missing','overlap','parent','source','other_row','review_category'])
def test_exact_phase_scope_is_required(tmp_path,variant):
    p,s,inv=inputs(tmp_path)
    if variant=='duplicate':s['facts']*=2
    if variant=='missing':s['reviews']=[]
    if variant=='overlap':s['reviews'][0]['observationId']=s['facts'][0]['observationId']
    if variant=='parent':s['parentSha256']='a'*64
    if variant=='source':s['sourceKind']='PROVIDER_OBSERVATIONS'
    if variant=='other_row':s['facts'][0]['observationId']=p['rows'][0]['observationId']
    if variant=='review_category':s['reviews'][0]['category']='RELISTING'
    with pytest.raises(ResearchError):ledger.overlay(p,s,inv,'f'*64)


@pytest.mark.parametrize('field,value',[('destinationEntryOnlyConfirmed',False),('sourceMarketHistoryConfirmed',True),('completeTransferPairConfirmed',True)])
def test_destination_entry_cannot_be_promoted_to_full_transfer_history(tmp_path,field,value):
    p,s,inv=inputs(tmp_path)
    p['rows'][1]['evidence'][0]['eventType']='이전상장'
    entry=next(t for t in inv['targets'] if t['symbol']=='000020');entry.update(category='INBOUND_TRANSFER',statusEventType='이전상장')
    f=s['facts'][0];f.update(category='INBOUND_TRANSFER',statusEventType='이전상장',dateBasis='EXCHANGE_LISTING_DATE',
        destinationEntryOnlyConfirmed=True,sourceMarketHistoryConfirmed=False,completeTransferPairConfirmed=False)
    f[field]=value
    with pytest.raises(ResearchError):ledger.overlay(p,s,inv,'f'*64)
