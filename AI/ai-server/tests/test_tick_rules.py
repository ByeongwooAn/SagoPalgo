from copy import deepcopy
import pytest
from pydantic import ValidationError
from app.replay.tick_rules import TickRulePack,lookup
from app.replay.models import ResearchError,utc

def pack():
    bounds=[0,2000,5000,20000,50000,200000,500000,None];ticks=[1,5,10,50,100,500,1000]
    return dict(schemaVersion='SAGOPALGO_TICK_RULES_V1',coverageComplete=False,rules=[dict(
        ruleId='synthetic-'+market,market=market,product='COMMON_STOCK',validFrom='2026-10-15',validTo='2026-10-16',
        knownAt='2026-11-06T00:00:00Z',evidenceUrl='https://synthetic.test/rule',evidenceSha256='a'*64,
        coverageBasis='DATED_OFFICIAL_GUIDANCE',bands=[dict(lower=bounds[i],upper=bounds[i+1],tick=t) for i,t in enumerate(ticks)]) for market in ['KOSPI','KOSDAQ']])

@pytest.mark.parametrize('market',['KOSPI','KOSDAQ'])
@pytest.mark.parametrize('price,tick',[(1999,1),(2000,5),(4999,5),(5000,10),(19999,10),(20000,50),(49999,50),(50000,100),(199999,100),(200000,500),(499999,500),(500000,1000)])
def test_each_boundary_uses_new_band(market,price,tick):
    r=lookup(TickRulePack.model_validate(pack()),market,'COMMON_STOCK','2026-10-15',str(price),utc('2026-11-06T00:00:00Z'))
    assert r['tickSize']==str(tick) and r['priceAligned']==(price%tick==0)

@pytest.mark.parametrize('day',['2026-10-14','2026-10-16','2023-11-01'])
def test_dates_outside_proven_interval_are_not_extrapolated(day):
    with pytest.raises(ResearchError,match='COVERAGE_UNCONFIRMED'):lookup(TickRulePack.model_validate(pack()),'KOSPI','COMMON_STOCK',day,'100',utc('2026-11-06T00:00:00Z'))

def test_unknown_product_and_future_evidence_are_blocked():
    p=TickRulePack.model_validate(pack())
    with pytest.raises(ResearchError,match='COVERAGE_UNCONFIRMED'):lookup(p,'KOSPI','ETF','2026-10-15','100',utc('2026-11-06T00:00:00Z'))
    with pytest.raises(ResearchError,match='NOT_YET_KNOWN'):lookup(p,'KOSPI','COMMON_STOCK','2026-10-15','100',utc('2026-11-05T00:00:00Z'))

@pytest.mark.parametrize('price',['NaN','Infinity','0','-1','invalid'])
def test_invalid_price(price):
    with pytest.raises(ResearchError):lookup(TickRulePack.model_validate(pack()),'KOSPI','COMMON_STOCK','2026-10-15',price,utc('2026-11-06T00:00:00Z'))

def test_ambiguous_period_and_price_gap_rejected():
    p=pack();p['rules'].append(deepcopy(p['rules'][0]));p['rules'][-1]['ruleId']='another'
    with pytest.raises(ValidationError):TickRulePack.model_validate(p)
    p=pack();p['rules'][0]['bands'][1]['lower']=2001
    with pytest.raises(ValidationError):TickRulePack.model_validate(p)
