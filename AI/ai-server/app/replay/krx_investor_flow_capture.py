"""Collect and verify timestamped, personal-local KIS investor-flow receipts."""

import argparse
from datetime import date, datetime, time, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import mkdtemp
from time import sleep
from urllib import error, parse, request

from .calendar_fetch import fetch_calendar_once
from .dataset import digest
from .history import BASE, KST, LIMIT, KisHistoryTransport, atomic_json, job_lock
from .models import ResearchError

TICKERS = ("005930", "000660")
MARKET = "J"
TR_ID = "FHPTJ04160001"
PATH = "/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily"
WINDOWS = {"close": (time(20, 10), time(20, 14, 30), time(20, 15)),
           "next-day": (time(8, 45), time(8, 50), time(8, 55))}
GROUPS = ("prsn", "orgn", "frgn")
QUANTITY_FIELDS = ("shnu_vol", "seln_vol", "ntby_qty")
AMOUNT_FIELDS = ("shnu_tr_pbmn", "seln_tr_pbmn", "ntby_tr_pbmn")
ROOT = Path(__file__).resolve().parents[4]
ARTIFACTS = ROOT / "AI" / "ai-server" / "research-artifacts"


def now():
    return datetime.now(KST)


def window(phase, target):
    local_date = target + timedelta(days=phase == "next-day")
    return tuple(datetime.combine(local_date, value, KST) for value in WINDOWS[phase])


def connection():
    names = ("SAGOPALGO_KIS_BASE_URL", "SAGOPALGO_KIS_APP_KEY", "SAGOPALGO_KIS_APP_SECRET")
    settings = {name: os.getenv(name) for name in names}
    if not all(settings.values()):
        try:
            result = subprocess.run(["docker", "compose", "config", "--environment"],
                                    cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                                    check=True, timeout=15)
        except (OSError, subprocess.SubprocessError, UnicodeError):
            raise ResearchError("FLOW_LOCAL_CONFIGURATION_UNAVAILABLE") from None
        for row in result.stdout.splitlines():
            name, _, value = row.partition("=")
            if name in settings and not settings[name]:
                settings[name] = value
    base, key, secret = (settings[name] for name in names)
    if not base or base.rstrip("/") != BASE:
        raise ResearchError("FLOW_LIVE_MARKET_CONFIGURATION_REQUIRED")
    return FlowTransport(key, secret)


class FlowTransport(KisHistoryTransport):
    def authenticate(self):
        if self.token is None:
            super().authenticate()

    def fetch_flow(self, ticker, target):
        query = parse.urlencode({"FID_COND_MRKT_DIV_CODE": MARKET, "FID_INPUT_ISCD": ticker,
                                 "FID_INPUT_DATE_1": target.strftime("%Y%m%d"),
                                 "FID_ORG_ADJ_PRC": "", "FID_ETC_CLS_CODE": ""})
        req = request.Request(BASE + PATH + "?" + query, headers={
            "Authorization": "Bearer " + self.token, "appkey": self.key, "appsecret": self.secret,
            "tr_id": TR_ID, "custtype": "P", "Accept": "application/json"})
        try:
            response = self.opener.open(req, timeout=7)
        except error.HTTPError as rejection:
            response = rejection
        with response:
            raw = response.read(LIMIT + 1)
            received = now()
            status = response.status
        if len(raw) > LIMIT or any(item.encode() in raw for item in (self.key, self.secret, self.token)):
            raise ResearchError("FLOW_RESPONSE_UNSAFE_TO_STORE")
        return status, raw, received


def open_day(cache, target, transport, clock=now):
    current = clock().astimezone(KST)
    if not (cache / current.date().isoformat()).exists():
        transport.authenticate()
    pack, folder, _ = fetch_calendar_once(cache, target.isoformat(), transport, at=current)
    match = [row for row in pack.calendar if row.businessDate == target.isoformat()]
    if len(match) != 1:
        raise ResearchError("FLOW_CALENDAR_DATE_UNVERIFIED")
    return match[0].openDay, folder


def parse_flow(raw, status, target):
    try:
        if status != 200:
            return None
        payload = json.loads(raw)
        if payload["rt_cd"] != "0":
            return None
        rows = [row for row in payload["output2"] if row["stck_bsop_date"] == target.strftime("%Y%m%d")]
        if len(rows) != 1:
            return None
        row, fields = rows[0], {}
        for group in GROUPS:
            for names, tolerance in ((QUANTITY_FIELDS, 0), (AMOUNT_FIELDS, 1)):
                keys = [f"{group}_{name}" for name in names]
                buy, sell, net = (int(str(row[key])) for key in keys)
                if buy < 0 or sell < 0 or abs(buy - sell - net) > tolerance:
                    return None
                fields.update(zip(keys, (buy, sell, net)))
        volume, amount = int(str(row["acml_vol"])), int(str(row["acml_tr_pbmn"]))
        if volume <= 0 or amount <= 0:
            return None
        return {**fields, "acml_vol": volume, "acml_tr_pbmn": amount}
    except (KeyError, TypeError, ValueError):
        return None


