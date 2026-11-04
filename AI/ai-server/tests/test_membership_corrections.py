"""Both public versions are cached and linked before a correction can confirm a date."""
import pytest

from app.replay import kind_membership_evidence as acquisition,membership_corrections as review,membership_evidence_facts as facts
from app.replay.dataset import canonical,digest,read_bytes,read_json
from app.replay.history import atomic_json
from app.replay.models import ResearchError
from test_universe_reconciliation import observation,issue
from test_membership_evidence_facts import body

ORIG="20240102000001"; CORR="20240103000001"
DOC_A="20240102000002"; DOC_B="20240103000002"


def setup(tmp_path):
    obs=observation(after=issue(market="KOSDAQ"))
    parent={"schemaVersion":"SAGOPALGO_UNIVERSE_RECONCILIATION_V1","sourceKind":"SYNTHETIC",
            "startDate":"2024-01-02","endDate":"2024-01-04","rows":[
                {"observationId":digest(canonical(obs)),"observation":obs,"resolution":"STATUS_IDENTITY_REVIEW"}]}
    path=tmp_path/'parent.json'; path.write_bytes(canonical(parent))
    source=tmp_path/'source'; acquisition.prepare(source,path,8)
    class SearchClient:
        source_kind='SYNTHETIC'
        def fetch(self,spec):
            return (f'''<a href="#viewer" onclick="openDisclsViewer('{ORIG}','')">신규상장</a>
              <a href="#viewer" onclick="openDisclsViewer('{CORR}','')">[정정] 신규상장</a>
              <div class="info type-00">전체 2건 : 1 /1</div>''').encode()
    acquisition.collect(source,SearchClient(),1)
    folder=tmp_path/'corrections'; review.prepare(folder,source)
    return source,folder


class Client:
    source_kind='SYNTHETIC'
    def __init__(self,fail=False): self.calls=[]; self.fail=fail
    def fetch(self,spec):
        self.calls.append(spec)
        if self.fail: raise OSError('private details')
        if spec['method']=='GET' and '/external/' not in spec['url']:
            return (f'''<h1>가상회사 (000010)</h1><select id="mainDoc">
              <option value="{DOC_A}|Y">신규상장 (2024.01.02)</option>
              <option value="{DOC_B}|Y">[정정] 신규상장 (2024.01.03)</option></select>''').encode()
        if spec['method']=='POST':
            doc=spec['parameters']['docNo']; stamp='2024/01/02' if doc==DOC_A else '2024/01/03'
            url=f'https://kind.krx.co.kr/external/{stamp}/000001/{doc}/70760.htm'
            return f"parent.setPath('','{url}','/external/x','03','13');".encode()
        corrected=DOC_B in spec['url']
        return body(correction=corrected,industry='new' if corrected else 'old',header_date='2024-01-02')


def test_review_reuses_all_original_corrected_steps_and_confirms_only_unchanged_membership(tmp_path):
    source,folder=setup(tmp_path); client=Client()
    assert review.collect(folder,source,client,1)['requests']==1
    assert review.collect(folder,source,client,6,sleep=lambda _:None)['requests']==6
    result=review.apply(folder,source,facts.build(source),{})
    assert result['verified']==1 and result['reviewRequired']==0 and result['correctionHeaderDateIssues']==0
    assert result['facts'][0]['reviewedCorrection'] and len(result['facts'][0]['acquisitionHashes'])==6
    assert result['correctionReviews'][0]['viewerLinkedVersions']
    before=len(client.calls)
    review.collect(folder,source,client,6)
    assert len(client.calls)==before==6


def test_failed_correction_capture_is_retained_without_automatic_retry(tmp_path):
    source,folder=setup(tmp_path)
    assert review.collect(folder,source,Client(fail=True),6)['states']=={'000010':'FAILED'}
    client=Client(); review.collect(folder,source,client,6)
    assert not client.calls
    result=review.apply(folder,source,facts.build(source),{})
    assert result['verified']==0 and result['reviewRequired']==1


@pytest.mark.parametrize('part',['raw','request','parent'])
def test_correction_lineage_and_raw_tampering_block_further_calls(tmp_path,part):
    source,folder=setup(tmp_path); review.collect(folder,source,Client(),1)
    if part=='raw': (folder/'raw/001.bin').write_bytes(b'mutated')
    elif part=='request':
        value=read_json(read_bytes(folder/'journal.json')); value['attempts'][0]['request']['url']='https://example.com'
        atomic_json(folder/'journal.json',value)
    else:
        value=read_json(read_bytes(folder/'plan.json')); value['targets'][0]['originalReceipt']='20240101000001'
        value['planId']=digest(canonical({k:v for k,v in value.items() if k!='planId'})); atomic_json(folder/'plan.json',value)
    client=Client()
    with pytest.raises(ResearchError): review.collect(folder,source,client,6)
    assert not client.calls


def test_viewer_rejects_wrong_full_code_and_ambiguous_version_labels():
    t={'symbol':'000010'}
    with pytest.raises(ResearchError): review.viewer_document(b'<h1>other (000020)</h1>',t,ORIG)
    raw=f'<h1>test (000010)</h1><select id="mainDoc"><option value="{DOC_A}|Y">신규상장 (2024.01.02)</option><option value="{DOC_B}|Y">신규상장 (2024.01.02)</option></select>'.encode()
    with pytest.raises(ResearchError,match='AMBIGUOUS'): review.viewer_document(raw,t,ORIG)


def test_additional_unreviewed_version_is_not_silently_ignored(tmp_path):
    source,folder=setup(tmp_path)
    class MoreVersions(Client):
        def fetch(self,spec):
            raw=super().fetch(spec)
            if b'</select>' in raw:
                raw=raw.replace(b'</select>','<option value="20240104000002|Y">신규상장 (2024.01.04)</option></select>'.encode())
            return raw
    review.collect(folder,source,MoreVersions(),6,sleep=lambda _:None)
    result=review.apply(folder,source,facts.build(source),{})
    assert result['verified']==0 and result['reviews'][0]['diagnostic']=='MEMBERSHIP_CORRECTION_UNREVIEWED_VERSION_PRESENT'
