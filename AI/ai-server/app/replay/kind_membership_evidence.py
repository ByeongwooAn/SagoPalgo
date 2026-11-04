"""Resumable public KIND disclosure discovery for an immutable unresolved ledger scope."""
import argparse
from datetime import timedelta
import json
from pathlib import Path
import re
import time
from urllib import parse, request

from .dataset import canonical, digest, read_bytes, read_json
from .distribution_facts import XForms
from .history import day, job_lock, now, NoRedirect
from .krx_storage import atomic_json
from .models import ResearchError, utc
from .session_evidence import validate_url
from .universe_reconciliation import MATCHED, MEMBERSHIP

BASE = "https://kind.krx.co.kr"
LIMIT = 2 * 1024 * 1024
STAGES = ("SEARCH", "VIEWER", "PATH", "BODY")
SCHEMA = "SAGOPALGO_KIND_MEMBERSHIP_EVIDENCE_PLAN_V1"


def html(raw):
    if len(raw) > LIMIT:
        raise ResearchError("MEMBERSHIP_EVIDENCE_RESPONSE_LIMIT")
    parser = XForms()
    parser.feed(raw.decode("utf-8-sig"))
    parser.close()
    if len(parser.stack) != 1:
        raise ResearchError("MEMBERSHIP_EVIDENCE_HTML_INVALID")
    return parser.root


def search_result(raw, target):
    root = html(raw)
    infos = [v for v in root.walk("div") if v.attrs.get("class") == "info type-00"]
    counts = re.findall(r"전체\s*([0-9,]+)\s*건\s*:\s*([0-9]+)\s*/\s*([0-9]+)", infos[0].text()) if len(infos) == 1 else []
    if len(counts) != 1:
        raise ResearchError("MEMBERSHIP_EVIDENCE_SEARCH_LAYOUT")
    total, page, pages = [int(v.replace(",", "")) for v in counts[0]]
    if total > 100 or page != 1 or pages != 1:
        raise ResearchError("MEMBERSHIP_EVIDENCE_SEARCH_INCOMPLETE")
    links = [v for v in root.walk("a") if v.attrs.get("href") == "#viewer"]
    if len(links) != total:
        raise ResearchError("MEMBERSHIP_EVIDENCE_SEARCH_COUNT")
    candidates = []
    for link in links:
        title = link.text()
        if "정정" in title:
            raise ResearchError("MEMBERSHIP_EVIDENCE_CORRECTION_REVIEW")
        priority = None
        if target["kind"] == "ADDED_OBSERVED":
            if re.match(r"^신규상장(?:\(|$)", title): priority = 0
            elif re.match(r"^주권\s*등\s*신규상장.*기준가격.*안내", title): priority = 1
        elif re.match(r"^상장폐지(?:\(|$)", title):
            priority = 0
        if priority is not None:
            matched = re.fullmatch(r"openDisclsViewer\('([0-9]{14})',''\);?", link.attrs.get("onclick", ""))
            if not matched:
                raise ResearchError("MEMBERSHIP_EVIDENCE_SEARCH_LINK_INVALID")
            candidates.append({"receipt":matched[1], "title":title, "priority":priority})
    if not candidates:
        raise ResearchError("MEMBERSHIP_EVIDENCE_NO_REVIEWED_SEARCH_TITLE")
    best = [v for v in candidates if v["priority"] == min(v["priority"] for v in candidates)]
    if len(best) != 1:
        raise ResearchError("MEMBERSHIP_EVIDENCE_SEARCH_AMBIGUOUS")
    return best[0]


