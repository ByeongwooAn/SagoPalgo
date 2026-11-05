"""Confirm relisting/destination entry dates, retaining unresolved delisting conflicts."""
from collections import Counter
import re

from . import remaining_membership_disclosures as capture, listing_disclosure_facts as listings
from . import delisting_disclosure_facts as exits, delisting_revision_facts as announcements
from .dataset import digest
from .kind_cases import compact, iso_date, one_row, scalar_date
from .models import ResearchError, utc


def relisting(raw,url,t,known,viewer_name,context):
    capture.engine.public.validate_url(url); form=url.rsplit('/',1)[-1].removesuffix('.htm')
    root=capture.engine.public.html(raw);text=root.text()
    if '정정신고' in compact(text) or '정정공시' in compact(text): raise ResearchError('RELISTING_CORRECTION_REVIEW')
    if (t['kind'],t['category'],t['statusEventType'])!=('ADDED_OBSERVED','RELISTING','재상장'):
        raise ResearchError('RELISTING_DIRECTION_OR_CLASSIFICATION_CONFLICT')
    excluded=[]
    if form=='70779' and t['market']=='KOSDAQ':
        titles=[v.text() for v in root.walk('a') if v.attrs.get('name')=='#2']
        titles += [v.text() for v in root.walk('div') if v.attrs.get('class')=='xforms_title']
        if titles!=['재상장']: raise ResearchError('RELISTING_TITLE_REVIEW')
        rows=exits.main_rows(raw);company=one_row(rows,'1.회사명')
        coded=[r for r in rows if 'A'+t['symbol'] in r]
        if (len(company)!=4 or company[1:3]!=['정식명','한글'] or not company[3]
                or len(coded)!=1 or len(coded[0])!=4 or coded[0][:3]!=['보통주',t['isin'],'A'+t['symbol']]
                or not re.fullmatch(r'[0-9,]+',coded[0][3]) or int(coded[0][3].replace(',',''))<=0):
            raise ResearchError('RELISTING_KOSDAQ_IDENTITY_REVIEW')
        issuer=company[3];source_name=None;stamp=scalar_date(rows,'10.상장일(매매개시일)');label=None
    elif form=='68156' and t['market']=='KOSPI':
        header=re.match(r'^◎\s*(.+?)\s*주권\s*재상장\s*내역\s*(.*)$',text)
        if not header: raise ResearchError('RELISTING_KOSPI_HEADER_REVIEW')
        issuer,tail=header.groups()
        simple=re.fullmatch(r'-\s*(재상장\s*-\s*인적분할)\s*-\s*(①.*)',tail)
        sections=re.fullmatch(r'\((재상장\s*-\s*인적분할)\)\s*\(1\)\s*보통주권\s*(①.*?)\s*\(2\)\s*종류주권\(3우선주\)\s*(①.*)',tail)
        if simple:label,text=simple.groups()
        elif sections:
            label,text,preferred=sections.groups()
            if len(re.findall(r'\([0-9]+\)\s*(?:보통주권|종류주권)',tail))!=2:
                raise ResearchError('RELISTING_KOSPI_SECTION_REVIEW')
            other_ids=re.findall(r'④\s*표준코드\s*:\s*([A-Z]{2}[A-Z0-9]{10})\s*\(단축코드\s*:\s*A([A-Z0-9]{6})\)',preferred)
            if (len(other_ids)!=1 or other_ids[0][0]==t['isin'] or other_ids[0][1]==t['symbol']
                    or not re.search(r'⑤\s*주식의\s*종류와\s*수\s*:\s*기명식\s*우선주\s+[0-9,]+주',preferred)):
                raise ResearchError('RELISTING_KOSPI_PREFERRED_SECTION_REVIEW')
            excluded=[{'shareClass':'종류주권(3우선주)','isin':other_ids[0][0],'stockCode':other_ids[0][1],
                       'sourceTextSha256':digest(preferred.encode('utf8')),'usedForCommonShareFact':False}]
        else: raise ResearchError('RELISTING_KOSPI_SECTION_REVIEW')
        names=re.findall(r'①\s*상장종목명\s*-\s*한글종목명\s*:\s*(.+?)\s*-\s*영문종목명\s*:',text)
        dates=re.findall(r'②\s*상장일\s*:\s*([0-9]{4})년\s*([0-9]{1,2})월\s*([0-9]{1,2})일\s*③',text)
        ids=re.findall(r'④\s*표준코드\s*:\s*([A-Z]{2}[A-Z0-9]{10})\s*\(단축코드\s*:\s*A([A-Z0-9]{6})\)',text)
        shares=re.findall(r'⑤\s*주식의\s*종류와\s*수\s*:\s*(?:-\s*)?(?:기명식\s*)?보통주\s+[0-9,]+주',text)
        if len(names)!=1 or len(dates)!=1 or len(ids)!=1 or len(shares)!=1 or ids[0]!=(t['isin'],t['symbol']):
            raise ResearchError('RELISTING_KOSPI_IDENTITY_OR_LAYOUT_REVIEW')
        source_name=names[0];stamp='%04d-%02d-%02d'%tuple(map(int,dates[0]));iso_date(stamp)
    else: raise ResearchError('RELISTING_FORM_OR_MARKET_REVIEW')
    if not t['observedFrom']<stamp<=t['observedTo'] or stamp!=t['statusDate']: raise ResearchError('RELISTING_DATE_CONFLICT')
    return {'observationId':t['observationId'],'kind':'MEMBERSHIP_ENTRY','stockCode':t['symbol'],'historyIsin':t['isin'],
        'sourceIsin':t['isin'],'isinProvided':True,'market':t['market'],'issuerName':issuer,'sourceListingName':source_name,
        'viewerIssuerName':viewer_name,'date':stamp,'dateBasis':'EXCHANGE_RELISTING_DATE','form':form,'sourceShareClass':'보통주',
        'marketBasis':'REVIEWED_MARKET_SPECIFIC_RELISTING_FORM','identityBasis':'VIEWER_AND_SOURCE_FULL_STOCK_CODE_AND_ISIN',
        'sourceRestructuringLabel':label,'excludedShareSections':excluded,'instrumentContext':context,'sourceUrl':url,'sourceSha256':digest(raw),'knownAt':known,
        'knowledgeBasis':'FETCH_TIME_ONLY','reviewedCorrection':False,'legalMergerCompletionConfirmed':False,
        'legalDemergerCompletionConfirmed':False,'firstEverIpoConfirmed':False,'exchangeRatio':None}


