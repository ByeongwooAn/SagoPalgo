"""Bounded, resumable KIND discovery for immutable name observations, without orders or inference."""
import argparse
from datetime import timedelta
import json
from pathlib import Path
import re
import time
from urllib.parse import urlencode

from . import kind_membership_evidence as public
from .dataset import canonical, digest, read_bytes, read_json
from .history import day, job_lock, now
from .krx_storage import atomic_json
from .models import ResearchError, StrictModel, utc
from pydantic import Field, model_validator


class Target(StrictModel):
    observationId: str = Field(pattern=r"^[0-9a-f]{64}$")
    symbol: str = Field(pattern=r"^[0-9A-Z]{6}$")
    isin: str = Field(pattern=r"^[0-9A-Z]{12}$")
    beforeMarket: str
    afterMarket: str
    beforeName: str = Field(min_length=1, max_length=300)
    afterName: str = Field(min_length=1, max_length=300)
    observedFrom: str
    observedTo: str

    @model_validator(mode="after")
    def bounds(self):
        if (self.beforeMarket not in {"KOSPI", "KOSDAQ"} or self.afterMarket not in {"KOSPI", "KOSDAQ"}
                or not day(self.observedFrom) < day(self.observedTo) or self.beforeName == self.afterName):
            raise ValueError("invalid name observation")
        return self


class Config(StrictModel):
    schemaVersion: str = "SAGOPALGO_NAME_DISCLOSURES_PLAN_V1"
    parentSha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sourceKind: str
    startDate: str
    endDate: str
    targets: list[Target] = Field(min_length=1, max_length=500)
    maxRequests: int = Field(default=1600, ge=1, le=3000)
    lookbackDays: int = 45
    maxAttemptsPerStage: int = 3
    minIntervalSeconds: int = 1

    @model_validator(mode="after")
    def bounds(self):
        if (self.schemaVersion != "SAGOPALGO_NAME_DISCLOSURES_PLAN_V1" or self.sourceKind not in {"SYNTHETIC", "PROVIDER_OBSERVATIONS"}
                or (self.lookbackDays, self.maxAttemptsPerStage, self.minIntervalSeconds) != (45, 3, 1)
                or len({v.observationId for v in self.targets}) != len(self.targets)
                or not all(day(self.startDate) <= day(t.observedFrom) < day(t.observedTo) <= day(self.endDate) for t in self.targets)
                or self.maxRequests < sum(t.beforeMarket == t.afterMarket for t in self.targets)):
            raise ValueError("invalid bounded name scope")
        return self


def targets_from(parent):
    if parent.get("schemaVersion") != "SAGOPALGO_UNIVERSE_RECONCILIATION_V2":
        raise ResearchError("NAME_DISCLOSURES_PARENT_INVALID")
    targets = []
    ids = set()
    for row in parent["rows"]:
        obs = row["observation"]
        if row["observationId"] != digest(canonical(obs)) or row["observationId"] in ids:
            raise ResearchError("NAME_DISCLOSURES_PARENT_INVALID")
        ids.add(row["observationId"])
        if obs["kind"] != "NAME_CHANGE_OBSERVED":
            continue
        before, after = obs["before"], obs["after"]
        if (row["resolution"] != "NAME_CHANGE_NEEDS_DISCLOSURE"
                or any(before[k] != after[k] for k in ["symbol", "isin", "classification"])
                or before["classification"] != "COMMON_SHARE" or before["isin"] != obs["isin"]):
            raise ResearchError("NAME_DISCLOSURES_IDENTITY_REVIEW_REQUIRED")
        targets.append({"observationId": row["observationId"], "symbol": before["symbol"], "isin": before["isin"],
                        "beforeMarket": before["market"], "afterMarket": after["market"],
                        "beforeName": before["name"], "afterName": after["name"],
                        "observedFrom": obs["observedFrom"], "observedTo": obs["observedTo"]})
    return targets


def prepare(folder, parent_path, max_requests=1600):
    raw = read_bytes(parent_path)
    parent = read_json(raw)
    targets = targets_from(parent)
    config = Config(parentSha256=digest(raw), sourceKind=parent["sourceKind"], startDate=parent["startDate"],
                    endDate=parent["endDate"], targets=targets, maxRequests=max_requests).model_dump(mode="json")
    plan = {**config, "planId": digest(canonical(config))}
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "raw").mkdir()
    atomic_json(folder / "plan.json", plan)
    atomic_json(folder / "journal.json", {"planId": plan["planId"], "attempts": []})
    return plan


