"""Read-only Docker/public GET diagnostics; never starts subscriptions or migrations."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit, urlencode


class CheckError(ValueError):
    pass


def run(args, **kwargs):
    try:
        result = subprocess.run(args, capture_output=True, timeout=35, **kwargs)
    except (OSError, subprocess.TimeoutExpired):
        raise CheckError("LOCAL_COMMAND_UNAVAILABLE") from None
    if result.returncode:
        raise CheckError("LOCAL_COMMAND_FAILED")
    return result.stdout


def validate_window(base, start, end):
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise CheckError("API_ORIGIN_INVALID")
    try:
        a, b = (datetime.fromisoformat(s.replace("Z", "+00:00")) for s in (start, end))
        if not a.tzinfo or not b.tzinfo or not a < b or b - a > timedelta(days=1) or any(t.second or t.microsecond for t in (a, b)):
            raise ValueError
    except ValueError:
        raise CheckError("BOUNDED_MINUTE_WINDOW_REQUIRED") from None
    if b > datetime.now(timezone.utc):
        raise CheckError("CLOSED_WINDOW_REQUIRED")
    return base.rstrip("/")


def public_get(url):
    executable = shutil.which("curl.exe") or shutil.which("curl")
    if not executable:
        raise CheckError("CURL_REQUIRED")
    raw = run([executable, "--noproxy", "*", "-sS", "--max-time", "15", "--max-filesize", "34603008",
               "-w", "\n%{http_code}", url])
    body, _, status = raw.rpartition(b"\n")
    try:
        value = json.loads(body)
        if not isinstance(value, dict): raise ValueError
        return {"http": int(status), "body": value}
    except (ValueError, TypeError):
        raise CheckError("PUBLIC_API_RESPONSE_INVALID") from None


def database_checks():
    # Binary LF stdin avoids Windows text-mode CRLF breaking the SQL terminator.
    script = b'''set -eu
export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
mysql -uroot "$MYSQL_DATABASE" --batch --skip-column-names <<'SQL'
SELECT 'STORAGE_025',COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('market_stream_events','market_stream_minutes');
SELECT 'STORAGE_026',COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('research_journal_clock','research_item_heads','research_versions','research_checkpoints');
SQL
'''
    raw = run(["docker", "exec", "-i", "sagopalgo-mysql", "sh"], input=script)
    try:
        rows = [line.split("\t") for line in raw.decode("utf-8").splitlines()]
        result = {k: int(v) for k, v in rows}
        if len(rows) != 2 or set(result) != {"STORAGE_025", "STORAGE_026"}:
            raise ValueError
        if not 0 <= result["STORAGE_025"] <= 2 or not 0 <= result["STORAGE_026"] <= 4:
            raise ValueError
        return result
    except (ValueError, UnicodeError):
        raise CheckError("DATABASE_PROBE_INVALID") from None


def configuration_checks():
    raw = run(["docker", "inspect", "sagopalgo-spring-api"])
    try:
        env = dict(x.split("=", 1) for x in json.loads(raw)[0]["Config"]["Env"] if "=" in x)
        # Deliberately return booleans only, never raw credentials/config values.
        return {"enabled": env.get("SAGOPALGO_MARKET_STREAM_ENABLED") == "true",
                "rightsConfirmed": env.get("SAGOPALGO_MARKET_STREAM_RIGHTS_CONFIRMED") == "true",
                "positiveSubscriptionBudget": int(env.get("SAGOPALGO_MARKET_STREAM_APPROVED_SUBSCRIPTIONS", "0")) > 0,
                "kisCredentialsPresent": bool(env.get("SAGOPALGO_KIS_APP_KEY")) and bool(env.get("SAGOPALGO_KIS_APP_SECRET"))}
    except (ValueError, KeyError, IndexError, TypeError):
        raise CheckError("CONFIGURATION_PROBE_INVALID") from None


def summarize(db, config, export, stream):
    blockers = []
    if db.get("STORAGE_025") != 2: blockers.append("STORAGE_025_REQUIRED")
    if db.get("STORAGE_026") != 4: blockers.append("STORAGE_026_REQUIRED")
    value = export.get("body", {})
    data = value.get("data") or {}
    valid_export = (export.get("http") == 200 and value.get("success") is True
                    and isinstance(data, dict) and data.get("schemaVersion") == "SAGOPALGO_STORED_EXPORT_V1"
                    and data.get("readOnly") is True and data.get("usableForTrading") is False
                    and data.get("streamCoverage") == "OBSERVED_ONLY" and isinstance(data.get("streamEvents"), list))
    if not valid_export: blockers.append("EXPORT_API_UNAVAILABLE")
    value = stream.get("body", {})
    sd = value.get("data") or {}
    valid_stream = (stream.get("http") == 200 and value.get("success") is True and isinstance(sd, dict)
                    and sd.get("contractVersion") == "KIS_KRX_STREAM_V1" and sd.get("usableForTrading") is False)
    if not valid_stream: blockers.append("STREAM_API_UNAVAILABLE")
    kinds = Counter()
    if valid_export:
        for event in data["streamEvents"]:
            if not isinstance(event, dict) or event.get("type") not in {"TRADE", "QUOTE"}:
                blockers.append("EXPORT_EVENT_INVALID")
                continue
            kinds[event["type"]] += 1
    storage_ready = not blockers
    sample = kinds["TRADE"] > 0 and kinds["QUOTE"] > 0 and storage_ready
    if not sample: blockers.append("NO_PERSISTED_TICK_SAMPLE")
    for field, code in [("enabled", "COLLECTION_DISABLED"), ("rightsConfirmed", "RIGHTS_UNCONFIRMED"),
                        ("positiveSubscriptionBudget", "SUBSCRIPTION_BUDGET_UNCONFIRMED"),
                        ("kisCredentialsPresent", "KIS_CREDENTIALS_REQUIRED")]:
        if config.get(field) is not True: blockers.append(code)
    return {"schemaVersion": "SAGOPALGO_PUBLIC_TICK_READINESS_V1", "readOnly": True,
            "scope": "LOCAL_DATABASE_AND_PUBLIC_GET_ONLY", "storageAndExportReady": storage_ready,
            "persistedSampleAvailable": sample, "continuousCollectionConfigurationDeclared": storage_ready and all(
                config.get(k) is True for k in ["enabled", "rightsConfirmed", "positiveSubscriptionBudget", "kisCredentialsPresent"]),
            "streamApiState": sd.get("state") if isinstance(sd, dict) else None,
            "observedCounts": dict(kinds), "configuration": config, "blockers": sorted(set(blockers)),
            "usableForTrading": False,
            "limitations": ["Existing local sample, not market completeness or permission verification.",
                            "No provider, account, order, schema, environment, or subscription mutations.",
                            "Table existence only; use tick audit for hashes, fields and time quality.",
                            "Positive budget is not sufficient capacity or confirmation of shared-key limits."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://192.168.0.2:8081")
    parser.add_argument("--stock-code", default="005930")
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output and args.output.exists(): raise CheckError("OUTPUT_EXISTS")
        if len(args.stock_code) != 6 or not args.stock_code.isascii() or not args.stock_code.isdigit():
            raise CheckError("STOCK_CODE_INVALID")
        base = validate_window(args.base_url, args.start, args.end)
        query = urlencode({"stockCode": args.stock_code, "from": args.start, "to": args.end})
        report = summarize(database_checks(), configuration_checks(),
                           public_get(base+"/api/v1/research/dataset-export?"+query),
                           public_get(base+"/api/v1/market/realtime?"+urlencode({"stockCode":args.stock_code})))
        report.update(checkedAt=datetime.now(timezone.utc).isoformat(), stockCode=args.stock_code,
                      startAt=args.start, endAt=args.end)
    except CheckError as error:
        report = {"status": "FAILED", "code": str(error), "readOnly": True}
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)
    if args.output and not args.output.exists():
        with args.output.open("x", encoding="utf-8") as stream: stream.write(encoded+"\n")
    print(encoded)
    return 0 if report.get("storageAndExportReady") else 1


if __name__ == "__main__":
    raise SystemExit(main())
