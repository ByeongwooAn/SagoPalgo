"""Version-two overlay binds direct full-code evidence to the exact historical observation."""
from copy import deepcopy

import pytest

from app.replay import membership_reconciliation as overlay
from app.replay.dataset import canonical,digest
from app.replay.models import ResearchError
from test_universe_reconciliation import observation,issue,resolve,source_row


def inputs():
    obs=observation(after=issue(market='KOSDAQ'))
    parent_row,_=resolve(obs,[source_row(market='KOSDAQ',name='different')])
    ref=source_row(market='KOSDAQ',name='공식약칭')
    from app.replay.universe_reconciliation import status_id
    parent={'rows':[parent_row],'membershipMatched':0,'unusedStatusReferences':[{'referenceId':status_id(ref)}],
            'marketUniverseComplete':False,'usableForTraining':False,'usableForTrading':False}
    fact={'observationId':digest(canonical(obs)),'kind':'MEMBERSHIP_ENTRY','stockCode':'000010','historyIsin':obs['isin'],
          'sourceIsin':obs['isin'],'market':'KOSDAQ','date':'2024-01-03','dateBasis':'EXCHANGE_ENTRY_APPLICATION_DATE',
          'issuerName':'주식회사 공식약칭','viewerIssuerName':'공식약칭','knownAt':'2026-11-04T13:00:00Z'}
    sup={'facts':[fact],'reviews':[],'correctionHeaderDateIssues':1}
    return parent,sup,{'records':[ref]}


def test_overlay_preserves_parent_and_observation_and_distinguishes_header_issue():
    parent,sup,status=inputs(); frozen=canonical(parent)
    result=overlay.overlay(parent,sup,status,'f'*64)
    assert canonical(parent)==frozen
    assert result['membershipMatched']==result['disclosureMatched']==result['resolvedParentTargets']==1
    assert result['supplementCorrectionHeaderDateIssues']==1 and result['unresolvedObservations']==0
    row=result['rows'][0]
    assert row['previousResolution']=='STATUS_IDENTITY_REVIEW' and row['knownAt']=='2026-11-04T13:00:00Z'
    assert row['observation']==parent['rows'][0]['observation'] and not row['observation']['legalEventConfirmed']
    assert not result['marketUniverseComplete'] and not result['usableForTraining']
    assert not result['unusedStatusReferences'] and row['statusIdentityBridge']['providerIssuerKey']=='00001'


@pytest.mark.parametrize('field,value',[('stockCode','000020'),('historyIsin','KR0000200001'),('sourceIsin','KR0000200001'),
    ('market','KOSPI'),('date','2024-01-04'),('kind','MEMBERSHIP_EXIT'),('observationId','b'*64)])
def test_overlay_rejects_unrelated_or_conflicting_supplemental_facts(field,value):
    parent,sup,status=inputs(); sup['facts'][0][field]=value
    with pytest.raises(ResearchError): overlay.overlay(parent,sup,status,'f'*64)


def test_duplicate_facts_and_fact_review_overlap_are_rejected():
    parent,sup,status=inputs(); sup['facts'].append(deepcopy(sup['facts'][0]))
    with pytest.raises(ResearchError): overlay.overlay(parent,sup,status,'f'*64)
    parent,sup,status=inputs(); sup['reviews']=[{'observationId':sup['facts'][0]['observationId'],'diagnostic':'pending'}]
    with pytest.raises(ResearchError): overlay.overlay(parent,sup,status,'f'*64)


def test_ambiguous_status_name_link_is_not_invented_even_after_direct_disclosure():
    parent,sup,status=inputs(); status['records'].append({**status['records'][0],'providerIssuerKey':'JPN07'})
    result=overlay.overlay(parent,sup,status,'f'*64)
    assert result['membershipMatched']==1
    assert 'statusIdentityBridge' not in result['rows'][0]
