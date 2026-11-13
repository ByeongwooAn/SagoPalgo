"""Audit a complete publication window outside the initial H05 notice sample."""

import argparse
from collections import Counter
from datetime import date
from pathlib import Path
import re

from .corporate_action_event_audit import body_fields
from .corporate_action_outcome_census import notice_review
from .corporate_action_outcomes import KST, SCOPE, checked_read, require
from .dataset import digest, read_bytes, read_json
from .historical_actions_followup import SCHEMA as SAMPLE_SCHEMA, WINDOWS, action_sample
from .kind_membership_evidence import html
from .krx_baseline_validation import immutable_json
from .market_calendar_evidence import text
from .models import utc


SCHEMA = "SAGOPALGO_H05_MARKET_ACTION_EXPANSION_V1"
DAY = r"\d{4}-\d{2}-\d{2}"


def extra_fields(market, role, form, body, issuer, symbol):
    if (market, role, form) == ("KOSPI", "DIVIDEND_OR_COMBINED", "99302.htm"):
        return body_fields(market, role, "99303.htm", body, issuer, symbol)
    if (market, role, form) == ("KOSDAQ", "DIVIDEND_OR_COMBINED", "70768.htm"):
        matches = re.findall(
            rf"1\. 권배락 실시일 ({DAY}) 2\. 권배락 사유 (.+?) 3\. 권배락 내역 "
            rf"회사명 주권종류 단축코드 기준가\(원\) {re.escape(issuer)} 보통주식 A{symbol} ([\d,]+) 4\. 기타",
            body,
        )
        if len(matches) == 1:
            applied, reason, price = matches[0]
            return {"appliedDate": date.fromisoformat(applied).isoformat(),
                    "referencePriceKrw": int(price.replace(",", "")), "publishedCause": reason}
    if (market, role, form) == ("KOSPI", "HALT_BOUNDARY_REVIEW", "99808.htm"):
        matches = re.findall(rf"3\. 매매거래정지 일시 ({DAY} \d{{2}}:\d{{2}}) "
                             rf"4\. 매매거래정지 해제일시 ({DAY} \d{{2}}:\d{{2}}) 5\.", body)
        if len(matches) == 1:
            start, end = (utc(value.replace(" ", "T") + ":00+09:00").astimezone(KST) for value in matches[0])
            if start < end and all(SCOPE[0] <= value.date().isoformat() <= SCOPE[1] for value in (start, end)):
                return {"status": "HALT_TIMES_SHARE_CLASS_UNCONFIRMED", "haltTimeKst": start.isoformat(),
                        "reopeningTimeKst": end.isoformat(), "actualFirstTradeAt": None}
    return None


def review_extra_form(job, notice):
    if notice["status"] != "BODY_SCOPE_OR_FIELDS_UNCONFIRMED":
        return
    viewer, _, body = notice["evidence"]
    captures = job / "captures"
    receipt = notice["receipt"]
    raw = checked_read(captures / f"proof-viewer-{receipt}" / "raw.bin", viewer["bodySha256"])
    headers = [node.text() for node in html(raw).walk("h1")]
    match = re.fullmatch(r"(.+) \(([0-9A-Z]{6})\)", headers[0]) if len(headers) == 1 else None
    if match is None:
        return
    issuer, symbol = match.groups()
    raw = checked_read(captures / f"proof-body-{receipt}" / "raw.bin", body["bodySha256"])
    fields = extra_fields(notice["market"], notice["role"], body["sourceUrl"].rsplit("/", 1)[-1], text(raw), issuer, symbol)
    if fields and "appliedDate" in fields:
        status = ("EXCHANGE_NOTICE_FIELDS_VERIFIED" if SCOPE[0] <= fields["appliedDate"] <= SCOPE[1]
                  else "APPLIED_DATE_OUTSIDE_SCOPE")
        notice.update(fields, status=status, noticeIssuer=issuer, noticeSymbol=symbol)
    elif fields:
        notice.update(fields, noticeIssuer=issuer, viewerSymbol=symbol)


def select_rows(inventory, sample, start, end):
    require(date.fromisoformat(start).isoformat() == start and date.fromisoformat(end).isoformat() == end
            and WINDOWS["marketActions"]["from"] <= start <= end <= SCOPE[2], "EXPANSION_WINDOW")
    candidates, prior = action_sample(inventory)
    reviewed = [row["receipt"] for row in sample["actionSample"]]
    require(sample["schemaVersion"] == SAMPLE_SCHEMA and len(reviewed) == len(prior) and set(reviewed) == prior
            and sample["actionCandidates"] == len(candidates), "EXPANSION_SAMPLE_BINDING")
    return [row for row, _ in candidates if start <= row["listedMinuteKst"][:10] <= end
            and row["receipt"] not in prior]


def build(manifest, artifacts, job):
    raw = read_bytes(manifest)
    spec = read_json(raw)
    require(spec["schemaVersion"] == SCHEMA, "EXPANSION_SCHEMA")
    at = utc(spec["reviewedAt"])
    inventory, sample = [read_json(checked_read(artifacts / pin["path"], pin["sha256"]))
                         for pin in (spec["inventory"], spec["sample"])]
    require(all(utc(report["knownAt"]) <= at for report in (inventory, sample)), "EXPANSION_FUTURE_INPUT")
    window = spec["publicationWindow"]
    rows = select_rows(inventory, sample, window["from"], window["through"])
    require(bool(rows), "EXPANSION_EMPTY_WINDOW")
    notices = notice_review(job, spec["receipts"], inventory | {"candidateRows": rows}, at, SCOPE[:2], WINDOWS, set())
    require([row["receipt"] for row in rows] == [notice["receipt"] for notice in notices], "EXPANSION_REPORT_SCOPE")
    for row, notice in zip(rows, notices):
        notice["membership"] = row["membership"]
        review_extra_form(job, notice)
    return {"schemaVersion": SCHEMA, "manifestSha256": digest(raw), "knownAt": at.isoformat(),
            "publicationWindow": window, "candidateCount": len(notices), "priorSampleCount": len(sample["actionSample"]),
            "statusCounts": dict(Counter(notice["status"] for notice in notices)), "notices": notices,
            "historicalFirstAvailabilityConfirmed": False, "usableForTrading": False, "usableForTraining": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit"))
    for name in ("manifest", "artifacts", "job"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = build(args.manifest, args.artifacts, args.job)
    immutable_json(args.job / "report.json", report, require_existing=args.action == "audit")
    print(report["statusCounts"])


if __name__ == "__main__":
    main()
