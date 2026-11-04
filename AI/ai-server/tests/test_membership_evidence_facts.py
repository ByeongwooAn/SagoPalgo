"""Reviewed full-code forms, KDR instrument context and legal-date boundaries."""
from copy import deepcopy

import pytest

from app.replay import membership_evidence_facts as facts
from app.replay.models import ResearchError

AT="2026-11-04T10:00:00Z"


def target(form="70760"):
    market,kind= facts.FORMS[form][:2] if form in facts.FORMS else ("KOSPI","ADDED_OBSERVED")
    return {"observationId":"a"*64,"kind":kind,"market":market,"symbol":"000010","isin":"KR0000100001",
            "observedFrom":"2024-01-02","observedTo":"2024-01-03","originalReceipt":"20240101000001","correctionReceipt":"20240102000001"}


def body(form="70760",stamp="2024-01-03",code="000010",isin="KR0000100001",share="보통주",industry="old",correction=False,header_date="2024-01-01"):
    if form=="68152":
        return (f'<html><body>◎ 가상회사 주권 신규상장 상장내역 ◎ ① 상장종목 - 한글종목명 : 가상회사보통주 - 영문종목명 : Synthetic '
                f'② 상장일 : {stamp[:4]}년 {stamp[5:7]}월 {stamp[8:]}일 ③ 업종 : 가상 '
                f'④ 표준코드 : {isin} (단축코드 :A{code}) ⑤ 주식의 종류와 수 : 보통주 100주</body></html>').encode()
    market,_,title,date_field,rule=facts.FORMS[form]
    company=["1.회사명","정식명","한글","가상회사"] if form=="70760" else ["1.회사명","가상회사"]
    rows=[company,[share,isin,"A"+code,"100"]]
    if form=="70718": rows.append(["3.사유","SPAC소멸합병상장"])
    if rule: rows.append([rule,"유가증권시장상장규정" if market=="KOSPI" else "코스닥시장상장규정"])
    rows += [["8.업종",industry],[date_field,stamp]]
    def table(values): return '<table>'+''.join('<tr>'+''.join('<td>'+v+'</td>' for v in r)+'</tr>' for r in values)+'</table>'
    prefix=''
    if correction:
        prefix='<a name="#2">정 정 신 고 (보고)</a>'+table([
            ['1. 정정관련 공시서류 :','신규상장'],['2. 정정관련 공시서류 제출일 :',header_date],
            ['3. 정정사유 :','업종 정정'],['4. 정정사항 :','업종']])+table([['항목','정정전','정정후'],['업종','old','new']])
    return ('<html><body>'+prefix+'<a name="#2">'+title+'</a>'+table(rows)+'</body></html>').encode()


def parse(raw,form="70760",**kwargs):
    t=target(form)
    url='https://kind.krx.co.kr/external/2024/01/01/000001/20240101000002/'+form+'.htm'
    return facts.parse_fact(raw,url,t,AT,"가상회사",**kwargs)


@pytest.mark.parametrize("form",[*facts.FORMS,"68152"])
def test_reviewed_forms_confirm_membership_date_without_asserting_first_ipo_or_merger(form):
    result=parse(body(form),form)
    assert result['stockCode']=='000010' and result['date']=='2024-01-03'
    assert result['knownAt']==AT and not result['legalMergerCompletionConfirmed'] and not result['firstEverIpoConfirmed']
    assert result['exchangeRatio'] is None


@pytest.mark.parametrize("change",["code","isin","date","share","market","direction","title"])
def test_mismatching_identity_scope_or_share_class_is_rejected(change):
    raw=body()
    t=target()
    if change=='code': raw=body(code='000020')
    if change=='isin': raw=body(isin='KR0000200001')
    if change=='date': raw=body(stamp='2024-01-04')
    if change=='share': raw=body(share='우선주')
    if change=='market': t['market']='KOSPI'
    if change=='direction': t['kind']='REMOVED_OBSERVED'
    if change=='title': raw=raw.replace('신규상장'.encode(),'다른양식'.encode())
    with pytest.raises(ResearchError): facts.parse_fact(raw,'https://kind.krx.co.kr/external/2024/01/01/000001/20240101000002/70760.htm',t,AT,'가상회사')


def test_kdr_requires_verified_historical_depositary_security_and_ordinary_share_context():
    raw=body(share='KDR')
    with pytest.raises(ResearchError,match='KDR_CONTEXT'): parse(raw)
    context={'symbol':'000010','isin':'KR0000100001','securityType':'주식예탁증권','shareType':'보통주'}
    assert parse(raw,instrument_context=context)['sourceShareClass']=='KDR'
    context['securityType']='주권'
    with pytest.raises(ResearchError,match='KDR_CONTEXT'): parse(raw,instrument_context=context)


def test_later_instrument_context_delays_kdr_fact_availability():
    context={'symbol':'000010','isin':'KR0000100001','securityType':'주식예탁증권','shareType':'보통주',
             'knownAt':'2026-11-05T00:00:00Z'}
    assert parse(body(share='KDR'),instrument_context=context)['knownAt']==context['knownAt']


def test_unreviewed_correction_cannot_be_silently_read_as_an_original():
    raw=body(correction=True,industry='new')
    with pytest.raises(ResearchError): parse(raw)
    assert parse(raw,reviewed_correction=True)['reviewedCorrection']


def test_header_date_issue_is_preserved_while_membership_fields_remain_equal():
    from app.replay.membership_corrections import review_industry_correction
    before=body(); after=body(correction=True,industry='new',header_date='2024-01-02')
    result=review_industry_correction(before,after,parse(before),parse(after,reviewed_correction=True),target())
    assert result['headerDateDiffersFromOriginalReceipt'] and not result['headerRelatedDateMatchesOriginalReceipt']
    assert result['membershipDateOnlyConfirmed'] and result['changedMainFields']==['8.업종']


def test_correction_of_membership_fields_or_unreviewed_business_fields_is_rejected():
    from app.replay.membership_corrections import review_industry_correction
    before=body(); after=body(correction=True,industry='new')
    a,b=parse(before),parse(after,reviewed_correction=True)
    b['date']='2024-01-04'
    with pytest.raises(ResearchError,match='MEMBERSHIP_FIELDS_CHANGED'): review_industry_correction(before,after,a,b,target())
    b=parse(after,reviewed_correction=True)
    after=after.replace(b'<td>100</td>',b'<td>200</td>')
    with pytest.raises(ResearchError,match='NONMEMBERSHIP_REVIEW'): review_industry_correction(before,after,a,b,target())


def test_plain_kospi_text_requires_matching_isin_and_ordinary_class():
    with pytest.raises(ResearchError,match='IDENTITY'): parse(body('68152',isin='KR0000200001'),'68152')
    with pytest.raises(ResearchError,match='IDENTITY'): parse(body('68152').replace('보통주 100주'.encode(),'우선주 100주'.encode()),'68152')
