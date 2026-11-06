"""Hash-bound intraday restrictions and conservative, point-in-time replay gates."""
import argparse
from datetime import timedelta, timezone
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import Field, model_validator

from .dataset import canonical, digest, read_bytes, read_json
from .models import Identifier, ResearchError, StrictModel, Timestamp, utc
from .krx_baseline_validation import immutable_json

KST = timezone(timedelta(hours=9))


class Phase(StrictModel):
    phaseId: Identifier
    market: Literal['KOSPI', 'KOSDAQ']
    businessDate: str = Field(pattern=r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
    kind: Literal['HALT', 'REOPENING_AUCTION', 'PROGRAM_BUY_PAUSE', 'PROGRAM_SELL_PAUSE']
    startAt: Timestamp
    endAt: Timestamp
    knownAt: Timestamp
    evidence: list[str] = Field(min_length=1, max_length=10)
    bodySha256s: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode='after')
    def valid(self):
        if (self.startAt >= self.endAt or any(t.astimezone(KST).date().isoformat() != self.businessDate for t in [self.startAt, self.endAt])
                or len(set(self.evidence)) != len(self.evidence) or len(set(self.bodySha256s)) != len(self.bodySha256s)
                or any(not re.fullmatch(r'[a-f0-9]{64}', v) for v in self.bodySha256s)):
            raise ValueError('invalid intraday phase')
        return self


