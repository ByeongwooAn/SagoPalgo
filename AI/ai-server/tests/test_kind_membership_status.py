"""Synthetic status pages preserve five-character issuer keys and reject incomplete censuses."""
import io

import pytest

from app.replay import kind_membership_status as status
from app.replay.dataset import canonical, read_bytes, read_json
from app.replay.history import atomic_json
from app.replay.models import ResearchError
from test_kind_cases import CAPTURED


def page(kind="LISTING", market="KOSPI", items=None, total=None, pages=1):
    items = items if items is not None else [{"key": "00001", "date": "2024-01-03", "name": "가상회사", "type": "신규상장"}]
    rows = []
    for row in items:
        icon = f"<img alt='{status.MARKETS[market][1]}'>"
        if kind == "LISTING":
            cells = [f"<td title='{row['name']}'>{icon}{row['name']}</td>", f"<td>{row['date']}</td>",
                     f"<td>{row['type']}</td>", "<td>주권</td>", "<td>가상업종</td>", "<td>대한민국</td>", "<td>가상주선인</td>"]
            rows.append(f'''<tr onclick="fnDetailView('{row['key']}','20230101000001')">{''.join(cells)}</tr>''')
        else:
            rows.append(f'''<tr><td>1</td><td>{icon}<a id="companysum" title="{row['name']}" onclick="companysummary_open('{row['key']}'); return false;">{row['name']}</a></td><td>{row['date']}</td><td>{row['type']}</td><td></td></tr>''')
    if not rows:
        rows = ["<tr><td>조회된 내용이 없습니다.</td></tr>"]
    summary = "회사명, 상장일, 상장유형,증권구분, 업종" if kind == "LISTING" else "번호, 회사명, 폐지일자, 폐지사유, 비고"
    caption = "신규상장기업현황 목록" if kind == "LISTING" else "목록"
    return (f'''<table summary="{summary}"><caption>{caption}</caption><tbody>{''.join(rows)}</tbody></table>
        <div class="info type-00">전체 <em>{len(items) if total is None else total}</em>건 : <strong>1</strong>/{pages}</div>''').encode()


class Client:
    source_kind = "SYNTHETIC"

    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def fetch(self, source):
        self.calls.append(source)
        if self.fail:
            raise OSError("private response")
        return page(source["kind"], source["market"])


def job(tmp_path):
    folder = tmp_path / "status"
    status.prepare(folder, "2024-01-02", "2024-01-04", "SYNTHETIC")
    return folder


@pytest.mark.parametrize("kind", list(status.ENDPOINTS))
def test_parser_keeps_alpha_issuer_key_without_inventing_full_stock_code_or_isin(kind):
    raw = page(kind, items=[{"key": "0001A", "date": "2024-01-03", "name": "가상회사", "type": "이전상장"}])
    row = status.parse_status(raw, kind, "KOSPI", "2024-01-02", "2024-01-04", CAPTURED, "SYNTHETIC")[0]
    assert row["providerIssuerKey"] == "0001A" and row["knownAt"] == CAPTURED
    assert not row["fullStockCodeProvided"] and not row["isinProvided"]
    assert "stockCode" not in row and "isin" not in row


@pytest.mark.parametrize("mutation", ["total", "pages", "market", "date", "duplicate", "key", "layout"])
def test_incomplete_or_ambiguous_pages_are_rejected(mutation):
    raw = page()
    if mutation == "total": raw = page(total=2)
    if mutation == "pages": raw = page(pages=2)
    if mutation == "market": raw = page(market="KOSDAQ")
    if mutation == "date": raw = raw.replace(b"2024-01-03", b"2024-01-05")
    if mutation == "duplicate": raw = page(items=[{"key":"00001","date":"2024-01-03","name":"가상","type":"신규상장"}]*2)
    if mutation == "key": raw = raw.replace(b"00001", b"bad")
    if mutation == "layout": raw = raw.replace("신규상장기업현황 목록".encode(), b"login")
    with pytest.raises(ResearchError):
        status.parse_status(raw, "LISTING", "KOSPI", "2024-01-02", "2024-01-04", CAPTURED, "SYNTHETIC")


def test_empty_page_requires_explicit_zero_total():
    assert status.parse_status(page(items=[]), "LISTING", "KOSPI", "2024-01-02", "2024-01-04", CAPTURED, "SYNTHETIC") == []


def test_bounded_capture_resumes_complete_sources_and_reuses_caches(tmp_path):
    folder = job(tmp_path)
    client = Client()
    assert status.capture(folder, client, 1, sleep=lambda _:None)["capturedSources"] == 1
    assert status.capture(folder, client, 4, sleep=lambda _:None)["capturedSources"] == 4
    assert status.capture(folder, client, 4)["capturedSources"] == 4
    assert len(client.calls) == 4
    result = status.report(folder)
    assert not result["completeMarketMembershipConfirmed"] and not result["independentProvider"]
    assert result["listingStatusExcludesSomeSpacMergers"] and not result["usableForTraining"]


def test_failure_preserves_reservation_and_never_automatically_retries(tmp_path):
    folder = job(tmp_path)
    failed = Client(fail=True)
    with pytest.raises(ResearchError, match="CAPTURE_FAILED"):
        status.capture(folder, failed, 4)
    assert status.report(folder)["attemptsUsed"] == 1
    client = Client()
    with pytest.raises(ResearchError, match="CAPTURE_RESERVED"):
        status.capture(folder, client, 4)
    assert not client.calls


@pytest.mark.parametrize("target", ["raw", "journal", "plan"])
def test_tampered_sources_stop_capture_before_network(tmp_path, target):
    folder = job(tmp_path)
    status.capture(folder, Client(), 1)
    if target == "raw": (folder / "raw" / "1.html").write_bytes(page(items=[]))
    else:
        path = folder / (target + ".json")
        value = read_json(read_bytes(path))
        if target == "plan": value["sources"][0]["url"] = "https://example.com"
        else: del value["attempts"][0]["sha256"]
        atomic_json(path, value)
    client = Client()
    with pytest.raises(ResearchError):
        status.capture(folder, client, 4)
    assert not client.calls


def test_transport_uses_fixed_post_scope_and_does_not_follow_redirects():
    class Opener:
        def open(self, req, timeout):
            assert req.full_url == status.ENDPOINTS["LISTING"] and req.method == "POST"
            assert b"marketType=1" in req.data and b"pageIndex=1" in req.data and timeout == 20
            return io.BytesIO(b"fixture")
    source = {"url":status.ENDPOINTS["LISTING"], "parameters":status.parameters("LISTING","KOSPI","2024-01-02","2024-01-04")}
    assert status.Transport(Opener()).fetch(source) == b"fixture"


def test_future_checkpoint_does_not_cause_unbounded_sleep_or_network(tmp_path):
    folder = job(tmp_path)
    status.capture(folder,Client(),1)
    journal = read_json(read_bytes(folder / "journal.json"))
    journal["attempts"][0].update(startedAt="2099-01-01T00:00:00Z",capturedAt="2099-01-01T00:00:01Z")
    atomic_json(folder / "journal.json",journal)
    client = Client()
    with pytest.raises(ResearchError,match="CLOCK_REGRESSION"):
        status.capture(folder,client,1,sleep=lambda _:pytest.fail("unbounded wait"))
    assert not client.calls
