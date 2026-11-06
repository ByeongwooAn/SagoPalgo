"""Bounded KIS daily-price acquisition. Separate entry point from offline replay."""
import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Literal
from urllib import error, parse, request

from pydantic import Field, ValidationError, model_validator

from .dataset import canonical, digest, read_bytes, read_json
from .models import ResearchError, StrictModel, utc
from .file_publish import replace_file

BASE = "https://openapi.koreainvestment.com:9443"
DAILY_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
LIMIT = 2 * 1024 * 1024
KST = timezone(timedelta(hours=9))


def day(value: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", value):
        raise ResearchError("HISTORY_DATE_INVALID")
    return date.fromisoformat(value)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class HistoryConfig(StrictModel):
    schemaVersion: Literal["SAGOPALGO_KIS_DAILY_REQUEST_V1"]
    stockCode: str = Field(pattern=r"^[0-9]{6}$")
    startDate: str
    endDate: str
    provenance: Literal["PROVIDER_HISTORICAL", "SYNTHETIC"]
    queryRightsConfirmed: bool
    queryRightsEvidence: str = Field(min_length=1, max_length=1000)
    trainingRightsConfirmed: bool = False
    trainingRightsEvidence: str = Field(default="", max_length=1000)
    windowDays: int = Field(default=60, ge=8, le=90)
    maxRequests: int = Field(default=64, ge=2, le=250)
    minIntervalSeconds: int = Field(default=2, ge=1, le=60)

    @model_validator(mode="after")
    def scope(self):
        start, end = day(self.startDate), day(self.endDate)
        if start > end or (end - start).days > 3653:
            raise ValueError("at most ten years per job")
        if self.trainingRightsConfirmed and not self.trainingRightsEvidence.strip():
            raise ValueError("training rights evidence required")
        return self


def parameters(config, start, end):
    return {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": config.stockCode,
            "FID_INPUT_DATE_1": start.strftime("%Y%m%d"), "FID_INPUT_DATE_2": end.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "1"}


def plan(config: HistoryConfig):
    first, end = day(config.startDate), day(config.endDate)
    windows = []
    while first <= end:
        last = min(first + timedelta(days=config.windowDays - 1), end)
        windows.append(parameters(config, first, last))
        if last == end:
            break
        first = last - timedelta(days=6)  # Seven-day overlaps; not a trading-calendar assumption.
    if len(windows) + 4 > config.maxRequests:
        raise ResearchError("HISTORY_BUDGET_TOO_SMALL")
    result = {"schemaVersion": "SAGOPALGO_KIS_DAILY_PLAN_V1", "config": config.model_dump(),
              "endpoint": BASE + DAILY_PATH, "transactionId": "FHKST03010100", "windows": windows,
              "verificationRequests": 3, "authenticationRequestsPerRun": 1}
    result["planId"] = digest(canonical(result))
    return result


def atomic_json(path: Path, value):
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())
    replace_file(temporary, path)


def prepare(config_path: Path, output: Path):
    raw = read_bytes(config_path)
    config = HistoryConfig.model_validate(read_json(raw))
    planned = plan(config)
    output.mkdir(parents=True, exist_ok=False)
    (output / "request.json").write_bytes(raw)
    (output / "plan.json").write_bytes(canonical(planned))
    atomic_json(output / "journal.json", {"planId": planned["planId"], "attempts": [], "status": "PLANNED"})
    return planned


