"""Explicit reviewed receipts supplement only unresolved V3 name observations."""
import argparse
from datetime import timedelta
import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

from pydantic import Field, model_validator

from . import name_disclosures as engine
from .dataset import canonical, digest, read_bytes, read_json
from .history import day
from .krx_storage import atomic_json
from .models import ResearchError, StrictModel

SCHEMA = "SAGOPALGO_NAME_ALIAS_PLAN_V1"
TITLES = {"FORMAL_ENGLISH_BRIDGE": "상호변경안내", "TRADING_ALIAS_NOTICE": "기타시장안내(약명및영문명)"}


class Case(StrictModel):
    observationId: str = Field(pattern=r"^[0-9a-f]{64}$")
    stockCode: str = Field(pattern=r"^[0-9A-Z]{6}$")
    mode: Literal["FORMAL_ENGLISH_BRIDGE", "TRADING_ALIAS_NOTICE"]
    receipt: str = Field(pattern=r"^[0-9]{14}$")


class Scope(StrictModel):
    schemaVersion: Literal["SAGOPALGO_NAME_ALIAS_CASES_V1"]
    cases: list[Case] = Field(min_length=1, max_length=10)


class Target(engine.Target):
    mode: Literal["FORMAL_ENGLISH_BRIDGE", "TRADING_ALIAS_NOTICE"]
    receipt: str = Field(pattern=r"^[0-9]{14}$")


class Config(engine.Config):
    schemaVersion: Literal["SAGOPALGO_NAME_ALIAS_PLAN_V1"] = SCHEMA
    casesSha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    targets: list[Target] = Field(min_length=1, max_length=10)
    maxRequests: int = Field(default=12, ge=3, le=90)

    @model_validator(mode="after")
    def bounds(self):
        if (self.schemaVersion != SCHEMA or self.sourceKind not in {"SYNTHETIC", "PROVIDER_OBSERVATIONS"}
                or (self.lookbackDays, self.maxAttemptsPerStage, self.minIntervalSeconds) != (45, 3, 1)
                or len({t.observationId for t in self.targets}) != len(self.targets)
                or len({t.receipt for t in self.targets}) != len(self.targets) or self.maxRequests < len(self.targets) * 3
                or any(not day(self.startDate) <= day(t.observedFrom) < day(t.observedTo) <= day(self.endDate)
                       or (t.beforeMarket, t.afterMarket) != ("KOSDAQ", "KOSDAQ")
                       or not day(t.observedFrom) - timedelta(days=45) <= day(t.receipt[:4] + '-' + t.receipt[4:6] + '-' + t.receipt[6:8]) <= day(t.observedTo)
                       for t in self.targets)):
            raise ValueError("invalid bounded alias scope")
        return self


def targets_from(parent, scope):
    if parent.get("schemaVersion") != "SAGOPALGO_UNIVERSE_RECONCILIATION_V3":
        raise ResearchError("NAME_ALIAS_PARENT_INVALID")
    rows = {}
    for row in parent["rows"]:
        identity = row["observationId"]
        if identity != digest(canonical(row["observation"])) or identity in rows:
            raise ResearchError("NAME_ALIAS_PARENT_INVALID")
        rows[identity] = row
    unresolved = {k for k, r in rows.items() if r["observation"]["kind"] == "NAME_CHANGE_OBSERVED" and r["resolution"] == "NAME_CHANGE_NEEDS_DISCLOSURE"}
    if {c.observationId for c in scope.cases} != unresolved or len(scope.cases) != len(unresolved):
        raise ResearchError("NAME_ALIAS_EXACT_REVIEW_SCOPE_REQUIRED")
    targets = []
    for case in scope.cases:
        obs = rows[case.observationId]["observation"]
        before, after = obs["before"], obs["after"]
        if (case.stockCode != before["symbol"] or any(before[k] != after[k] for k in ["symbol", "isin", "classification"])
                or obs["isin"] != before["isin"] or before["classification"] != "COMMON_SHARE"):
            raise ResearchError("NAME_ALIAS_IDENTITY_MISMATCH")
        targets.append({"observationId": case.observationId, "symbol": case.stockCode, "isin": before["isin"],
            "beforeMarket": before["market"], "afterMarket": after["market"], "beforeName": before["name"], "afterName": after["name"],
            "observedFrom": obs["observedFrom"], "observedTo": obs["observedTo"], "mode": case.mode, "receipt": case.receipt})
    return targets


