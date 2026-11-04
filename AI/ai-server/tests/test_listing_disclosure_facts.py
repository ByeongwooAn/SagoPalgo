"""Membership evidence is exact-code, date-bound and conservative about correction versions."""
import json

import pytest

from app.replay import listing_disclosure_coverage as capture, listing_disclosure_facts as facts
from app.replay.models import ResearchError
from test_listing_disclosure_coverage import planned
from test_kind_membership_evidence import Client
from test_membership_evidence_facts import body, target, AT

LATER = '2026-11-05T00:00:00Z'


def context():
    return {'symbol':'000010','isin':'KR0000100001','securityType':'주권','shareType':'보통주','knownAt':AT}


class FactClient(Client):
    def __init__(self, stamp='2024-01-03', code='000010'):
        super().__init__(); self.stamp=stamp; self.code=code
    def fetch(self, spec):
        raw=super().fetch(spec)
        return body(stamp=self.stamp, code=self.code) if '/external/' in spec['url'] else raw


def collected(tmp_path, monkeypatch, client=None):
    job, p, inv=planned(tmp_path)
    monkeypatch.setattr(capture.engine,'now',lambda:AT)
    capture.collect(job, client or FactClient(), 8, sleep=lambda _:None)
    plan,_,_=capture.load(job); identity=plan['targets'][0]['observationId']
    c=context(); c['knownAt']=LATER
    return job,p,inv,{identity:c}


def test_fact_retains_direct_identity_status_reference_and_later_context(tmp_path,monkeypatch):
    job,_,_,ctx=collected(tmp_path,monkeypatch)
    r=facts.build(job,ctx); f=r['facts'][0]
    assert r['verified']==1 and r['reviewRequired']==0
    assert f['date']==f['statusDate']=='2024-01-03' and f['knownAt']==LATER
    assert f['statusReferenceId'] and len(f['versions'][0]['acquisitionHashes'])==4
    assert f['firstEverIpoConfirmed'] is False and not f['legalMergerCompletionConfirmed']


@pytest.mark.parametrize('variant',['code','date','source_missing'])
def test_review_preserves_sources_and_known_time(tmp_path,monkeypatch,variant):
    client=FactClient(code='999999') if variant=='code' else FactClient(stamp='2024-01-04') if variant=='date' else Client(search_raw=b'<html>unreviewed</html>')
    job,_,_,ctx=collected(tmp_path,monkeypatch,client)
    r=facts.build(job,ctx)
    assert r['verified']==0 and r['reviewRequired']==1 and r['reviews'][0]['knownAt']==LATER


@pytest.mark.parametrize('variant',['modern','old','dash','spaces','colon_after_share','no_colon_header'])
def test_reviewed_kospi_layout_variants_keep_same_exact_identity(variant):
    raw=body('68152')
    if variant=='modern': raw=raw.replace('신규상장 상장내역 ◎ ① 상장종목'.encode(),'신규상장 내역 ① 상장종목명'.encode())
    if variant=='dash': raw=raw.replace('수 : 보통주'.encode(),'수 : - 보통주'.encode())
    if variant=='spaces': raw=raw.replace(b'2024',b'2024').replace('단축코드 :A'.encode(),'단축코드 : A'.encode()).replace('상장일 : 2024'.encode(),'상장일 :2024'.encode())
    if variant=='colon_after_share': raw=raw.replace('수 : 보통주 100주'.encode(),'수 - 보통주 : 100주'.encode())
    if variant=='no_colon_header': raw=raw.replace('수 : 보통주 100주'.encode(),'수 - 보통주 100주'.encode())
    f=facts.parse_fact(raw,'https://kind.krx.co.kr/external/2024/01/01/000001/20240101000002/68152.htm',target('68152'),AT,'가상회사',context())
    assert f['sourceIsin']=='KR0000100001' and f['stockCode']=='000010' and f['date']=='2024-01-03'
    assert not f['firstEverIpoConfirmed']


@pytest.mark.parametrize('variant',['code','isin','share','date','correction','duplicate_date'])
def test_kospi_flexible_spacing_does_not_relax_identity_or_dates(variant):
    raw=body('68152')
    if variant=='code': raw=raw.replace(b'A000010',b'A999999')
    if variant=='isin': raw=raw.replace(b'KR0000100001',b'KR9999999999')
    if variant=='share': raw=raw.replace('보통주 100주'.encode(),'우선주 100주'.encode())
    if variant=='date': raw=raw.replace('2024년 01월 03일'.encode(),'2024년 01월 04일'.encode())
    if variant=='correction': raw=raw.replace(b'</body>', '정정공시</body>'.encode())
    if variant=='duplicate_date': raw=raw.replace(b'</body>','② 상장일 : 2024년 01월 03일 ③</body>'.encode())
    with pytest.raises(ResearchError): facts.parse_fact(raw,'https://kind.krx.co.kr/external/2024/01/01/000001/20240101000002/68152.htm',target('68152'),AT,'가상회사',context())


