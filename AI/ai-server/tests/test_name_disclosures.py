"""Immutable scope, exact security identity, versions, bounded resume and cached audit."""
import pytest

from app.replay import name_disclosures as names
from app.replay.dataset import canonical, digest, read_json, read_bytes
from app.replay.krx_storage import atomic_json
from app.replay.models import ResearchError
from test_universe_reconciliation import observation, issue

RECEIPT = "20240102000001"
DOC = "20240102000002"
URL = "https://kind.krx.co.kr/external/2024/01/02/000001/" + DOC + "/70765.htm"


def search(titles=("변경상장(상호변경)",), total=None, pages=1):
    links = ''.join(f'''<a href="#viewer" onclick="openDisclsViewer('{int(RECEIPT)+i}','')">{t}</a>''' for i, t in enumerate(titles))
    return (links + f'<div class="info type-00">전체 {len(titles) if total is None else total}건 : 1 /{pages}</div>').encode()


def viewer(code="000010", extra=""):
    return (f'<h1>가상회사 ({code})</h1><select id="mainDoc"><option value="{DOC}|Y">변경상장(상호변경) (2024.01.02)</option>{extra}</select>').encode()


class Client:
    source_kind = "SYNTHETIC"
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def fetch(self, spec):
        self.calls += 1
        if self.fail:
            raise OSError("private transport details")
        if "details.do" in spec["url"]:
            return search()
        if "acptno=" in spec["url"]:
            return viewer()
        if spec["method"] == "POST":
            return f"parent.setPath('','{URL}','/external/x','03','13');".encode()
        return b'<html>synthetic body for separate name parser</html>'


def planned(tmp_path, transfer=False):
    obs = observation("NAME_CHANGE_OBSERVED", before=issue(name="가상구명"), after=issue(name="가상신명", market="KOSDAQ" if transfer else "KOSPI"))
    row = {"observationId": digest(canonical(obs)), "observation": obs, "resolution": "NAME_CHANGE_NEEDS_DISCLOSURE"}
    parent = {"schemaVersion": "SAGOPALGO_UNIVERSE_RECONCILIATION_V2", "sourceKind": "SYNTHETIC", "startDate": "2024-01-02", "endDate": "2024-01-04", "rows": [row]}
    p = tmp_path / "parent.json"
    p.write_bytes(canonical(parent))
    folder = tmp_path / "job"
    names.prepare(folder, p, 10)
    return folder, p


def test_resume_and_offline_cache_reuse(tmp_path):
    folder, _ = planned(tmp_path)
    client = Client()
    assert names.collect(folder, client, 2, sleep=lambda _: None)["states"] == {"PENDING": 1}
    assert names.collect(folder, client, 3, sleep=lambda _: None)["states"] == {"BODIES_CAPTURED": 1}
    assert names.collect(folder, Client(True), 10)["attemptsUsed"] == client.calls == 4
    assert not names.summary(folder)["nameChangeConfirmed"]


def test_transfer_is_separate_context_and_has_no_requests(tmp_path):
    folder, _ = planned(tmp_path, True)
    client = Client(True)
    assert names.collect(folder, client, 10)["states"] == {"TRANSFER_CONTEXT_REQUIRED": 1}
    assert client.calls == 0


def test_failure_requires_explicit_retry_and_preserves_old_receipt(tmp_path):
    folder, _ = planned(tmp_path)
    failed = Client(True)
    assert names.collect(folder, failed, 10)["states"] == {"FAILED": 1}
    assert names.collect(folder, failed, 10)["attemptsUsed"] == 1
    assert names.collect(folder, Client(), 10, True, sleep=lambda _: None)["states"] == {"BODIES_CAPTURED": 1}
    assert names.load(folder)[1]["attempts"][0]["diagnostic"] == "NAME_DISCLOSURES_CAPTURE_FAILED"