def candidates(raw):
    root = public.html(raw)
    infos = [v for v in root.walk("div") if v.attrs.get("class") == "info type-00"]
    counts = re.findall(r"전체\s*([0-9,]+)\s*건\s*:\s*([0-9]+)\s*/\s*([0-9]+)", infos[0].text()) if len(infos) == 1 else []
    if len(counts) != 1:
        raise ResearchError("NAME_DISCLOSURES_SEARCH_LAYOUT")
    total, page, pages = [int(v.replace(",", "")) for v in counts[0]]
    links = [v for v in root.walk("a") if v.attrs.get("href") == "#viewer"]
    if total > 100 or page != 1 or pages not in ({0, 1} if total == 0 else {1}) or len(links) != total:
        raise ResearchError("NAME_DISCLOSURES_SEARCH_INCOMPLETE")
    result = []
    for link in links:
        title = re.sub(r"\s+", "", link.text())
        reviewed = {"변경상장(상호변경)", "변경상장(상호변경)(상호변경)",
                    "상장안내(액면병합/상호변경)", "상장안내(합병/상호변경)"}
        if title.removeprefix("[정정]") not in reviewed:
            continue
        m = re.fullmatch(r"openDisclsViewer\('([0-9]{14})',''\);?", link.attrs.get("onclick", ""))
        if not m:
            raise ResearchError("NAME_DISCLOSURES_SEARCH_LINK_INVALID")
        result.append({"receipt": m[1], "corrected": title.startswith("[정정]"),
                       "viewerTitle": "상장안내" if title.removeprefix("[정정]").startswith("상장안내") else "변경상장"})
    if len(result) > 4 or len({v["receipt"] for v in result}) != len(result):
        raise ResearchError("NAME_DISCLOSURES_CANDIDATE_REVIEW_REQUIRED")
    return sorted(result, key=lambda v: v["receipt"])


def viewer(raw, target, candidate):
    root = public.html(raw)
    headers = [v.text() for v in root.walk("h1") if re.search(r"\([0-9A-Z]{6}\)$", v.text())]
    if len(headers) != 1 or not headers[0].endswith("(" + target["symbol"] + ")"):
        raise ResearchError("NAME_DISCLOSURES_VIEWER_CODE_MISMATCH")
    selectors = [v for v in root.walk("select") if v.attrs.get("id") == "mainDoc"]
    options = [v for v in selectors[0].walk("option") if v.attrs.get("value")] if len(selectors) == 1 else []
    if not 1 <= len(options) <= 4:
        raise ResearchError("NAME_DISCLOSURES_VERSION_REVIEW_REQUIRED")
    receipt = candidate["receipt"]
    stamp = receipt[:4] + "." + receipt[4:6] + "." + receipt[6:8]
    selected, documents = [], []
    for option in options:
        value = re.fullmatch(r"([0-9]{14})\|[YN]", option.attrs["value"])
        if not value:
            raise ResearchError("NAME_DISCLOSURES_VIEWER_DOCUMENT_INVALID")
        documents.append(value[1])
        label = re.sub(r"\s+", "", option.text())
        base_title = candidate.get("viewerTitle", "변경상장")
        title = ("[정정]" if candidate["corrected"] else "") + base_title
        if label in {title + "(" + stamp + ")", title + "(상호변경)(" + stamp + ")"}:
            selected.append(value[1])
    if len(selected) != 1 or len(documents) != len(set(documents)):
        raise ResearchError("NAME_DISCLOSURES_DOCUMENT_AMBIGUOUS")
    return {"document": selected[0], "documents": documents,
            "viewerIssuerName": headers[0][:-(len(target["symbol"]) + 2)].strip()}


