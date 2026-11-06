import hashlib
from pathlib import Path
import pytest
import test_quote_execution as book
from app.replay import tick_quality
from app.replay.tick_rules import TickRulePack,build_history
from app.replay.quote_execution import estimate_quotes
from app.replay.dataset import canonical,digest
from app.replay.models import utc,ResearchError
from test_tick_rules import pack

@pytest.fixture(autouse=True)
def pin(monkeypatch):
    raw=book.EVIDENCE
    monkeypatch.setattr(tick_quality,'SESSION_BLOB',hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest())

def rules():
    p=pack()
    for r in p['rules']:r.update(validFrom='2025-11-03',validTo='2025-11-04',knownAt='2025-11-04T00:00:00Z')
    return TickRulePack.model_validate(p)

def test_engine_blocks_future_rule_knowledge_and_explicitly_binds_expost_comparison():
    args=[book.data(),book.cfg(),book.EVIDENCE,book.policy(tickSize='100'),[book.order()]]
    assert estimate_quotes(*args)['outcomes'][0]['reasons']==['PRICE_OFF_ASSUMED_TICK_GRID']
    blocked=estimate_quotes(*args,tick_rules=rules())
    assert blocked['outcomes'][0]['reasons']==['TICK_RULE_NOT_YET_KNOWN']
    result=estimate_quotes(*args,tick_rules=rules(),rules_known_at=utc('2025-11-04T00:00:00Z'))
    assert result['outcomes'][0]['status']=='ESTIMATED_FILLED'
    assert result['tickRuleBinding']['exPostEvidence'] and not result['usableForStrategyValidation']

def test_override_requires_pack():
    with pytest.raises(ResearchError,match='PACK_REQUIRED'):
        estimate_quotes(book.data(),book.cfg(),book.EVIDENCE,book.policy(),[book.order()],rules_known_at=utc('2025-11-04T00:00:00Z'))

def source_fixture(root):
    bands=pack()['rules'][0]['bands'];bounds=['2,000원미만인','2,000원이상5,000원미만인','5,000원이상20,000원미만인','20,000원이상50,000원미만인','50,000원이상200,000원미만인','200,000원이상500,000원미만인','500,000원이상인']
    for market,article in [('KOSPI',32),('KOSDAQ',18)]:
        versions=[]
        for i,day in enumerate(['2023-09-01','2026-09-14']):
            bid=market+str(i);p=root/bid;p.mkdir()
            raw=(f'<input name="BOOKID" id="BOOKID" value="{bid}">제{article}조(호가단위)'+''.join(f'가격이{x}종목:{b["tick"]}원' for x,b in zip(bounds,bands))+f'제{article+1}조(').encode()
            (p/'body.html').write_bytes(raw)
            (p/'receipt.json').write_bytes(canonical(dict(sha256=digest(raw),parameters=dict(bookid=bid,noformyn='N',oldyn='Y'),capturedAt='2026-11-06T00:00:00Z')))
            versions.append(dict(book=bid,revision=f'제{i+1}차',listedDate=day))
        (root/(market+'-versions.json')).write_bytes(canonical(versions))

def test_history_build_requires_equal_complete_revision_chain_and_original_hash(tmp_path):
    source_fixture(tmp_path)
    p,report=build_history(tmp_path)
    assert len(p.rules)==2 and len(report['sources'])==4
    f=tmp_path/'KOSPI0/body.html';f.write_bytes(f.read_bytes()+b'tamper')
    with pytest.raises(ResearchError,match='HASH_MISMATCH'):build_history(tmp_path)
