"""Compare dated KRX/KSD notices and the KIS ledger contract with historical rule candidates."""
import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta
import json
from pathlib import Path
import re

from . import calendar_flag_audit as flags, calendar_rule_evidence as rules, market_calendar_evidence as market_source
from .calendar_fetch import PATH as KIS_PATH
from .dataset import canonical, digest, read_bytes, read_json
from .history import day
from .models import ResearchError, utc
from .session_notice_inventory import body_path, viewer_documents


SCHEMA = "SAGOPALGO_CALENDAR_EXCEPTION_AUDIT_V1"
KIND = "https://kind.krx.co.kr"
KSD = "https://www.ksd.or.kr/ko/api"
KIS_GUIDE = "https://apiportal.koreainvestment.com/api/apis/public/detail?accessUrl=" + KIS_PATH.replace("/", "%2F")
MARKET_NAMES = {"KOSPI": ("유가증권시장", "99340"), "KOSDAQ": ("코스닥시장", "71985")}
FIELDS = ("krxTradingSchedule", "standardSettlementCalendar", "standardSettlementForTrade")
KIS_FIELDS = {
    "bzdy_yn": ("businessDay", "FINANCIAL_INSTITUTION_BUSINESS_DAY", "금융기관이 업무를 하는 날"),
    "tr_day_yn": ("tradingDay", "SECURITIES_SERVICES_DAY", "입출금, 이체"),
    "opnd_yn": ("openDay", "STOCK_MARKET_OPEN_DAY", "주식시장이 개장되는 날"),
    "sttl_day_yn": ("settlementDay", "STOCK_SETTLEMENT_DAY", "주식을 인수하고 돈을 지불하는 날"),
}


def read_capture(cache, key, expected):
    if not re.fullmatch(r"[a-z0-9-]{1,60}", key):
        raise ResearchError("CALENDAR_EXCEPTION_SOURCE_ID")
    receipt_bytes = read_bytes(cache / key / "receipt.json")
    raw = read_bytes(cache / key / "body")
    receipt = read_json(receipt_bytes)
    if (digest(receipt_bytes) != expected or digest(raw) != receipt["bodySha256"]
            or receipt["status"] != "COMPLETE" or len(raw) > market_source.LIMIT
            or utc(receipt["startedAt"]) > utc(receipt["capturedAt"])):
        raise ResearchError("CALENDAR_EXCEPTION_CAPTURE_MISMATCH")
    return receipt, raw


def captured_fact(captures, key, dependencies=()):
    receipt, _ = captures[key]
    related = [captures[item][0] for item in dependencies]
    return {
        "sourceUrl": receipt["url"], "rawSha256": receipt["bodySha256"],
        "knownAt": max((r["capturedAt"] for r in [receipt, *related]), key=utc),
    }


def krx_notice(captures, key, market):
    receipt, raw = captures[key]
    name, form = MARKET_NAMES[market]
    if not re.fullmatch(fr"{re.escape(KIND)}/external/(?:[0-9]+/)+{form}\.htm", receipt["url"]):
        raise ResearchError("CALENDAR_EXCEPTION_KRX_IDENTITY")
    related = []
    if key + "-viewer" in captures or key + "-route" in captures:
        viewer_key, route_key = key + "-viewer", key + "-route"
        viewer, route = captures[viewer_key], captures[route_key]
        documents = viewer_documents(viewer[1])
        if (not re.fullmatch(fr"{re.escape(KIND)}/common/disclsviewer\.do\?acptno=[0-9]{{14}}&method=search",
                             viewer[0]["url"]) or len(documents) != 1 or documents[0]["correctionMarked"]):
            raise ResearchError("CALENDAR_EXCEPTION_KRX_VIEWER")
        document = documents[0]["document"]
        if (route[0]["url"] != KIND + "/common/disclsviewer.do" or route[0]["method"] != "POST"
                or route[0]["parameters"] != {"method": "searchContents", "docNo": document}
                or body_path(route[1], document) != receipt["url"]):
            raise ResearchError("CALENDAR_EXCEPTION_KRX_ROUTE")
        related = [viewer_key, route_key]
    text = re.sub(r"\s+", "", market_source.text(raw))
    match = re.fullmatch(fr"::{form}_{name}휴장안내{name}휴장안내1\.휴장일자(.+?)2\.휴장사유.+?"
                         fr"3\.대상시장(.+?)4\.근거규정{name}업무규정제5조", text)
    if not match or name not in match[2] or ("주식" not in match[2] if market == "KOSPI" else "전체" not in match[2]):
        raise ResearchError("CALENDAR_EXCEPTION_KRX_SCOPE")
    dates = re.findall(r"([0-9]{4})년([0-9]{1,2})월([0-9]{1,2})일\([월화수목금토일]\)", match[1])
    if not dates or len(dates) != len(match[1].split(",")):
        raise ResearchError("CALENDAR_EXCEPTION_KRX_DATES")
    return captured_fact(captures, key, related), [date(*map(int, parts)).isoformat() for parts in dates]


