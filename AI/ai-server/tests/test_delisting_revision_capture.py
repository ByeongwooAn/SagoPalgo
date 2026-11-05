"""Archived document dates come from the full-code viewer; captured parent bodies are immutable seeds."""
import pytest

from app.replay import delisting_disclosure_coverage as primary,delisting_revision_capture as archive
from app.replay.models import ResearchError
from test_delisting_disclosure_coverage import planned
from test_kind_membership_evidence import search
from app.replay.dataset import read_json,read_bytes
from app.replay.krx_storage import atomic_json

DOC_OLD='20240101000002'; DOC_NEW='20240102000002'


def viewer(active=True):
    return ('<h1>가상회사 (000030)</h1><select id="mainDoc">'
        f'<option value="{DOC_OLD}|N">상장폐지 (2024.01.01)</option>'
        f'<option value="{DOC_NEW}|'+('Y' if active else 'N')+'">[정정]상장폐지 (2024.01.02)</option></select>').encode()


class PrimaryClient:
    source_kind='SYNTHETIC'
    def fetch(self,spec):
        if 'details.do' in spec['url']: return search('[정정]상장폐지')
        if 'acptno=' in spec['url']: return viewer()
        if spec['method']=='POST': return f"parent.setPath('','https://kind.krx.co.kr/external/2024/01/02/000001/{DOC_NEW}/70769.htm','/external/x','03','13');".encode()
        return b'<html>current source body</html>'


class ArchiveClient:
    source_kind='SYNTHETIC'
    def __init__(self,fail=False): self.calls=0; self.fail=fail
    def fetch(self,spec):
        self.calls+=1
        if self.fail: raise OSError('private transport detail')
        if spec['method']=='POST': return f"parent.setPath('','https://kind.krx.co.kr/external/2024/01/01/000001/{DOC_OLD}/70769.htm','/external/x','03','13');".encode()
        return b'<html>older source body</html>'


def prepared(tmp_path):
    job,_,_=planned(tmp_path); primary.collect(job,PrimaryClient(),8,sleep=lambda _:None)
    folder=tmp_path/'archive'; archive.prepare(folder,job,4)
    return folder,job


def test_old_document_is_captured_while_current_body_is_reused(tmp_path):
    folder,job=prepared(tmp_path); c=ArchiveClient()
    assert archive.collect(folder,job,c,1,sleep=lambda _:None)['states']=={'PENDING':1,'CAPTURED':1}
    result=archive.collect(folder,job,c,1,sleep=lambda _:None)
    assert result['documents']==2 and result['seededDocuments']==1 and result['states']=={'CAPTURED':2}
    assert archive.collect(folder,job,ArchiveClient(True),4)['attemptsUsed']==c.calls==2


def test_failed_archive_attempt_requires_explicit_retry(tmp_path):
    folder,job=prepared(tmp_path)
    assert archive.collect(folder,job,ArchiveClient(True),4)['attemptsUsed']==1
    assert archive.collect(folder,job,ArchiveClient(True),4)['attemptsUsed']==1
    assert archive.collect(folder,job,ArchiveClient(),4,True,sleep=lambda _:None)['states']=={'CAPTURED':2}
    assert archive.load(folder,job)[1]['attempts'][0]['state']=='FAILED'


@pytest.mark.parametrize('variant',['parent_raw','raw','request','plan','document'])
def test_parent_seed_and_new_files_are_audited_before_network(tmp_path,variant):
    folder,job=prepared(tmp_path); archive.collect(folder,job,ArchiveClient(),2,sleep=lambda _:None)
    if variant=='parent_raw': (job/'raw/0004.bin').write_bytes(b'changed')
    elif variant=='raw': (folder/'raw/0001.bin').write_bytes(b'changed')
    elif variant=='plan':
        p=read_json(read_bytes(folder/'plan.json')); p['targets'][0]['documents'][0]['document']='20240101000003'; atomic_json(folder/'plan.json',p)
    else:
        j=read_json(read_bytes(folder/'journal.json'))
        if variant=='request': j['attempts'][0]['request']['parameters']['docNo']='20240101000003'
        else: j['attempts'][0]['document']=DOC_NEW
        atomic_json(folder/'journal.json',j)
    c=ArchiveClient(True)
    with pytest.raises(ResearchError): archive.collect(folder,job,c,1)
    assert c.calls==0


def test_viewer_requires_unique_active_version_and_exact_code():
    with pytest.raises(ResearchError): archive.viewer_documents(viewer(False),{'symbol':'000030'})
    with pytest.raises(ResearchError): archive.viewer_documents(viewer(),{'symbol':'999999'})


@pytest.mark.parametrize('url',[f'https://kind.krx.co.kr/external/2024/01/02/000001/{DOC_OLD}/70769.htm',
    f'https://kind.krx.co.kr/external/2024/01/01/000001/{DOC_NEW}/70769.htm',f'https://example.com/external/2024/01/01/000001/{DOC_OLD}/70769.htm'])
def test_archive_url_is_bound_to_viewer_document_and_publication_date(url):
    raw=f"parent.setPath('','{url}','/external/x','03','13');".encode()
    with pytest.raises(ResearchError): archive.path_url(raw,{'document':DOC_OLD,'publicationDate':'2024-01-01'})