def viewer_result(raw, target):
    root = html(raw)
    headers = [v.text() for v in root.walk("h1") if re.search(r"\([0-9A-Z]{6}\)$", v.text())]
    if len(headers) != 1 or not headers[0].endswith("("+target["symbol"]+")"):
        raise ResearchError("MEMBERSHIP_EVIDENCE_VIEWER_CODE_MISMATCH")
    selectors = [v for v in root.walk("select") if v.attrs.get("id") == "mainDoc"]
    options = [v for v in selectors[0].walk("option") if v.attrs.get("value")] if len(selectors) == 1 else []
    if len(options) != 1 or "정정" in options[0].text():
        raise ResearchError("MEMBERSHIP_EVIDENCE_CORRECTION_REVIEW")
    matched = re.fullmatch(r"([0-9]{14})\|[YN]", options[0].attrs["value"])
    if not matched:
        raise ResearchError("MEMBERSHIP_EVIDENCE_VIEWER_DOCUMENT_INVALID")
    return {"document":matched[1], "viewerIssuerName":headers[0][:-(len(target["symbol"])+2)].strip()}


def path_result(raw, receipt, document):
    if len(raw) > LIMIT:
        raise ResearchError("MEMBERSHIP_EVIDENCE_RESPONSE_LIMIT")
    text = raw.decode("utf-8-sig")
    paths = re.findall(r"parent\.setPath\('[^']*','(https://kind\.krx\.co\.kr/external/[^']+)','[^']*','[0-9]{2}','[0-9]{2}'\);", text)
    if len(paths) != 1:
        raise ResearchError("MEMBERSHIP_EVIDENCE_PATH_AMBIGUOUS")
    url = paths[0]
    validate_url(url)
    parts = url.split("/")
    if "".join(parts[4:7]) != receipt[:8] or parts[-2] != document:
        raise ResearchError("MEMBERSHIP_EVIDENCE_PATH_ID_MISMATCH")
    return url


def prepare(folder, parent_path, max_requests=256):
    raw = read_bytes(parent_path)
    parent = read_json(raw)
    if (parent.get("schemaVersion") != "SAGOPALGO_UNIVERSE_RECONCILIATION_V1" or type(max_requests) is not int
            or not 1 <= max_requests <= 512 or parent["sourceKind"] not in {"SYNTHETIC", "PROVIDER_OBSERVATIONS"}):
        raise ResearchError("MEMBERSHIP_EVIDENCE_PARENT_INVALID")
    targets = []
    for row in parent["rows"]:
        obs = row["observation"]
        if row["observationId"] != digest(canonical(obs)):
            raise ResearchError("MEMBERSHIP_EVIDENCE_PARENT_INVALID")
        if obs["kind"] not in MEMBERSHIP or row["resolution"] in MATCHED:
            continue
        if obs["kind"] == "MARKET_TRANSFER_OBSERVED":
            raise ResearchError("MEMBERSHIP_EVIDENCE_TRANSFER_PAIR_REQUIRES_SEPARATE_SCOPE")
        issue = obs["after"] or obs["before"]
        if (not re.fullmatch(r"[A-Z0-9]{6}", issue["symbol"]) or not re.fullmatch(r"[A-Z0-9]{12}", issue["isin"])
                or issue["market"] not in {"KOSPI", "KOSDAQ"}):
            raise ResearchError("MEMBERSHIP_EVIDENCE_PARENT_INVALID")
        first, last = day(obs["observedFrom"]),day(obs["observedTo"])
        if not day(parent["startDate"]) <= first < last <= day(parent["endDate"]):
            raise ResearchError("MEMBERSHIP_EVIDENCE_PARENT_INVALID")
        targets.append({"observationId":row["observationId"], "kind":obs["kind"], "symbol":issue["symbol"],
                        "isin":issue["isin"], "market":issue["market"], "observedFrom":obs["observedFrom"],
                        "observedTo":obs["observedTo"], "previousResolution":row["resolution"]})
    if not 1 <= len(targets) <= 100 or len({v["observationId"] for v in targets}) != len(targets) or len(targets)*4 > max_requests:
        raise ResearchError("MEMBERSHIP_EVIDENCE_SCOPE_OR_BUDGET_INVALID")
    payload = {"schemaVersion":SCHEMA, "parentSha256":digest(raw), "sourceKind":parent["sourceKind"],
               "startDate":parent["startDate"], "endDate":parent["endDate"], "targets":targets,
               "maxRequests":max_requests, "maxAttemptsPerStage":3, "lookbackDays":45, "minIntervalSeconds":1}
    plan = {**payload, "planId":digest(canonical(payload))}
    folder.mkdir(parents=True,exist_ok=False)
    (folder/"raw").mkdir()
    atomic_json(folder/"plan.json",plan)
    atomic_json(folder/"journal.json",{"planId":plan["planId"],"attempts":[]})
    return plan


