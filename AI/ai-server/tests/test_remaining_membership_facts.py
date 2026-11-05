"""Common/preferred sections and destination listings must not imply unverified legal histories."""
import pytest
from app.replay import remaining_membership_facts as facts,remaining_membership_disclosures as capture
from app.replay.models import ResearchError
from test_membership_evidence_facts import body,target,AT
from test_remaining_membership_disclosures import planned,Current


def t(market='KOSPI',code='000010'):
    return {**target('70760'),'symbol':code,'isin':'KR'+code+'0001','market':market,'category':'RELISTING',
            'statusEventType':'재상장','statusDate':'2024-01-03'}


def kospi(mixed=False,code='000010'):
    def section(code,share='보통주'):
        return (f'① 상장종목명 - 한글종목명 : 가상회사{share} - 영문종목명 : Synthetic '
            f'② 상장일 : 2024년 01월 03일 ③ 업종 : 가상 '
            f'④ 표준코드 : KR{code}0001(단축코드 : A{code}) ⑤ 주식의 종류와 수 : 기명식 {share} 100주 ⑥ 액면가 : 100')
    text='◎ 가상회사 주권 재상장 내역 '
    text+=('(재상장-인적분할) (1) 보통주권 '+section(code)+' (2) 종류주권(3우선주) '+section('00001L','우선주')) if mixed else '- 재상장-인적분할 - '+section(code)
    return ('<html><body>'+text+'</body></html>').encode()


def parse(raw,market='KOSPI',form='68156',target_value=None):
    return facts.parse_fact(raw,'https://kind.krx.co.kr/external/2024/01/02/000001/20240102000002/'+form+'.htm',
                            target_value or t(market),AT,'가상회사',{'knownAt':AT})


@pytest.mark.parametrize('mixed',[False,True])
def test_only_common_share_section_confirms_relisting(mixed):
    f=parse(kospi(mixed))
    assert f['sourceIsin']=='KR0000100001' and f['date']=='2024-01-03' and f['dateBasis']=='EXCHANGE_RELISTING_DATE'
    assert not f['legalDemergerCompletionConfirmed'] and not f['legalMergerCompletionConfirmed'] and f['exchangeRatio'] is None
    assert len(f['excludedShareSections'])==int(mixed)
    if mixed:assert not f['excludedShareSections'][0]['usedForCommonShareFact']


@pytest.mark.parametrize('code',['000010','0120G0'])
def test_alphanumeric_full_stock_code_is_preserved_in_relisting_fact(code):
    f=parse(kospi(code=code),target_value=t(code=code))
    assert f['stockCode']==code


@pytest.mark.parametrize('variant',['code','isin','date','market','share','title','category','correction','duplicate','preferred_code','section_label'])
def test_mismatched_identity_dates_classes_or_section_bindings_are_rejected(variant):
    raw=kospi(mixed=variant in {'preferred_code','section_label'});value=t()
    if variant=='code':value['symbol']='999999'
    if variant=='isin':value['isin']='KR9999999999'
    if variant=='date':value['statusDate']='2024-01-04'
    if variant=='market':value['market']='KOSDAQ'
    if variant=='share':raw=raw.replace('기명식 보통주'.encode(),'기명식 우선주'.encode())
    if variant=='title':raw=raw.replace('재상장 내역'.encode(),'신규상장 내역'.encode())
    if variant=='category':value['category']='INBOUND_TRANSFER'
    if variant=='correction':raw=raw.replace(b'</body>','정정공시</body>'.encode())
    if variant=='duplicate':raw=raw.replace(b'</body>',kospi()+b'</body>')
    if variant=='preferred_code':raw=raw.replace(b'A00001L',b'A000010')
    if variant=='section_label':raw=raw.replace('종류주권(3우선주)'.encode(),'보통주권'.encode())
    with pytest.raises(ResearchError):parse(raw,target_value=value)


def test_kosdaq_relisting_validates_table_full_code_isin_and_date():
    raw=body().replace('신규상장'.encode(),'재상장'.encode())
    f=parse(raw,'KOSDAQ','70779')
    assert f['form']=='70779' and f['dateBasis']=='EXCHANGE_RELISTING_DATE'
    with pytest.raises(ResearchError):parse(raw.replace(b'KR0000100001',b'KR9999999999'),'KOSDAQ','70779')


def test_destination_listing_does_not_construct_an_out_of_scope_source_market_history():
    value={**t('KOSDAQ'),'category':'INBOUND_TRANSFER','statusEventType':'이전상장'}
    f=parse(body(),'KOSDAQ','70760',value)
    assert f['destinationEntryOnlyConfirmed'] and not f['completeTransferPairConfirmed']
    assert not f['sourceMarketHistoryConfirmed'] and f['sourceMarket'] is None and not f['firstEverIpoConfirmed']


def test_build_confirms_relisting_but_retains_conflicting_delisting_date(tmp_path):
    job,_,_=planned(tmp_path);capture.collect(job,Current(),16,sleep=lambda _:None)
    plan,_,_=capture.load(job);contexts={v['observationId']:{'knownAt':AT} for v in plan['targets']}
    result=facts.build(job,contexts)
    assert (result['verified'],result['reviewRequired'])==(1,1)
    assert result['reviews'][0]['diagnostic']=='MEMBERSHIP_FACT_DATE_CONFLICT'
    assert result['reviews'][0]['candidateVersions'][0]['announcement']['announcedDelistingDate']=='2023-12-01'
    assert not result['usableForTraining'] and not result['marketUniverseComplete']
