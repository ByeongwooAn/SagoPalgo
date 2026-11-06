from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.replay.cost_rules import CostPack,TaxRule,Fill,FeeProfile,Rounding,calculate,rounded,main
from app.replay.dataset import canonical,read_json
from app.replay.models import ResearchError,utc

AT=utc('2026-11-07T00:00:00Z')

def pack():
    # Synthetic evidence and rates fixture, independent of downloaded official files.
    rules=[]
    for y,st,kd in [(2023,'5','20'),(2024,'3','18'),(2025,'0','15'),(2026,'5','20')]:
        for market in ['KOSPI','KOSDAQ']:
            rules.append(dict(ruleId=f'{y}-{market}',market=market,product='COMMON_STOCK',exchange='KRX',validFrom=f'{y}-01-01',validTo=f'{y+1}-01-01',knownAt='2026-11-06T00:00:00Z',basis='SETTLEMENT_DATE',securitiesTaxBps=st if market=='KOSPI' else kd,ruralTaxBps='15' if market=='KOSPI' else '0',evidenceUrl='https://synthetic.test/tax',evidenceSha256='a'*64))
    return CostPack(schemaVersion='SAGOPALGO_COST_RULES_V1',accountFeeStatus='UNCONFIRMED',taxCollectionStatus='UNCONFIRMED',taxes=rules)

def fill(**changes):
    v=dict(fillId='f1',orderRef='o1',accountAlias='personal',stockCode='005930',market='KOSPI',exchange='KRX',product='COMMON_STOCK',channel='KB_OPENAPI',funding='CASH',taxTreatment='ORDINARY_TAXABLE',side='SELL',executedAt='2024-12-27T01:00:00Z',settlementDate='2025-01-02',settlementConfirmed=True,notionalWon='1000000')
    v.update(changes);return Fill.model_validate(v)

def profile(**changes):
    v=dict(schemaVersion='SAGOPALGO_FEE_PROFILE_V1',profileId='synthetic-fee',accountAlias='personal',channel='KB_OPENAPI',funding='CASH',product='COMMON_STOCK',markets=['KOSPI','KOSDAQ'],validFrom='2023-01-01',validTo='2027-01-01',knownAt='2026-11-06T00:00:00Z',provenance='SYNTHETIC',evidenceSha256='b'*64,aggregation='DAILY_SYMBOL_SIDE',rounding=dict(unitWon=1,mode='DOWN'),bands=[dict(lowerWon=0,upperWon=None,bps='1.5',fixedWon=0)],minimumWon=0)
    v.update(changes);return FeeProfile.model_validate(v)

def scenario(fills,**kw):return calculate(pack(),fills,AT,profile(),Rounding(unitWon=1,mode='DOWN'),**kw)

@pytest.mark.parametrize('market,year,st,rural',[(m,y,s if m=='KOSPI' else k,'1500' if m=='KOSPI' else '0') for y,s,k in [(2023,'500','2000'),(2024,'300','1800'),(2025,'0','1500'),(2026,'500','2000')] for m in ['KOSPI','KOSDAQ']])
def test_year_and_market_rates(market,year,st,rural):
    r=scenario([fill(market=market,executedAt=f'{year}-06-01T00:00:00Z',settlementDate=f'{year}-06-03')])['rows'][0]
    assert Decimal(r['rawSecuritiesTaxWon'])==Decimal(st) and Decimal(r['rawRuralTaxWon'])==Decimal(rural)

def test_year_end_uses_supplied_settlement_date_not_execution_year():
    r=scenario([fill()]);assert r['rows'][0]['taxRuleId']=='2025-KOSPI'
    assert r['scenarioTaxWon']=='1500' and r['scenarioFeeWon']=='150' and r['scenarioTotalWon']=='1650'
    assert not r['brokerReconciled'] and not r['usableForTrading']