def requests_for(target, completed):
    if target["beforeMarket"] != target["afterMarket"]:
        return
    parameters = {"method": "searchDetailsSub", "forward": "details_sub", "currentPageSize": "100", "pageIndex": "1",
                  "orderMode": "0", "orderStat": "D", "fromDate": (day(target["observedFrom"]) - timedelta(days=45)).isoformat(),
                  "toDate": target["observedTo"], "repIsuSrtCd": "A" + target["symbol"], "searchCodeType": "number",
                  "searchCorpName": target["symbol"], "reportNm": "변경상장", "reportCd": "", "allRepIsuSrtCd": "", "marketType": ""}
    yield "SEARCH", {"url": public.BASE + "/disclosure/details.do", "method": "POST", "parameters": parameters}
    selected = candidates(completed["SEARCH"])
    if not selected:
        alternate = {**parameters, "reportNm": "상장안내"}
        yield "NOTICE_SEARCH", {"url": public.BASE + "/disclosure/details.do", "method": "POST", "parameters": alternate}
        selected = candidates(completed["NOTICE_SEARCH"])
    if not selected:
        raise ResearchError("NAME_DISCLOSURES_NO_REVIEWED_TITLE")
    for index, candidate in enumerate(selected):
        label = "V" + str(index)
        yield label + "_VIEWER", {"url": public.BASE + "/common/disclsviewer.do?" + urlencode({"acptno": candidate["receipt"], "method": "search"}),
                                 "method": "GET", "parameters": None}
        doc = viewer(completed[label + "_VIEWER"], target, candidate)["document"]
        yield label + "_PATH", {"url": public.BASE + "/common/disclsviewer.do", "method": "POST",
                               "parameters": {"method": "searchContents", "docNo": doc}}
        url = public.path_result(completed[label + "_PATH"], candidate["receipt"], doc)
        yield label + "_BODY", {"url": url, "method": "GET", "parameters": None}


def inspect(folder, target, latest, expected=None):
    completed = {}
    try:
        for stage, spec in requests_for(target, completed):
            key = (target["observationId"], stage)
            if expected is not None:
                expected[key] = spec
            entry = latest.get(key)
            if not entry:
                return stage, spec, completed, "PENDING"
            if entry["request"] != spec:
                raise ResearchError("NAME_DISCLOSURES_REQUEST_TAMPERED")
            if entry["state"] != "CAPTURED":
                return stage, spec, completed, entry["state"]
            completed[stage] = read_bytes(folder / "raw" / f"{entry['seq']:04d}.bin")
        return None, None, completed, "TRANSFER_CONTEXT_REQUIRED" if not completed else "BODIES_CAPTURED"
    except ResearchError as exc:
        if str(exc) == "NAME_DISCLOSURES_REQUEST_TAMPERED":
            raise
        return None, None, completed, str(exc)


def load(folder):
    plan = read_json(read_bytes(folder / "plan.json"))
    config = Config.model_validate({k: v for k, v in plan.items() if k != "planId"}).model_dump(mode="json")
    if plan != {**config, "planId": digest(canonical(config))}:
        raise ResearchError("NAME_DISCLOSURES_PLAN_INVALID")
    journal = read_json(read_bytes(folder / "journal.json"))
    if set(journal) != {"planId", "attempts"} or journal["planId"] != plan["planId"] or len(journal["attempts"]) > plan["maxRequests"]:
        raise ResearchError("NAME_DISCLOSURES_JOURNAL_INVALID")
    ids = {t["observationId"] for t in plan["targets"]}
    latest, counts = {}, {}
    for seq, entry in enumerate(journal["attempts"], 1):
        key = (entry["targetId"], entry["stage"])
        if (type(entry["seq"]) is not int or entry["seq"] != seq or key[0] not in ids
                or not re.fullmatch(r"SEARCH|NOTICE_SEARCH|V[0-3]_(?:VIEWER|PATH|BODY)", key[1])
                or entry["state"] not in {"RESERVED", "CAPTURED", "FAILED"}
                or key in latest and latest[key]["state"] == "CAPTURED"):
            raise ResearchError("NAME_DISCLOSURES_JOURNAL_INVALID")
        counts[key] = counts.get(key, 0) + 1
        if counts[key] > plan["maxAttemptsPerStage"]:
            raise ResearchError("NAME_DISCLOSURES_STAGE_BUDGET")
        utc(entry["startedAt"])
        fields = {"seq", "targetId", "stage", "state", "startedAt", "request"}
        if "sha256" in entry:
            fields |= {"sha256", "capturedAt"}
            if utc(entry["capturedAt"]) < utc(entry["startedAt"]) or digest(read_bytes(folder / "raw" / f"{seq:04d}.bin")) != entry["sha256"]:
                raise ResearchError("NAME_DISCLOSURES_RAW_TAMPERED")
        if entry["state"] == "CAPTURED":
            fields |= {"sha256", "capturedAt"}
        if entry["state"] == "FAILED":
            fields |= {"diagnostic", "finishedAt"}
            if utc(entry["finishedAt"]) < utc(entry["startedAt"]):
                raise ResearchError("NAME_DISCLOSURES_JOURNAL_INVALID")
        if set(entry) != fields:
            raise ResearchError("NAME_DISCLOSURES_JOURNAL_INVALID")
        latest[key] = entry
    expected = {}
    for target in plan["targets"]:
        inspect(folder, target, latest, expected)
    if any(e["request"] != expected.get((e["targetId"], e["stage"])) for e in journal["attempts"]):
        raise ResearchError("NAME_DISCLOSURES_REQUEST_TAMPERED")
    return plan, journal, latest


