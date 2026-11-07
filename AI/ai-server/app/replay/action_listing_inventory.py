"""Read the KIND stock-issue list independently of disclosure title searches."""

from datetime import date
import re

from .corporate_action_outcomes import WINDOWS, capture, require, unique
from .distribution_facts import Node
from .kind_membership_evidence import BASE
from .session_notice_inventory import ListHTML

ENDPOINT = BASE + "/corpgeneral/stockissuelist.do"
MARKET_TYPES = {"KOSPI": ("stockMkt", "유가증권"), "KOSDAQ": ("kosdaqMkt", "코스닥")}
LISTING_TYPES = {"3": "변경상장", "5": "재상장"}


def listing_queries():
    for market in MARKET_TYPES:
        for listing_type in LISTING_TYPES:
            for start, end in WINDOWS:
                yield market, listing_type, start, min(end, "2026-11-02")


def listing_request(market, listing_type, start, end, page):
    return {
        "url": ENDPOINT, "method": "POST",
        "parameters": {"method": "searchStockIssueList", "forward": "searchStockIssueList",
                       "currentPageSize": "100", "pageIndex": str(page), "marketType": MARKET_TYPES[market][0],
                       "listingType": listing_type, "fromDate": start, "toDate": end},
    }


def listing_page(raw, market, listing_type, start, end, page):
    parser = ListHTML()
    parser.feed(raw.decode("utf-8-sig"))
    parser.close()
    infos = [n.text() for n in parser.root.walk("div") if n.attrs.get("class") == "info type-00"]
    require(len(parser.stack) == 1 and len(infos) == 1, "STOCK_LISTING_LAYOUT")
    total, current, pages = (int(x.replace(",", "")) for x in
                             unique(r"전체\s*([0-9,]+)\s*건\s*:\s*(\d+)\s*/\s*(\d+)", infos[0]))
    # KIND represents an empty result as either 1/0 or 1/1.
    require(total <= 2000 and current == page and
            (1 <= page <= pages == (total + 99) // 100 if total else page == 1 and pages in (0, 1)),
            "STOCK_LISTING_PAGE_RANGE")
    rows = []
    for tr in parser.root.walk("tr"):
        cells = [c for c in tr.children if isinstance(c, Node) and c.tag == "td"]
        if not cells or (not total and len(cells) == 1 and "조회" in cells[0].text()):
            continue
        require(len(cells) == 6, "STOCK_LISTING_COLUMNS")
        issuer, listed, kind, quantity, face, reason = (c.text() for c in cells)
        product_suffix, notice_id = unique(r"^fnDetailView(Etf)?\('(\d{14})'\);?$", tr.attrs.get("onclick", ""))
        require(date.fromisoformat(listed).isoformat() == listed and start <= listed <= end and
                kind == LISTING_TYPES[listing_type] and
                (product_suffix == "Etf" or
                 any(n.attrs.get("alt") == MARKET_TYPES[market][1] for n in cells[0].walk("img"))) and
                re.fullmatch(r"-?[0-9][0-9,]*", quantity) is not None, "STOCK_LISTING_ROW")
        rows.append({"market": market, "listingType": kind, "issuer": issuer, "listingDate": listed,
                     "signedShareChange": int(quantity.replace(",", "")), "faceValueDisplay": face,
                     "reason": reason, "processId": notice_id, "exchangeTradedFund": product_suffix == "Etf"})
    require(len(rows) == min(100, max(0, total - (page - 1) * 100)), "STOCK_LISTING_PAGE_ROWS")
    return total, max(1, pages), rows


def inventory(job, pins, at):
    evidence, partitions, used = [], [], set()
    for market, listing_type, start, end in listing_queries():
        page, pages, total, seen = 1, 1, None, set()
        while page <= pages:
            name = f"stock-{market}-{listing_type}-{start}-{page:02}"
            raw, proof = capture(job, pins, name, listing_request(market, listing_type, start, end, page), at)
            used.add(name)
            count, page_count, rows = listing_page(raw, market, listing_type, start, end, page)
            if page == 1:
                total, pages = count, page_count
            require((count, page_count) == (total, pages), "STOCK_LISTING_COUNT_CHANGED")
            for row in rows:
                identity = tuple(row.values())
                require(identity not in seen, "STOCK_LISTING_DUPLICATE_ROW")
                seen.add(identity)
                if not row["exchangeTradedFund"] and re.search("소각|합병|분할", row["reason"]):
                    evidence.append(row | {"evidence": proof, "shareClass": None,
                                           "legalOrCancellationDate": None})
            page += 1
        require(total == len(seen), "STOCK_LISTING_COVERAGE")
        partitions.append({"market": market, "listingType": listing_type, "from": start, "through": end,
                           "rows": total, "pages": pages})
    require(used == set(pins), "STOCK_LISTING_CAPTURE_SCOPE")
    return {"partitions": partitions, "relevantRows": evidence}


def changed_listing(rows, market, issuer, listing_date, reason, signed_change):
    matches = [row for row in rows if
               (row["market"], row["issuer"], row["listingDate"], row["listingType"], row["reason"],
                row["signedShareChange"]) == (market, issuer, listing_date, "변경상장", reason, signed_change)]
    require(len(matches) == 1, "STOCK_LISTING_REVIEWED_CASE_MATCH")
    return matches[0]