@pytest.mark.parametrize('year,expected',[(2024,'1800'),(2025,'1500'),(2026,'2000')])
def test_exact_january_boundary(year,expected):
    f=fill(executedAt=f'{year-1}-12-26T01:00:00Z',settlementDate=f'{year}-01-02')
    assert scenario([f])['scenarioTaxWon']==expected

def test_missing_account_and_rounding_produce_null_total_not_free_trade():
    r=calculate(pack(),[fill()],AT)
    assert r['scenarioFeeWon'] is None and r['scenarioTaxWon'] is None and r['scenarioTotalWon'] is None
    assert set(r['rows'][0]['reasons'])=={'ACCOUNT_FEE_UNCONFIRMED','TAX_COLLECTION_RULE_UNCONFIRMED'}
    assert r['rows'][0]['rawRuralTaxWon']=='1500'

def test_buy_has_no_sell_tax_even_without_settlement_confirmation():
    r=scenario([fill(side='BUY',settlementConfirmed=False)])
    assert r['scenarioTaxWon']=='0' and r['scenarioFeeWon']=='150'

@pytest.mark.parametrize('changes,reason',[
    ({'settlementConfirmed':False},'SETTLEMENT_DATE_UNCONFIRMED'),
    ({'settlementDate':'2027-01-04'},'SETTLEMENT_AFTER_ASOF'),
    ({'executedAt':'2026-11-08T00:00:00Z','settlementDate':'2026-11-10'},'FILL_NOT_YET_KNOWN'),
])
def test_missing_or_future_inputs_block(changes,reason):
    r=scenario([fill(**changes)])
    assert reason in r['rows'][0]['reasons'] and r['scenarioTotalWon'] is None

def test_future_evidence_does_not_become_past_knowledge():
    r=calculate(pack(),[fill()],utc('2025-02-01T00:00:00Z'),profile(),Rounding(unitWon=1,mode='DOWN'))
    assert set(r['rows'][0]['reasons'])=={'TAX_EVIDENCE_NOT_YET_KNOWN','FEE_EVIDENCE_NOT_YET_KNOWN'}

@pytest.mark.parametrize('changes,reason',[
    ({'accountAlias':'another'},'FEE_PROFILE_SCOPE_MISMATCH'),
    ({'validFrom':'2025-01-01'},'FEE_PROFILE_PERIOD_UNCONFIRMED'),
    ({'knownAt':'2026-11-08T00:00:00Z'},'FEE_EVIDENCE_NOT_YET_KNOWN')])
def test_fee_scope_period_and_knowledge(changes,reason):
    r=calculate(pack(),[fill()],AT,profile(**changes),Rounding(unitWon=1,mode='DOWN'))
    assert reason in r['rows'][0]['reasons'] and r['scenarioFeeWon'] is None

def test_split_fee_rounding_uses_declared_aggregation_and_never_pools_tax():
    fs=[fill(fillId='a',notionalWon='3334',market='KOSDAQ'),fill(fillId='b',notionalWon='3334',market='KOSDAQ')]
    tax=Rounding(unitWon=1,mode='DOWN')
    daily=calculate(pack(),fs,AT,profile(),tax)
    each=calculate(pack(),fs,AT,profile(aggregation='PER_FILL'),tax)
    assert daily['scenarioFeeWon']=='1' and each['scenarioFeeWon']=='0'
    assert len(daily['feeGroups'])==1 and len(each['feeGroups'])==2
    assert daily['scenarioTaxWon']=='10' # floor(3334*0.0015) twice, not pooled.

def test_different_sides_symbols_days_accounts_are_not_fee_pooled():
    fs=[fill(fillId='a',orderRef='a'),fill(fillId='b',orderRef='b',side='BUY'),fill(fillId='c',orderRef='c',stockCode='000660'),fill(fillId='d',orderRef='a',executedAt='2024-12-28T01:00:00Z')]
    r=scenario(fs);assert len(r['feeGroups'])==4
    bad=scenario([fill(accountAlias='different')]);assert bad['scenarioFeeWon'] is None

