"""Synthetic notice layouts; public captures and actual market data stay local."""
import io
import json

import pytest
from pydantic import ValidationError

from app.replay.kb_market_evidence import LIMIT, canonical_url, capture_notice, import_notice, load_capture, notice_pack
from app.replay.models import ResearchError, utc
from app.replay.reference import ReferencePack, combine, reconcile, references_as_of
from app.replay.reference_cli import main
from test_reference import collected, complete_pack

URL = "https://www.kbsec.com/go.able?idt=20241226&linkcd=s060901010000&seq=99999"
CAPTURED = "2026-11-03T08:00:00Z"
NOTICE = """<html><body><h3>가상 연말 안내</h3><p>등록일 2024/12/26 13:44:42</p>
<p>연말시장운영 및 2025년 연초 개장일 안내</p>
<p>2. 연말휴장일 : 2024.12.31(화)</p><p>휴장일은 결제일에 포함되지 않음</p>
<p>1. 연초개장일: 2025. 1. 2(목)</p>
<p>가. 유가증권, 코스닥, 코넥스, 일반상품, K-OTC시장</p>
<table><tr><th>구분</th><th>변경 전</th><th>변경 후</th></tr>
<tr><td>정규시장</td><td>09:00 ~ 15:30</td><td>10:00 ~ 15:30</td></tr>
<tr><td>시간외</td><td>08:30~08:40</td><td>09:30~09:40</td></tr></table>
<p>나. 파생상품시장</p><p>정규시장 08:45 ~ 15:45 09:45 ~ 15:45</p>
<p>다. 국내주식소수점</p><p>1회 10:00 10:30</p></body></html>"""

NOTICE_2026 = """<html><body>등록일 2025/12/22 16:02:05
2025년 연말 시장운영 및 2026년 개장일 안내
2. 연말휴장일 : 2025.12.31 휴장일은 결제일에 포함되지 않음
연초개장일 : 2026.1.2
1. 유가증권 시장, 코스닥 시장 및 코넥스, 금시장
1) 한국거래소(KRX) 구 분 매매거래시간 당사 주문접수시간 변경전 변경후
정규시장 (대량, 바스켓매매 포함) (채권(국채,Repo 포함),금현물)
09:00 ~ 15:30 10:00 ~ 15:30 08:00 ~ 15:30
경쟁대량매매 09:00 ~ 15:00 10:00 ~ 15:00 10:00 ~ 15:00
2) 넥스트레이드(NXT) 정규시장 프리마켓 미운영 메인마켓 10:00:30 ~ 15:20
2. 선물, 옵션 09:45 ~ 15:45
</body></html>"""


def receipt_2026():
    return {"url": URL.replace("idt=20241226", "idt=20251222"), "capturedAt": CAPTURED}


def receipt():
    return {"url": URL, "capturedAt": CAPTURED}


class Opener:
    def __init__(self, body=NOTICE.encode(), fail=False):
        self.calls = []
        self.body = body
        self.fail = fail

    def open(self, req, timeout):
        self.calls.append(req)
        if self.fail:
            raise OSError("private untrusted response")
        return io.BytesIO(self.body)


@pytest.mark.parametrize("encoding", ["utf-8", "cp949"])
def test_import_uses_equity_changed_session_and_only_explicit_calendar_facts(encoding):
    pack = notice_pack(receipt(), NOTICE.encode(encoding), "KOSPI", "OBSERVED_AT")
    session = pack.sessions[0]
    assert session.market == "KOSPI" and session.businessDate == "2025-01-02"
    assert session.openAt == utc("2025-01-02T10:00:00+09:00") and session.closeAt == utc("2025-01-02T15:30:00+09:00")
    assert session.knownAt == utc(CAPTURED)
    assert [(d.businessDate, d.openDay, d.settlementDay) for d in pack.calendar] == [("2024-12-31", False, False), ("2025-01-02", True, None)]
    assert all(d.businessDay is None and d.tradingDay is None for d in pack.calendar)
    assert not pack.coverage and not pack.listings and not pack.actions


@pytest.mark.parametrize("market", ["KOSPI", "KOSDAQ", "KONEX"])
def test_document_explicitly_covers_each_selected_equity_market_without_extra_sessions(market):
    pack = notice_pack(receipt(), NOTICE.encode(), market, "OBSERVED_AT")
    assert len(pack.sessions) == 1 and pack.sessions[0].market == market