def parse_fact(raw,url,t,known,name,context,corrected=False):
    if t['category']=='RELISTING':
        if corrected: raise ResearchError('RELISTING_CORRECTION_REVIEW')
        return relisting(raw,url,t,known,name,context)
    if t['category']=='DELISTING_REVIEW':return exits.parse_fact(raw,url,t,known,name,context,corrected)
    if t['category']!='INBOUND_TRANSFER' or not url.endswith('/70760.htm') or t['market']!='KOSDAQ':
        raise ResearchError('DESTINATION_LISTING_FORM_OR_CLASSIFICATION_REVIEW')
    f=listings.parse_fact(raw,url,t,known,name,context,corrected)
    return {**f,'destinationEntryOnlyConfirmed':True,'sourceMarketHistoryConfirmed':False,'sourceMarket':None,
        'completeTransferPairConfirmed':False,'sourceAnnouncementType':'신규상장','statusClassification':'이전상장'}


def build(folder,contexts):
    plan,journal,latest=capture.load(folder);facts,reviews=[],[]
    if set(contexts)!={t['observationId'] for t in plan['targets']}: raise ResearchError('REMAINING_FACT_CONTEXT_SCOPE_CONFLICT')
    for t in plan['targets']:
        identity=t['observationId'];context=contexts[identity]
        times=[context['knownAt']]+[e.get('finishedAt',e.get('capturedAt',e['startedAt'])) for e in journal['attempts'] if e['targetId']==identity]
        known=max(times,key=utc);_,_,completed,state=capture.inspect(folder,t,latest);versions=[]
        try:
            if state!='BODIES_CAPTURED':raise ResearchError(state)
            for i,c in enumerate(capture.candidates(completed['SEARCH'],t)):
                label='V'+str(i);v=capture.viewer(completed[label+'_VIEWER'],t,c);entry=latest[(identity,label+'_BODY')]
                root=capture.engine.public.html(completed[label+'_VIEWER'])
                active=[o.attrs.get('value','').split('|')[0] for s in root.walk('select') if s.attrs.get('id')=='mainDoc'
                        for o in s.walk('option') if re.fullmatch(r'[0-9]{14}\|Y',o.attrs.get('value',''))]
                if len(active)!=1: raise ResearchError('REMAINING_ACTIVE_VERSION_REVIEW')
                version={**c,**v,'activeDocument':active[0],'sourceUrl':entry['request']['url'],'sourceSha256':entry['sha256'],
                    'acquisitionHashes':{s:latest[(identity,s)]['sha256'] for s in ['SEARCH',label+'_VIEWER',label+'_PATH',label+'_BODY']}}
                try:
                    f=parse_fact(completed[label+'_BODY'],entry['request']['url'],t,known,v['viewerIssuerName'],context,c['corrected'])
                    if f['date']!=t['statusDate']:raise ResearchError('REMAINING_FACT_STATUS_DATE_CONFLICT')
                    version['fact']=f
                except (ValueError,KeyError,TypeError,IndexError) as exc:
                    version['diagnostic']=str(exc) if isinstance(exc,ResearchError) else 'REMAINING_FACT_INPUT_REVIEW'
                    if t['category']=='DELISTING_REVIEW':
                        version['announcement']=announcements.announcement(completed[label+'_BODY'],entry['request']['url'],t,known,context,c['corrected'])
                versions.append(version)
            if not versions or any('fact' not in v for v in versions):
                diagnostics={v['diagnostic'] for v in versions if 'diagnostic' in v}
                raise ResearchError(next(iter(diagnostics)) if len(diagnostics)==1 else 'REMAINING_CANDIDATES_REVIEW')
            docs={v['document'] for v in versions}
            if (len(docs)!=len(versions) or any(set(v['documents'])!=docs or v['activeDocument']!=versions[-1]['document'] for v in versions)
                    or versions[0]['corrected'] or any(not v['corrected'] for v in versions[1:])):
                raise ResearchError('REMAINING_VERSION_LINEAGE_REVIEW')
            keys=['stockCode','historyIsin','sourceIsin','market','date','dateBasis','form','sourceShareClass']
            if any(any(v['fact'][k]!=versions[0]['fact'][k] for k in keys) for v in versions):raise ResearchError('REMAINING_CORRECTION_CONFLICT')
            facts.append({**versions[-1]['fact'],'knownAt':known,'versions':versions,'category':t['category'],
                'statusDate':t['statusDate'],'statusEventType':t['statusEventType'],'statusReferenceId':t['statusReferenceId'],
                'allLegalEffectsConfirmed':False})
        except (ValueError,KeyError,TypeError,IndexError) as exc:
            reviews.append({'observationId':identity,'symbol':t['symbol'],'category':t['category'],'statusDate':t['statusDate'],
                'knownAt':known,'candidateVersions':versions,'diagnostic':str(exc) if isinstance(exc,ResearchError) else 'REMAINING_FACT_INPUT_REVIEW'})
    return {'schemaVersion':'SAGOPALGO_REMAINING_MEMBERSHIP_FACTS_V1','planId':plan['planId'],'parentSha256':plan['parentSha256'],
        'inventorySha256':plan['inventorySha256'],'sourceKind':plan['sourceKind'],'targets':len(plan['targets']),'facts':facts,'reviews':reviews,
        'verified':len(facts),'reviewRequired':len(reviews),'verifiedByCategory':dict(Counter(f['category'] for f in facts)),
        'formCounts':dict(Counter(f['form'] for f in facts)),'marketUniverseComplete':False,'usableForTraining':False,'usableForTrading':False}
