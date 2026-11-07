"""Apply verified market and clearing rules to historical calendar candidates offline."""
import argparse
from collections import Counter
from datetime import timedelta
import json
from pathlib import Path
import re

from . import calendar_flag_audit as flags, historical_session_rules as rules
from .dataset import canonical, digest, read_bytes, read_json
from .history import day
from .models import ResearchError, utc
from .rule_effective_evidence import body


CLEARING_TITLE = "증권시장 청산결제 업무규정"
CLEARING_EDITIONS = (
    ("210018187", 0, "2287", "2025-03-04"),
    ("210185757", 1, "2418", "2026-04-27"),
)
LEGACY = {"KOSPI": "7", "KOSDAQ": "7bu2"}
SCHEMA = "SAGOPALGO_CALENDAR_RULE_EVIDENCE_V1"
ACCEPTED_OPEN = {"EXPLICIT_SCHEDULE", "RECONSTRUCTED"}


def clause(raw, book, anchor):
    text = body(raw)
    blocks = re.findall(fr'<a name="bon{anchor}"[^>]*>.*?(?=<a name="bon[0-9]|\Z)', text, re.S)
    identity = re.findall(fr"printJo\('([0-9]+)','[0-9]+','bon{anchor}'\)", text)
    if len(blocks) != 1 or identity != [book]:
        raise ResearchError("CALENDAR_RULE_CLAUSE_IDENTITY")
    return re.sub(r"\s+", "", rules.html_text(blocks[0]))


def holiday_clause(raw, book, market):
    value = clause(raw, book, "5")
    action = "매매거래를하지아니한다" if market == "KOSPI" else "시장을휴장한다"
    year_end = "12월31일" if market == "KOSPI" else "연말의1일간"
    if (not value.startswith("제5조(휴장)") or not all(word in value for word in (
            action, year_end, "토요일", "공휴일", "시장관리상필요"))
            or not any(word in value for word in ("근로자의날", "노동절"))):
        raise ResearchError("CALENDAR_HOLIDAY_RULE_REVIEW")
    return digest(value.encode())


def settlement_clause(raw, book, anchor):
    value = clause(raw, book, anchor)
    title = {"6": "제6조(대상매매거래)", "7": "제7조(매매거래의종류)",
             "7bu2": "제7조의2(매매거래의종류)"}[anchor]
    count_basis = "휴장일을제외하고계산한다" if anchor == "6" else "일수의계산시휴장일은제외한다"
    trade_basis = "체결한날을포함하여" if anchor == "6" else "체결한날부터기산하여"
    if (not value.startswith(title) or not all(word in value for word in (
            "보통거래", trade_basis + "3일째되는날에결제", count_basis, "결제일을변경할수있다",
            "세칙에서정하는경우" if anchor != "6" else "세칙으로정하는경우"))):
        raise ResearchError("CALENDAR_SETTLEMENT_RULE_REVIEW")
    return digest(value.encode())


def clearing_rules(folder, expected_hashes):
    facts = {}
    for book, revision, number, effective in CLEARING_EDITIONS:
        receipt = read_json(read_bytes(folder / book / "receipt.json"))
        raw = read_bytes(folder / book / "body.html")
        if (receipt.get("status") != "COMPLETE" or receipt.get("url") != rules.VIEW
                or receipt.get("method") != "POST"
                or receipt.get("parameters") != {"bookid": book, "noformyn": "N", "oldyn": "Y"}
                or digest(raw) != expected_hashes.get(book) or receipt.get("bodySha256") != expected_hashes.get(book)
                or utc(receipt["startedAt"]) > utc(receipt["capturedAt"]) or len(raw) > rules.LIMIT):
            raise ResearchError("CALENDAR_CLEARING_CAPTURE_MISMATCH")
        text = body(raw)
        titles = re.findall(r'<p class="title">(.*?)</p>', text, re.S)
        versions = re.findall(r'<p class="selBox"[^>]*>(?:\(타\))?제([0-9]+)차', text)
        headers = re.findall(r'<p class="jang"[^>]*>\[(.*?)</p>', text, re.S)
        ey, em, ed = map(int, effective.split("-"))
        pattern = fr"규정제{number}호<시행일:{ey}\.{em}\.{ed}\.?\s*>\]"
        if ([rules.html_text(title) for title in titles] != [CLEARING_TITLE] or versions != [str(revision)]
                or len(headers) != 1 or not re.search(pattern, re.sub(r"\s+", "", rules.html_text(headers[0])))):
            raise ResearchError("CALENDAR_CLEARING_BODY_IDENTITY")
        scope = clause(raw, book, "2")
        holidays = clause(raw, book, "3")
        if not all(word in scope for word in ("유가증권시장", "코스닥시장")) or not all(word in holidays for word in (
                "제3조(휴장일)", "토요일", "공휴일", "청산업무를수행하지아니한다", "청산업무를할수있다")):
            raise ResearchError("CALENDAR_CLEARING_SCOPE_REVIEW")
        facts[book] = {
            "bookId": book, "ruleNumber": number, "effectiveDate": effective, "knownAt": receipt["capturedAt"],
            "bodySha256": receipt["bodySha256"], "holidayClauseSha256": digest(holidays.encode()),
            "settlementClauseSha256": settlement_clause(raw, book, "6"),
            "marketScope": list(flags.MARKETS), "ruleUrl": rules.VIEW,
            "exceptionPossible": True,
        }
    return facts