def load_job(path):
    planned = read_json(read_bytes(path / "plan.json"))
    config = HistoryConfig.model_validate(read_json(read_bytes(path / "request.json")))
    if planned != plan(config):
        raise ResearchError("HISTORY_PLAN_TAMPERED")
    journal = read_json(read_bytes(path / "journal.json"))
    if journal.get("planId") != planned["planId"] or not isinstance(journal.get("attempts"), list):
        raise ResearchError("HISTORY_JOURNAL_INVALID")
    if len(journal["attempts"]) > config.maxRequests:
        raise ResearchError("HISTORY_BUDGET_EXCEEDED")
    completed_targets = set()
    for index, attempt in enumerate(journal["attempts"], 1):
        if attempt.get("number") != index or attempt.get("kind") not in {"AUTH", "WINDOW", "VERIFY"}:
            raise ResearchError("HISTORY_JOURNAL_INVALID")
        if attempt.get("status") not in {"IN_FLIGHT", "FAILED", "COMPLETE"}:
            raise ResearchError("HISTORY_JOURNAL_INVALID")
        utc(attempt["startedAt"])
        if attempt["status"] != "IN_FLIGHT" and utc(attempt["finishedAt"]) < utc(attempt["startedAt"]):
            raise ResearchError("HISTORY_JOURNAL_INVALID")
        if attempt["kind"] == "AUTH":
            valid = attempt.get("params") is None and attempt.get("target") == "authentication" and not attempt.get("file")
        elif attempt["kind"] == "WINDOW":
            target = attempt.get("target", "")
            valid = isinstance(target, str) and target.isdigit() and str(int(target)) == target and int(target) < len(planned["windows"]) and attempt.get("params") == planned["windows"][int(target)]
        else:
            target = day(attempt["target"])
            valid = day(config.startDate) <= target <= day(config.endDate) and attempt.get("params") == parameters(config, target, target)
        if not valid or (attempt["status"] == "COMPLETE" and attempt["kind"] != "AUTH" and not attempt.get("file")):
            raise ResearchError("HISTORY_JOURNAL_INVALID")
        if attempt["status"] == "COMPLETE" and attempt["kind"] != "AUTH":
            identity = (attempt["kind"], attempt["target"])
            if identity in completed_targets:
                raise ResearchError("HISTORY_JOURNAL_INVALID")
            completed_targets.add(identity)
        if attempt.get("file"):
            expected = f"response-{index:04d}.json"
            if attempt["file"] != expected or digest(read_bytes(path / expected)) != attempt.get("sha256"):
                raise ResearchError("HISTORY_RESPONSE_TAMPERED")
    return planned, config, journal


def parse_page(raw, params, retrieved_at):
    body = read_json(raw)
    if not isinstance(body, dict) or body.get("rt_cd") != "0":
        raise ResearchError("HISTORY_PROVIDER_REJECTED")
    if not isinstance(body.get("output1"), dict) or body["output1"].get("stck_shrn_iscd") != params["FID_INPUT_ISCD"]:
        raise ResearchError("HISTORY_IDENTITY_UNCONFIRMED")
    data = body.get("output2")
    if not isinstance(data, list) or len(data) > 100:
        raise ResearchError("HISTORY_PAGE_INVALID")
    first = datetime.strptime(params["FID_INPUT_DATE_1"], "%Y%m%d").date()
    last = datetime.strptime(params["FID_INPUT_DATE_2"], "%Y%m%d").date()
    rows, padding = {}, 0
    for item in data:
        if not isinstance(item, dict):
            raise ResearchError("HISTORY_ROW_INVALID")
        fields = ["stck_oprc", "stck_hgpr", "stck_lwpr", "stck_clpr", "acml_vol"]
        if not item.get("stck_bsop_date") and all(item.get(k) in (None, "", "0") for k in fields):
            padding += 1
            continue
        stamp = item.get("stck_bsop_date")
        if not isinstance(stamp, str) or not re.fullmatch(r"[0-9]{8}", stamp):
            raise ResearchError("HISTORY_ROW_DATE_INVALID")
        at = datetime.strptime(stamp, "%Y%m%d").date()
        if not first <= at <= last:
            raise ResearchError("HISTORY_ROW_OUTSIDE_WINDOW")
        for key in fields:
            if not isinstance(item.get(key), str) or not re.fullmatch(r"[0-9]{1,24}", item[key]):
                raise ResearchError("HISTORY_ROW_NUMBER_INVALID")
        opened, high, low, closed, volume = [int(item[k]) for k in fields]
        nontrading = opened == high == low == closed == volume == 0
        if not nontrading and not (0 < low <= min(opened, closed) <= max(opened, closed) <= high):
            raise ResearchError("HISTORY_OHLC_INVALID")
        row = {"stockCode": params["FID_INPUT_ISCD"], "exchange": "KRX", "currency": "KRW", "timeframe": "DAY",
               "businessDate": at.isoformat(), "datePrecision": "DATE",
               "open": str(opened), "high": str(high), "low": str(low), "close": str(closed), "volume": str(volume),
               "priceBasis": "RAW", "status": "NON_TRADING_OR_UNKNOWN" if nontrading else "OBSERVED_PRICE",
               "retrievedAt": retrieved_at,
               "providerFlags": {key: item.get(key) for key in ["flng_cls_code", "prtt_rate", "mod_yn", "revl_issu_reas"]}}
        if at.isoformat() in rows:
            raise ResearchError("HISTORY_DUPLICATE_DATE")
        rows[at.isoformat()] = row
    if len(rows) > (last - first).days + 1:
        raise ResearchError("HISTORY_PAGE_TRUNCATION_RISK")
    return rows, padding


