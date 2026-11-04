"""Explicit Korean/English fields, trading aliases, date roles and conservative identity bridges."""
from copy import deepcopy

import pytest

from app.replay import name_alias_facts as facts
from app.replay.models import ResearchError

AT = '2026-11-04T12:00:00Z'
LATER = '2026-11-04T13:00:00Z'


def target_context():
    t = {'symbol': '000010', 'isin': 'KR0000100001', 'beforeMarket': 'KOSDAQ', 'afterMarket': 'KOSDAQ',
         'beforeName': '가상구명', 'afterName': '가상신명', 'observedFrom': '2024-01-02', 'observedTo': '2024-01-03'}
    c = {s: {'symbol': t['symbol'], 'isin': t['isin'], 'market': 'KOSDAQ', 'name': t[s + 'Name'],
          'abbreviatedName': '구약명' if s == 'before' else '가상신명', 'englishName': 'OLD GLOBAL' if s == 'before' else 'NEW GLOBAL',
          'shareType': '보통주', 'securityType': '주권', 'date': t['observedFrom' if s == 'before' else 'observedTo'], 'knownAt': AT}
         for s in ['before', 'after']}
    return t, c


def alias_body(before='구약명', after='가상신명', stamp='2024-01-03', issuer='(주)가상구명'):
    return (f'<html><a name="#2">기타시장안내(약명 및 영문명)</a><table><tr><td>1.종목명</td><td>{issuer}</td></tr>'
      '<tr><td>2.변경내역</td></tr><tr><td>주권종류</td><td>변경대상</td><td>변경전</td><td>변경후</td></tr>'
      f'<tr><td>보통주</td><td>한글약명</td><td>{before}</td><td>{after}</td></tr><tr><td>3.상장일</td><td>{stamp}</td></tr></table></html>').encode()


def issuer_body():
    rows = [['1. 변경내용', '가. 변경전', '국문', '주식회사 가상구명컴퍼니'], ['영문', 'OLD GLOBAL Inc.'],
            ['나. 변경후', '국문', '주식회사 가상신명'], ['영문', 'NEW GLOBAL Inc.'], ['3. 주주총회일', '2024-01-02']]
    return ('<html><div class="xforms_title">상호변경안내</div><table>' + ''.join('<tr>' + ''.join('<td>'+v+'</td>' for v in r) + '</tr>' for r in rows) + '</table></html>').encode()


def parent_row():
    return {'nameReview': {'candidateVersions': [{'parsed': {'form': '70765', 'beforeName': '(주)가상구명컴퍼니', 'afterName': '(주)가상신명',
             'date': '2024-01-03'}, 'sourceSha256': 'a'*64, 'sourceUrl': 'https://kind.krx.co.kr/external/2024/01/02/000001/20240102000002/70765.htm'}]}}


def test_trading_alias_uses_both_krx_abbreviations_and_separate_full_name_basis():
    t, c = target_context(); parsed = facts.parse_alias(alias_body())
    f = facts.alias_fact(parsed, t, c)
    assert f['nameMatchBasis'] == {'before': 'DECLARED_ISSUER_FORMAL_NAME', 'after': 'DECLARED_KOREAN_ALIAS'}
    assert f['dateBasis'] == 'EXCHANGE_TRADING_ALIAS_LISTING_DATE'
    assert not f['corporateNameChangeConfirmed'] and f['corporateLegalEffectiveDate'] is None


@pytest.mark.parametrize('variant', ['before_alias', 'after_alias', 'full_name', 'issuer', 'date', 'isin', 'code', 'market', 'class', 'date_context'])
def test_wrong_alias_identity_or_date_is_never_approved(variant):
    t, c = target_context(); p = facts.parse_alias(alias_body())
    if variant == 'before_alias': p['beforeAlias'] = '임의추정'
    if variant == 'after_alias': p['afterAlias'] = '임의추정'
    if variant == 'full_name': c['before']['name'] = t['beforeName'] = '다른정식명'
    if variant == 'issuer': p['issuerName'] = '다른회사'
    if variant == 'date': p['date'] = t['observedFrom']
    if variant == 'isin': c['before']['isin'] = 'KR9999999999'
    if variant == 'code': c['after']['symbol'] = '999999'
    if variant == 'market': c['before']['market'] = 'KOSPI'
    if variant == 'class': c['before']['shareType'] = '우선주'
    if variant == 'date_context': c['after']['date'] = '2024-01-04'
    with pytest.raises(ResearchError): facts.alias_fact(p, t, c)


def test_bilingual_bridge_uses_existing_listing_date_and_keeps_meeting_date_separate():
    t, c = target_context(); p = facts.parse_issuer(issuer_body())
    f = facts.bridge_fact(p, t, c, parent_row())
    assert f['date'] == '2024-01-03' and f['shareholderMeetingDate'] == '2024-01-02'
    assert f['corporateLegalEffectiveDate'] is None and not f['shareholderMeetingDateIsListingDate']
    assert facts.english_key(' KBIO  Company Inc. ') == facts.english_key('KBIO COMPANY')
    assert facts.english_key('KBIO INCORPORATED') != facts.english_key('KBIO')
    with pytest.raises(ResearchError): facts.english_key('케이바이오')


@pytest.mark.parametrize('variant', ['english_before', 'english_after', 'formal_after', 'old_listing_name', 'duplicate_listing', 'listing_date', 'meeting_date'])
def test_bridge_requires_both_english_fields_and_unique_existing_name_date(variant):
    t, c = target_context(); p = facts.parse_issuer(issuer_body()); row = parent_row()
    if variant == 'english_before': c['before']['englishName'] = 'DIFFERENT'
    if variant == 'english_after': p['afterEnglish'] = 'DIFFERENT'
    if variant == 'formal_after': p['afterKorean'] = '다른회사'
    if variant == 'old_listing_name': row['nameReview']['candidateVersions'][0]['parsed']['beforeName'] = '다른이름'
    if variant == 'duplicate_listing': row['nameReview']['candidateVersions'] *= 2
    if variant == 'listing_date': row['nameReview']['candidateVersions'][0]['parsed']['date'] = '2024-01-01'
    if variant == 'meeting_date': p['shareholderMeetingDate'] = '2024-01-04'
    with pytest.raises(ResearchError): facts.bridge_fact(p, t, c, row)


@pytest.mark.parametrize('variant', ['title', 'correction', 'duplicate_alias', 'preferred', 'missing_date', 'duplicate_issuer'])
def test_unreviewed_or_ambiguous_form_is_rejected(variant):
    raw = alias_body()
    if variant == 'title': raw = raw.replace('기타시장안내'.encode(), '다른제목'.encode())
    if variant == 'correction': raw = raw.replace(b'</html>', '<div>정정신고</div></html>'.encode())
    if variant == 'duplicate_alias': raw = raw.replace(b'</table>', '<tr><td>보통주</td><td>한글약명</td><td>구약명</td><td>가상신명</td></tr></table>'.encode())
    if variant == 'preferred': raw = raw.replace('보통주'.encode(), '우선주'.encode())
    if variant == 'missing_date': raw = raw.replace('3.상장일'.encode(), '다른날짜'.encode())
    if variant == 'duplicate_issuer': raw = raw.replace(b'</table>', '<tr><td>1.종목명</td><td>다른회사</td></tr></table>'.encode())
    with pytest.raises(ResearchError): facts.parse_alias(raw)
