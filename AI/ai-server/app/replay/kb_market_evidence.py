"""Public KB year-end notice capture, and offline evidence-scoped import."""
from datetime import datetime
from pathlib import Path
import re
from urllib import parse, request

from .dataset import canonical, digest, read_bytes, read_json
from .history import KST, NoRedirect, atomic_json, now
from .models import ResearchError, utc
from .reference import ReferencePack
from .session_evidence import NoticeText

LIMIT = 1024 * 1024
AVAILABILITY = ("OBSERVED_AT", "PROVIDER_PUBLICATION_ASSUMED")


def canonical_url(url):
    parts = parse.urlsplit(url)
    query = parse.parse_qs(parts.query, keep_blank_values=True)
    if (parts.scheme != "https" or parts.netloc != "www.kbsec.com" or parts.path != "/go.able" or parts.fragment
            or set(query) != {"idt", "linkcd", "seq"} or any(len(v) != 1 for v in query.values())
            or not re.fullmatch(r"[0-9]{8}", query.get("idt", [""])[0])
            or query.get("linkcd") != ["s060901010000"] or not re.fullmatch(r"[0-9]{1,12}", query.get("seq", [""])[0])):
        raise ResearchError("KB_NOTICE_URL_INVALID")
    return "https://www.kbsec.com/go.able?" + parse.urlencode({k: query[k][0] for k in ["idt", "linkcd", "seq"]})


def load_capture(folder):
    receipt = read_json(read_bytes(folder / "receipt.json"))
    if not isinstance(receipt, dict) or receipt.get("schemaVersion") != "SAGOPALGO_KB_NOTICE_CAPTURE_V1" or receipt.get("status") != "COMPLETE":
        raise ResearchError("KB_NOTICE_CAPTURE_INCOMPLETE")
    if canonical_url(receipt["url"]) != receipt["url"]:
        raise ResearchError("KB_NOTICE_RECEIPT_INVALID")
    utc(receipt["capturedAt"])
    body = read_bytes(folder / "body.html")
    if len(body) > LIMIT or digest(body) != receipt.get("bodySha256"):
        raise ResearchError("KB_NOTICE_CAPTURE_TAMPERED")
    return receipt, body


def capture_notice(url, cache: Path, opener=None):
    url = canonical_url(url)
    folder = cache / digest(url.encode())
    folder.parent.mkdir(parents=True, exist_ok=True)
    try:
        folder.mkdir()
    except FileExistsError:
        if not (folder / "receipt.json").is_file():
            raise ResearchError("KB_NOTICE_CAPTURE_RESERVED")
        receipt, _ = load_capture(folder)
        if receipt["url"] != url:
            raise ResearchError("KB_NOTICE_RECEIPT_INVALID")
        return folder, True
    receipt = {"schemaVersion": "SAGOPALGO_KB_NOTICE_CAPTURE_V1", "url": url, "status": "IN_FLIGHT",
               "startedAt": now(), "maxGetRequests": 1}
    atomic_json(folder / "receipt.json", receipt)
    try:
        client = opener or request.build_opener(NoRedirect())
        req = request.Request(url, headers={"Accept": "text/html", "User-Agent": "SagoPalgo-local-research/1"}, method="GET")
        with client.open(req, timeout=20) as response:
            body = response.read(LIMIT + 1)
        if len(body) > LIMIT:
            raise ResearchError("KB_NOTICE_RESPONSE_LIMIT")
        (folder / "body.html").write_bytes(body)
        receipt.update(status="COMPLETE", capturedAt=now(), bodySha256=digest(body))
        atomic_json(folder / "receipt.json", receipt)
        return folder, False
    except Exception as exc:
        code = str(exc) if isinstance(exc, ResearchError) else "KB_NOTICE_CAPTURE_FAILED"
        receipt.update(status="FAILED", diagnostic=code, finishedAt=now())
        atomic_json(folder / "receipt.json", receipt)
        raise ResearchError(code) from None