def comparable(row):
    return {k: v for k, v in row.items() if k not in {"retrievedAt", "providerFlags"}}


def observations(path, planned, journal):
    merged, windows, checks, overlaps, padding = {}, {}, {}, 0, 0
    for attempt in journal["attempts"]:
        if attempt.get("status") != "COMPLETE" or attempt["kind"] == "AUTH":
            continue
        rows, blanks = parse_page(read_bytes(path / attempt["file"]), attempt["params"], attempt["finishedAt"])
        padding += blanks
        if attempt["kind"] == "VERIFY":
            checks[attempt["target"]] = rows
            continue
        windows[attempt["target"]] = rows
        for stamp, row in rows.items():
            if stamp in merged:
                if comparable(row) != comparable(merged[stamp]):
                    raise ResearchError("HISTORY_OVERLAP_CONFLICT")
                overlaps += 1
            else:
                merged[stamp] = row
    return merged, windows, checks, overlaps, padding


@contextmanager
def job_lock(path):
    lock = path / ".collect.lock"
    try:
        with lock.open("xb") as stream:
            stream.write(canonical({"pid": os.getpid(), "startedAt": now()}))
    except FileExistsError:
        raise ResearchError("HISTORY_JOB_LOCKED") from None
    try:
        yield
    finally:
        lock.unlink()