def test_extra_viewer_version_is_not_approved_even_if_original_body_matches(tmp_path,monkeypatch):
    job,_,_,ctx=collected(tmp_path,monkeypatch)
    from app.replay.dataset import digest,read_json,read_bytes
    from app.replay.krx_storage import atomic_json
    p=job/'raw/0002.bin'; raw=p.read_bytes().replace(b'</select>', '<option value="20240202000001|Y">[정정]신규상장 (2024.02.02)</option></select>'.encode()); p.write_bytes(raw)
    j=read_json(read_bytes(job/'journal.json')); j['attempts'][1]['sha256']=digest(raw); atomic_json(job/'journal.json',j)
    # The original version label in this fixture has no dated title, so even selecting it is refused.
    with pytest.raises(ResearchError): facts.build(job,ctx)


def test_reviewed_reit_note_keeps_common_share_isin_and_listing_date_checks():
    raw=body('68152').replace('가상회사 주권'.encode(),'가상회사 부동산투자회사 주권'.encode())
    raw=raw.replace('상장내역 ◎ ①'.encode(),'상장내역 ◎ (동 주권은 부동산투자회사법에 의한 부동산투자회사 주권임) ①'.encode())
    f=facts.parse_fact(raw,'https://kind.krx.co.kr/external/2024/01/01/000001/20240101000002/68152.htm',target('68152'),AT,'가상회사',context())
    assert f['reitNoticePresent'] and f['sourceShareClass']=='보통주' and f['sourceIsin']=='KR0000100001'


class CorrectionClient:
    source_kind='SYNTHETIC'
    def __init__(self,changed=False): self.calls=0; self.changed=changed
    def fetch(self,spec):
        self.calls+=1
        if 'details.do' in spec['url']:
            return ('''<a href="#viewer" onclick="openDisclsViewer('20240102000001','')">신규상장</a>'''
                    '''<a href="#viewer" onclick="openDisclsViewer('20240102000003','')">[정정]신규상장</a>'''
                    '<div class="info type-00">전체 2건 : 1 /1</div>').encode()
        if 'acptno=' in spec['url']:
            return ('<h1>가상회사 (000010)</h1><select id="mainDoc">'
                    '<option value="20240102000002|Y">신규상장 (2024.01.02)</option>'
                    '<option value="20240102000004|Y">[정정]신규상장 (2024.01.02)</option></select>').encode()
        if spec['method']=='POST':
            doc=spec['parameters']['docNo']
            return f"parent.setPath('','https://kind.krx.co.kr/external/2024/01/02/000001/{doc}/70760.htm','/external/x','03','13');".encode()
        corrected='20240102000004' in spec['url']
        return body(correction=corrected,stamp='2024-01-04' if corrected and self.changed else '2024-01-03')


@pytest.mark.parametrize('changed',[False,True])
def test_correction_original_and_latest_must_agree_on_identity_and_date(tmp_path,monkeypatch,changed):
    job,_,_,ctx=collected(tmp_path,monkeypatch,CorrectionClient(changed))
    r=facts.build(job,ctx)
    if changed:
        assert r['verified']==0 and r['reviews'][0]['diagnostic']=='LISTING_FACT_CORRECTION_CONFLICT'
    else:
        assert r['verified']==1 and len(r['facts'][0]['versions'])==2
        assert r['facts'][0]['otherCorrectionContentInterpreted'] is False


@pytest.mark.parametrize('wrong_zero_identity',[False,True])
def test_original_zero_duplicate_requires_identical_validated_correction_row(tmp_path,monkeypatch,wrong_zero_identity):
    class DuplicateClient(CorrectionClient):
        def fetch(self,spec):
            raw=super().fetch(spec)
            if '/20240102000002/' in spec['url']:
                marker='<tr><td>보통주</td><td>KR0000100001</td><td>A000010</td><td>100</td></tr>'.encode()
                zero=marker.replace(b'>100<',b'>0<')
                if wrong_zero_identity: zero=zero.replace(b'KR0000100001',b'KR9999999999')
                raw=raw.replace(marker,zero+marker)
            return raw
    job,_,_,ctx=collected(tmp_path,monkeypatch,DuplicateClient())
    r=facts.build(job,ctx)
    if wrong_zero_identity: assert r['verified']==0
    else:
        assert r['verified']==1 and r['facts'][0]['versions'][0]['fact']['zeroDuplicateCommonShareRowReviewed']
        assert r['facts'][0]['versions'][0]['sourceSha256']==r['facts'][0]['versions'][0]['fact']['sourceSha256']
