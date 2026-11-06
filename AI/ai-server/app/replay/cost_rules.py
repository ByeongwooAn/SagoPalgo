"""Offline, evidence-bound post-trade cost ledger. No broker/profile auto-discovery."""
import argparse
from collections import defaultdict
from datetime import date, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_UP, ROUND_HALF_UP, localcontext
from pathlib import Path
from typing import Literal
import json
import sys

from pydantic import Field, model_validator, ValidationError

from .dataset import canonical, digest, read_bytes, read_json
from .models import StrictModel, Timestamp, Number, Identifier, ResearchError, utc


def day(value):
    parsed=date.fromisoformat(value)
    if parsed.isoformat()!=value:raise ValueError('ISO date required')
    return parsed


class TaxRule(StrictModel):
    ruleId: Identifier
    market: Literal['KOSPI','KOSDAQ']
    product: Literal['COMMON_STOCK']
    exchange: Literal['KRX']
    validFrom: str
    validTo: str
    knownAt: Timestamp
    basis: Literal['SETTLEMENT_DATE']
    securitiesTaxBps: Number
    ruralTaxBps: Number
    evidenceUrl: str = Field(pattern=r'^https://')
    evidenceSha256: str = Field(pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def valid(self):
        if day(self.validFrom)>=day(self.validTo):raise ValueError('empty tax period')
        if Decimal(self.securitiesTaxBps)+Decimal(self.ruralTaxBps)>10000:raise ValueError('tax exceeds notional')
        return self


class CostPack(StrictModel):
    schemaVersion: Literal['SAGOPALGO_COST_RULES_V1']
    accountFeeStatus: Literal['UNCONFIRMED']
    taxCollectionStatus: Literal['UNCONFIRMED']
    taxes: list[TaxRule] = Field(min_length=1,max_length=1000)

    @model_validator(mode='after')
    def unique(self):
        if len({r.ruleId for r in self.taxes})!=len(self.taxes):raise ValueError('duplicate tax rule')
        for i,r in enumerate(self.taxes):
            for p in self.taxes[:i]:
                if (r.market,r.product,r.exchange)==(p.market,p.product,p.exchange) and max(r.validFrom,p.validFrom)<min(r.validTo,p.validTo):
                    raise ValueError('overlapping tax periods')
        return self


class Fill(StrictModel):
    fillId: Identifier
    orderRef: Identifier
    accountAlias: Identifier
    stockCode: str = Field(pattern=r'^\d{6}$')
    market: Literal['KOSPI','KOSDAQ']
    exchange: Literal['KRX']
    product: Literal['COMMON_STOCK']
    channel: Literal['KB_OPENAPI']
    funding: Literal['CASH']
    taxTreatment: Literal['ORDINARY_TAXABLE']
    side: Literal['BUY','SELL']
    executedAt: Timestamp
    settlementDate: str
    settlementConfirmed: bool
    notionalWon: str = Field(pattern=r'^[1-9][0-9]{0,17}$')

    @model_validator(mode='after')
    def valid(self):
        if day(self.settlementDate)<self.executedAt.astimezone(timezone(timedelta(hours=9))).date():
            raise ValueError('settlement before execution')
        return self


class FeeBand(StrictModel):
    lowerWon: int = Field(ge=0)
    upperWon: int | None = Field(default=None,gt=0)
    bps: Number
    fixedWon: int = Field(default=0,ge=0,le=100000000)


class Rounding(StrictModel):
    unitWon: Literal[1,10]
    mode: Literal['DOWN','UP','HALF_UP']


class FeeProfile(StrictModel):
    schemaVersion: Literal['SAGOPALGO_FEE_PROFILE_V1']
    profileId: Identifier
    accountAlias: Identifier
    channel: Literal['KB_OPENAPI']
    funding: Literal['CASH']
    product: Literal['COMMON_STOCK']
    markets: list[Literal['KOSPI','KOSDAQ']] = Field(min_length=1,max_length=2)
    validFrom: str
    validTo: str
    knownAt: Timestamp
    provenance: Literal['SYNTHETIC','ACCOUNT_DOCUMENT']
    # Declaration with evidence, not an automatic assertion by this program.
    evidenceSha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    aggregation: Literal['PER_FILL','PER_ORDER','DAILY_SYMBOL_SIDE']
    rounding: Rounding
    bands: list[FeeBand] = Field(min_length=1,max_length=20)
    minimumWon: int = Field(default=0,ge=0,le=100000000)

    @model_validator(mode='after')
    def valid(self):
        if day(self.validFrom)>=day(self.validTo) or len(set(self.markets))!=len(self.markets):raise ValueError('invalid profile scope')
        if self.bands[0].lowerWon!=0 or self.bands[-1].upperWon is not None:raise ValueError('incomplete fee tiers')
        for i,b in enumerate(self.bands):
            if Decimal(b.bps)>10000 or (b.upperWon is not None and b.lowerWon>=b.upperWon):raise ValueError('invalid fee tier')
            if i and self.bands[i-1].upperWon!=b.lowerWon:raise ValueError('fee tier gap/overlap')
        return self


def rounded(value,rule):
    mode={'DOWN':ROUND_DOWN,'UP':ROUND_UP,'HALF_UP':ROUND_HALF_UP}[rule.mode]
    return (value/Decimal(rule.unitWon)).to_integral_value(rounding=mode)*rule.unitWon


def calculate(pack,fills,as_of,profile=None,tax_rounding=None):
    """Tax rounding is an explicit scenario until KB collection/actual fills are verified."""
    if not fills or len(fills)>10000 or len({f.fillId for f in fills})!=len(fills):raise ResearchError('COST_FILL_ID_OR_COUNT_INVALID')
    # A caller cannot split one order across instruments/markets/sides to pool fees.
    orders={}
    for f in fills:
        key=(f.accountAlias,f.orderRef,f.executedAt.astimezone(timezone(timedelta(hours=9))).date())
        identity=(f.stockCode,f.market,f.exchange,f.side,f.executedAt.astimezone(timezone(timedelta(hours=9))).date())
        if key in orders and orders[key]!=identity:raise ResearchError('COST_ORDER_IDENTITY_CONFLICT')
        orders[key]=identity
    with localcontext() as c:
        c.prec=80
        return _calculate(pack,fills,as_of,profile,tax_rounding)


def _calculate(pack,fills,as_of,profile,tax_rounding):
    rows=[];groups=defaultdict(list)
    for f in sorted(fills,key=lambda x:(x.executedAt,x.fillId)):
        trade_day=f.executedAt.astimezone(timezone(timedelta(hours=9))).date().isoformat()
        reasons=[];raw_st=None;raw_rural=None;tax=None;rule_id=None
        if f.executedAt>as_of:reasons.append('FILL_NOT_YET_KNOWN')
        if f.side=='BUY':raw_st=raw_rural=Decimal(0);tax=Decimal(0)
        elif not f.settlementConfirmed:reasons.append('SETTLEMENT_DATE_UNCONFIRMED')
        elif day(f.settlementDate)>as_of.astimezone(timezone(timedelta(hours=9))).date():reasons.append('SETTLEMENT_AFTER_ASOF')
        else:
            candidates=[r for r in pack.taxes if r.market==f.market and r.product==f.product and r.exchange==f.exchange and r.validFrom<=f.settlementDate<r.validTo]
            if not candidates:reasons.append('TAX_PERIOD_UNCONFIRMED')
            elif candidates[0].knownAt>as_of:reasons.append('TAX_EVIDENCE_NOT_YET_KNOWN')
            else:
                r=candidates[0];rule_id=r.ruleId
                raw_st=Decimal(f.notionalWon)*Decimal(r.securitiesTaxBps)/10000
                raw_rural=Decimal(f.notionalWon)*Decimal(r.ruralTaxBps)/10000
                if tax_rounding is None:reasons.append('TAX_COLLECTION_RULE_UNCONFIRMED')
                else:tax=rounded(raw_st,tax_rounding)+rounded(raw_rural,tax_rounding)
        p=profile
        if p is None:reasons.append('ACCOUNT_FEE_UNCONFIRMED')
        elif (p.accountAlias!=f.accountAlias or p.channel!=f.channel or p.funding!=f.funding or p.product!=f.product or f.market not in p.markets):
            reasons.append('FEE_PROFILE_SCOPE_MISMATCH')
        elif not p.validFrom<=trade_day<p.validTo:reasons.append('FEE_PROFILE_PERIOD_UNCONFIRMED')
        elif p.knownAt>as_of:reasons.append('FEE_EVIDENCE_NOT_YET_KNOWN')
        else:
            group=(p.profileId,f.accountAlias,trade_day,f.stockCode,f.market,f.exchange,f.side,f.channel,f.funding)
            if p.aggregation=='PER_ORDER':group+=(f.orderRef,)
            elif p.aggregation=='PER_FILL':group+=(f.fillId,)
            groups[group].append(f)
        rows.append(dict(fillId=f.fillId,notionalWon=f.notionalWon,settlementDate=f.settlementDate,taxRuleId=rule_id,
            rawSecuritiesTaxWon=None if raw_st is None else format(raw_st,'f'),rawRuralTaxWon=None if raw_rural is None else format(raw_rural,'f'),
            scenarioTaxWon=None if tax is None else format(tax,'f'),reasons=reasons))
    fees=[]
    for group,members in sorted(groups.items()):
        value=sum(Decimal(f.notionalWon) for f in members);p=profile
        b=next(b for b in p.bands if b.lowerWon<=value and (b.upperWon is None or value<b.upperWon))
        raw=value*Decimal(b.bps)/10000+b.fixedWon
        fees.append(dict(fillIds=[f.fillId for f in members],notionalWon=format(value,'f'),rawFeeWon=format(raw,'f'),
                         scenarioFeeWon=format(max(Decimal(p.minimumWon),rounded(raw,p.rounding)),'f')))
    blocked=any(r['reasons'] for r in rows)
    fee_total=sum(Decimal(g['scenarioFeeWon']) for g in fees) if not any(any(x.startswith(('ACCOUNT_FEE','FEE_')) for x in r['reasons']) for r in rows) else None
    tax_total=sum(Decimal(r['scenarioTaxWon']) for r in rows) if all(r['scenarioTaxWon'] is not None for r in rows) else None
    return dict(schemaVersion='SAGOPALGO_COST_REPORT_V1',status='BLOCKED' if blocked else 'CALCULATED_SCENARIO',
        fillsSha256=digest(canonical([f.model_dump(mode='json') for f in sorted(fills,key=lambda x:(x.executedAt,x.fillId))])),
        packSha256=digest(canonical(pack.model_dump(mode='json'))),profileSha256=digest(canonical(profile.model_dump(mode='json'))) if profile else None,
        asOf=as_of.isoformat(),rows=rows,feeGroups=fees,scenarioFeeWon=None if fee_total is None else format(fee_total,'f'),
        scenarioTaxWon=None if tax_total is None else format(tax_total,'f'),
        scenarioTotalWon=None if blocked or fee_total is None or tax_total is None else format(fee_total+tax_total,'f'),
        taxRoundingScenario=tax_rounding.model_dump() if tax_rounding else None,
        inputBasis='DECLARED_EXECUTION_ROWS',profileProvenance=profile.provenance if profile else None,
        brokerReconciled=False,accountFeeStatus='UNCONFIRMED' if profile is None else 'DECLARED_EVIDENCE_NOT_ATTESTED',
        usableForTrading=False,usableForStrategyValidation=False)


def _main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['pack','fills','as-of','output']:parser.add_argument('--'+key,required=True)
    parser.add_argument('--profile')
    parser.add_argument('--tax-rounding-scenario')
    a=parser.parse_args(argv)
    pack=CostPack.model_validate(read_json(read_bytes(Path(a.pack))))
    fills=[Fill.model_validate(x) for x in read_json(read_bytes(Path(a.fills)))]
    profile=FeeProfile.model_validate(read_json(read_bytes(Path(a.profile)))) if a.profile else None
    rounding=Rounding.model_validate(read_json(read_bytes(Path(a.tax_rounding_scenario)))) if a.tax_rounding_scenario else None
    report=calculate(pack,fills,utc(a.as_of),profile,rounding)
    with Path(a.output).open('xb') as f:f.write(canonical(report)+b'\n')
    return 0 if report['status']=='CALCULATED_SCENARIO' else 1


def main(argv=None):
    try:return _main(argv)
    except ResearchError as error:code=str(error)
    except ValidationError:code='COST_SCHEMA_INVALID'
    except (ValueError,TypeError,KeyError,OverflowError):code='COST_INPUT_INVALID'
    except OSError:code='COST_FILE_OPERATION_FAILED'
    print(json.dumps({'status':'FAILED','code':code}),file=sys.stderr)
    return 2


if __name__=='__main__':raise SystemExit(main())
