"""Synthetic discovery chains exercise strict scope, cache replay and bounded recovery."""
import json

import pytest

from app.replay import kind_membership_evidence as evidence
from app.replay.dataset import canonical,digest,read_bytes,read_json
from app.replay.history import atomic_json
from app.replay.models import ResearchError
from test_universe_reconciliation import observation

RECEIPT="20240102000001"
DOCUMENT="20240102000002"
URL="https://kind.krx.co.kr/external/2024/01/02/000001/"+DOCUMENT+"/70760.htm"


def search(title="신규상장",count=1,pages=1):
    link=f'''<a href="#viewer" onclick="openDisclsViewer('{RECEIPT}','')">{title}</a>'''
    return (link+f'<div class="info type-00">전체 {count}건 : 1 /{pages}</div>').encode()


def viewer(code="000010",documents=1,title="신규상장"):
    options="".join(f"<option value='{int(DOCUMENT)+i}|Y'>{title}</option>" for i in range(documents))
    return f'<h1>가상회사 ({code})</h1><select id="mainDoc">{options}</select>'.encode()


def path(url=URL):
    return f"parent.setPath('','{url}','/external/x','03','13');".encode()


class Client:
    source_kind="SYNTHETIC"
    def __init__(self,fail=None,search_raw=None): self.calls=[]; self.fail=fail; self.search_raw=search_raw
    def fetch(self,spec):
        self.calls.append(spec)
        if len(self.calls)==self.fail: raise OSError("private details")
        if "details.do" in spec["url"]: return self.search_raw if self.search_raw is not None else search()
        if spec["method"]=="GET" and "/external/" not in spec["url"]: return viewer()
        if spec["method"]=="POST": return path()
        return b"<html>synthetic body retained for later strict parser</html>"


def planned(tmp_path):
    parent={"schemaVersion":"SAGOPALGO_UNIVERSE_RECONCILIATION_V1","sourceKind":"SYNTHETIC",
            "startDate":"2024-01-02","endDate":"2024-01-04","rows":[
                {"observationId":digest(canonical(observation())),"observation":observation(),"resolution":"NO_STATUS_EVIDENCE"}]}
    p=tmp_path/"parent.json"; p.write_bytes(canonical(parent))
    folder=tmp_path/"evidence"
    evidence.prepare(folder,p,8)
    return folder


def test_discovery_is_resumable_and_complete_cache_never_refetches(tmp_path):
    folder=planned(tmp_path); client=Client()
    assert evidence.collect(folder,client,2,sleep=lambda _:None)["states"]=={"PENDING":1}
    assert evidence.collect(folder,client,4,sleep=lambda _:None)["states"]=={"BODY_CAPTURED":1}
    assert evidence.collect(folder,client,4)["attemptsUsed"]==4 and len(client.calls)==4
    plan,_,_=evidence.load(folder)
    assert plan["targets"][0]["symbol"]=="000010" and not evidence.summary(folder)["membershipConfirmed"]


@pytest.mark.parametrize("kind",["pages","count","correction","ambiguous","wrong_code","multiple_documents","wrong_path","host"])
def test_ambiguous_unreviewed_or_mismatching_discovery_cannot_reach_untrusted_body(kind):
    target={"kind":"ADDED_OBSERVED","symbol":"000010"}
    with pytest.raises(ResearchError):
        if kind=="pages": evidence.search_result(search(pages=2),target)
        if kind=="count": evidence.search_result(search(count=2),target)
        if kind=="correction": evidence.search_result(search("[정정]신규상장"),target)
        if kind=="ambiguous": evidence.search_result(search()+search(),target)
        if kind=="wrong_code": evidence.viewer_result(viewer("000020"),target)
        if kind=="multiple_documents": evidence.viewer_result(viewer(documents=2),target)
        if kind=="wrong_path": evidence.path_result(path(),RECEIPT,"20240102000003")
        if kind=="host": evidence.path_result(path("https://example.com/70760.htm"),RECEIPT,DOCUMENT)


def test_search_prioritizes_membership_notice_over_price_reference():
    main=search("신규상장(가상회사)").decode().split('<div')[0]
    fallback=search("주권 등 신규상장 기준가격 안내 (SPAC소멸합병상장)").decode().split('<div')[0]
    raw=(main+fallback+'<div class="info type-00">전체 2건 : 1 /1</div>').encode()
    assert evidence.search_result(raw,{"kind":"ADDED_OBSERVED"})["priority"]==0


def test_no_search_result_is_a_review_state_and_not_a_failure_retry_loop(tmp_path):
    folder=planned(tmp_path)
    client=Client(search_raw='<div class="info type-00">전체 0건 : 1 /1</div>'.encode())
    report=evidence.collect(folder,client,8,sleep=lambda _:None)
    assert report["states"]=={"MEMBERSHIP_EVIDENCE_NO_REVIEWED_SEARCH_TITLE":1}
    evidence.collect(folder,client,8)
    assert len(client.calls)==1


def test_failed_stage_requires_explicit_recovery_and_preserves_prior_attempt(tmp_path):
    folder=planned(tmp_path)
    report=evidence.collect(folder,Client(fail=1),8)
    assert report["states"]=={"FAILED":1}
    client=Client()
    assert evidence.collect(folder,client,8)["attemptsUsed"]==1 and not client.calls
    assert evidence.collect(folder,client,4,True,sleep=lambda _:None)["states"]=={"BODY_CAPTURED":1}
    _,journal,_=evidence.load(folder)
    assert journal["attempts"][0]["state"]=="FAILED" and len(journal["attempts"])==5


@pytest.mark.parametrize("target",["raw","request","plan"])
def test_all_stored_data_and_request_paths_are_verified_before_new_calls(tmp_path,target):
    folder=planned(tmp_path)
    evidence.collect(folder,Client(),1)
    if target=="raw": (folder/"raw/0001.bin").write_bytes(b"mutated")
    elif target=="request":
        j=read_json(read_bytes(folder/"journal.json")); j["attempts"][0]["request"]["url"]="https://example.com"
        atomic_json(folder/"journal.json",j)
    else:
        p=read_json(read_bytes(folder/"plan.json")); p["maxRequests"]=7; atomic_json(folder/"plan.json",p)
    client=Client()
    with pytest.raises(ResearchError): evidence.collect(folder,client,4)
    assert not client.calls


def test_per_stage_recovery_budget_is_bounded(tmp_path):
    folder=planned(tmp_path)
    for _ in range(3): evidence.collect(folder,Client(fail=1),1,True,sleep=lambda _:None)
    client=Client()
    assert evidence.collect(folder,client,4,True)["attemptsUsed"]==3 and not client.calls