def market_rules(rule_report, rules_cache, effective_cache):
    facts = {}
    for version in rule_report["versions"]:
        expected = version["expected"]
        book, market = expected["bookId"], expected["market"]
        effective = version.get("resolvedEffectiveDate", expected["effectiveDate"])
        if book in facts or not version["identityConfirmed"] or market not in LEGACY:
            raise ResearchError("CALENDAR_MARKET_RULE_IDENTITY")
        if book == "210016900":
            raw = read_bytes(effective_cache / "kosdaq-2280-archived" / "body.html")
        else:
            _, raw = rules.audit_capture(rules_cache, book)
        if digest(raw) != version["bodySha256"]:
            raise ResearchError("CALENDAR_MARKET_RULE_HASH")
        day(effective)
        fact = {
            "bookId": book, "market": market, "ruleNumber": expected["ruleNumber"], "effectiveDate": effective,
            "knownAt": version["knownAt"], "bodySha256": version["bodySha256"], "ruleUrl": rules.VIEW,
            "holidayClauseSha256": holiday_clause(raw, book, market),
        }
        if effective < CLEARING_EDITIONS[0][3]:
            fact["settlementClauseSha256"] = settlement_clause(raw, book, LEGACY[market])
        facts[book] = fact
    return facts


def value(status, item=None, known=None, books=()):
    return {"status": status, "value": item, "knownAt": known, "bookIds": sorted(set(books))}


def date_rows(calendar, periods, facts, clearing, evidence):
    result = []
    previous = None
    for row in calendar:
        date = row["businessDate"]
        current_date = day(date)
        if previous is not None and current_date != previous + timedelta(days=1):
            raise ResearchError("CALENDAR_RULE_DATE_GAP")
        previous = current_date
        active = [p for p in periods if p["startDate"] <= date <= p["endDate"]]
        if len(active) != 1 or not active[0]["continuityConfirmed"]:
            raise ResearchError("CALENDAR_MARKET_RULE_PERIOD_GAP")
        books = active[0]["bookIds"]
        opening = row["fields"]["openDay"]
        if not books or any(facts[book]["effectiveDate"] > date for book in books):
            raise ResearchError("CALENDAR_MARKET_RULE_EFFECTIVE_DATE")
        if opening["status"] not in ACCEPTED_OPEN:
            unknown = value("UNKNOWN")
            result.append({"businessDate": date, "krxTradingSchedule": unknown, "standardSettlementCalendar": unknown})
            continue
        known = max([*(facts[book]["knownAt"] for book in books),
                     *(evidence[claim["sourceId"]]["knownAt"] for claim in opening["claims"])], key=utc)
        opened = opening["value"]
        trade_status = "DATED_SCHEDULE_WITH_RULE" if opening["status"] == "EXPLICIT_SCHEDULE" else (
            "RULE_OPEN_CANDIDATE" if opened else "RULE_HOLIDAY")
        trading = value(trade_status, opened, known, books)
        current = [item for item in clearing.values() if item["effectiveDate"] <= date]
        settlement_books = books
        if current:
            edition = max(current, key=lambda item: item["effectiveDate"])
            known = max(known, edition["knownAt"], key=utc)
            settlement_books = [*books, edition["bookId"]]
        elif not all("settlementClauseSha256" in facts[book] for book in books):
            raise ResearchError("CALENDAR_LEGACY_SETTLEMENT_RULE_GAP")
        explicit = row["fields"]["settlementDay"]
        if explicit["claims"]:
            known = max(known, *(evidence[claim["sourceId"]]["knownAt"] for claim in explicit["claims"]), key=utc)
        if explicit["status"] == "CONFLICT" or (
                explicit["status"] == "EXPLICIT_SCHEDULE" and explicit["value"] is not opened):
            settlement = value("CONFLICT", known=known, books=settlement_books)
        else:
            settlement = value("STANDARD_DAY_CANDIDATE" if opened else "RULE_EXCLUDED",
                               opened, known, settlement_books)
        result.append({"businessDate": date, "krxTradingSchedule": trading, "standardSettlementCalendar": settlement})
    return result


def attach_trade_dates(rows):
    for index, row in enumerate(rows):
        initial = row["standardSettlementCalendar"]
        trading = row["krxTradingSchedule"]
        if trading["value"] is False:
            row["standardSettlementForTrade"] = value("NO_SCHEDULED_TRADE", known=trading["knownAt"], books=trading["bookIds"])
            continue
        if initial["value"] is not True:
            row["standardSettlementForTrade"] = value("UNCONFIRMED_CALENDAR")
            continue
        count, known, books = 0, initial["knownAt"], set(initial["bookIds"])
        outcome = None
        for following in rows[index + 1:]:
            candidate = following["standardSettlementCalendar"]
            if candidate["value"] is None:
                outcome = value("UNCONFIRMED_CALENDAR")
                break
            known = max(known, candidate["knownAt"], key=utc)
            books.update(candidate["bookIds"])
            count += candidate["value"]
            if count == 2:
                outcome = value("T_PLUS_TWO_CANDIDATE", following["businessDate"], known, books)
                break
        row["standardSettlementForTrade"] = outcome or value("AFTER_SCOPE", known=known, books=books)


