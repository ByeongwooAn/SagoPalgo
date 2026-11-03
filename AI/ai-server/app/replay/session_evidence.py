"""Bounded public KIND notice capture. No historical publication time is inferred."""
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib import request

from .dataset import canonical, digest, read_bytes, read_json
from .history import NoRedirect, atomic_json, day, now
from .models import ResearchError
from .reference import ReferencePack

LIMIT = 512 * 1024
URL_PATTERN = r"https://kind\.krx\.co\.kr/external/[0-9]{4}/[0-9]{2}/[0-9]{2}/[0-9]{6}/[0-9]{14}/[0-9]{5}\.htm"


class NoticeText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, value):
        if not self.hidden:
            self.parts.append(value)


def validate_url(url):
    if not re.fullmatch(URL_PATTERN, url):
        raise ResearchError("SESSION_SOURCE_URL_INVALID")


def notice_reference(raw: bytes, url: str, captured_at: str):
    validate_url(url)
    if len(raw) > LIMIT:
        raise ResearchError("SESSION_RESPONSE_LIMIT")
    try:
        html = raw.decode("utf-8-sig")
    except UnicodeError:
        html = raw.decode("cp949")
    parser = NoticeText()
    parser.feed(html)
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    # Only the two reviewed regular-equity notice layouts are supported.
    intro = re.split(r"1\.\s*(?:거래시간|[0-9]{4}년 연말)", text, maxsplit=1)[0]
    venues = {code for label, code in [("유가증권", "KOSPI"), ("코스닥", "KOSDAQ"), ("코넥스", "KONEX")]
              if re.search(label + r"시장의", intro)}
    if len(venues) != 1:
        raise ResearchError("SESSION_NOTICE_MARKET_AMBIGUOUS")
    if "대학수학능력시험일" in intro:
        announced = re.findall(r"시험일\s*\(([0-9]{4})년\s*([0-9]{1,2})월\s*([0-9]{1,2})일\)", intro)
        effective = re.findall(r"3\.\s*시행일\s*:\s*([0-9]{4})\s*\.\s*([0-9]{1,2})\s*\.\s*([0-9]{1,2})", text)
        if len(announced) != 1 or len(effective) != 1 or tuple(map(int, announced[0])) != tuple(map(int, effective[0])):
            raise ResearchError("SESSION_NOTICE_DATE_AMBIGUOUS")
        sections = re.split(r"나\.\s*변경\s*후", text)
        if len(sections) != 2:
            raise ResearchError("SESSION_NOTICE_LAYOUT_UNSUPPORTED")
        changed = re.split(r"2\.\s*변경사유", sections[1])[0]
        times = re.findall(r"정규시장\s*:\s*([0-9]{2}:[0-9]{2})\s*~\s*([0-9]{2}:[0-9]{2})", changed)
        stamp = effective[0]
    elif "연말 시장운영 일정" in intro and "연초 개장일" in intro:
        effective = re.findall(r"2\.\s*([0-9]{4})년 연초 개장일\s*\(([0-9]{1,2})\.([0-9]{1,2})\s*,", text)
        if len(effective) != 1:
            raise ResearchError("SESSION_NOTICE_DATE_AMBIGUOUS")
        changed = re.split(r"2\.\s*[0-9]{4}년 연초 개장일", text)[-1]
        times = re.findall(r"정규장은 개장시각만 1시간 연기\s*:\s*([0-9]{2}:[0-9]{2})\s*~\s*([0-9]{2}:[0-9]{2})", changed)
        stamp = effective[0]
    else:
        raise ResearchError("SESSION_NOTICE_LAYOUT_UNSUPPORTED")
    if len(times) != 1:
        raise ResearchError("SESSION_NOTICE_TIME_AMBIGUOUS")
    business_date = datetime(*map(int, stamp)).date().isoformat()
    day(business_date)
    opened, closed = times[0]
    evidence = url + "; raw-sha256:" + digest(raw) + "; knowledge=FETCH_TIME_ONLY"
    return ReferencePack.model_validate({
        "schemaVersion": "SAGOPALGO_MARKET_REFERENCE_V1", "provider": "KRX_KIND_SESSION_NOTICE",
        "provenance": "PROVIDER_OBSERVATIONS", "reference": evidence, "observedAt": captured_at,
        "sessions": [{"market": venues.pop(), "businessDate": business_date,
                      "openAt": business_date + "T" + opened + ":00+09:00",
                      "closeAt": business_date + "T" + closed + ":00+09:00",
                      "knownAt": captured_at, "evidence": evidence}],
        "calendar": [], "listings": [], "actions": [], "coverage": [],
    })


def fetch_session_notice(url: str, cache: Path, opener=None):
    validate_url(url)
    folder = cache / digest(url.encode())
    folder.parent.mkdir(parents=True, exist_ok=True)
    try:
        folder.mkdir()
    except FileExistsError:
        receipt = read_json(read_bytes(folder / "receipt.json")) if (folder / "receipt.json").is_file() else {}
        if not isinstance(receipt, dict) or receipt.get("status") != "COMPLETE" or receipt.get("url") != url:
            raise ResearchError("SESSION_CAPTURE_RESERVED")
        raw = read_bytes(folder / "body.html")
        if digest(raw) != receipt.get("bodySha256"):
            raise ResearchError("SESSION_CACHE_TAMPERED")
        pack = notice_reference(raw, url, receipt["capturedAt"])
        normalized = read_bytes(folder / "reference.json")
        if normalized != canonical(pack.model_dump(mode="json")) or digest(normalized) != receipt.get("referenceSha256"):
            raise ResearchError("SESSION_CACHE_TAMPERED")
        return pack, folder, True
    receipt = {"schemaVersion": "SAGOPALGO_SESSION_CAPTURE_V1", "url": url, "status": "IN_FLIGHT",
               "startedAt": now(), "maxGetRequests": 1, "knowledgeBasis": "FETCH_TIME_ONLY"}
    atomic_json(folder / "receipt.json", receipt)
    try:
        client = opener or request.build_opener(NoRedirect())
        req = request.Request(url, headers={"Accept": "text/html", "User-Agent": "SagoPalgo-local-research/1"}, method="GET")
        with client.open(req, timeout=20) as response:
            raw = response.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ResearchError("SESSION_RESPONSE_LIMIT")
        captured_at = now()
        (folder / "body.html").write_bytes(raw)
        receipt.update(bodySha256=digest(raw), capturedAt=captured_at)
        pack = notice_reference(raw, url, captured_at)
        normalized = canonical(pack.model_dump(mode="json"))
        (folder / "reference.json").write_bytes(normalized)
        receipt.update(status="COMPLETE", referenceSha256=digest(normalized))
        atomic_json(folder / "receipt.json", receipt)
        return pack, folder, False
    except Exception as exc:
        code = str(exc) if isinstance(exc, ResearchError) else "SESSION_CAPTURE_FAILED"
        receipt.update(status="FAILED", diagnostic=code, finishedAt=now())
        atomic_json(folder / "receipt.json", receipt)
        raise ResearchError(code) from None
