"""Audit KRX stock-issue details and separate common-share notice evidence."""

from collections import Counter, defaultdict
from datetime import date, timedelta
import re

from .action_listing_inventory import ENDPOINT, MARKET_TYPES
from .corporate_action_event_audit import name_key
from .corporate_action_outcomes import capture, require
from .distribution_facts import Node, XForms
from .restructuring_outcomes import DAY, stamp

REASONS = {"주식소각", "감자(주식소각)", "이익소각"}


def detail_spec(process):
    require(re.fullmatch(r"[0-9]{14}", process) is not None, "STOCK_DETAIL_PROCESS_ID")
    return {"method": "POST", "url": ENDPOINT,
            "parameters": {"method": "searchStockIssueDetail", "forward": "searchStockIssueDetail",
                           "bzProcsNo": process, "contnId": process}}


def stock_fields(raw):
    require(len(raw) <= 65536, "STOCK_DETAIL_SIZE")
    parser = XForms()
    parser.feed(raw.decode("utf-8-sig"))
    parser.close()
    fields = {}
    require(len(parser.stack) == 1, "STOCK_DETAIL_LAYOUT")
    for table in parser.root.walk("table"):
        for row in table.walk("tr"):
            cells = [n for n in row.children if isinstance(n, Node) and n.tag in {"th", "td"}]
            require(len(cells) % 2 == 0, "STOCK_DETAIL_LAYOUT")
            for key, value in zip(cells[::2], cells[1::2]):
                label = key.text()
                require(key.tag == "th" and value.tag == "td" and label not in fields, "STOCK_DETAIL_DUPLICATE_FIELD")
                fields[label] = value
    return fields


def signed_quantity(value):
    require(re.fullmatch(r"-?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)", value) is not None, "STOCK_DETAIL_QUANTITY")
    return int(value.replace(",", ""))


def detail_fields(raw, row, scope):
    fields = stock_fields(raw)
    required = {"회사명", "상장일", "상장방식", "발행사유", "발행일", "발행주식수", "누적발행주식수"}
    require(required <= fields.keys(), "STOCK_DETAIL_REQUIRED_FIELDS")
    issuer, listed, listing_type, reason, issued, changed, outstanding = (
        fields[k].text() for k in ("회사명", "상장일", "상장방식", "발행사유", "발행일", "발행주식수", "누적발행주식수"))
    market = MARKET_TYPES[row["market"]][1]
    quantity, balance = signed_quantity(changed), signed_quantity(outstanding)
    identity = (issuer, listed, listing_type, reason, quantity)
    expected = (row["issuer"], row["listingDate"], row["listingType"], row["reason"], row["signedShareChange"])
    if identity != expected or not any(n.attrs.get("alt") == market for n in fields["회사명"].walk("img")):
        return {"status": "STOCK_LISTING_DETAIL_CONFLICT", "detailIdentity": list(identity)}
    require(reason in REASONS and quantity < 0 and balance >= 0, "STOCK_DETAIL_VALUE")
    if not issued:
        return {"status": "STOCK_ISSUE_DATE_MISSING", "stockIssueReportedChange": quantity,
                "stockIssueReportedOutstanding": balance}
    require(date.fromisoformat(issued).isoformat() == issued, "STOCK_ISSUE_DATE_VALUE")
    if issued > listed:
        return {"status": "STOCK_ISSUE_DATE_AFTER_LISTING", "reportedIssueDate": issued}
    status = "CANCELLATION_DATE_UNVERIFIED_SHARE_CLASS" if scope[0] <= issued <= scope[1] else "CANCELLATION_DATE_OUTSIDE_SCOPE"
    return {"status": status, "reportedIssueDate": issued, "stockIssueReportedChange": quantity,
            "stockIssueReportedOutstanding": balance}


def kospi_common_notice(body):
    amount = r"([0-9][0-9,]*)"
    serial = r"(?:\s*\(제\s*[0-9]+회\))?"
    shares = re.findall(r"기명식\s+보통주\s*:?\s*" + amount + r"주\s*→\s*" + amount +
                        r"주" + serial + r"\s*▶?\s*-?\s*변경주식수\s*:\s*-" + amount + "주", body)
    dates = re.findall(r"발행일(?:\(소각일\))?\s*:?\s*(?:▶\s*기명식\s+보통주" + serial + r"\s*:\s*)?" + DAY, body)
    listings = re.findall(r"변경상장일\s*:\s*" + DAY, body)
    symbols = re.findall(r"▶\s*(?:보통주\s+)?표준코드\s*:\s*([A-Z0-9]{12})\s*\(단축코드\s*:\s*A([A-Z0-9]{6})\)", body)
    if not (len(shares) == len(dates) == len(listings) == len(symbols) == 1 and
            re.search(r"변경사유\s*:\s*(?:주식소각|감자\(주식소각\)|이익소각)\s+⑨", body)):
        return None
    before, after, removed = map(signed_quantity, shares[0])
    if before - after != removed or removed <= 0:
        return None
    isin, symbol = symbols[0]
    return {"symbol": symbol, "isin": isin, "after": after, "signedShareChange": -removed,
            "cancellationDate": stamp(dates[0]), "listingDate": stamp(listings[0])}


