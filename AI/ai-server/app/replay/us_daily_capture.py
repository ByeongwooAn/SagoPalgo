"""Capture bounded, read-only KIS NASDAQ raw daily pages for the prototype."""

import argparse
from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep
from urllib import parse, request

from .dataset import digest, read_json
from .file_publish import publish_directory
from .history import BASE, KisHistoryTransport, atomic_json
from .models import ResearchError

SYMBOLS = ("AAPL", "NVDA")
START = date(2023, 11, 1)
END = date(2026, 11, 2)
PATH = "/uapi/overseas-price/v1/quotations/dailyprice"
MAX_PAGES_PER_SYMBOL = 20


def rows_from_page(raw):
    document = read_json(raw)
    if document.get("rt_cd") != "0":
        code = document.get("msg_cd", "")
        raise ResearchError(f"US_DAILY_PROVIDER_{code}" if str(code).isalnum() else "US_DAILY_PROVIDER_ERROR")
    rows = document.get("output2")
    if not isinstance(rows, list) or not rows:
        raise ResearchError("US_DAILY_PAGE_EMPTY")
    return rows


def fetch_page(transport, symbol, cursor):
    params = {"AUTH": "", "EXCD": "NAS", "SYMB": symbol, "GUBN": "0",
              "BYMD": cursor.strftime("%Y%m%d"), "MODP": "0"}
    req = request.Request(BASE + PATH + "?" + parse.urlencode(params), method="GET", headers={
        "Authorization": "Bearer " + transport.token, "appkey": transport.key, "appsecret": transport.secret,
        "tr_id": "HHDFS76240000", "custtype": "P", "Accept": "application/json",
    })
    raw = transport.read(req)
    if any(value.encode() in raw for value in (transport.key, transport.secret, transport.token)):
        raise ResearchError("US_DAILY_SENSITIVE_RESPONSE")
    return raw


def fetch_with_retry(transport, symbol, cursor):
    for delay in (0, 8, 16):
        sleep(delay)
        try:
            raw = fetch_page(transport, symbol, cursor)
            return raw, rows_from_page(raw)
        except ResearchError as exc:
            if str(exc) != "US_DAILY_PROVIDER_OPSQ0008" or delay == 16:
                raise ResearchError(f"{symbol} {cursor}: {exc}") from None


def collect(output, transport):
    if output.exists():
        raise ResearchError("US_DAILY_CAPTURE_EXISTS")
    transport.authenticate()
    with TemporaryDirectory(dir=output.parent) as temporary:
        stage = Path(temporary) / "capture"
        stage.mkdir()
        pages = []
        for symbol in SYMBOLS:
            cursor = END
            for page in range(1, MAX_PAGES_PER_SYMBOL + 1):
                raw, rows = fetch_with_retry(transport, symbol, cursor)
                days = [date.fromisoformat(str(row["xymd"])) for row in rows]
                if max(days) > cursor:
                    raise ResearchError("US_DAILY_PAGE_AFTER_CURSOR")
                name = f"{symbol}-{page:02}.json"
                (stage / name).write_bytes(raw)
                pages.append({"ticker": symbol, "file": name, "byDate": cursor.isoformat(),
                              "sha256": digest(raw), "rows": len(days),
                              "receivedAt": datetime.now(timezone.utc).isoformat()})
                print(f"{symbol} {cursor} · {len(days)} rows · oldest {min(days)}", flush=True)
                if min(days) <= START:
                    break
                cursor = min(days) - timedelta(days=1)
                sleep(0.55)
            else:
                raise ResearchError("US_DAILY_PAGE_BUDGET_EXHAUSTED")
        atomic_json(stage / "capture.json", {"provider": "KIS", "market": "NASDAQ", "currency": "USD",
                                           "priceBasis": "RAW", "start": START.isoformat(),
                                           "end": END.isoformat(), "pages": pages})
        publish_directory(stage, output)
    return len(pages)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(f"Captured {collect(args.output, KisHistoryTransport(os.getenv('SAGOPALGO_KIS_APP_KEY'), os.getenv('SAGOPALGO_KIS_APP_SECRET')))} pages.")
        return 0
    except ResearchError as exc:
        print(exc)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        print("US_DAILY_CAPTURE_INVALID")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