def ksd_notice(captures, key, year, cache, expected_text):
    receipt, raw = captures[key]
    detail_key, files_key = f"ksd-{year}-detail", f"ksd-{year}-attachments"
    detail_receipt, detail_raw = captures[detail_key]
    files_receipt, files_raw = captures[files_key]
    detail, files = read_json(detail_raw), read_json(files_raw)
    post = detail["body"]
    attachment, post_id = post["atchFileId"], post["nttId"]
    board = "KR_NOT_000003"
    if (str(detail["status"]) != "200" or str(files["status"]) != "200" or post["bbsId"] != board
            or not post["frstRegistPnttm"].startswith(year + "12") or not re.search(r"연말.*주식.*유의사항", post["bbsSj"])
            or detail_receipt["url"] != f"{KSD}/content/{post_id}?menuId=KR_ABT_070200"
            or files_receipt["url"] != f"{KSD}/content/attach/{attachment}?fileStreCours={board}"
            or receipt["url"] != f"{KSD}/download/attach?atchFileId={attachment}&fileSn=1&fileStreCours={board}"
            or not any(f["atchFileId"] == attachment and f["fileSn"] == 1 and f["fileStreCours"] == board
                       and f["fileExtsn"] == ".hwp" for f in files["body"]["list"])
            or not raw.startswith(bytes.fromhex("d0cf11e0a1b11ae1"))):
        raise ResearchError("CALENDAR_EXCEPTION_KSD_IDENTITY")
    text_raw = read_bytes(cache / key / "text.txt")
    if len(text_raw) > market_source.LIMIT or digest(text_raw) != expected_text:
        raise ResearchError("CALENDAR_EXCEPTION_KSD_TEXT_HASH")
    text = text_raw.decode("utf-8")
    first = re.findall(r"올해 마지막 영업일\*인 12월 ([0-9]{1,2})일\([월화수목금토일]\)에 결제\*\*가"
                       r" 이루어지기 위해서는 12월 ([0-9]{1,2})일\([월화수목금토일]\)까지", text)
    second = re.findall(r"매수일로부터 2영업일에 결제 \(12월 ([0-9]{1,2})일 매수분은 "
                        r"([0-9]{4})년 1월 ([0-9]{1,2})일에 결제\)", text)
    if (len(first) != 1 or len(second) != 1 or int(second[0][1]) != int(year) + 1
            or "12월 결산 상장법인" not in text or "한국거래소의 증권시장" not in text
            or "청산결제기획팀" not in text):
        raise ResearchError("CALENDAR_EXCEPTION_KSD_SCHEDULE")
    y = int(year)
    settle, trade = map(int, first[0])
    next_trade, next_year, next_settle = map(int, second[0])
    pairs = [(date(y, 12, trade), date(y, 12, settle)), (date(y, 12, next_trade), date(next_year, 1, next_settle))]
    if not pairs[0][0] < pairs[1][0] <= pairs[0][1] < pairs[1][1]:
        raise ResearchError("CALENDAR_EXCEPTION_KSD_DATES")
    return (captured_fact(captures, key, (detail_key, files_key)),
            [(trade.isoformat(), settle.isoformat()) for trade, settle in pairs])