def kosdaq_common_notice(body, symbol):
    quantity = r"([0-9][0-9,]*)"
    reduced = re.findall(r"보통주\s+A" + symbol + r"\s+-" + quantity, body)
    after = re.findall(r"보통주\s+" + quantity + r"\s+\d{4}-\d{2}-\d{2}", body)
    listing = re.findall(r"5\.\s*상장일\s+(\d{4}-\d{2}-\d{2})", body)
    issue = re.findall(r"보통주\s+주식소각\s+-\s+-" + quantity +
                       r"\s+-\s+(\(['’]\d{2}\.\d{2}\.\d{2}\)|-)(?:\s|$)", body)
    if not (len(reduced) == len(after) == len(listing) == len(issue) == 1 and "발행회수(발행일)" in body):
        return None
    size, issued_label = issue[0]
    if signed_quantity(size) <= 0 or signed_quantity(size) != signed_quantity(reduced[0]):
        return None
    listed = date.fromisoformat(listing[0])
    issued = None
    if issued_label != "-":
        year, month, day = map(int, re.findall(r"[0-9]+", issued_label))
        years = {y for y in (listed.year - 1, listed.year) if y % 100 == year}
        if len(years) != 1:
            return None
        issued = date(years.pop(), month, day)
        if issued > listed:
            return None
    return {"symbol": symbol, "isin": None, "after": signed_quantity(after[0]),
            "signedShareChange": -signed_quantity(size), "cancellationDate": issued.isoformat() if issued else None,
            "listingDate": listing[0]}


def common_notice(market, form, body, symbol):
    if market == "KOSPI" and form == "68155.htm":
        fields = kospi_common_notice(body)
        if fields and fields["symbol"] == symbol:
            return fields
    elif market == "KOSDAQ" and form == "70763.htm":
        return kosdaq_common_notice(body, symbol)
    return None


def gap_targets(rows, candidates):
    by_issuer = defaultdict(list)
    for candidate in candidates:
        if "상장" in candidate["title"] and "소각" in candidate["title"]:
            by_issuer[candidate["market"], name_key(candidate["issuerDisplayName"])].append(candidate)
    result = set()
    for row in rows:
        if row["status"] != "STOCK_ISSUE_DATE_MISSING":
            continue
        start = (date.fromisoformat(row["listingDate"]) - timedelta(days=14)).isoformat()
        for candidate in by_issuer[row["market"], name_key(row["issuer"])]:
            if start <= candidate["listedMinuteKst"][:10] <= row["listingDate"]:
                result.add(candidate["receipt"])
    return result


def notice_links(notices, rows, scope):
    indexed, linked = defaultdict(list), defaultdict(list)
    for row in rows:
        if "stockIssueReportedOutstanding" not in row:
            continue
        key = row["market"], name_key(row["issuer"]), row["listingDate"], row["signedShareChange"]
        indexed[key].append(row)
    for notice in notices:
        if notice["status"] != "COMMON_SHARE_NOTICE_FIELDS":
            continue
        key = notice["market"], name_key(notice["noticeIssuer"]), notice["listingDate"], notice["signedShareChange"]
        candidates = indexed[key]
        if len(candidates) != 1:
            notice["status"] = "STOCK_DETAIL_LINK_MISSING_OR_AMBIGUOUS"
            continue
        row = candidates[0]
        notice["processId"] = row["processId"]
        linked[row["processId"]].append(notice)
    for row in rows:
        related = linked[row["processId"]]
        if not related:
            continue
        symbols = {n["symbol"] for n in related}
        isins = {n["isin"] for n in related if n["isin"]}
        listed_issue_date = row.get("reportedIssueDate")
        notice_dates = {n["cancellationDate"] for n in related if n["cancellationDate"]}
        dates = notice_dates | ({listed_issue_date} if listed_issue_date else set())
        if (len(dates) > 1 or
                any(row["stockIssueReportedOutstanding"] != n["after"] for n in related)):
            status = "CANCELLATION_NOTICE_DETAIL_CONFLICT"
        elif len(symbols) != 1 or len(isins) > 1:
            status = "CANCELLATION_NOTICE_SECURITY_CONFLICT"
        else:
            row.update(symbol=symbols.pop(), isin=next(iter(isins), None), shareClass="COMMON")
            issued = next(iter(dates), None)
            if issued is None:
                status = "COMMON_SHARE_CANCELLATION_DATE_MISSING"
            elif scope[0] <= issued <= scope[1]:
                status = ("COMMON_SHARE_CANCELLATION_CONFIRMED" if listed_issue_date and notice_dates else
                          "COMMON_SHARE_CANCELLATION_DATE_FROM_DETAIL" if listed_issue_date else
                          "COMMON_SHARE_CANCELLATION_DATE_FROM_NOTICE")
                row["actualCancellationDate"] = issued
            else:
                status = "CANCELLATION_DATE_OUTSIDE_SCOPE"
        row["status"] = status
        for notice in related:
            notice["status"] = status


def audit(job, pins, parent, at, scope):
    rows, used = [], set()
    for row in parent["stockListingInventory"]["relevantRows"]:
        if row["reason"] not in REASONS:
            continue
        name = "stock-detail-" + row["processId"]
        require(name not in used, "STOCK_DETAIL_DUPLICATE_TARGET")
        if name in pins:
            raw, proof = capture(job, pins, name, detail_spec(row["processId"]), at)
            fields = detail_fields(raw, row, scope) | {"detailEvidence": proof}
        else:
            fields = {"status": "STOCK_DETAIL_NOT_CAPTURED"}
        rows.append(row | {"shareClass": None, "actualCancellationDate": None, **fields})
        used.add(name)
    require(set(pins) <= used, "STOCK_DETAIL_CAPTURE_SCOPE")
    return rows


def counts(rows):
    return dict(Counter(row["status"] for row in rows))