@pytest.mark.parametrize("mutation", ["raw", "request", "orphan", "plan", "identity", "duplicate"])
def test_tampering_or_invalid_scope_blocks_before_network(tmp_path, mutation):
    folder, parent = planned(tmp_path)
    if mutation in {"identity", "duplicate"}:
        value = read_json(read_bytes(parent))
        if mutation == "identity":
            value["rows"][0]["observation"]["after"]["isin"] = "KR9999999999"
            value["rows"][0]["observationId"] = digest(canonical(value["rows"][0]["observation"]))
        else:
            value["rows"] *= 2
        atomic_json(parent, value)
        with pytest.raises(ResearchError):
            names.prepare(tmp_path / "other", parent)
        return
    names.collect(folder, Client(), 4, sleep=lambda _: None)
    if mutation == "raw":
        (folder / "raw/0001.bin").write_bytes(b"changed")
    elif mutation == "plan":
        value = read_json(read_bytes(folder / "plan.json"))
        value["lookbackDays"] = 46
        atomic_json(folder / "plan.json", value)
    else:
        value = read_json(read_bytes(folder / "journal.json"))
        if mutation == "request":
            value["attempts"][0]["request"]["parameters"]["repIsuSrtCd"] = "A999999"
        else:
            value["attempts"][0]["stage"] = "V3_BODY"
        atomic_json(folder / "journal.json", value)
    client = Client(True)
    with pytest.raises((ResearchError, ValueError)):
        names.collect(folder, client, 1)
    assert client.calls == 0


@pytest.mark.parametrize("variant", ["page", "count", "too_many", "wrong_code", "same_day_ambiguous"])
def test_ambiguous_discovery_is_not_confirmed(variant):
    with pytest.raises(ResearchError):
        if variant == "page": names.candidates(search(pages=2))
        if variant == "count": names.candidates(search(total=2))
        if variant == "too_many": names.candidates(search(("변경상장(상호변경)",) * 5))
        if variant == "wrong_code": names.viewer(viewer("999999"), {"symbol": "000010"}, {"receipt": RECEIPT, "corrected": False})
        if variant == "same_day_ambiguous": names.viewer(viewer(extra=f'<option value="20240102000003|Y">변경상장(상호변경) (2024.01.02)</option>'), {"symbol": "000010"}, {"receipt": RECEIPT, "corrected": False})


def test_unrelated_warrants_are_excluded_but_corrections_retained():
    result = names.candidates(search(("주식워런트증권 변경상장(종목명 변경)", "변경상장(상호변경)", "[정정] 변경상장(상호변경)")))
    assert len(result) == 2 and result[1]["corrected"]
    assert names.candidates(search(())) == []


def test_reviewed_repeated_title_marker_is_not_a_different_event():
    assert len(names.candidates(search(('변경상장(상호변경)(상호변경)',)))) == 1
    assert not names.candidates(search(('변경상장(상호변경)(다른사유)',)))


def test_missing_primary_title_uses_bounded_notice_search_and_resumes(tmp_path):
    folder, _ = planned(tmp_path)
    class NoticeClient(Client):
        def fetch(self, spec):
            self.calls += 1
            if 'details.do' in spec['url']:
                return search(('상장안내(합병/상호변경)',)) if spec['parameters']['reportNm'] == '상장안내' else search(())
            if 'acptno=' in spec['url']:
                return viewer().replace('변경상장(상호변경)'.encode(), '상장안내'.encode())
            if spec['method'] == 'POST':
                return f"parent.setPath('','{URL}','/external/x','03','13');".encode()
            return b'<html>separate parser verifies this form</html>'
    client = NoticeClient()
    assert names.collect(folder, client, 1, sleep=lambda _: None)['states'] == {'PENDING': 1}
    assert names.collect(folder, client, 4, sleep=lambda _: None)['states'] == {'BODIES_CAPTURED': 1}
    assert client.calls == 5
    assert names.load(folder)[1]['attempts'][1]['stage'] == 'NOTICE_SEARCH'
    assert names.collect(folder, Client(True), 10)['attemptsUsed'] == 5