def kis_guide(captures):
    receipt, raw = captures["kis-guide"]
    guide = read_json(raw)
    records = {(r["bodyType"], r["propertyCd"]): r["description"] for r in guide["apiPropertys"]}
    request_fields = {code for location, code in records if location == "req_b"}
    response_fields = {code for location, code in records if location == "res_b"}
    if (receipt["url"] != KIS_GUIDE or guide["accessUrl"] != KIS_PATH or guide["httpMethod"] != "GET"
            or guide["name"] != "국내휴장일조회[국내주식-040]" or records["req_h", "tr_id"] != "CTCA0903R"
            or len(records) != len(guide["apiPropertys"])
            or request_fields != {"BASS_DT", "CTX_AREA_NK", "CTX_AREA_FK"}
            or response_fields != {*KIS_FIELDS, "bass_dt", "wday_dvsn_cd", "rt_cd", "msg_cd", "msg1", "output"}
            or any(marker not in records["res_b", code] for code, (_, _, marker) in KIS_FIELDS.items())
            or "opnd_yn" not in guide["apiSummary"] or "다음조회 불가" not in records["res_h", "tr_cont"]):
        raise ResearchError("CALENDAR_EXCEPTION_KIS_GUIDE_SCOPE")
    return {
        **captured_fact(captures, "kis-guide"), "trId": "CTCA0903R",
        "fields": {code: {"normalizedField": field, "meaning": meaning}
                   for code, (field, meaning, _) in KIS_FIELDS.items()},
        "orderCalendarField": "opnd_yn", "marketScope": "DOMESTIC_NO_EXPLICIT_MARKET",
        "perMarketApplicability": "UNKNOWN", "continuationDocumentedSupported": False,
    }


def comparison(candidate, claims, evidence, cutoff=None):
    if cutoff is not None:
        claims = [item for item in claims if utc(evidence[item["sourceId"]]["knownAt"]) <= cutoff]
        if candidate["knownAt"] is None or utc(candidate["knownAt"]) > cutoff:
            candidate = rules.value("UNKNOWN")
    supported = {item["value"] for item in claims}
    value = candidate["value"]
    if len(supported) > 1 or candidate["status"] == "CONFLICT" or (value is not None and supported and value not in supported):
        status = "CONFLICT"
    elif value is not None and value in supported:
        status = "CONFIRMED"
    else:
        status = "UNKNOWN"
    return {"status": status, "value": value if status == "CONFIRMED" else None,
            "candidate": candidate, "claims": claims}


def claim(source, value):
    return {"sourceId": source, "value": value}


def build(manifest_path, rule_path, flag_path, cache):
    manifest = read_json(read_bytes(manifest_path))
    rule_raw, flag_raw = read_bytes(rule_path), read_bytes(flag_path)
    if (manifest["schemaVersion"] != SCHEMA + "_INPUT" or digest(rule_raw) != manifest["ruleSha256"]
            or digest(flag_raw) != manifest["flagSha256"]):
        raise ResearchError("CALENDAR_EXCEPTION_INPUT_HASH")
    baseline, prior = read_json(rule_raw), read_json(flag_raw)
    start, end = baseline["startDate"], baseline["endDate"]
    if (baseline["schemaVersion"] != rules.SCHEMA or prior["schemaVersion"] != flags.SCHEMA
            or baseline["calendarSha256"] != digest(flag_raw) or (start, end) != (prior["startDate"], prior["endDate"])):
        raise ResearchError("CALENDAR_EXCEPTION_INPUT_SCOPE")

    captures = {key: read_capture(cache, key, sha) for key, sha in manifest["captureReceiptSha256"].items()}
    evidence = {key: source for key, source in prior["marketEvidence"].items() if source["kind"] == "DATED_MARKET_NOTICE"}
    claims = defaultdict(list)
    for key in captures:
        match = re.fullmatch(r"krx-(kospi|kosdaq)-[0-9]{8}", key)
        if match:
            market = match[1].upper()
            source, dates = krx_notice(captures, key, market)
            evidence[key] = {**source, "kind": "KRX_DATED_CLOSURE_NOTICE", "markets": [market]}
            for stamp in dates:
                claims[market, stamp, FIELDS[0]].append(claim(key, False))
    for key, text_hash in manifest["ksdTextSha256"].items():
        match = re.fullmatch(r"ksd-([0-9]{4})-press", key)
        if not match:
            raise ResearchError("CALENDAR_EXCEPTION_KSD_SOURCE_ID")
        source, pairs = ksd_notice(captures, key, match[1], cache, text_hash)
        evidence[key] = {**source, "kind": "KSD_DATED_YEAR_END_SETTLEMENT_GUIDANCE", "markets": list(flags.MARKETS)}
        for market in flags.MARKETS:
            for trade, settle in pairs:
                claims[market, trade, FIELDS[2]].append(claim(key, settle))
                claims[market, settle, FIELDS[1]].append(claim(key, True))
    if any(not start <= stamp <= end for _, stamp, _ in claims):
        raise ResearchError("CALENDAR_EXCEPTION_CLAIM_OUTSIDE_SCOPE")

    markets = {}
    expected_dates = [(day(start) + timedelta(days=i)).isoformat() for i in range((day(end) - day(start)).days + 1)]
    for market in flags.MARKETS:
        base_rows = baseline["markets"][market]["rows"]
        prior_rows = prior["marketReports"][market]["rows"]
        if any([r["businessDate"] for r in rows] != expected_dates for rows in (base_rows, prior_rows)):
            raise ResearchError("CALENDAR_EXCEPTION_DATE_GAP")
        rows = []
        for original, old in zip(base_rows, prior_rows):
            stamp = original["businessDate"]
            for field, flag in zip(FIELDS, ("openDay", "settlementDay")):
                claims[market, stamp, field].extend(item for item in old["fields"][flag]["claims"]
                                                   if item["sourceId"] in evidence)
            rows.append({"businessDate": stamp, **{
                field: comparison(original[field], claims[market, stamp, field], evidence) for field in FIELDS
            }})
        markets[market] = {"rows": rows, "summary": {field: dict(Counter(r[field]["status"] for r in rows))
                                                    for field in FIELDS}}
    guide = kis_guide(captures)
    observed = prior["providerObservations"]
    if observed is None or observed["scope"] != "DOMESTIC_NO_EXPLICIT_MARKET" or observed["appliedToMarketFlags"]:
        raise ResearchError("CALENDAR_EXCEPTION_KIS_SAMPLE_SCOPE")
    provider = {
        "guide": guide, "sample": observed, "comparisonKnownAt": max(guide["knownAt"], observed["knownAt"], key=utc),
        "continuationAssessment": "GUIDE_AND_OBSERVED_HEADER_DISAGREE" if observed["hasMore"] else "NO_SIGNAL_OBSERVED",
        "continuationSuccessVerified": False, "appliedToMarketFlags": False,
    }
    return {
        "schemaVersion": SCHEMA, "ruleSha256": digest(rule_raw), "flagSha256": digest(flag_raw),
        "startDate": start, "endDate": end, "markets": markets, "evidence": evidence, "provider": provider,
        "historicalFirstPublicationConfirmed": False, "settlementExceptionsVerifiedForAllDates": False,
        "actualSettlementConfirmed": False, "usableForTraining": False, "usableForTrading": False,
    }


