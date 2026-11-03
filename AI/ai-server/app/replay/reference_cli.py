import argparse
import json
import os
from pathlib import Path
import sys

from pydantic import ValidationError

from .calendar_fetch import fetch_calendar_once
from .history import KisHistoryTransport
from .local_use import bind_local_use
from .models import ResearchError
from .reference import check_reference_files
from .session_evidence import fetch_session_notice


def main(argv=None):
    parser = argparse.ArgumentParser(description="Personal-local use evidence and historical reference checks")
    commands = parser.add_subparsers(dest="command", required=True)
    accept = commands.add_parser("accept-local")
    accept.add_argument("--job", required=True, type=Path)
    accept.add_argument("--output", required=True, type=Path)
    calendar = commands.add_parser("calendar-fetch")
    calendar.add_argument("--basis-date", required=True)
    calendar.add_argument("--cache", required=True, type=Path)
    session = commands.add_parser("session-fetch")
    session.add_argument("--url", required=True)
    session.add_argument("--cache", required=True, type=Path)
    check = commands.add_parser("check")
    check.add_argument("--job", required=True, type=Path)
    check.add_argument("--local-use", required=True, type=Path)
    check.add_argument("--reference", nargs="+", required=True, type=Path)
    check.add_argument("--output", required=True, type=Path)
    check.add_argument("--market", choices=["KOSPI", "KOSDAQ", "KONEX", "UNSPECIFIED"], default="UNSPECIFIED")
    args = parser.parse_args(argv)
    try:
        if args.command == "accept-local":
            value = bind_local_use(args.job, args.output)
            result = {"status": "LOCAL_SCOPE_RECORDED", "policyId": value["policyId"], "basis": value["basis"]}
        elif args.command == "calendar-fetch":
            transport = KisHistoryTransport(os.getenv("SAGOPALGO_KIS_APP_KEY"), os.getenv("SAGOPALGO_KIS_APP_SECRET"))
            pack, folder, cached = fetch_calendar_once(args.cache, args.basis_date, transport)
            dates = sorted(r.businessDate for r in pack.calendar)
            result = {"status": "CAPTURED", "cached": cached, "dates": len(dates),
                      "firstDate": dates[0] if dates else None, "lastDate": dates[-1] if dates else None,
                      "referenceFile": str(folder / "reference.json"), "autoPagination": False}
        elif args.command == "session-fetch":
            pack, folder, cached = fetch_session_notice(args.url, args.cache)
            session = pack.sessions[0]
            result = {"status": "CAPTURED", "cached": cached, "market": session.market,
                      "businessDate": session.businessDate, "openAt": session.openAt.isoformat(),
                      "closeAt": session.closeAt.isoformat(), "knowledgeBasis": "FETCH_TIME_ONLY",
                      "referenceFile": str(folder / "reference.json")}
        else:
            result = check_reference_files(args.job, args.local_use, args.reference, args.output, args.market)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1 if result.get("status") == "REFERENCE_GAPS" else 0
    except ResearchError as exc:
        code = str(exc)
    except (ValidationError, ValueError, TypeError, KeyError, UnicodeError):
        code = "REFERENCE_INPUT_INVALID"
    except OSError:
        code = "REFERENCE_FILE_FAILED"
    print(json.dumps({"status": "FAILED", "code": code}), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
