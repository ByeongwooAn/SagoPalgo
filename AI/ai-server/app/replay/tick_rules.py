"""Evidence-bound tick lookup. Unknown periods/products never inherit today's rule."""
import argparse
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .dataset import canonical, digest, read_bytes, read_json
from .models import ResearchError, StrictModel, Timestamp, utc
import re
import html


class Band(StrictModel):
    lower: int = Field(ge=0)
    upper: int | None = Field(default=None,gt=0)
    tick: int = Field(gt=0)


class Rule(StrictModel):
    ruleId: str = Field(min_length=1,max_length=100)
    market: Literal['KOSPI','KOSDAQ']
    product: Literal['COMMON_STOCK']
    validFrom: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    validTo: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    knownAt: Timestamp
    evidenceUrl: str = Field(pattern=r'^https://')
    evidenceSha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    coverageBasis: Literal['DATED_RULE_SNAPSHOT','DATED_OFFICIAL_GUIDANCE','ARCHIVED_BYLAW_INTERVAL']
    bands: list[Band] = Field(min_length=1,max_length=20)

    @model_validator(mode='after')
    def boundaries(self):
        if date.fromisoformat(self.validFrom)>=date.fromisoformat(self.validTo):raise ValueError('empty period')
        if self.bands[0].lower!=0 or self.bands[-1].upper is not None:raise ValueError('incomplete prices')
        for i,b in enumerate(self.bands):
            if b.upper is not None and b.lower>=b.upper:raise ValueError('empty band')
            if i and self.bands[i-1].upper!=b.lower:raise ValueError('price gap/overlap')
        return self


class TickRulePack(StrictModel):
    schemaVersion: Literal['SAGOPALGO_TICK_RULES_V1']
    coverageComplete: Literal[False]
    rules: list[Rule] = Field(min_length=1,max_length=10000)

    @model_validator(mode='after')
    def unique(self):
        if len({r.ruleId for r in self.rules})!=len(self.rules):raise ValueError('duplicate rule')
        for i,r in enumerate(self.rules):
            for p in self.rules[:i]:
                if (p.market,p.product)==(r.market,r.product) and max(p.validFrom,r.validFrom)<min(p.validTo,r.validTo):
                    raise ValueError('ambiguous period')
        return self


def lookup(pack,market,product,trading_date,price,known_at):
    day=date.fromisoformat(trading_date).isoformat()
    if not isinstance(price,str) or len(price)>30:raise ResearchError('TICK_PRICE_INVALID')
    try:p=Decimal(price)
    except Exception:raise ResearchError('TICK_PRICE_INVALID') from None
    if not p.is_finite() or p<=0 or p>Decimal('1000000000000'):raise ResearchError('TICK_PRICE_INVALID')
    candidates=[r for r in pack.rules if r.market==market and r.product==product and r.validFrom<=day<r.validTo]
    if not candidates:raise ResearchError('TICK_RULE_COVERAGE_UNCONFIRMED')
    r=candidates[0]
    if known_at<r.knownAt:raise ResearchError('TICK_RULE_NOT_YET_KNOWN')
    b=next(b for b in r.bands if b.lower<=p and (b.upper is None or p<b.upper))
    return {'ruleId':r.ruleId,'market':market,'product':product,'tradingDate':day,'price':price,
            'tickSize':str(b.tick),'priceAligned':p%Decimal(b.tick)==0,
            'evidenceSha256':r.evidenceSha256,'evidenceUrl':r.evidenceUrl,
            'knownAt':r.knownAt.isoformat(),'coverageBasis':r.coverageBasis,
            'usableForTrading':False,'usableForStrategyValidation':False}


def build_history(folder):
    """Audit all consecutive captured bylaw revisions; merge only identical stock grids."""
    rules=[];sources=[]
    for market,article in [('KOSPI',32),('KOSDAQ',18)]:
        versions=read_json(read_bytes(folder/(market+'-versions.json')))
        revisions=[int(re.search(r'\d+',v['revision']).group()) for v in versions]
        if sorted(revisions)!=list(range(min(revisions),max(revisions)+1)) or len(set(revisions))!=len(revisions):
            raise ResearchError('TICK_REVISION_CHAIN_GAP')
        if min(v['listedDate'] for v in versions)>'2023-11-01':raise ResearchError('TICK_BASELINE_MISSING')
        grids=[];market_sources=[]
        for v in versions:
            raw=read_bytes(folder/v['book']/'body.html');receipt=read_json(read_bytes(folder/v['book']/'receipt.json'))
            if digest(raw)!=receipt['sha256'] or receipt['parameters']!={'bookid':v['book'],'noformyn':'N','oldyn':'Y'}:
                raise ResearchError('TICK_SOURCE_HASH_MISMATCH')
            s=raw.decode('utf-8')
            if f'name="BOOKID" id="BOOKID" value="{v["book"]}"' not in s:raise ResearchError('TICK_SOURCE_IDENTITY_MISMATCH')
            text=html.unescape(re.sub('<[^>]+>',' ',s));text=re.sub(r'\s+','',text)
            section=text.split(f'제{article}조(호가단위)',1)[1].split(f'제{article+1}조(',1)[0]
            values=re.findall(r'가격이([^:]+)종목:([0-9,]+)원',section)[:7]
            expected=['2,000원미만인','2,000원이상5,000원미만인','5,000원이상20,000원미만인','20,000원이상50,000원미만인','50,000원이상200,000원미만인','200,000원이상500,000원미만인','500,000원이상인']
            if [x for x,y in values]!=expected:raise ResearchError('TICK_ARTICLE_LAYOUT_UNSUPPORTED')
            grid=[int(t.replace(',','')) for _,t in values];grids.append(grid)
            market_sources.append({**v,'sha256':digest(raw),'capturedAt':receipt['capturedAt'],'article':article})
        if any(g!=grids[0] for g in grids):raise ResearchError('TICK_CHANGED_GRID_REQUIRES_INTERVAL_REVIEW')
        sources.extend([dict(market=market,**v) for v in market_sources])
        bounds=[0,2000,5000,20000,50000,200000,500000,None]
        rules.append(dict(ruleId='krx-history-'+market,market=market,product='COMMON_STOCK',validFrom='2023-11-01',validTo='2026-11-07',
            knownAt=max(v['capturedAt'] for v in market_sources),evidenceUrl='https://rule.krx.co.kr/out/regulation/regulationViewPop.do',
            evidenceSha256=digest(canonical(market_sources)),coverageBasis='ARCHIVED_BYLAW_INTERVAL',
            bands=[dict(lower=bounds[i],upper=bounds[i+1],tick=t) for i,t in enumerate(grids[0])]))
    pack=TickRulePack.model_validate(dict(schemaVersion='SAGOPALGO_TICK_RULES_V1',coverageComplete=False,rules=rules))
    return pack,{'sources':sources,'sameStockGridAcrossAllRevisions':True,'scopeFrom':'2023-11-01','scopeToExclusive':'2026-11-07'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['pack','market','product','date','price','known-at','output']:parser.add_argument('--'+name,required=True)
    parser.add_argument('--assumed-tick')
    args=parser.parse_args(argv)
    raw=read_bytes(Path(args.pack));pack=TickRulePack.model_validate(read_json(raw))
    result=lookup(pack,args.market,args.product,args.date,args.price,utc(args.known_at))
    result['packSha256']=digest(raw)
    if args.assumed_tick is not None:result['assumptionMatches']=Decimal(args.assumed_tick)==Decimal(result['tickSize'])
    with Path(args.output).open('xb') as f:f.write(canonical(result)+b'\n')
    return 0


if __name__=='__main__':raise SystemExit(main())