def capture(folder, phase, target, ticker, transport, clock):
    _, start, deadline = window(phase, target)
    requested = clock()
    if not start <= requested < deadline:
        return
    attempt = Path(mkdtemp(prefix=f"{phase}-{ticker}-", dir=folder))
    receipt = {"phase": phase, "targetDate": target.isoformat(), "ticker": ticker,
               "market": MARKET, "trId": TR_ID, "requestedAt": requested.isoformat()}
    try:
        status, raw, received = transport.fetch_flow(ticker, target)
        (attempt / "body.json").write_bytes(raw)
        receipt.update(http=status, receivedAt=received.isoformat(), bodySha256=digest(raw))
    except (OSError, ResearchError):
        receipt["failure"] = "FLOW_REQUEST_FAILED"
    atomic_json(attempt / "receipt.json", receipt)


def available(folder, phase, target, ticker):
    _, start, deadline = window(phase, target)
    choices = []
    for attempt in folder.glob(f"{phase}-{ticker}-*"):
        receipt_file = attempt / "receipt.json"
        if not receipt_file.is_file():
            continue
        receipt = json.loads(receipt_file.read_bytes())
        if (receipt["phase"], receipt["targetDate"], receipt["ticker"], receipt["market"], receipt["trId"]) != (
                phase, target.isoformat(), ticker, MARKET, TR_ID):
            raise ResearchError("FLOW_RECEIPT_SCOPE_MISMATCH")
        if "bodySha256" not in receipt:
            continue
        raw = (attempt / "body.json").read_bytes()
        if digest(raw) != receipt["bodySha256"]:
            raise ResearchError("FLOW_RESPONSE_HASH_MISMATCH")
        requested = datetime.fromisoformat(receipt["requestedAt"])
        received = datetime.fromisoformat(receipt["receivedAt"])
        if start <= requested <= received <= deadline:
            fields = parse_flow(raw, receipt["http"], target)
            if fields is not None:
                choices.append((received, receipt_file, receipt, fields))
    return max(choices, default=None, key=lambda choice: (choice[0], choice[1].name))


def audit(folder, target):
    result = {"targetDate": target.isoformat(), "tickers": {}}
    for ticker in TICKERS:
        close = available(folder, "close", target, ticker)
        next_day = available(folder, "next-day", target, ticker)
        entry = {}
        for phase, observation in (("close", close), ("nextDay", next_day)):
            entry[phase] = ({"receivedAt": observation[2]["receivedAt"],
                             "bodySha256": observation[2]["bodySha256"],
                             "receipt": observation[1].parent.name + "/receipt.json"} if observation else None)
        entry["changedFields"] = ([key for key in close[3] if close[3][key] != next_day[3][key]]
                                  if close and next_day else None)
        result["tickers"][ticker] = entry
    result["commonByCutoff"] = all(entry["close"] is not None for entry in result["tickers"].values())
    return result


def run(phase, root, cache, factory=connection, clock=now, sleeper=sleep):
    current = clock().astimezone(KST)
    target = current.date() - timedelta(days=phase == "next-day")
    folder = root / target.isoformat()
    if phase == "close" and target.weekday() >= 5:
        return {"targetDate": target.isoformat(), "status": "WEEKEND"}
    begin, start, deadline = window(phase, target)
    if not begin <= current < deadline:
        raise ResearchError("FLOW_OUTSIDE_CAPTURE_WINDOW")
    if phase == "next-day" and not any(available(folder, "close", target, code) for code in TICKERS):
        return {"targetDate": target.isoformat(), "status": "NO_PRIOR_EVIDENCE"}
    folder.mkdir(parents=True, exist_ok=True)
    with job_lock(folder):
        pending = [code for code in TICKERS if not available(folder, phase, target, code)]
        if not pending:
            output = audit(folder, target)
            atomic_json(folder / "audit.json", output)
            return {**output, "status": "CAPTURED"}
        transport = factory()
        if phase == "close":
            opened, calendar_path = open_day(cache, target, transport, clock)
            atomic_json(folder / "calendar.json", {"targetDate": target.isoformat(), "openDay": opened,
                                                   "calendarReceiptSha256": digest((calendar_path / "receipt.json").read_bytes())})
            if not opened:
                return {"targetDate": target.isoformat(), "status": "CLOSED"}
        transport.authenticate()
        while (seconds := (start - clock()).total_seconds()) > 0:
            sleeper(min(seconds, 20))
        for code in pending:
            capture(folder, phase, target, code, transport, clock)
        output = audit(folder, target)
        atomic_json(folder / "audit.json", output)
        key = "close" if phase == "close" else "nextDay"
        output["status"] = ("CAPTURED" if all(entry[key] for entry in output["tickers"].values())
                            else "CAPTURE_INCOMPLETE")
        return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("close", "next-day", "calendar", "audit"))
    parser.add_argument("--date", type=date.fromisoformat, help="Trading date for offline audit")
    args = parser.parse_args()
    if (args.action == "audit") != (args.date is not None):
        parser.error("--date is required only for audit")
    root = ARTIFACTS / "kis-investor-flow-live"
    cache = ARTIFACTS / "kis-calendar-cache"
    try:
        if args.action == "audit":
            result = audit(root / args.date.isoformat(), args.date)
        elif args.action == "calendar":
            target = now().date()
            opened, _ = open_day(cache, target, connection())
            result = {"targetDate": target.isoformat(), "openDay": opened}
        else:
            result = run(args.action, root, cache)
    except (OSError, ResearchError, ValueError, KeyError, TypeError) as exc:
        print(str(exc) if isinstance(exc, ResearchError) else "FLOW_CAPTURE_FAILED", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return int(result.get("status") == "CAPTURE_INCOMPLETE")


if __name__ == "__main__":
    sys.exit(main())