def as_of(report, market, stamp, at):
    day(stamp)
    cutoff = utc(at)
    if market not in flags.MARKETS or not report["startDate"] <= stamp <= report["endDate"]:
        raise ResearchError("CALENDAR_EXCEPTION_QUERY_OUTSIDE_SCOPE")
    row = next(item for item in report["markets"][market]["rows"] if item["businessDate"] == stamp)
    fields = {field: comparison(row[field]["candidate"], row[field]["claims"], report["evidence"], cutoff)
              for field in FIELDS}
    provider = report["provider"]
    observed = None
    if utc(provider["comparisonKnownAt"]) <= cutoff:
        sample = provider["sample"]
        entry = next((r for r in sample["rows"] if r["businessDate"] == stamp), None)
        if entry is not None:
            observed = {field: entry[field] for field in flags.FLAGS}
            observed.update(scope=sample["scope"], bodySha256=sample["bodySha256"], knownAt=sample["knownAt"])
    return {"market": market, "businessDate": stamp, "asOf": cutoff.isoformat(), **fields, "kisObservation": observed,
            "usableForTrading": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "audit", "as-of"))
    for name in ("manifest", "rule-report", "flag-report", "cache", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--market", choices=flags.MARKETS)
    parser.add_argument("--date")
    parser.add_argument("--at")
    args = parser.parse_args(argv)
    if args.command == "as-of" and not all((args.market, args.date, args.at)):
        parser.error("as-of requires --market, --date and --at")
    try:
        report = build(args.manifest, args.rule_report, args.flag_report, args.cache)
        encoded = canonical(report)
        if args.command == "build":
            with args.output.open("xb") as stream:
                stream.write(encoded)
        elif read_bytes(args.output) != encoded:
            raise ResearchError("CALENDAR_EXCEPTION_REPORT_MISMATCH")
        result = (as_of(report, args.market, args.date, args.at) if args.command == "as-of" else
                  {"reportSha256": digest(encoded), "markets": {k: v["summary"] for k, v in report["markets"].items()}})
        print(canonical(result).decode("utf-8"))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(json.dumps({"diagnostic": str(error) if isinstance(error, ResearchError) else "CALENDAR_EXCEPTION_INPUT_INVALID"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
