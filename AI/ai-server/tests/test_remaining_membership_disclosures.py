"""Only the exact V6 status rows may be acquired, including alphanumeric stock codes."""
import json
import pytest
from app.replay import remaining_membership_disclosures as capture
from app.replay.dataset import canonical,digest
from app.replay.models import ResearchError
from test_delisting_disclosure_coverage import planned as previous
from test_kind_membership_evidence import search,Client,viewer,path,DOCUMENT


def planned(tmp_path):
    _,parent,inventory=previous(tmp_path);p=json.loads(parent.read_bytes())
    p['schemaVersion']='SAGOPALGO_UNIVERSE_RECONCILIATION_V6';p['rows'][0]['resolution']='DISCLOSURE_MATCH'
    parent.write_bytes(canonical(p));job=tmp_path/'remaining';capture.prepare(job,parent,inventory,16)
    return job,parent,inventory


class Current(Client):
    def fetch(self,spec):
        raw=super().fetch(spec)
        if 'details.do' in spec['url']:
            self.code=spec['parameters']['repIsuSrtCd'][1:]
            return search('재상장' if self.code=='000020' else '상장폐지')
        if 'acptno=' in spec['url']:
            return viewer(self.code,title=('재상장' if self.code=='000020' else '상장폐지')+'(2024.01.02)')
        if spec['method']=='POST':
            form='70779' if self.code=='000020' else '70769'
            return path('https://kind.krx.co.kr/external/2024/01/02/000001/'+DOCUMENT+'/'+form+'.htm')
        if '/external/' in spec['url']:
            if self.code=='000020':
                from test_membership_evidence_facts import body
                return body(code=self.code,isin='KR0000200001').replace('신규상장'.encode(),'재상장'.encode())
            from test_delisting_disclosure_facts import source
            return source(code=self.code,stamp='2023-12-01')
        return raw


def test_plan_retains_exact_unverified_rows_and_extended_search_dates(tmp_path):
    job,_,_=planned(tmp_path);p,_,_=capture.load(job)
    assert [t['category'] for t in p['targets']]==['RELISTING','DELISTING_REVIEW']
    assert all(t['searchThrough']=='2024-01-04' for t in p['targets'])
    assert p['maxRequests']==16 and p['minIntervalSeconds']==1


@pytest.mark.parametrize('variant',['schema','inventory','missing','status','new_listing'])
def test_parent_inventory_and_exact_subset_are_required(tmp_path,variant):
    _,parent,inv=planned(tmp_path);p=json.loads(parent.read_bytes());v=json.loads(inv.read_bytes())
    if variant=='schema':p['schemaVersion']='SAGOPALGO_UNIVERSE_RECONCILIATION_V5'
    if variant=='inventory':p['listingInventorySha256']='a'*64
    if variant=='missing':v['targets']=v['targets'][:-1];p['listingInventorySha256']=digest(canonical(v))
    if variant=='status':p['rows'][1]['evidence'][0]['date']='2024-01-04'
    if variant=='new_listing':p['rows'][0]['resolution']='STATUS_LIST_MATCH'
    parent.write_bytes(canonical(p));inv.write_bytes(canonical(v))
    with pytest.raises(ResearchError):capture.prepare(tmp_path/'invalid',parent,inv,16)


@pytest.mark.parametrize('title',['상장폐지결정','재상장신청','신규상장기업안내','주권상장폐지'])
def test_issuer_decisions_and_unreviewed_titles_are_excluded(title):
    with pytest.raises(ResearchError):capture.candidates(search(title),{'kind':'ADDED_OBSERVED'})


def test_kospi_relisting_and_transfer_newlisting_titles_are_distinct_candidates():
    assert capture.candidates(search('주권재상장'),{'kind':'ADDED_OBSERVED'})[0]['viewerTitle']=='주권재상장'
    assert capture.candidates(search('신규상장(이전상장)'),{'kind':'ADDED_OBSERVED'})[0]['viewerTitle']=='신규상장'


def test_search_is_bounded_and_full_code_is_never_derived_from_provider_key(tmp_path):
    job,_,_=planned(tmp_path);t=capture.load(job)[0]['targets'][0];t['symbol']='0120G0'
    _,spec=next(capture.requests_for(t,{}))
    assert spec['parameters']['repIsuSrtCd']=='A0120G0' and spec['parameters']['toDate']=='2024-01-04'


def test_resume_and_complete_cache_make_no_extra_requests(tmp_path):
    job,_,_=planned(tmp_path);client=Current()
    assert capture.collect(job,client,2,sleep=lambda _:None)['states']=={'PENDING':2}
    assert capture.collect(job,client,8,sleep=lambda _:None)['states']=={'BODIES_CAPTURED':2}
    assert capture.collect(job,Client(fail=1),16)['attemptsUsed']==len(client.calls)==8


def test_failed_request_needs_explicit_retry_and_retains_original_receipt(tmp_path):
    job,_,_=planned(tmp_path)
    assert capture.collect(job,Client(fail=1),1)['attemptsUsed']==1
    assert capture.collect(job,Client(fail=1),0)['attemptsUsed']==1
    assert capture.collect(job,Current(),16,True,sleep=lambda _:None)['states']=={'BODIES_CAPTURED':2}
    assert capture.load(job)[1]['attempts'][0]['state']=='FAILED'


@pytest.mark.parametrize('variant',['raw','request','orphan'])
def test_tampered_cache_is_rejected_before_fetch(tmp_path,variant):
    job,_,_=planned(tmp_path);capture.collect(job,Current(),16,sleep=lambda _:None)
    if variant=='raw':(job/'raw/0001.bin').write_bytes(b'changed')
    else:
        j=json.loads((job/'journal.json').read_bytes())
        if variant=='request':j['attempts'][0]['request']['parameters']['repIsuSrtCd']='A999999'
        else:j['attempts'][0]['stage']='V3_BODY'
        (job/'journal.json').write_bytes(canonical(j))
    client=Client(fail=1)
    with pytest.raises(ResearchError):capture.collect(job,client,1)
    assert not client.calls