def test_provider_publication_assumption_is_explicit_and_separate_from_observation():
    assumed = notice_pack(receipt(), NOTICE.encode(), "KOSPI", "PROVIDER_PUBLICATION_ASSUMED")
    observed = notice_pack(receipt(), NOTICE.encode(), "KOSPI", "OBSERVED_AT")
    publication = utc("2024-12-26T13:44:42+09:00")
    assert assumed.sessions[0].knownAt == publication and assumed.observedAt == utc(CAPTURED)
    assert "availability=PROVIDER_PUBLICATION_ASSUMED" in assumed.reference
    assert "registered-at=2024-12-26T13:44:42+09:00" in assumed.reference
    before = references_as_of([assumed], "005930", utc("2024-12-26T13:44:41+09:00"), "2025-01-02", "KOSPI")
    after = references_as_of([assumed], "005930", publication, "2025-01-02", "KOSPI")
    assert before["session"] is None and after["session"]
    assert references_as_of([observed], "005930", publication, "2025-01-02", "KOSPI")["session"] is None


@pytest.mark.parametrize("availability", ["OBSERVED_AT", "PROVIDER_PUBLICATION_ASSUMED"])
def test_2026_layout_uses_krx_changed_hours_without_broker_order_or_nxt_hours(availability):
    pack = notice_pack(receipt_2026(), NOTICE_2026.encode(), "KOSPI", availability)
    session = pack.sessions[0]
    assert session.businessDate == "2026-01-02"
    assert session.openAt == utc("2026-01-02T10:00:00+09:00")
    assert session.closeAt == utc("2026-01-02T15:30:00+09:00")
    assert pack.calendar[0].businessDate == "2025-12-31" and pack.calendar[0].settlementDay is False


@pytest.mark.parametrize("changed", [
    NOTICE_2026.replace("1) 한국거래소(KRX)", "거래소 미확인"),
    NOTICE_2026.replace("2) 넥스트레이드(NXT)", "시장 경계 미확인"),
    NOTICE_2026.replace("당사 주문접수시간", "열 순서 미확인"),
    NOTICE_2026.replace("08:00 ~ 15:30", "열 없음"),
    NOTICE_2026.replace("경쟁대량매매", "경계 미확인"),
], ids=["no-krx", "no-nxt-boundary", "no-order-column", "missing-column", "no-regular-row-boundary"])
def test_2026_layout_requires_explicit_venue_and_column_boundaries(changed):
    with pytest.raises(ResearchError):
        notice_pack(receipt_2026(), changed.encode(), "KOSPI", "OBSERVED_AT")


@pytest.mark.parametrize("text", [
    NOTICE.replace("2024/12/26", "2024/12/27"),
    NOTICE.replace("2024/12/26 13:44:42", "2027/12/26 13:44:42"),
    NOTICE.replace("2025년", "2024년"),
    NOTICE.replace("2024.12.31", "2025.1.3"),
    NOTICE.replace("코스닥, 코넥스,", "코스닥,"),
    NOTICE.replace("나. 파생상품시장", "파생상품 표제 변경"),
    NOTICE.replace("등록일", "수정 시각"),
    NOTICE.replace("휴장일은 결제일에 포함되지 않음", "결제 정보 미확인"),
    NOTICE.replace("10:00 ~ 15:30", "16:30 ~ 10:00"),
    NOTICE.replace("10:00 ~ 15:30", "10:00 ~ 15:30 정규시장 09:00~15:30 11:00~17:30"),
], ids=["url-registration-conflict", "future-registration", "title-year-conflict", "closure-after-open", "wrong-market-scope",
        "missing-derivative-boundary", "no-registration", "no-settlement-evidence", "reversed-session", "ambiguous-equity-time"])
def test_unsupported_or_conflicting_evidence_is_rejected(text):
    with pytest.raises((ResearchError, ValidationError)):
        notice_pack(receipt(), text.encode(), "KOSPI", "OBSERVED_AT")


@pytest.mark.parametrize("url", [URL.replace("https:", "http:"), URL.replace("www.kbsec.com", "www.kbsec.com.evil.example"),
                                 URL + "&account=forbidden", URL + "#fragment", URL + "&seq=other", URL.replace("s060901010000", "private")])
def test_invalid_source_url_is_rejected_before_any_network_or_directory_write(tmp_path, url):
    opener = Opener()
    with pytest.raises(ResearchError, match="URL_INVALID"):
        capture_notice(url, tmp_path / "cache", opener)
    assert not opener.calls and not (tmp_path / "cache").exists()