class Day(StrictModel):
    market: Literal['KOSPI', 'KOSDAQ']
    businessDate: str = Field(pattern=r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
    coverage: Literal['PARTIAL', 'COMPLETE']
    knownAt: Timestamp
    openAt: Timestamp | None = None
    closeAt: Timestamp | None = None

    @model_validator(mode='after')
    def valid(self):
        # Validate even dates without a session or phase.
        utc(self.businessDate + 'T00:00:00Z')
        if (self.openAt is None) != (self.closeAt is None):raise ValueError('both session bounds required')
        if self.coverage == 'COMPLETE' and self.openAt is None:raise ValueError('complete day needs session bounds')
        if self.openAt is not None and (self.openAt >= self.closeAt or any(t.astimezone(KST).date().isoformat() != self.businessDate for t in [self.openAt, self.closeAt])):
            raise ValueError('invalid intraday session bounds')
        return self


class Timeline(StrictModel):
    schemaVersion: Literal['SAGOPALGO_INTRADAY_TIMELINE_V1']
    timelineId: str = Field(pattern=r'^[a-f0-9]{64}$')
    sourceDecisionSha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    provenance: Literal['EVIDENCED_PARTIAL', 'SYNTHETIC']
    createdAt: Timestamp
    days: list[Day] = Field(min_length=1, max_length=20000)
    phases: list[Phase] = Field(max_length=100000)
    allIntradayInterruptionsComplete: Literal[False]
    usableForTrading: Literal[False]
    usableForStrategyValidation: Literal[False]

    @model_validator(mode='after')
    def valid(self):
        value=self.model_dump(mode='json');value.pop('timelineId')
        if self.timelineId != digest(canonical(value)):raise ValueError('timeline identity mismatch')
        days={(d.market,d.businessDate):d for d in self.days}
        if len(days)!=len(self.days) or len({p.phaseId for p in self.phases})!=len(self.phases):raise ValueError('duplicate intraday identity')
        if any(d.knownAt>self.createdAt for d in self.days) or any(p.knownAt>self.createdAt for p in self.phases):raise ValueError('future knowledge in timeline')
        if self.provenance=='EVIDENCED_PARTIAL' and any(d.coverage!='PARTIAL' or d.openAt is not None for d in self.days):
            raise ValueError('partial evidence cannot confirm ordinary sessions')
        for p in self.phases:
            d=days.get((p.market,p.businessDate))
            if d is None or d.knownAt<p.knownAt:raise ValueError('phase outside known day coverage')
            if d.openAt is not None and not d.openAt<=p.startAt<p.endAt<=d.closeAt:raise ValueError('phase outside session')
        for key in days:
            market_phases=sorted([p for p in self.phases if (p.market,p.businessDate)==key and p.kind in {'HALT','REOPENING_AUCTION'}],key=lambda p:p.startAt)
            if any(a.endAt>b.startAt for a,b in zip(market_phases,market_phases[1:])):raise ValueError('overlapping market phases')
        return self


def timeline_value(value):
    """Normalize timestamp bytes before calculating the stable artifact identity."""
    value=dict(value)
    value['createdAt']=utc(value['createdAt']).isoformat().replace('+00:00','Z')
    value['days']=[Day.model_validate(d).model_dump(mode='json') for d in value['days']]
    value['phases']=[Phase.model_validate(p).model_dump(mode='json') for p in value['phases']]
    value['timelineId']=digest(canonical(value))
    return Timeline.model_validate(value)


class ReplayIntraday(StrictModel):
    timeline: Timeline
    timelineSha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    market: Literal['KOSPI', 'KOSDAQ']
    orderClass: Literal['ORDINARY', 'PROGRAM']

    @model_validator(mode='after')
    def valid(self):
        if digest(canonical(self.timeline.model_dump(mode='json')))!=self.timelineSha256:raise ValueError('timeline bytes mismatch')
        if not any(d.market==self.market for d in self.timeline.days):raise ValueError('market not evidenced')
        return self


def load_policy(path, expected_sha256, market, order_class):
    raw=read_bytes(path)
    if digest(raw)!=expected_sha256:raise ResearchError('INTRADAY_TIMELINE_HASH_MISMATCH')
    return ReplayIntraday.model_validate({'timeline':read_json(raw),'timelineSha256':expected_sha256,'market':market,'orderClass':order_class})


def gate(policy, at, end, side):
    """No future knowledge is inspected to decide an earlier order or bar attempt.

    Intervals are half open. A boundary at bar.endAt does not taint that bar;
    a known restriction at any other point inside it prevents a bar estimate.
    """
    if side not in {'BUY','SELL'} or end<=at:raise ResearchError('INTRADAY_GATE_INPUT_INVALID')
    date=at.astimezone(KST).date().isoformat()
    days=[d for d in policy.timeline.days if (d.market,d.businessDate)==(policy.market,date) and d.knownAt<=at]
    # A future phase cannot reveal its presence, type or times in this response.
    visible=[p for p in policy.timeline.phases if p.market==policy.market and p.businessDate==date and p.knownAt<=at]
    relevant=[p for p in visible if p.kind in {'HALT','REOPENING_AUCTION'} or policy.orderClass=='PROGRAM' and p.kind=='PROGRAM_'+side+'_PAUSE']
    overlaps=[p for p in relevant if p.startAt<end and at<p.endAt]
    if overlaps:
        priority={'HALT':0,'REOPENING_AUCTION':1,'PROGRAM_BUY_PAUSE':2,'PROGRAM_SELL_PAUSE':2}
        p=min(overlaps,key=lambda p:(priority[p.kind],p.startAt,p.phaseId))
        status={'HALT':'MARKET_HALTED','REOPENING_AUCTION':'REOPENING_AUCTION_UNSUPPORTED',
                'PROGRAM_BUY_PAUSE':'PROGRAM_BUY_PAUSED','PROGRAM_SELL_PAUSE':'PROGRAM_SELL_PAUSED'}[p.kind]
        if not p.startAt<=at<p.endAt:status='INTRADAY_BAR_CROSSES_PHASE_BOUNDARY'
        return {'status':status,'phaseIds':sorted(p.phaseId for p in overlaps)}
    if len(days)!=1 or days[0].coverage!='COMPLETE':return {'status':'INTRADAY_COVERAGE_UNCONFIRMED','phaseIds':[]}
    d=days[0]
    if not d.openAt<=at<end<=d.closeAt:return {'status':'OUTSIDE_INTRADAY_SESSION','phaseIds':[]}
    # Unknown future restrictions cannot make a full-bar interval seem confirmed.
    return None


class EvidenceScope(StrictModel):
    schemaVersion: Literal['SAGOPALGO_INTRADAY_EVIDENCE_SCOPE_V1']
    decisionSha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    createdAt: Timestamp


def program_phase(row, raw, known_at):
    from .market_calendar_evidence import text
    value=text(raw);form=row['url'].rsplit('/',1)[1]
    supported={'99404.htm':('KOSPI','BUY'),'99405.htm':('KOSPI','SELL'),'70711.htm':('KOSDAQ','BUY'),'70710.htm':('KOSDAQ','SELL')}
    if form not in supported or supported[form][0]!=row['market']:raise ResearchError('INTRADAY_PROGRAM_FORM_UNSUPPORTED')
    market,side=supported[form]
    if not re.search(r'향후\s*5분간',value) or not re.search(r'프로그램\s*'+('매수' if side=='BUY' else '매도')+r'호가',value):
        raise ResearchError('INTRADAY_PROGRAM_SCOPE_CONFLICT')
    if market=='KOSPI':
        matches=re.findall(r'2\.\s*발동일시\s*([0-9]{4})년\s*([0-9]{2})월\s*([0-9]{2})일\s*([0-9]{2})시\s*([0-9]{2})분\s*([0-9]{2})초',value)
        if len(matches)!=1:raise ResearchError('INTRADAY_PROGRAM_TIME_AMBIGUOUS')
        y,m,d,h,minute,s=matches[0];stamp=f'{y}-{m}-{d}T{h}:{minute}:{s}+09:00'
    else:
        matches=re.findall(r'1\.\s*일자 및 시각\s*([0-9]{4}-[0-9]{2}-[0-9]{2})\s*([0-9]{2}:[0-9]{2}:[0-9]{2})',value)
        if len(matches)!=1:raise ResearchError('INTRADAY_PROGRAM_TIME_AMBIGUOUS')
        stamp=matches[0][0]+'T'+matches[0][1]+'+09:00'
    start=utc(stamp)
    return {'phaseId':market.lower()+'-program-'+row['document'],'market':market,'businessDate':start.astimezone(KST).date().isoformat(),
        'kind':'PROGRAM_'+side+'_PAUSE','startAt':start.isoformat(),'endAt':(start+timedelta(minutes=5)).isoformat(),
        'knownAt':known_at,'evidence':[row['url']],'bodySha256s':[row['bodySha256']]}


def build_timeline(scope_path, decision_path, decision, category_report, category_inventory, category_job):
    scope=EvidenceScope.model_validate(read_json(read_bytes(scope_path)))
    if digest(read_bytes(decision_path))!=scope.decisionSha256 or canonical(decision)!=read_bytes(decision_path):
        raise ResearchError('INTRADAY_DECISION_HASH_MISMATCH')
    if (decision.get('schemaVersion')!='SAGOPALGO_SESSION_COVERAGE_DECISION_V1'
            or digest(canonical(category_report)) not in decision['reviewReportSha256s']
            or digest(canonical(category_inventory))!=category_report['inventorySha256']):
        raise ResearchError('INTRADAY_SOURCE_BINDING_MISMATCH')
    if scope.createdAt<utc(decision['knownAt']):raise ResearchError('INTRADAY_KNOWLEDGE_BEFORE_SOURCE')
    known=scope.createdAt.isoformat();phases=[]
    events={(e['market'],e['document']):e for e in decision['marketEvents']}
    for p in decision['interruptionPairing']:
        if not decision['startDate']<=p['businessDate']<=decision['endDate']:continue
        if p['status']!='PAIRED':raise ResearchError('INTRADAY_UNPAIRED_INTERRUPTION')
        halt=events[(p['market'],p['haltDocument'])];resume=events[(p['market'],p['resumptionDocument'])]
        common={'market':p['market'],'businessDate':p['businessDate'],'knownAt':known,
            'evidence':[halt['url'],resume['url']],'bodySha256s':[halt['bodySha256'],resume['bodySha256']]}
        phases += [{**common,'phaseId':p['market'].lower()+'-halt-'+p['haltDocument'],'kind':'HALT',
                    'startAt':p['haltAt'],'endAt':p['quoteAcceptanceResumesAt']},
                   {**common,'phaseId':p['market'].lower()+'-auction-'+p['resumptionDocument'],'kind':'REOPENING_AUCTION',
                    'startAt':p['quoteAcceptanceResumesAt'],'endAt':p['continuousTradingResumesAt']}]
    versions={(r['market'],v['document'],v['bodySha256']):(r,v) for r in category_inventory['rows'] for v in r['versions']}
    for row in category_report['reviewedBodies']:
        if row['classification']!='PROGRAM_ORDER_PAUSE':continue
        listed,version=versions[(row['market'],row['document'],row['bodySha256'])];raw=read_bytes(category_job/version['rawFile'])
        if digest(raw)!=row['bodySha256']:raise ResearchError('INTRADAY_BODY_HASH_MISMATCH')
        phase=program_phase(row,raw,known)
        if listed['issuer'] or phase['businessDate']!=listed['reportedAtKstText'][:10]:
            raise ResearchError('INTRADAY_PROGRAM_LIST_DATE_OR_SCOPE_CONFLICT')
        if decision['startDate']<=phase['businessDate']<=decision['endDate']:phases.append(phase)
    phases.sort(key=lambda p:(p['market'],p['businessDate'],p['startAt'],p['phaseId']))
    keys=sorted({(p['market'],p['businessDate']) for p in phases})
    return timeline_value({'schemaVersion':'SAGOPALGO_INTRADAY_TIMELINE_V1','sourceDecisionSha256':scope.decisionSha256,
        'provenance':'EVIDENCED_PARTIAL','createdAt':known,'days':[{'market':m,'businessDate':d,'coverage':'PARTIAL','knownAt':known} for m,d in keys],
        'phases':phases,'allIntradayInterruptionsComplete':False,'usableForTrading':False,'usableForStrategyValidation':False})


def main():
    from . import session_coverage_review as coverage
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['build','audit'])
    for name in ['scope','decision','parent','rules','boundary-job','boundary-inventory','boundary-review','category-job','category-inventory','category-review','output']:
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    try:
        boundary=coverage.build_review(a.boundary_job,a.parent,a.rules,a.boundary_inventory,a.boundary_review)
        category=coverage.build_review(a.category_job,a.parent,a.rules,a.category_inventory,a.category_review)
        decision=coverage.combine_reports([boundary,category],read_json(read_bytes(a.rules)));immutable_json(a.decision,decision,True)
        timeline=build_timeline(a.scope,a.decision,decision,category,read_json(read_bytes(a.category_inventory)),a.category_job)
        immutable_json(a.output,timeline.model_dump(mode='json'),a.command=='audit')
        print(json.dumps({'status':'PARTIAL_RESTRICTIONS_ONLY','days':len(timeline.days),'phases':len(timeline.phases),
                          'timelineId':timeline.timelineId,'sha256':digest(read_bytes(a.output))}));return 0
    except (ValueError,KeyError,TypeError,OSError) as ex:
        print(json.dumps({'error':str(ex) if isinstance(ex,ResearchError) else 'INTRADAY_INPUT_INVALID'}));return 2


if __name__=='__main__':raise SystemExit(main())
