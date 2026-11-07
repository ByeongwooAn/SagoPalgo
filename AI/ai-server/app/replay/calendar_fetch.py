"""One calendar GET per local day/cache. Never recursively pages KIS ledger service."""
from datetime import datetime, timezone
from pathlib import Path
from urllib import parse, request

from .dataset import canonical, digest, read_bytes, read_json
from .history import BASE, KST, LIMIT, atomic_json, day, now
from .models import ResearchError, utc
from .reference import ReferencePack

PATH = "/uapi/domestic-stock/v1/quotations/chk-holiday"
SOURCE = "https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/chk_holiday/chk_holiday.py"


def calendar_reference(raw: bytes, captured_at: str, continuation: str):
    data = read_json(raw)
    if not isinstance(data, dict) or data.get("rt_cd") != "0":
        raise ResearchError("CALENDAR_PROVIDER_REJECTED")
    rows = data.get("output")
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ResearchError("CALENDAR_ROWS_INVALID")
    calendar = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("bass_dt"), str):
            raise ResearchError("CALENDAR_ROW_INVALID")
        at = datetime.strptime(row["bass_dt"], "%Y%m%d").date().isoformat()
        flags = {}
        for original, target in [("bzdy_yn", "businessDay"), ("tr_day_yn", "tradingDay"),
                                 ("opnd_yn", "openDay"), ("sttl_day_yn", "settlementDay")]:
            if row.get(original) not in {"Y", "N"}:
                raise ResearchError("CALENDAR_FLAG_INVALID")
            flags[target] = row[original] == "Y"
        calendar.append({"businessDate": at, **flags})
    dates = sorted(r["businessDate"] for r in calendar)
    coverage = []
    if dates:
        coverage.append({"dimension": "CALENDAR", "startDate": dates[0], "endDate": dates[-1], "scope": "MARKET",
                         "stockCodes": [], "status": "PARTIAL", "evidence": SOURCE + "; observed page only"})
    return ReferencePack.model_validate({"schemaVersion": "SAGOPALGO_MARKET_REFERENCE_V1", "provider": "KIS_CALENDAR",
        "provenance": "PROVIDER_OBSERVATIONS", "reference": SOURCE + "; raw-sha256:" + digest(raw),
        "observedAt": captured_at, "calendar": calendar, "sessions": [], "listings": [], "actions": [], "coverage": coverage})


def audit_cached_calendar(folder: Path, receipt=None):
    """Verify and reparse the captured page without constructing a transport."""
    if receipt is None:
        receipt = read_json(read_bytes(folder / "receipt.json"))
    if not isinstance(receipt, dict) or receipt.get("status") != "COMPLETE":
        raise ResearchError("CALENDAR_DAILY_REQUEST_RESERVED")
    continuation = receipt.get("continuation")
    if (receipt.get("schemaVersion") != "SAGOPALGO_CALENDAR_RECEIPT_V1"
            or type(receipt.get("dailyLimit")) is not int or receipt["dailyLimit"] != 1
            or receipt.get("autoPagination") is not False or not isinstance(continuation, str)
            or len(continuation) > 8 or receipt.get("hasMore") is not (continuation in {"M", "F"})):
        raise ResearchError("CALENDAR_CACHE_TAMPERED")
    day(receipt["basisDate"])
    utc(receipt["capturedAt"])
    raw = read_bytes(folder / "body.json")
    if len(raw) > LIMIT or digest(raw) != receipt.get("bodySha256"):
        raise ResearchError("CALENDAR_CACHE_TAMPERED")
    pack = calendar_reference(raw, receipt["capturedAt"], continuation)
    normalized = read_bytes(folder / "reference.json")
    if normalized != canonical(pack.model_dump(mode="json")) or digest(normalized) != receipt.get("referenceSha256"):
        raise ResearchError("CALENDAR_CACHE_TAMPERED")
    return pack, receipt


def fetch_calendar_once(cache: Path, basis_date: str, transport, at=None):
    basis = day(basis_date)
    clock = at or datetime.now(timezone.utc)
    local_day = clock.astimezone(KST).date().isoformat()
    folder = cache / local_day
    fingerprint = digest(transport.key.encode())
    folder.parent.mkdir(parents=True, exist_ok=True)
    try:
        folder.mkdir()
    except FileExistsError:
        if not (folder / "receipt.json").is_file():
            raise ResearchError("CALENDAR_DAILY_REQUEST_RESERVED") from None
        receipt = read_json(read_bytes(folder / "receipt.json"))
        if not isinstance(receipt, dict) or receipt.get("status") != "COMPLETE" or receipt.get("basisDate") != basis_date or receipt.get("keyFingerprint") != fingerprint:
            raise ResearchError("CALENDAR_DAILY_REQUEST_RESERVED") from None
        pack, _ = audit_cached_calendar(folder, receipt)
        return pack, folder, True
    receipt = {"schemaVersion": "SAGOPALGO_CALENDAR_RECEIPT_V1", "basisDate": basis_date, "localDay": local_day,
               "keyFingerprint": fingerprint, "startedAt": clock.isoformat(), "status": "IN_FLIGHT",
               "dailyLimit": 1, "autoPagination": False}
    atomic_json(folder / "receipt.json", receipt)
    try:
        transport.authenticate()
        query = parse.urlencode({"BASS_DT": basis.strftime("%Y%m%d"), "CTX_AREA_FK": "", "CTX_AREA_NK": ""})
        req = request.Request(BASE + PATH + "?" + query, method="GET", headers={
            "Authorization": "Bearer " + transport.token, "appkey": transport.key, "appsecret": transport.secret,
            "tr_id": "CTCA0903R", "custtype": "P", "Accept": "application/json"})
        with transport.opener.open(req, timeout=20) as response:
            raw = response.read(LIMIT + 1)
            continuation = response.headers.get("tr_cont", "")
        if len(raw) > LIMIT or len(continuation) > 8:
            raise ResearchError("CALENDAR_RESPONSE_LIMIT")
        if any(value.encode() in raw for value in [transport.key, transport.secret, transport.token]):
            raise ResearchError("CALENDAR_SENSITIVE_RESPONSE")
        captured_at = now()
        (folder / "body.json").write_bytes(raw)
        receipt.update(bodySha256=digest(raw), capturedAt=captured_at, continuation=continuation,
                       hasMore=continuation in {"M", "F"})
        pack = calendar_reference(raw, captured_at, continuation)
        normalized = canonical(pack.model_dump(mode="json"))
        (folder / "reference.json").write_bytes(normalized)
        receipt.update(status="COMPLETE", referenceSha256=digest(normalized))
        atomic_json(folder / "receipt.json", receipt)
        return pack, folder, False
    except Exception as exc:
        code = str(exc) if isinstance(exc, ResearchError) else "CALENDAR_REQUEST_FAILED"
        receipt.update(status="FAILED", diagnostic=code, finishedAt=now())
        atomic_json(folder / "receipt.json", receipt)
        raise ResearchError(code) from None
