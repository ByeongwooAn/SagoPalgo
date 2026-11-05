"""Exchange delisting dates and explicitly declared liquidation periods have separate roles."""
from collections import Counter
import re

from . import delisting_disclosure_coverage as capture, membership_evidence_facts as parser
from .dataset import digest
from .distribution_facts import Node
from .kind_cases import compact,one_row,iso_date
from .models import ResearchError,utc


def main_rows(raw):
    root=capture.engine.public.html(raw); tables=[]
    for table in root.walk('table'):
        rows=[[v.text() for v in tr.children if isinstance(v,Node) and v.tag in {'td','th'}] for tr in table.walk('tr')]
        if rows and rows[0] and compact(rows[0][0])=='1.회사명':
            if list(table.walk('table')): raise ResearchError('DELISTING_FACT_NESTED_TABLE_REVIEW')
            tables.append(rows)
    if len(tables)!=1: raise ResearchError('DELISTING_FACT_TABLE_REVIEW')
    return tables[0]


def declared_period(rows,form,delisting_date):
    label='6.정리매매기간' if form=='70769' else '5.정리매매허용기간'
    indices=[i for i,r in enumerate(rows) if r and compact(r[0])==label]
    if not indices:
        return {'status':'FIELD_NOT_PROVIDED','start':None,'end':None,'rawRows':[], 'actualTradingConfirmed':False}
    if len(indices)!=1: raise ResearchError('DELISTING_LIQUIDATION_PERIOD_AMBIGUOUS')
    i=indices[0]; first=rows[i]; last=rows[i+1] if i+1<len(rows) else []
    if (len(first) not in {3,4} or first[1]!='시작일' or len(first)==4 and first[3]!='-' and not re.fullmatch(r'[0-9]+매매일',first[3])
            or len(last)!=2 or last[0] not in {'만료일','종료일'}):
        raise ResearchError('DELISTING_LIQUIDATION_LAYOUT_REVIEW')
    start=None if first[2] in {'-','해당없음','없음','미실시'} else iso_date(first[2])
    end=None if last[1] in {'-','해당없음','없음','미실시'} else iso_date(last[1])
    if (start is None)!=(end is None): raise ResearchError('DELISTING_LIQUIDATION_PARTIAL_DATES')
    if start is not None and (start>end or delisting_date is not None and end>=delisting_date):
        raise ResearchError('DELISTING_LIQUIDATION_DATE_CONFLICT')
    return {'status':'DECLARED_DATES' if start is not None else 'DATES_NOT_PROVIDED', 'start':start,'end':end,
            'rawRows':[first,last],'declaredTradingSessions':first[3] if len(first)==4 and first[3]!='-' else None,
            'actualTradingConfirmed':False}


def parse_fact(raw,url,t,known,viewer_name,context,corrected=False):
    form=url.rsplit('/',1)[1].removesuffix('.htm')
    if form not in {'70769','68051'}: raise ResearchError('DELISTING_FACT_FORM_REVIEW_REQUIRED')
    fact=parser.parse_fact(raw,url,t,known,viewer_name,context,corrected)
    rows=main_rows(raw)
    label='5.상장폐지사유' if form=='70769' else '3.상장폐지사유'
    reason=one_row(rows,label)
    if len(reason)!=2 or not reason[1]: raise ResearchError('DELISTING_FACT_REASON_REVIEW')
    return {**fact,'sourceDelistingReason':reason[1], 'liquidationTradingPeriod':declared_period(rows,form,fact['date']),
        'reasonTextMatchesStatus':compact(reason[1])==compact(t['statusEventType']), 'reasonSemanticsConfirmed':False,
        'mergerReasonStated':'합병' in reason[1], 'legalMergerCompletionConfirmed':False,'exchangeRatio':None,
        'delistingDateIsLiquidationEnd':False}