def audit(path: Path, check_daily=False):
    planned, config, journal = load_job(path)
    merged, windows, checks, overlaps, padding = observations(path, planned, journal)
    dates = sorted(merged)
    selected = sorted(set([dates[0], dates[len(dates) // 2], dates[-1]])) if dates else []
    verified = 0
    for stamp in selected:
        if stamp in checks and stamp in checks[stamp] and comparable(checks[stamp][stamp]) == comparable(merged[stamp]):
            verified += 1
    report = {"schemaVersion": "SAGOPALGO_KIS_DAILY_AUDIT_V1", "planId": planned["planId"], "provenance": config.provenance,
              "requestStart": config.startDate, "requestEnd": config.endDate, "recordCount": len(merged),
              "firstDate": dates[0] if dates else None, "lastDate": dates[-1] if dates else None,
              "plannedWindows": len(planned["windows"]), "completedWindows": len(windows),
              "emptyWindows": sum(not rows for rows in windows.values()), "overlapComparisons": overlaps,
              "verificationTargets": selected, "verificationPassed": verified, "providerPadding": padding,
              "callsUsed": len(journal["attempts"]), "maxRequests": config.maxRequests,
              "status": "COLLECTED" if len(windows) == len(planned["windows"]) and dates and verified == len(selected) else "PARTIAL",
              "marketCoverage": "UNVERIFIED_NO_CALENDAR", "datePrecision": "DATE", "priceBasis": "RAW",
              "queryRightsConfirmed": config.queryRightsConfirmed, "trainingRightsConfirmed": config.trainingRightsConfirmed,
              "usableForTraining": False, "usableForTrading": False,
              "limitations": ["Date-only observations; no invented open/close/publication timestamps.",
                              "Request-window coverage is not exchange, delisted-universe or corporate-action completeness.",
                              "Training rights and dated calendar must be checked before model use."]}
    rows = [merged[k] for k in dates]
    if check_daily:
        data = b"".join(canonical(row) + b"\n" for row in rows)
        if read_bytes(path / "daily.jsonl") != data or read_json(read_bytes(path / "audit.json")).get("dailySha256") != digest(data):
            raise ResearchError("HISTORY_DAILY_TAMPERED")
    return report, rows


def collect(path: Path, transport, sleeper=time.sleep):
    with job_lock(path):
        planned, config, journal = load_job(path)
        if not config.queryRightsConfirmed:
            raise ResearchError("HISTORY_QUERY_RIGHTS_REQUIRED")
        if day(config.endDate) >= datetime.now(KST).date():
            raise ResearchError("HISTORY_CLOSED_DATES_REQUIRED")
        merged, completed, checked, _, _ = observations(path, planned, journal)
        pending = [(str(i), params) for i, params in enumerate(planned["windows"]) if str(i) not in completed]
        if not pending and audit(path)[0]["status"] == "COLLECTED":
            return publish(path)
        if any(a.get("status") == "IN_FLIGHT" for a in journal["attempts"]):
            raise ResearchError("HISTORY_UNRESOLVED_ATTEMPT")
        current_dates = sorted(merged)
        targets = set([current_dates[0], current_dates[len(current_dates) // 2], current_dates[-1]]) if current_dates else set()
        remaining_checks = 3 if pending else len(targets - set(checked))
        if len(journal["attempts"]) + 1 + len(pending) + remaining_checks > config.maxRequests:
            raise ResearchError("HISTORY_BUDGET_EXCEEDED")

        def call(kind, target, params=None):
            if len(journal["attempts"]) >= config.maxRequests:
                raise ResearchError("HISTORY_BUDGET_EXCEEDED")
            sleeper(config.minIntervalSeconds)
            attempt = {"number": len(journal["attempts"]) + 1, "kind": kind, "target": target,
                       "params": params, "startedAt": now(), "status": "IN_FLIGHT"}
            journal["attempts"].append(attempt)
            journal["status"] = "RUNNING"
            atomic_json(path / "journal.json", journal)  # Durable budget reservation BEFORE network.
            try:
                if kind == "AUTH":
                    transport.authenticate()
                else:
                    raw = transport.fetch(params)
                    if not isinstance(raw, bytes) or len(raw) > LIMIT:
                        raise ResearchError("HISTORY_RESPONSE_LIMIT")
                    filename = f'response-{attempt["number"]:04d}.json'
                    with (path / filename).open("xb") as stream:
                        stream.write(raw)
                        stream.flush()
                        os.fsync(stream.fileno())
                    attempt.update(file=filename, sha256=digest(raw))
                    rows, _ = parse_page(raw, params, now())
                    if kind == "WINDOW" and any(stamp in merged and comparable(row) != comparable(merged[stamp]) for stamp, row in rows.items()):
                        raise ResearchError("HISTORY_OVERLAP_CONFLICT")
                    if kind == "VERIFY" and (target not in rows or comparable(rows[target]) != comparable(merged[target])):
                        raise ResearchError("HISTORY_VERIFICATION_MISMATCH")
                attempt.update(status="COMPLETE", finishedAt=now())
                atomic_json(path / "journal.json", journal)
                return rows if kind != "AUTH" else None
            except Exception as exc:
                code = str(exc) if isinstance(exc, ResearchError) else "HISTORY_REQUEST_FAILED"
                attempt.update(status="FAILED", diagnostic=code, finishedAt=now())
                journal["status"] = "PARTIAL"
                atomic_json(path / "journal.json", journal)
                publish(path)
                raise ResearchError(code) from None

        call("AUTH", "authentication")
        for target, params in pending:
            call("WINDOW", target, params)
            merged, _, checked, _, _ = observations(path, planned, journal)
        dates = sorted(merged)
        for stamp in sorted(set([dates[0], dates[len(dates) // 2], dates[-1]])) if dates else []:
            if stamp not in checked:
                call("VERIFY", stamp, parameters(config, day(stamp), day(stamp)))
        journal["status"] = "COLLECTED" if dates else "PARTIAL"
        atomic_json(path / "journal.json", journal)
        return publish(path)


def publish(path):
    report, rows = audit(path)
    data = b"".join(canonical(row) + b"\n" for row in rows)
    temporary = path / "daily.jsonl.tmp"
    temporary.write_bytes(data)
    replace_file(temporary, path / "daily.jsonl")
    report["dailySha256"] = digest(data)
    atomic_json(path / "audit.json", report)
    return report


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class KisHistoryTransport:
    def __init__(self, key, secret, opener=None):
        if not key or not secret:
            raise ResearchError("HISTORY_CREDENTIALS_MISSING")
        self.key, self.secret, self.token = key, secret, None
        self.opener = opener or request.build_opener(NoRedirect())

    def read(self, req):
        try:
            with self.opener.open(req, timeout=20) as response:
                body = response.read(LIMIT + 1)
            if len(body) > LIMIT:
                raise ResearchError("HISTORY_RESPONSE_LIMIT")
            return body
        except (error.URLError, TimeoutError, OSError):
            raise ResearchError("HISTORY_HTTP_FAILED") from None

    def authenticate(self):
        body = canonical({"grant_type": "client_credentials", "appkey": self.key, "appsecret": self.secret})
        raw = self.read(request.Request(BASE + "/oauth2/tokenP", data=body, headers={"Content-Type": "application/json"}, method="POST"))
        value = read_json(raw)
        token = value.get("access_token") if isinstance(value, dict) else None
        if not isinstance(token, str) or not token or len(token) > 16384 or any(c in token for c in "\r\n"):
            raise ResearchError("HISTORY_AUTH_FAILED")
        self.token = token  # Never persisted, printed, or placed in URLs.

    def fetch(self, params):
        if not self.token:
            raise ResearchError("HISTORY_AUTH_REQUIRED")
        req = request.Request(BASE + DAILY_PATH + "?" + parse.urlencode(params), method="GET", headers={
            "Authorization": "Bearer " + self.token, "appkey": self.key, "appsecret": self.secret,
            "tr_id": "FHKST03010100", "custtype": "P", "Accept": "application/json"})
        raw = self.read(req)
        if any(value.encode() in raw for value in [self.key, self.secret, self.token]):
            raise ResearchError("HISTORY_SENSITIVE_RESPONSE")
        return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description="KIS daily research: plan/audit offline, collect performs bounded authenticated reads")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("plan")
    create.add_argument("--config", required=True, type=Path)
    create.add_argument("--output", required=True, type=Path)
    for command in ["collect", "audit"]:
        item = commands.add_parser(command)
        item.add_argument("--job", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            result = prepare(args.config, args.output)
            value = {"status": "PLANNED", "planId": result["planId"], "windows": len(result["windows"])}
        elif args.command == "collect":
            planned, config, journal = load_job(args.job)
            if config.provenance != "PROVIDER_HISTORICAL":
                raise ResearchError("HISTORY_LIVE_PROVENANCE_REQUIRED")
            value = collect(args.job, KisHistoryTransport(os.getenv("SAGOPALGO_KIS_APP_KEY"), os.getenv("SAGOPALGO_KIS_APP_SECRET")))
        else:
            with job_lock(args.job):
                value = audit(args.job, check_daily=True)[0]
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
        return 0 if value.get("status") != "PARTIAL" else 1
    except ResearchError as exc:
        code = str(exc)
    except (ValidationError, ValueError, TypeError, KeyError, UnicodeError):
        code = "HISTORY_INPUT_INVALID"
    except OSError:
        code = "HISTORY_FILE_FAILED"
    print(json.dumps({"status": "FAILED", "code": code}), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
