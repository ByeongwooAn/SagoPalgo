"""Cross-check the two public SEIBro date displays without assuming payment completed."""

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
import re
from xml.etree import ElementTree as ET

from .corporate_action_outcomes import capture, require
from .dataset import digest, canonical

SEIBRO = "https://seibro.or.kr"
SERVICE = SEIBRO + "/websquare/engine/proworks/callServletService.jsp"
MARKETS = {"KOSPI": ("11", "유가증권시장"), "KOSDAQ": ("12", "코스닥시장")}
PAYMENT_SCOPE = ("2023-11-01", "2026-11-02")
TASK = "ksd.safe.bip.cnts.Company.process."


def request_spec(route, market, year, role, half=None):
    start = "20231101" if route == "payment" and year == 2023 else f"{year}0101"
    end = "20261102" if year == 2026 else f"{year}1231"
    if half == 1:
        end = f"{year}0630"
    elif half == 2:
        start = f"{year}0701"
    fields = {"RGT_STD_DT_FROM": start, "RGT_STD_DT_TO": end, "ISSUCO_CUSTNO": ""}
    code = MARKETS[market][0]
    if route == "stat":
        page, task = "01041", "EntrFnafInfoPTask"
        action = "divStatInfoListCnt" if role == "count" else "divStatInfoPList"
        fields.update(KOR_SECN_NM="", SECN_KACD="0101", RGT_RSN_DTAIL_SORT_CD="", LIST_TPCD=code,
                      START_PAGE="1", END_PAGE="10000")
    else:
        page, task = "01022", "EntrSkedulPTask"
        action = "costPaymentScheduleInfoListCnt" if role == "count" else "costPaymentScheduleInfoListEL1"
        fields.update(CALTOT_MART_TPCD=code, PAY_COST_TPCD="1", AG_ORG_TPCD="", STARTPAGE="1", ENDPAGE="10000")
    return {"url": SERVICE, "method": "POST",
            "parameters": {"task": TASK + task, "action": action, "fields": fields, "page": page}}


def source_url(page):
    return SEIBRO + f"/websquare/control.jsp?w2xPath=/IPORTAL/user/company/BIP_CNTS{page}V.xml"


def provider_xml(raw, tag):
    require(0 < len(raw) <= 8 * 1024 * 1024 and b"<!" not in raw, "KSD_XML_SIZE_OR_DECLARATION")
    root = ET.fromstring(raw)
    require(root.tag == tag and root.attrib.get("result", "").isdigit(), "KSD_RESPONSE_SHAPE")
    return root


def parse_count(raw):
    root = provider_xml(raw, "result")
    require(root.attrib["result"] == "1" and len(root) == 1 and root[0].tag == "LIST_CNT", "KSD_COUNT_LAYOUT")
    value = root[0].attrib.get("value", "")
    require(value.isascii() and value.isdigit() and 0 <= int(value) <= 10000, "KSD_COUNT_RANGE")
    return int(value)


def parse_rows(raw):
    root = provider_xml(raw, "vector")
    require(0 <= len(root) == int(root.attrib["result"]) <= 10000, "KSD_ROWS_LAYOUT")
    for i, item in enumerate(root):
        require(item.tag == "data" and item.attrib.get("vectorkey") == str(i) and len(item) == 1
                and item[0].tag == "result", "KSD_ROW_LAYOUT")
        result = item[0]
        values = {field.tag: field.get("value") for field in result}
        require(len(values) == len(result) and all(v is not None for v in values.values()), "KSD_ROW_FIELDS")
        yield values


def ksd_date(value):
    require(re.fullmatch(r"[0-9]{8}", value) is not None, "KSD_DATE_FORMAT")
    return date(int(value[:4]), int(value[4:6]), int(value[6:])).isoformat()