def prepare(folder, parent_path, cases_path, max_requests=12):
    raw, cases_raw = read_bytes(parent_path), read_bytes(cases_path)
    parent, scope = read_json(raw), Scope.model_validate(read_json(cases_raw))
    payload = Config(parentSha256=digest(raw), casesSha256=digest(cases_raw), sourceKind=parent["sourceKind"],
        startDate=parent["startDate"], endDate=parent["endDate"], targets=targets_from(parent, scope), maxRequests=max_requests).model_dump(mode="json")
    plan = {**payload, "planId": digest(canonical(payload))}
    folder.mkdir(parents=True, exist_ok=False); (folder / "raw").mkdir()
    atomic_json(folder / "plan.json", plan); atomic_json(folder / "journal.json", {"planId": plan["planId"], "attempts": []})
    return plan


def requests_for(target, completed):
    yield "V0_VIEWER", {"url": engine.public.BASE + "/common/disclsviewer.do?" + urlencode({"acptno": target["receipt"], "method": "search"}), "method": "GET", "parameters": None}
    selected = engine.viewer(completed["V0_VIEWER"], target, {"receipt": target["receipt"], "corrected": False, "viewerTitle": TITLES[target["mode"]]})
    if len(selected["documents"]) != 1:
        raise ResearchError("NAME_ALIAS_VERSION_REVIEW_REQUIRED")
    yield "V0_PATH", {"url": engine.public.BASE + "/common/disclsviewer.do", "method": "POST", "parameters": {"method": "searchContents", "docNo": selected["document"]}}
    url = engine.public.path_result(completed["V0_PATH"], target["receipt"], selected["document"])
    expected = "70659" if target["mode"] == "FORMAL_ENGLISH_BRIDGE" else "70792"
    if not url.endswith('/' + expected + '.htm'):
        raise ResearchError("NAME_ALIAS_FORM_REVIEW_REQUIRED")
    yield "V0_BODY", {"url": url, "method": "GET", "parameters": None}


def load(folder):
    return engine.load(folder, Config, requests_for)


def inspect(folder, target, latest):
    return engine.inspect(folder, target, latest, request_builder=requests_for)


def collect(folder, transport, max_new_requests, retry_failed=False, **kwargs):
    return engine.collect(folder, transport, max_new_requests, retry_failed, config_type=Config, request_builder=requests_for, **kwargs)


def summary(folder):
    return engine.summary(folder, Config, requests_for)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest="command", required=True)
    for command in ["plan", "collect", "audit"]:
        p = sub.add_parser(command); p.add_argument("--job", type=Path, required=True)
        if command == "plan":
            p.add_argument("--parent", type=Path, required=True); p.add_argument("--cases", type=Path, required=True); p.add_argument("--max-requests", type=int, default=12)
        if command == "collect":
            p.add_argument("--max-new-requests", type=int, required=True); p.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = prepare(args.job, args.parent, args.cases, args.max_requests) if args.command == "plan" else collect(args.job, engine.public.Transport(), args.max_new_requests, args.retry_failed) if args.command == "collect" else summary(args.job)
        print(json.dumps({k: v for k, v in result.items() if k != "targets"}, sort_keys=True), flush=True); return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"diagnostic": str(exc) if isinstance(exc, ResearchError) else "NAME_ALIAS_INPUT_INVALID"})); return 2


if __name__ == "__main__": raise SystemExit(main())
