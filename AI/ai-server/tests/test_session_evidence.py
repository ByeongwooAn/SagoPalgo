"""Synthetic notices test extraction; real downloaded notices stay outside Git."""
import copy
import io
import json

import pytest
from pydantic import ValidationError

from app.replay.models import ResearchError, utc
from app.replay.reference import ReferencePack, combine, reconcile, references_as_of
from app.replay.reference_cli import main
from app.replay.session_evidence import LIMIT, fetch_session_notice, notice_reference
from test_reference import collected, complete_pack

URL = "https://kind.krx.co.kr/external/2024/01/01/000001/20240101000001/70780.htm"
CAPTURED = "2026-11-03T07:00:00Z"
CSAT = """<html><head><style>.hidden {}</style></head><body>
기타시장안내 대학수학능력시험일(2024년 11월 14일) 출근시간 조정으로 코스닥시장의 거래시간이 변경됩니다.
1. 거래시간 변경 가. 변경 전 정규시장 : 09:00~15:30
나. 변경 후 주식 정규시장 : 10:00~16:30 장종료후 시간외시장 : 16:40~18:00
2. 변경사유 : 대학수학능력시험 3. 시행일 : 2024. 11. 14 (목)
4. 근거규정 : 가상 테스트 문장</body></html>"""
YEAR_OPEN = """<p>기타시장안내 2024년 연말 시장운영 일정 및 2025년 연초 개장일 안내
코넥스시장의 2024년 연말 시장운영 일정입니다.
1. 2024년 연말 시장운영 일정 연말 휴장일 : 2024.12.31
2. 2025년 연초 개장일(1.2, 목) : 증시 개장식에 따른 매매거래시간 임시변경
정규장은 개장시각만 1시간 연기 : 10:00~15:30
장종료후 시간외시장은 현행과 동일 : 15:40~18:00
3. 근거규정 : 가상 테스트 문장</p>"""


@pytest.mark.parametrize("encoding", ["utf-8", "cp949"])
def test_csat_extracts_changed_regular_session_not_old_or_after_hours(encoding):
    pack = notice_reference(CSAT.encode(encoding), URL, CAPTURED)
    session = pack.sessions[0]
    assert session.market == "KOSDAQ" and session.businessDate == "2024-11-14"
    assert session.openAt == utc("2024-11-14T10:00:00+09:00")
    assert session.closeAt == utc("2024-11-14T16:30:00+09:00")
    assert session.knownAt == pack.observedAt == utc(CAPTURED)
    assert "FETCH_TIME_ONLY" in session.evidence and "raw-sha256" in session.evidence
    assert not pack.calendar and not pack.listings and not pack.actions and not pack.coverage


def test_year_open_preserves_unchanged_close_and_does_not_turn_year_end_notice_into_calendar():
    pack = notice_reference(YEAR_OPEN.encode(), URL, CAPTURED)
    session = pack.sessions[0]
    assert session.businessDate == "2025-01-02" and session.market == "KONEX"
    assert session.closeAt == utc("2025-01-02T15:30:00+09:00")
    assert not pack.calendar and not pack.coverage


@pytest.mark.parametrize("changed", [
    CSAT.replace("2024. 11. 14", "2024. 11. 15"),
    CSAT.replace("코스닥시장의", "코스닥시장의 코넥스시장의"),
    CSAT.replace("코스닥시장의", "해외시장의"),
    CSAT.replace("나. 변경 후", "형식이 변경됨"),
    CSAT.replace("10:00~16:30", "10:00~16:30 정규시장 : 11:00~17:30"),
    CSAT.replace("10:00~16:30", "16:30~10:00"),
    CSAT.replace("10:00~16:30", "25:00~16:30"),
    CSAT.replace("10:00~16:30", "확인되지 않음"),
    YEAR_OPEN.replace("(1.2, 목)", "(확인 필요)"),
    "<html>로그인이 필요합니다</html>",
], ids=["date-conflict", "two-markets", "unknown-market", "changed-layout", "two-times", "reversed-time", "invalid-time", "missing-time", "missing-date", "login-page"])
def test_changed_layout_conflicting_dates_or_times_and_wrong_markets_fail_closed(changed):
    with pytest.raises((ResearchError, ValidationError, ValueError)):
        notice_reference(changed.encode(), URL, CAPTURED)


class Opener:
    def __init__(self, body=CSAT.encode(), fail=False):
        self.calls = []
        self.body = body
        self.fail = fail

    def open(self, req, timeout):
        self.calls.append(req)
        if self.fail:
            raise OSError("untrusted response containing private detail")
        return io.BytesIO(self.body)


@pytest.mark.parametrize("url", [
    URL.replace("https:", "http:"), URL.replace("kind.krx.co.kr", "kind.krx.co.kr.evil.example"),
    URL + "?token=not-allowed", URL.replace("/external/", "/external/../private/"),
])
def test_source_url_rejected_before_network_or_reservation(tmp_path, url):
    opener = Opener()
    with pytest.raises(ResearchError, match="SOURCE_URL_INVALID"):
        fetch_session_notice(url, tmp_path / "cache", opener)
    assert not opener.calls and not (tmp_path / "cache").exists()


def test_public_fetch_has_no_auth_and_cache_revalidates_without_network(tmp_path):
    opener = Opener()
    pack, folder, cached = fetch_session_notice(URL, tmp_path, opener)
    assert not cached and len(opener.calls) == 1
    req = opener.calls[0]
    assert req.method == "GET" and not req.data and not req.has_header("Authorization")
    second, _, cached = fetch_session_notice(URL, tmp_path, opener)
    assert cached and second == pack and len(opener.calls) == 1
    receipt = json.loads((folder / "receipt.json").read_bytes())
    assert receipt["status"] == "COMPLETE" and receipt["knowledgeBasis"] == "FETCH_TIME_ONLY"
    assert receipt["maxGetRequests"] == 1