def summarize_rows(rows, route, market, fields, evidence):
    start, end = fields["RGT_STD_DT_FROM"], fields["RGT_STD_DT_TO"]
    for row in rows:
        record_date = row["RGT_STD_DT"]
        require(start <= record_date <= end, "KSD_DATE_SCOPE")
        code = row["SHOTN_ISIN"]
        market_label = row["LIST_TPNM" if route == "stat" else "CALTOT_MART_TPCD"]
        require(market_label == MARKETS[market][1], "KSD_MARKET_SCOPE")
        if not re.fullmatch(r"[0-9A-Z]{6}", code):
            continue
        common = row["SECN_DTAIL_KANM" if route == "stat" else "SECN_KACD"] == "보통주"
        if not common:
            continue
        base = {"market": market, "symbol": code, "sourceRowSha256": digest(canonical(row)), "evidence": evidence}
        if route == "payment":
            require(row["PAY_COST_TPCD"] == "배당/분배금" and row["RGT_RACD"] == "배당/분배", "KSD_PAYMENT_SCOPE")
            yield base | {"issuer": row["REP_SECN_NM"], "displayedPaymentDate": ksd_date(record_date)}
        else:
            amount = row["CASH_ALOC_AMT"] or "0"
            require(re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", amount) is not None, "KSD_CASH_AMOUNT")
            if Decimal(amount) > 0:
                paid = row["TH1_PAY_TERM_BEGIN_DT"]
                yield base | {"issuer": row["KOR_SECN_NM"], "recordDate": ksd_date(record_date),
                              "displayedPaymentDate": ksd_date(paid) if paid else None,
                              "cashAmountPerShare": amount, "distributionType": row["RGT_RSN_DTAIL_SORT_NM"]}


def cross_check(stat, payment):
    schedule, stat_by_date, other_dates = defaultdict(list), defaultdict(list), defaultdict(set)

    def key(row):
        return row["market"], row["symbol"], row["displayedPaymentDate"]

    for row in payment:
        schedule[key(row)].append(row)
        other_dates[row["market"], row["symbol"]].add(row["displayedPaymentDate"])
    for row in stat:
        stat_by_date[key(row)].append(row)
    results = []
    for row in stat:
        identity = key(row)
        candidates = schedule[identity]
        displayed = row["displayedPaymentDate"]
        if displayed is None:
            status = "PAYMENT_DATE_MISSING"
        elif not PAYMENT_SCOPE[0] <= displayed <= PAYMENT_SCOPE[1]:
            status = "PAYMENT_DATE_OUTSIDE_SCOPE"
        elif len(candidates) > 1 or len(stat_by_date[identity]) > 1:
            status = "AMBIGUOUS_SCHEDULE_LINK"
        elif len(candidates) == 1:
            status = "DISPLAYED_DATE_AGREES"
        else:
            status = "PAYMENT_SCHEDULE_LINK_MISSING"
        results.append(row | {"status": status, "scheduleMatches": candidates, "actualPaymentDate": None,
                              "otherPaymentDates": sorted(other_dates[identity[:2]]) if
                              status == "PAYMENT_SCHEDULE_LINK_MISSING" else []})
    unmatched = [row for row in payment if key(row) not in stat_by_date]
    return {"dividendRows": results, "unmatchedScheduleRows": unmatched,
            "dividendCounts": dict(Counter(row["status"] for row in results))}


def recheck_stat(job, pins, at, market, year, annual, expected):
    evidence, observed, total, used = [], Counter(), 0, set()
    for half in (1, 2):
        prefix = f"ksd-recheck-{market}-{year}-h{half}"
        count, count_proof = capture(job, pins, prefix + "-count", request_spec("stat", market, year, "count", half), at)
        spec = request_spec("stat", market, year, "rows", half)
        raw, row_proof = capture(job, pins, prefix + "-rows", spec, at)
        rows, count = list(parse_rows(raw)), parse_count(count)
        used.update((prefix + "-count", prefix + "-rows"))
        fields = spec["parameters"]["fields"]
        require(all(fields["RGT_STD_DT_FROM"] <= row["RGT_STD_DT"] <= fields["RGT_STD_DT_TO"] for row in rows),
                "KSD_RECHECK_DATE_SCOPE")
        evidence.append({"half": half, "reportedCount": count, "returnedRows": len(rows),
                         "countEvidence": count_proof, "rowEvidence": row_proof})
        total += count
        observed.update(digest(canonical(row)) for row in rows)
    annual_rows = Counter(digest(canonical(row)) for row in annual)
    return {"annualCountMatchesHalfCounts": expected == total, "sameRowsAcrossQueries": annual_rows == observed,
            "annualOnlyRows": sum((annual_rows - observed).values()),
            "halfOnlyRows": sum((observed - annual_rows).values()), "halves": evidence}, used


def audit(job, pins, at):
    selected = defaultdict(list)
    partitions, used = [], set()
    for route in ("stat", "payment"):
        for market in MARKETS:
            for year in range(2023, 2027):
                count_name, rows_name = (f"ksd-{route}-{market}-{year}-{role}" for role in ("count", "rows"))
                count, count_proof = capture(job, pins, count_name, request_spec(route, market, year, "count"), at)
                spec = request_spec(route, market, year, "rows")
                raw, proof = capture(job, pins, rows_name, spec, at)
                count, rows = parse_count(count), list(parse_rows(raw))
                used.update((count_name, rows_name))
                entry = {"route": route, "market": market, "year": year, "reportedCount": count,
                         "returnedRows": len(rows), "countAgrees": count == len(rows),
                         "countEvidence": count_proof, "rowEvidence": proof}
                if route == "stat" and count != len(rows):
                    entry["halfYearRecheck"], rechecked = recheck_stat(job, pins, at, market, year, rows, count)
                    used.update(rechecked)
                partitions.append(entry)
                evidence = proof | {"sourceUrl": source_url(spec["parameters"]["page"])}
                selected[route].extend(summarize_rows(rows, route, market, spec["parameters"]["fields"], evidence))
    require(used == set(pins), "KSD_CAPTURE_SCOPE")
    return cross_check(selected["stat"], selected["payment"]) | {"partitions": partitions}