def load(folder):
    plan = read_json(read_bytes(folder/"plan.json"))
    payload = {k:v for k,v in plan.items() if k!="planId"}
    if (plan.get("schemaVersion")!=SCHEMA or plan.get("planId")!=digest(canonical(payload))
            or set(plan)!={"schemaVersion","parentSha256","sourceKind","startDate","endDate","targets","maxRequests",
                           "maxAttemptsPerStage","lookbackDays","minIntervalSeconds","planId"}
            or plan.get("maxAttemptsPerStage")!=3 or plan.get("lookbackDays")!=45 or plan.get("minIntervalSeconds")!=1
            or type(plan.get("maxRequests")) is not int or not 1<=plan["maxRequests"]<=512
            or plan.get("sourceKind") not in {"SYNTHETIC","PROVIDER_OBSERVATIONS"}
            or not 1<=len(plan["targets"])<=100 or len({v["observationId"] for v in plan["targets"]})!=len(plan["targets"])):
        raise ResearchError("MEMBERSHIP_EVIDENCE_PLAN_INVALID")
    for target in plan["targets"]:
        if (set(target)!={"observationId","kind","symbol","isin","market","observedFrom","observedTo","previousResolution"}
                or target["kind"] not in {"ADDED_OBSERVED","REMOVED_OBSERVED"}
                or not re.fullmatch(r"[0-9a-f]{64}",target["observationId"])
                or not re.fullmatch(r"[A-Z0-9]{6}",target["symbol"]) or not re.fullmatch(r"[A-Z0-9]{12}",target["isin"])
                or target["market"] not in {"KOSPI","KOSDAQ"}
                or not day(plan["startDate"])<=day(target["observedFrom"])<day(target["observedTo"])<=day(plan["endDate"])):
            raise ResearchError("MEMBERSHIP_EVIDENCE_PLAN_INVALID")
    journal=read_json(read_bytes(folder/"journal.json"))
    if (set(journal)!={"planId","attempts"} or journal["planId"]!=plan["planId"]
            or not isinstance(journal["attempts"],list) or len(journal["attempts"])>plan["maxRequests"]):
        raise ResearchError("MEMBERSHIP_EVIDENCE_JOURNAL_INVALID")
    latest,counts={},{}
    target_ids={v["observationId"] for v in plan["targets"]}
    for seq,entry in enumerate(journal["attempts"],1):
        if (type(entry.get("seq")) is not int or entry["seq"]!=seq or entry.get("targetId") not in target_ids
                or entry.get("stage") not in STAGES or entry.get("state") not in {"RESERVED","CAPTURED","FAILED"}):
            raise ResearchError("MEMBERSHIP_EVIDENCE_JOURNAL_INVALID")
        key=(entry["targetId"],entry["stage"])
        if key in latest and latest[key]["state"]=="CAPTURED":
            raise ResearchError("MEMBERSHIP_EVIDENCE_DUPLICATE_CAPTURE")
        counts[key]=counts.get(key,0)+1
        if counts[key]>3:
            raise ResearchError("MEMBERSHIP_EVIDENCE_STAGE_BUDGET")
        utc(entry["startedAt"])
        fields={"seq","targetId","stage","state","startedAt","request"}
        if "sha256" in entry:
            fields|={"sha256","capturedAt"}
            if utc(entry["capturedAt"])<utc(entry["startedAt"]) or digest(read_bytes(folder/"raw"/f"{seq:04d}.bin"))!=entry["sha256"]:
                raise ResearchError("MEMBERSHIP_EVIDENCE_RAW_TAMPERED")
        if entry["state"]=="CAPTURED": fields|={"sha256","capturedAt"}
        if entry["state"]=="FAILED":
            fields|={"diagnostic","finishedAt"}
            if utc(entry["finishedAt"])<utc(entry["startedAt"]):
                raise ResearchError("MEMBERSHIP_EVIDENCE_JOURNAL_INVALID")
        if set(entry)!=fields:
            raise ResearchError("MEMBERSHIP_EVIDENCE_JOURNAL_INVALID")
        latest[key]=entry
    expected={}
    for target in plan["targets"]: inspect_target(folder,target,latest,expected)
    if any(entry["request"]!=expected.get((entry["targetId"],entry["stage"])) for entry in journal["attempts"]):
        raise ResearchError("MEMBERSHIP_EVIDENCE_REQUEST_TAMPERED")
    return plan,journal,latest