def build(manifest, calendar_path, rule_path, rules_cache, effective_cache, clearing_cache):
    scope = read_json(read_bytes(manifest))
    cal_bytes, rule_bytes = read_bytes(calendar_path), read_bytes(rule_path)
    if (scope["schemaVersion"] != "SAGOPALGO_CALENDAR_RULE_EVIDENCE_INPUT_V1"
            or scope["calendarSha256"] != digest(cal_bytes) or scope["sessionRuleSha256"] != digest(rule_bytes)):
        raise ResearchError("CALENDAR_RULE_INPUT_HASH")
    calendar, rule_report = read_json(cal_bytes), read_json(rule_bytes)
    if (calendar["schemaVersion"] != flags.SCHEMA or rule_report["schemaVersion"] != "SAGOPALGO_SESSION_RULE_REPORT_V2"
            or any(calendar[k] != rule_report[k] for k in ("startDate", "endDate"))):
        raise ResearchError("CALENDAR_RULE_INPUT_SCOPE")
    facts = market_rules(rule_report, rules_cache, effective_cache)
    clearing = clearing_rules(clearing_cache, scope["clearingBodySha256"])
    markets = {}
    for market in flags.MARKETS:
        by_market = {book: fact for book, fact in facts.items() if fact["market"] == market}
        rows = date_rows(calendar["marketReports"][market]["rows"], rule_report["markets"][market]["rulePeriods"],
                         by_market, clearing, calendar["marketEvidence"])
        if not rows or (rows[0]["businessDate"], rows[-1]["businessDate"]) != (calendar["startDate"], calendar["endDate"]):
            raise ResearchError("CALENDAR_RULE_DATE_GAP")
        attach_trade_dates(rows)
        markets[market] = {
            "brokerBusinessDayStatus": "UNKNOWN_PROVIDER_DEFINITION_REQUIRED",
            "summary": {field: dict(Counter(row[field]["status"] for row in rows)) for field in (
                "krxTradingSchedule", "standardSettlementCalendar", "standardSettlementForTrade")},
            "rows": rows,
        }
    return {
        "schemaVersion": SCHEMA, "calendarSha256": scope["calendarSha256"], "sessionRuleSha256": scope["sessionRuleSha256"],
        "startDate": calendar["startDate"], "endDate": calendar["endDate"], "markets": markets,
        "marketRuleFacts": facts, "clearingRuleFacts": clearing, "settlementExceptionsVerifiedForAllDates": False,
        "actualTradingOrSettlementConfirmed": False, "usableForTrading": False, "usableForTraining": False,
    }


def as_of(report, market, date, at):
    cutoff = utc(at)
    day(date)
    row = next((row for row in report["markets"][market]["rows"] if row["businessDate"] == date), None)
    if row is None:
        raise ResearchError("CALENDAR_RULE_QUERY_OUTSIDE_SCOPE")
    return {"market": market, "businessDate": date, "asOf": cutoff.isoformat(),
            **{key: item if item["knownAt"] and utc(item["knownAt"]) <= cutoff else value("UNKNOWN")
               for key, item in row.items() if key != "businessDate"},
            "brokerBusinessDayStatus": "UNKNOWN_PROVIDER_DEFINITION_REQUIRED", "usableForTrading": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "audit", "as-of"):
        sub = commands.add_parser(command)
        for name in ("manifest", "calendar", "rule-report", "rules-cache", "effective-cache", "clearing-cache", "output"):
            sub.add_argument("--" + name, type=Path, required=True)
        if command == "as-of":
            sub.add_argument("--market", choices=flags.MARKETS, required=True)
            sub.add_argument("--date", required=True)
            sub.add_argument("--at", required=True)
    args = parser.parse_args(argv)
    try:
        report = build(args.manifest, args.calendar, args.rule_report, args.rules_cache, args.effective_cache, args.clearing_cache)
        encoded = canonical(report)
        if args.command == "build":
            with args.output.open("xb") as stream:
                stream.write(encoded)
        elif read_bytes(args.output) != encoded:
            raise ResearchError("CALENDAR_RULE_REPORT_MISMATCH")
        result = (as_of(report, args.market, args.date, args.at) if args.command == "as-of" else
                  {"reportSha256": digest(encoded), "markets": {k: v["summary"] for k, v in report["markets"].items()}})
        print(canonical(result).decode("utf-8"))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(json.dumps({"diagnostic": str(error) if isinstance(error, ResearchError) else "CALENDAR_RULE_INPUT_INVALID"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