def test_capture_and_offline_import_are_separate_cached_and_non_overwriting(tmp_path):
    opener = Opener()
    folder, cached = capture_notice(URL, tmp_path / "cache", opener)
    assert not cached and len(opener.calls) == 1 and not opener.calls[0].has_header("Authorization")
    reordered = "https://www.kbsec.com/go.able?seq=99999&linkcd=s060901010000&idt=20241226"
    assert canonical_url(reordered) == URL
    _, cached = capture_notice(reordered, tmp_path / "cache", opener)
    assert cached and len(opener.calls) == 1
    assert not (folder / "reference.json").exists()
    target = tmp_path / "reference.json"
    imported = import_notice(folder, target, "KOSPI")
    assert imported.sessions[0].market == "KOSPI" and len(opener.calls) == 1
    with pytest.raises(FileExistsError):
        import_notice(folder, target, "KOSPI")
    (folder / "body.html").write_bytes(b"changed")
    with pytest.raises(ResearchError, match="TAMPERED"):
        import_notice(folder, tmp_path / "other.json", "KOSPI")
    with pytest.raises(ResearchError, match="TAMPERED"):
        capture_notice(URL, tmp_path / "cache", opener)
    assert len(opener.calls) == 1


@pytest.mark.parametrize("oversize", [False, True])
def test_failed_capture_preserves_reservation_and_no_retry(tmp_path, oversize):
    opener = Opener(b"x" * (LIMIT + 1) if oversize else b"", fail=not oversize)
    with pytest.raises(ResearchError) as error:
        capture_notice(URL, tmp_path, opener)
    assert str(error.value) == ("KB_NOTICE_RESPONSE_LIMIT" if oversize else "KB_NOTICE_CAPTURE_FAILED")
    with pytest.raises(ResearchError, match="INCOMPLETE"):
        capture_notice(URL, tmp_path, opener)
    assert len(opener.calls) == 1


def test_failed_parse_keeps_successful_capture_available_for_offline_diagnostics(tmp_path):
    folder, _ = capture_notice(URL, tmp_path / "cache", Opener(b"unsupported page"))
    with pytest.raises(ResearchError, match="LAYOUT_UNSUPPORTED"):
        import_notice(folder, tmp_path / "reference.json", "KOSPI")
    stored, body = load_capture(folder)
    assert stored["status"] == "COMPLETE" and body == b"unsupported page"
    assert not (tmp_path / "reference.json").exists()


def test_partial_flags_merge_with_full_flags_commutatively_without_inventing_values():
    partial = notice_pack(receipt(), NOTICE.encode(), "KOSPI", "OBSERVED_AT")
    value = partial.model_dump(mode="json")
    value["calendar"][0].update(businessDay=True, tradingDay=False)
    full = ReferencePack.model_validate(value)
    first = combine([partial, full])["calendar"]
    assert first == combine([full, partial])["calendar"]
    assert first["2024-12-31"].businessDay is True
    assert first["2025-01-02"].settlementDay is None
    value["calendar"][0]["openDay"] = True
    with pytest.raises(ResearchError, match="REFERENCE_CONFLICT"):
        combine([partial, ReferencePack.model_validate(value)])


def test_partial_flags_are_not_counted_false_or_reported_as_trading_open_disagreement(tmp_path):
    _, report, rows = collected(tmp_path)
    value = complete_pack()
    value["calendar"][0].update(tradingDay=None, businessDay=None, settlementDay=None)
    value["reference"] = "fixture; availability=PROVIDER_PUBLICATION_ASSUMED"
    result = reconcile(report, rows, [ReferencePack.model_validate(value)])
    assert result["knownTradingDates"] == 1 and result["knownOpenDates"] == 2
    assert result["calendarFlagDifferences"] == []
    assert result["calendarUnknownFlags"] == {"businessDay": 1, "tradingDay": 1, "settlementDay": 1}
    assert result["providerPublicationAssumptions"] == [value["reference"]]
    assert "CALENDAR_FLAGS_PARTIAL" in {i["code"] for i in result["issues"]}


def test_cli_public_capture_then_two_explicit_availability_modes_are_offline(tmp_path, monkeypatch, capsys):
    opener = Opener()
    monkeypatch.setattr("app.replay.kb_market_evidence.request.build_opener", lambda *args: opener)
    assert main(["kb-notice-capture", "--url", URL, "--cache", str(tmp_path)]) == 0
    folder = json.loads(capsys.readouterr().out)["captureFolder"]
    for availability in ["OBSERVED_AT", "PROVIDER_PUBLICATION_ASSUMED"]:
        assert main(["kb-notice-import", "--capture", folder, "--market", "KOSPI", "--availability", availability,
                     "--output", str(tmp_path / (availability + ".json"))]) == 0
        assert json.loads(capsys.readouterr().out)["availability"] == availability
    assert len(opener.calls) == 1