def build(folder,contexts):
    from .delisting_revision_capture import viewer_documents
    plan,journal,latest=capture.load(folder)
    if set(contexts)!={t['observationId'] for t in plan['targets']}: raise ResearchError('DELISTING_FACT_CONTEXT_SCOPE_MISMATCH')
    facts,reviews=[],[]
    for t in plan['targets']:
        identity=t['observationId']; context=contexts[identity]
        times=[context['knownAt']]+[e.get('finishedAt',e.get('capturedAt',e['startedAt'])) for e in journal['attempts'] if e['targetId']==identity]
        known=max(times,key=utc); _,_,completed,state=capture.inspect(folder,t,latest); versions=[]
        try:
            if state!='BODIES_CAPTURED': raise ResearchError(state)
            for index,candidate in enumerate(capture.candidates(completed['SEARCH'])):
                label='V'+str(index); v=capture.viewer(completed[label+'_VIEWER'],t,candidate)
                entry=latest[(identity,label+'_BODY')]
                documents=viewer_documents(completed[label+'_VIEWER'],t)
                version={**candidate,**v,'activeDocument':next(d['document'] for d in documents if d['active']),
                    'sourceUrl':entry['request']['url'],'sourceSha256':entry['sha256'],
                    'acquisitionHashes':{s:latest[(identity,s)]['sha256'] for s in ['SEARCH',label+'_VIEWER',label+'_PATH',label+'_BODY']}}
                try:
                    p=parse_fact(completed[label+'_BODY'],entry['request']['url'],t,known,v['viewerIssuerName'],context,candidate['corrected'])
                    if p['date']!=t['statusDate']: raise ResearchError('DELISTING_FACT_STATUS_DATE_CONFLICT')
                    version['fact']=p
                except (ValueError,KeyError,TypeError) as exc:
                    version['diagnostic']=str(exc) if isinstance(exc,ResearchError) else 'DELISTING_FACT_FORM_INPUT_REVIEW'
                versions.append(version)
            valid=[v for v in versions if 'fact' in v]
            if not valid:
                diagnostics={v['diagnostic'] for v in versions}
                raise ResearchError(next(iter(diagnostics)) if len(diagnostics)==1 else 'DELISTING_FACT_CANDIDATE_REVIEW')
            histories={tuple(sorted(v['documents'])) for v in valid}
            if len(histories)!=1: raise ResearchError('DELISTING_FACT_MULTIPLE_VALID_DISCLOSURES')
            docs=set(next(iter(histories))); chain=[v for v in versions if v['document'] in docs]
            if (set(v['document'] for v in chain)!=docs or len(chain)!=len(docs)
                    or any(set(v['documents'])!=docs for v in chain) or len([v for v in chain if not v['corrected']])!=1
                    or chain[0]['corrected'] or any(not v['corrected'] for v in chain[1:])):
                raise ResearchError('DELISTING_FACT_VERSION_LINEAGE_REVIEW')
            if any('fact' not in v for v in chain): raise ResearchError('DELISTING_FACT_CORRECTION_CONFLICT')
            if any(v['activeDocument']!=chain[-1]['document'] for v in chain):
                raise ResearchError('DELISTING_FACT_ACTIVE_DOCUMENT_CONFLICT')
            fields=['stockCode','historyIsin','sourceIsin','market','date','dateBasis','form','sourceShareClass']
            if any(any(v['fact'][k]!=chain[0]['fact'][k] for k in fields) for v in chain):
                raise ResearchError('DELISTING_FACT_CORRECTION_IDENTITY_OR_DATE_CONFLICT')
            chosen=chain[-1]['fact']
            facts.append({**chosen,'knownAt':known,'statusReferenceId':t['statusReferenceId'],'statusDate':t['statusDate'],
                'statusEventType':t['statusEventType'],'versions':chain,'otherCandidateReceipts':[v['receipt'] for v in versions if v not in chain],
                'liquidationPeriodChangedByCorrection':any(v['fact']['liquidationTradingPeriod']!=chain[0]['fact']['liquidationTradingPeriod'] for v in chain),
                'correctionPolicy':'FULL_CODE_ISIN_MARKET_SHARE_CLASS_AND_DELISTING_DATE_EQUAL_OTHER_FIELDS_RETAINED',
                'otherCorrectionContentInterpreted':False if len(chain)>1 else None})
        except (ValueError,KeyError,TypeError) as exc:
            reviews.append({'observationId':identity,'symbol':t['symbol'],'market':t['market'],'statusDate':t['statusDate'],
                'knownAt':known,'candidateVersions':versions,'diagnostic':str(exc) if isinstance(exc,ResearchError) else 'DELISTING_FACT_INPUT_REVIEW'})
    return {'schemaVersion':'SAGOPALGO_DELISTING_FACTS_V1','planId':plan['planId'],'parentSha256':plan['parentSha256'],
        'inventorySha256':plan['inventorySha256'],'sourceKind':plan['sourceKind'],'targets':len(plan['targets']),'facts':facts,'reviews':reviews,
        'verified':len(facts),'reviewRequired':len(reviews),'formCounts':dict(Counter(f['form'] for f in facts)),
        'liquidationPeriodCounts':dict(Counter(f['liquidationTradingPeriod']['status'] for f in facts)),
        'allLegalEffectsConfirmed':False,'usableForTraining':False,'usableForTrading':False}