@pytest.mark.parametrize("name", ["body.html", "reference.json"])
def test_changed_cached_source_or_derivation_is_detected_before_network(tmp_path, name):
    opener = Opener()
    _, folder, _ = fetch_session_notice(URL, tmp_path, opener)
    (folder / name).write_bytes(b"changed")
    with pytest.raises(ResearchError, match="CACHE_TAMPERED"):
        fetch_session_notice(URL, tmp_path, opener)
    assert len(opener.calls) == 1


@pytest.mark.parametrize("body,fail,code", [(b"unsupported layout", False, "SESSION_NOTICE_MARKET_AMBIGUOUS"),
                                          (b"x" * (LIMIT + 1), False, "SESSION_RESPONSE_LIMIT"),
                                          (b"", True, "SESSION_CAPTURE_FAILED")], ids=["unsupported-layout", "oversized-response", "transport-failure"])
def test_failure_keeps_receipt_and_does_not_retry_or_echo_response(tmp_path, body, fail, code):
    opener = Opener(body, fail)
    with pytest.raises(ResearchError) as caught:
        fetch_session_notice(URL, tmp_path, opener)
    assert str(caught.value) == code
    with pytest.raises(ResearchError, match="CAPTURE_RESERVED"):
        fetch_session_notice(URL, tmp_path, opener)
    assert len(opener.calls) == 1


def test_market_session_identity_allows_other_venue_but_rejects_same_venue_conflict():
    kosdaq = notice_reference(CSAT.encode(), URL, CAPTURED)
    konex = notice_reference(CSAT.replace("코스닥", "코넥스").replace("10:00~16:30", "10:00~15:30").encode(), URL, CAPTURED)
    assert len(combine([kosdaq, konex])["sessions"]) == 2
    changed = kosdaq.model_dump(mode="json")
    changed["sessions"][0]["evidence"] += " conflict"
    with pytest.raises(ResearchError, match="REFERENCE_CONFLICT"):
        combine([kosdaq, ReferencePack.model_validate(changed)])


def test_session_market_and_capture_time_are_both_required_for_visibility():
    pack = notice_reference(CSAT.encode(), URL, CAPTURED)
    for market, at in [("KOSPI", CAPTURED), ("UNSPECIFIED", CAPTURED), ("KOSDAQ", "2024-11-14T16:30:00+09:00")]:
        assert references_as_of([pack], "000001", utc(at), "2024-11-14", market)["session"] is None
    assert references_as_of([pack], "000001", utc(CAPTURED), "2024-11-14", "KOSDAQ")["session"]["market"] == "KOSDAQ"


def test_wrong_or_legacy_market_session_cannot_satisfy_explicit_coverage(tmp_path):
    _, report, rows = collected(tmp_path)
    legacy = ReferencePack.model_validate(complete_pack())
    result = reconcile(report, rows, [legacy], "KOSPI")
    codes = {v["code"] for v in result["issues"]}
    assert result["matchedSessionDates"] == 0 and result["excludedSessionRecords"] == 2
    assert {"SESSION_MISSING", "PRICE_SESSION_MISSING", "SESSION_COVERAGE_UNCONFIRMED"} <= codes
    scoped = copy.deepcopy(complete_pack())
    for session in scoped["sessions"]:
        session["market"] = "KOSPI"
    scoped["sessions"].pop()
    result = reconcile(report, rows, [ReferencePack.model_validate(scoped)], "KOSPI")
    assert result["matchedSessionDates"] == 1
    assert next(i for i in result["issues"] if i["code"] == "SESSION_COVERAGE_UNCONFIRMED")["count"] == 1


def test_real_unscoped_reconciliation_cannot_claim_scope_ready(tmp_path):
    _, report, rows = collected(tmp_path)
    report["provenance"] = "PROVIDER_HISTORICAL"
    result = reconcile(report, rows, [ReferencePack.model_validate(complete_pack())])
    assert "SESSION_MARKET_UNSPECIFIED" in {i["code"] for i in result["issues"]}


def test_evidenced_closed_day_needs_no_session_but_still_requires_calendar_evidence(tmp_path):
    _, report, rows = collected(tmp_path)
    value = complete_pack()
    value["calendar"][1].update(openDay=False, tradingDay=False)
    value["sessions"] = [{**value["sessions"][0], "market": "KOSPI"}]
    result = reconcile(report, rows[:1], [ReferencePack.model_validate(value)], "KOSPI")
    assert result["referenceScopeReady"] and result["matchedSessionDates"] == 1
    value["calendar"].pop()
    result = reconcile(report, rows[:1], [ReferencePack.model_validate(value)], "KOSPI")
    assert "SESSION_COVERAGE_UNCONFIRMED" in {i["code"] for i in result["issues"]}


def test_cli_public_session_fetch_emits_metadata_and_uses_cached_evidence(tmp_path, monkeypatch, capsys):
    opener = Opener()
    monkeypatch.setattr("app.replay.session_evidence.request.build_opener", lambda *args: opener)
    args = ["session-fetch", "--url", URL, "--cache", str(tmp_path)]
    assert main(args) == 0 and not json.loads(capsys.readouterr().out)["cached"]
    assert main(args) == 0 and json.loads(capsys.readouterr().out)["cached"]
    assert len(opener.calls) == 1


def test_cli_wrong_market_is_rejected_before_reference_read(tmp_path):
    with pytest.raises(SystemExit) as caught:
        main(["check", "--job", str(tmp_path), "--local-use", "missing", "--reference", "missing", "--output", "missing", "--market", "NXT"])
    assert caught.value.code == 2