def equity_times(text):
    segments = re.split(r"가\.\s*유가증권,\s*코스닥,\s*코넥스,", text)
    if len(segments) == 2:
        equity = re.split(r"나\.\s*파생상품시장", segments[1])
        if len(equity) != 2 or "변경전" not in equity[0].replace(" ", "") or "변경후" not in equity[0].replace(" ", ""):
            raise ResearchError("KB_NOTICE_EQUITY_SECTION_INVALID")
        times = re.findall(r"정규시장\s*([0-9]{2}:[0-9]{2})\s*~\s*([0-9]{2}:[0-9]{2})\s*([0-9]{2}:[0-9]{2})\s*~\s*([0-9]{2}:[0-9]{2})", equity[0])
        if len(times) != 1:
            raise ResearchError("KB_NOTICE_FACTS_AMBIGUOUS")
        return times[0]
    # Reviewed 2026 layout has separate KRX/NXT tables and a broker order-hours column.
    equity = re.split(r"1\.\s*유가증권 시장,\s*코스닥 시장 및 코넥스,", text)
    krx = re.split(r"1\)\s*한국거래소\(KRX\)", equity[1]) if len(equity) == 2 else []
    sections = re.split(r"2\)\s*넥스트레이드\(NXT\)", krx[1]) if len(krx) == 2 else []
    if len(sections) != 2:
        raise ResearchError("KB_NOTICE_EQUITY_SECTION_INVALID")
    regular = sections[0].split("경쟁대량매매")
    if (len(regular) != 2 or regular[0].count("정규시장") != 1 or "당사 주문접수시간" not in regular[0]
            or "변경전" not in regular[0].replace(" ", "") or "변경후" not in regular[0].replace(" ", "")):
        raise ResearchError("KB_NOTICE_EQUITY_SECTION_INVALID")
    ranges = re.findall(r"([0-9]{2}:[0-9]{2})\s*~\s*([0-9]{2}:[0-9]{2})", regular[0])
    if len(ranges) != 3:
        raise ResearchError("KB_NOTICE_FACTS_AMBIGUOUS")
    return (*ranges[0], *ranges[1])


def notice_pack(receipt, raw, market, availability):
    if market not in {"KOSPI", "KOSDAQ", "KONEX"} or availability not in AVAILABILITY:
        raise ResearchError("KB_NOTICE_SCOPE_INVALID")
    url = canonical_url(receipt["url"])
    try:
        html = raw.decode("utf-8-sig")
    except UnicodeError:
        html = raw.decode("cp949")
    parser = NoticeText()
    parser.feed(html)
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    # Narrow reviewed year-end layout; never use derivatives or fractional-order windows.
    registered = re.findall(r"등록일\s*([0-9]{4}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2})", text)
    titles = set(re.findall(r"연말\s*시장운영 및 ([0-9]{4})년 (?:연초 )?개장일", text))
    opened = re.findall(r"연초개장일\s*:\s*([0-9]{4})\.\s*([0-9]{1,2})\.\s*([0-9]{1,2})", text)
    closed = re.findall(r"2\.\s*연말휴장일\s*:\s*([0-9]{4})\.\s*([0-9]{1,2})\.\s*([0-9]{1,2})", text)
    if len(registered) != 1 or len(titles) != 1 or len(opened) != 1 or len(closed) != 1:
        raise ResearchError("KB_NOTICE_LAYOUT_UNSUPPORTED")
    times = equity_times(text)
    if "휴장일은 결제일에 포함되지 않음" not in text:
        raise ResearchError("KB_NOTICE_FACTS_AMBIGUOUS")
    opening = datetime(*map(int, opened[0])).date()
    closure = datetime(*map(int, closed[0])).date()
    publication = datetime.strptime(registered[0], "%Y/%m/%d %H:%M:%S").replace(tzinfo=KST)
    observed = utc(receipt["capturedAt"])
    if (str(opening.year) not in titles or closure >= opening or closure.year + 1 != opening.year
            or publication > observed or publication.date() > closure
            or publication.strftime("%Y%m%d") != parse.parse_qs(parse.urlsplit(url).query)["idt"][0]):
        raise ResearchError("KB_NOTICE_DATES_CONFLICT")
    known = publication.isoformat() if availability == "PROVIDER_PUBLICATION_ASSUMED" else receipt["capturedAt"]
    evidence = (url + "; raw-sha256:" + digest(raw) + "; availability=" + availability
                + "; registered-at=" + publication.isoformat())
    return ReferencePack.model_validate({
        "schemaVersion": "SAGOPALGO_MARKET_REFERENCE_V1", "provider": "KB_PUBLIC_YEAR_END_NOTICE",
        "provenance": "PROVIDER_OBSERVATIONS", "reference": evidence, "observedAt": receipt["capturedAt"],
        "sessions": [{"market": market, "businessDate": opening.isoformat(),
                      "openAt": opening.isoformat() + "T" + times[2] + ":00+09:00",
                      "closeAt": opening.isoformat() + "T" + times[3] + ":00+09:00",
                      "knownAt": known, "evidence": evidence}],
        "calendar": [{"businessDate": closure.isoformat(), "businessDay": None, "tradingDay": None,
                      "openDay": False, "settlementDay": False},
                     {"businessDate": opening.isoformat(), "businessDay": None, "tradingDay": None,
                      "openDay": True, "settlementDay": None}],
        "listings": [], "actions": [], "coverage": [],
    })


def import_notice(folder: Path, output: Path, market, availability="OBSERVED_AT"):
    receipt, raw = load_capture(folder)
    pack = notice_pack(receipt, raw, market, availability)
    with output.open("xb") as stream:
        stream.write(canonical(pack.model_dump(mode="json")))
    return pack