def requests_for(target, completed):
    first=(day(target["observedFrom"])-timedelta(days=45)).isoformat()
    parameters={"method":"searchDetailsSub","forward":"details_sub","currentPageSize":"100","pageIndex":"1",
                "orderMode":"0","orderStat":"D","fromDate":first,"toDate":target["observedTo"],
                "repIsuSrtCd":"A"+target["symbol"],"searchCodeType":"number","searchCorpName":target["symbol"],
                "reportNm":"신규상장" if target["kind"]=="ADDED_OBSERVED" else "상장폐지",
                "reportCd":"","allRepIsuSrtCd":"","marketType":""}
    yield "SEARCH",{"url":BASE+"/disclosure/details.do","method":"POST","parameters":parameters}
    selected=search_result(completed["SEARCH"],target)
    yield "VIEWER",{"url":BASE+"/common/disclsviewer.do?"+parse.urlencode({"acptno":selected["receipt"],"method":"search"}),"method":"GET","parameters":None}
    viewer=viewer_result(completed["VIEWER"],target)
    yield "PATH",{"url":BASE+"/common/disclsviewer.do","method":"POST","parameters":{"method":"searchContents","docNo":viewer["document"]}}
    url=path_result(completed["PATH"],selected["receipt"],viewer["document"])
    yield "BODY",{"url":url,"method":"GET","parameters":None}


def inspect_target(folder,target,latest,expected=None):
    completed={}
    try:
        for stage,req in requests_for(target,completed):
            if expected is not None: expected[(target["observationId"],stage)]=req
            entry=latest.get((target["observationId"],stage))
            if not entry: return stage,req,completed,"PENDING"
            if entry["request"]!=req:
                raise ResearchError("MEMBERSHIP_EVIDENCE_REQUEST_TAMPERED")
            if entry["state"]!="CAPTURED": return stage,req,completed,entry["state"]
            completed[stage]=read_bytes(folder/"raw"/f"{entry['seq']:04d}.bin")
        return None,None,completed,"BODY_CAPTURED"
    except ResearchError as exc:
        if str(exc)=="MEMBERSHIP_EVIDENCE_REQUEST_TAMPERED": raise
        return None,None,completed,str(exc)


class Transport:
    source_kind="PROVIDER_OBSERVATIONS"
    def __init__(self,opener=None): self.opener=opener
    def fetch(self,spec):
        url=spec["url"]
        if url.startswith(BASE+"/external/"): validate_url(url)
        elif not (url==BASE+"/disclosure/details.do" or url==BASE+"/common/disclsviewer.do" or
                  re.fullmatch(re.escape(BASE)+r"/common/disclsviewer\.do\?acptno=[0-9]{14}&method=search",url)):
            raise ResearchError("MEMBERSHIP_EVIDENCE_URL_INVALID")
        data=parse.urlencode(spec["parameters"]).encode() if spec["parameters"] is not None else None
        req=request.Request(url,data=data,method=spec["method"],headers={"User-Agent":"SagoPalgo-local-research/1","Accept":"text/html"})
        try:
            with (self.opener or request.build_opener(NoRedirect())).open(req,timeout=20) as response: raw=response.read(LIMIT+1)
        except Exception:
            raise ResearchError("MEMBERSHIP_EVIDENCE_HTTP_FAILED") from None
        if len(raw)>LIMIT: raise ResearchError("MEMBERSHIP_EVIDENCE_RESPONSE_LIMIT")
        return raw