def test_per_order_and_daily_aggregation_are_different():
    fs=[fill(fillId='a',orderRef='a'),fill(fillId='b',orderRef='b')]
    assert len(calculate(pack(),fs,AT,profile(aggregation='PER_ORDER'),Rounding(unitWon=1,mode='DOWN'))['feeGroups'])==2
    assert len(scenario(fs)['feeGroups'])==1

@pytest.mark.parametrize('amount,expected',[('9999',10),('10000',27),('10001',27)])
def test_fee_tier_boundaries_and_fixed_component(amount,expected):
    p=profile(bands=[dict(lowerWon=0,upperWon=10000,bps='1',fixedWon=10),dict(lowerWon=10000,upperWon=None,bps='10',fixedWon=17)])
    r=calculate(pack(),[fill(notionalWon=amount)],AT,p,Rounding(unitWon=1,mode='DOWN'))
    assert Decimal(r['scenarioFeeWon'])==expected

@pytest.mark.parametrize('mode,value,unit,expected',[('DOWN','19.99',10,10),('UP','19.01',10,20),('HALF_UP','15',10,20),('DOWN','0.99',1,0),('UP','0.01',1,1)])
def test_decimal_rounding_exact(mode,value,unit,expected):
    assert rounded(Decimal(value),Rounding(unitWon=unit,mode=mode))==expected

def test_component_tax_rounding_not_combined_assumption():
    f=fill(executedAt='2026-01-01T00:00:00Z',settlementDate='2026-01-02',notionalWon='1000')
    assert scenario([f])['scenarioTaxWon']=='1' # explicit scenario: floor(.5)+floor(1.5)

def test_minimum_fee_and_large_integer_precision():
    r=calculate(pack(),[fill(notionalWon='1')],AT,profile(minimumWon=7),Rounding(unitWon=1,mode='DOWN'))
    assert r['scenarioFeeWon']=='7'
    r=scenario([fill(notionalWon='999999999999999999')])
    assert Decimal(r['scenarioFeeWon'])==Decimal('149999999999999')

def test_duplicate_fill_and_conflicting_order_rejected():
    with pytest.raises(ResearchError,match='ID_OR_COUNT'):scenario([fill(),fill()])
    with pytest.raises(ResearchError,match='IDENTITY_CONFLICT'):scenario([fill(),fill(fillId='f2',side='BUY')])

def test_schema_invalid_dates_overlaps_and_products():
    p=pack().model_dump(mode='json');p['taxes'].append(deepcopy(p['taxes'][0]));p['taxes'][-1]['ruleId']='duplicate-period'
    with pytest.raises(ValidationError):CostPack.model_validate(p)
    with pytest.raises(ValidationError):fill(product='ETF')
    with pytest.raises(ValidationError):fill(settlementDate='2024-01-01')
    with pytest.raises(ValidationError):profile(bands=[dict(lowerWon=1,bps='1')])
    with pytest.raises(ValidationError):profile(bands=[dict(lowerWon=0,upperWon=100,bps='1'),dict(lowerWon=101,upperWon=None,bps='1')])

def test_deterministic_results_and_hashed_inputs():
    fs=[fill(fillId='a'),fill(fillId='b')]
    assert canonical(scenario(fs))==canonical(scenario(list(reversed(fs))))
    assert len(scenario(fs)['fillsSha256'])==64

def test_cli_blocked_result_preserved_and_exclusive(tmp_path):
    p=tmp_path/'pack';p.write_bytes(canonical(pack().model_dump(mode='json')))
    fs=tmp_path/'fills';fs.write_bytes(canonical([fill().model_dump(mode='json')]))
    output=tmp_path/'report'
    args=['--pack',str(p),'--fills',str(fs),'--as-of','2026-11-07T00:00:00Z','--output',str(output)]
    assert main(args)==1
    saved=output.read_bytes();assert read_json(saved)['status']=='BLOCKED'
    assert main(args)==2 and output.read_bytes()==saved