def summary(folder):
    plan, journal, latest = load(folder)
    counts = {}
    for target in plan["targets"]:
        state = inspect(folder, target, latest)[3]
        counts[state] = counts.get(state, 0) + 1
    return {"planId": plan["planId"], "sourceKind": plan["sourceKind"], "targets": len(plan["targets"]), "states": counts,
            "attemptsUsed": len(journal["attempts"]), "maxRequests": plan["maxRequests"], "nameChangeConfirmed": False,
            "usableForTraining": False, "usableForTrading": False}


def collect(folder, transport, max_new_requests, retry_failed=False, sleep=time.sleep):
    if type(max_new_requests) is not int or not 0 <= max_new_requests <= 3000:
        raise ResearchError("NAME_DISCLOSURES_RUN_BUDGET_INVALID")
    with job_lock(folder):
        plan, journal, latest = load(folder)
        if transport.source_kind != plan["sourceKind"]:
            raise ResearchError("NAME_DISCLOSURES_SOURCE_KIND_MISMATCH")
        used = 0
        for index, target in enumerate(plan["targets"], 1):
            while True:
                stage, spec, _, state = inspect(folder, target, latest)
                if not stage or state in {"RESERVED", "FAILED"} and not retry_failed:
                    break
                key = (target["observationId"], stage)
                if sum(e["targetId"] == key[0] and e["stage"] == key[1] for e in journal["attempts"]) >= 3:
                    break
                if used >= max_new_requests or len(journal["attempts"]) >= plan["maxRequests"]:
                    return summary(folder)
                if journal["attempts"]:
                    elapsed = (utc(now()) - utc(journal["attempts"][-1]["startedAt"])).total_seconds()
                    if elapsed < 0:
                        raise ResearchError("NAME_DISCLOSURES_CLOCK_REGRESSION")
                    if elapsed < 1:
                        sleep(1 - elapsed)
                seq = len(journal["attempts"]) + 1
                entry = {"seq": seq, "targetId": key[0], "stage": stage, "state": "RESERVED", "startedAt": now(), "request": spec}
                journal["attempts"].append(entry)
                atomic_json(folder / "journal.json", journal)
                try:
                    raw = transport.fetch(spec)
                    (folder / "raw" / f"{seq:04d}.bin").write_bytes(raw)
                    entry.update(state="CAPTURED", sha256=digest(raw), capturedAt=now())
                    atomic_json(folder / "journal.json", journal)
                except Exception as exc:
                    entry.update(state="FAILED", diagnostic=str(exc) if isinstance(exc, ResearchError) else "NAME_DISCLOSURES_CAPTURE_FAILED", finishedAt=now())
                    atomic_json(folder / "journal.json", journal)
                latest[key] = entry
                used += 1
                if entry["state"] == "FAILED":
                    break
            if index % 10 == 0:
                print(json.dumps({"progress": True, "targetsVisited": index, "attemptsUsed": len(journal["attempts"])}), flush=True)
        return summary(folder)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ["plan", "collect", "audit"]:
        p = sub.add_parser(command)
        p.add_argument("--job", type=Path, required=True)
        if command == "plan":
            p.add_argument("--parent", type=Path, required=True)
            p.add_argument("--max-requests", type=int, default=1600)
        if command == "collect":
            p.add_argument("--max-new-requests", type=int, required=True)
            p.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = prepare(args.job, args.parent, args.max_requests) if args.command == "plan" else collect(args.job, public.Transport(), args.max_new_requests, args.retry_failed) if args.command == "collect" else summary(args.job)
        print(json.dumps({k: v for k, v in result.items() if k != "targets"}, sort_keys=True), flush=True)
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"diagnostic": str(exc) if isinstance(exc, ResearchError) else "NAME_DISCLOSURES_INPUT_INVALID"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