def collect(folder,transport,max_new_requests,retry_failed=False,sleep=time.sleep):
    if type(max_new_requests) is not int or not 0<=max_new_requests<=512:
        raise ResearchError("MEMBERSHIP_EVIDENCE_RUN_BUDGET_INVALID")
    with job_lock(folder):
        plan,journal,latest=load(folder)
        if transport.source_kind!=plan["sourceKind"]:
            raise ResearchError("MEMBERSHIP_EVIDENCE_SOURCE_KIND_MISMATCH")
        # All cached request paths must be derived from the immutable plan before any new call.
        for target in plan["targets"]: inspect_target(folder,target,latest)
        used=0
        for index,target in enumerate(plan["targets"],1):
            while True:
                stage,spec,_,state=inspect_target(folder,target,latest)
                if not stage or state in {"RESERVED","FAILED"} and not retry_failed: break
                key=(target["observationId"],stage)
                attempts=sum(v["targetId"]==key[0] and v["stage"]==key[1] for v in journal["attempts"])
                if attempts>=3: break
                if used>=max_new_requests or len(journal["attempts"])>=plan["maxRequests"]: return summary(folder)
                if journal["attempts"]:
                    elapsed=(utc(now())-utc(journal["attempts"][-1]["startedAt"])).total_seconds()
                    if elapsed<0: raise ResearchError("MEMBERSHIP_EVIDENCE_CLOCK_REGRESSION")
                    if elapsed<1: sleep(1-elapsed)
                seq=len(journal["attempts"])+1
                entry={"seq":seq,"targetId":key[0],"stage":stage,"state":"RESERVED","startedAt":now(),"request":spec}
                journal["attempts"].append(entry)
                atomic_json(folder/"journal.json",journal)
                try:
                    raw=transport.fetch(spec)
                    (folder/"raw"/f"{seq:04d}.bin").write_bytes(raw)
                    entry.update(state="CAPTURED",sha256=digest(raw),capturedAt=now())
                    atomic_json(folder/"journal.json",journal)
                except Exception as exc:
                    code=str(exc) if isinstance(exc,ResearchError) else "MEMBERSHIP_EVIDENCE_CAPTURE_FAILED"
                    entry.update(state="FAILED",diagnostic=code,finishedAt=now())
                    atomic_json(folder/"journal.json",journal)
                latest[key]=entry
                used+=1
                if entry["state"]=="FAILED": break
            if index%5==0: print(json.dumps({"progress":True,"targetsVisited":index,"attemptsUsed":len(journal["attempts"])}),flush=True)
        return summary(folder)


def summary(folder):
    plan,journal,latest=load(folder)
    counts={}
    for target in plan["targets"]:
        state=inspect_target(folder,target,latest)[3]
        counts[state]=counts.get(state,0)+1
    return {"planId":plan["planId"],"targets":len(plan["targets"]),"states":counts,"attemptsUsed":len(journal["attempts"]),
            "maxRequests":plan["maxRequests"],"sourceKind":plan["sourceKind"],"membershipConfirmed":False,"usableForTraining":False,"usableForTrading":False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    for command in ["plan","collect","audit"]:
        p=sub.add_parser(command); p.add_argument("--job",type=Path,required=True)
        if command=="plan": p.add_argument("--parent",type=Path,required=True); p.add_argument("--max-requests",type=int,default=256)
        if command=="collect": p.add_argument("--max-new-requests",type=int,required=True); p.add_argument("--retry-failed",action="store_true")
    args=parser.parse_args(argv)
    try:
        result=prepare(args.job,args.parent,args.max_requests) if args.command=="plan" else collect(args.job,Transport(),args.max_new_requests,args.retry_failed) if args.command=="collect" else summary(args.job)
        print(json.dumps({k:v for k,v in result.items() if k!="targets" or not isinstance(v,list)},sort_keys=True),flush=True)
        return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({"diagnostic":str(exc) if isinstance(exc,ResearchError) else "MEMBERSHIP_EVIDENCE_INPUT_INVALID"}))
        return 2


if __name__=="__main__": raise SystemExit(main())
