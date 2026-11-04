"""Explicit original/correction review; retain both versions and require unchanged membership identity/date."""
from copy import deepcopy
import argparse
import json
from pathlib import Path
import re
import time
from urllib import parse

from . import kind_membership_evidence as acquisition,membership_evidence_facts as facts
from .dataset import canonical,digest,read_bytes,read_json
from .history import job_lock,now
from .krx_storage import atomic_json
from .models import ResearchError,utc
from .distribution_facts import Node
from .kind_cases import compact,iso_date,one_row

SCHEMA="SAGOPALGO_MEMBERSHIP_CORRECTION_PLAN_V1"
STAGES=("ORIGINAL_VIEWER","CORRECTION_VIEWER","ORIGINAL_PATH","ORIGINAL_BODY","CORRECTION_PATH","CORRECTION_BODY")


def correction_targets(parent,source_job,latest):
    targets=[]
    for target in parent["targets"]:
        _,_,completed,state=acquisition.inspect_target(source_job,target,latest)
        if state!="MEMBERSHIP_EVIDENCE_CORRECTION_REVIEW": continue
        if target["kind"]!="ADDED_OBSERVED" or target["market"]!="KOSDAQ":
            raise ResearchError("MEMBERSHIP_CORRECTION_SCOPE_UNSUPPORTED")
        links=[v for v in acquisition.html(completed["SEARCH"]).walk("a") if v.attrs.get("href")=="#viewer"]
        original=[v for v in links if v.text()=="신규상장"]
        corrected=[v for v in links if re.sub(r"\s+","",v.text())=="[정정]신규상장"]
        if len(original)!=1 or len(corrected)!=1:
            raise ResearchError("MEMBERSHIP_CORRECTION_LINEAGE_AMBIGUOUS")
        receipts=[]
        for v in [original[0],corrected[0]]:
            m=re.fullmatch(r"openDisclsViewer\('([0-9]{14})',''\);?",v.attrs.get("onclick",""))
            if not m: raise ResearchError("MEMBERSHIP_CORRECTION_LINEAGE_AMBIGUOUS")
            receipts.append(m[1])
        if not receipts[0]<receipts[1]: raise ResearchError("MEMBERSHIP_CORRECTION_LINEAGE_AMBIGUOUS")
        targets.append({**target,"originalReceipt":receipts[0],"correctionReceipt":receipts[1],
                        "searchSha256":latest[(target["observationId"],"SEARCH")]["sha256"]})
    if not 1<=len(targets)<=8: raise ResearchError("MEMBERSHIP_CORRECTION_SCOPE_INVALID")
    return targets


def prepare(folder,source_job):
    parent,_,latest=acquisition.load(source_job)
    targets=correction_targets(parent,source_job,latest)
    payload={"schemaVersion":SCHEMA,"sourcePlanId":parent["planId"],"parentSha256":parent["parentSha256"],
             "sourceKind":parent["sourceKind"],"targets":targets,"maxRequests":len(targets)*6,"minIntervalSeconds":1}
    plan={**payload,"planId":digest(canonical(payload))}
    folder.mkdir(parents=True,exist_ok=False); (folder/"raw").mkdir()
    atomic_json(folder/"plan.json",plan); atomic_json(folder/"journal.json",{"planId":plan["planId"],"attempts":[]})
    return plan


def viewer_document(raw,target,receipt):
    root=acquisition.html(raw)
    headers=[v.text() for v in root.walk("h1") if re.search(r"\([A-Z0-9]{6}\)$",v.text())]
    selectors=[v for v in root.walk("select") if v.attrs.get("id")=="mainDoc"]
    options=[v for v in selectors[0].walk("option") if v.attrs.get("value")] if len(selectors)==1 else []
    if len(headers)!=1 or not headers[0].endswith("("+target["symbol"]+")") or not 1<=len(options)<=4:
        raise ResearchError("MEMBERSHIP_CORRECTION_VIEWER_INVALID")
    wanted=receipt[:4]+"."+receipt[4:6]+"."+receipt[6:8]
    matched=[]
    all_documents=[]
    for option in options:
        value=re.fullmatch(r"([0-9]{14})\|[YN]",option.attrs["value"])
        if not value: raise ResearchError("MEMBERSHIP_CORRECTION_VIEWER_INVALID")
        all_documents.append(value[1])
        if "신규상장" in option.text() and "("+wanted+")" in option.text(): matched.append(value[1])
    if len(matched)!=1 or len(all_documents)!=len(set(all_documents)):
        raise ResearchError("MEMBERSHIP_CORRECTION_DOCUMENT_AMBIGUOUS")
    return {"document":matched[0],"documents":all_documents,"viewerIssuerName":headers[0][:-(len(target["symbol"])+2)].strip()}


def requests_for(target,completed):
    for label in ["ORIGINAL","CORRECTION"]:
        receipt=target["originalReceipt" if label=="ORIGINAL" else "correctionReceipt"]
        yield label+"_VIEWER",{"url":acquisition.BASE+"/common/disclsviewer.do?"+parse.urlencode({"acptno":receipt,"method":"search"}),"method":"GET","parameters":None}
    for label in ["ORIGINAL","CORRECTION"]:
        receipt=target["originalReceipt" if label=="ORIGINAL" else "correctionReceipt"]
        viewer=viewer_document(completed[label+"_VIEWER"],target,receipt)
        yield label+"_PATH",{"url":acquisition.BASE+"/common/disclsviewer.do","method":"POST","parameters":{"method":"searchContents","docNo":viewer["document"]}}
        url=acquisition.path_result(completed[label+"_PATH"],receipt,viewer["document"])
        yield label+"_BODY",{"url":url,"method":"GET","parameters":None}


def load(folder,source_job):
    parent,_,source_latest=acquisition.load(source_job)
    plan=read_json(read_bytes(folder/"plan.json")); payload={k:v for k,v in plan.items() if k!="planId"}
    if (plan.get("schemaVersion")!=SCHEMA or plan.get("planId")!=digest(canonical(payload))
            or plan.get("sourcePlanId")!=parent["planId"] or plan.get("parentSha256")!=parent["parentSha256"]
            or plan.get("sourceKind")!=parent["sourceKind"] or not 1<=len(plan["targets"])<=8
            or plan["targets"]!=correction_targets(parent,source_job,source_latest)
            or plan.get("maxRequests")!=len(plan["targets"])*6 or plan.get("minIntervalSeconds")!=1):
        raise ResearchError("MEMBERSHIP_CORRECTION_PLAN_INVALID")
    source_targets={v["observationId"]:v for v in parent["targets"]}
    for target in plan["targets"]:
        base={k:v for k,v in target.items() if k not in {"originalReceipt","correctionReceipt","searchSha256"}}
        if (base!=source_targets.get(target["observationId"]) or target["searchSha256"]!=source_latest[(target["observationId"],"SEARCH")]["sha256"]):
            raise ResearchError("MEMBERSHIP_CORRECTION_PARENT_MISMATCH")
    journal=read_json(read_bytes(folder/"journal.json")); latest={}
    if set(journal)!={"planId","attempts"} or journal["planId"]!=plan["planId"] or len(journal["attempts"])>plan["maxRequests"]:
        raise ResearchError("MEMBERSHIP_CORRECTION_JOURNAL_INVALID")
    ids={v["observationId"] for v in plan["targets"]}
    for seq,entry in enumerate(journal["attempts"],1):
        key=(entry["targetId"],entry["stage"])
        if (type(entry["seq"]) is not int or entry["seq"]!=seq or key in latest or key[0] not in ids or key[1] not in STAGES
                or entry["state"] not in {"RESERVED","CAPTURED","FAILED"}):
            raise ResearchError("MEMBERSHIP_CORRECTION_JOURNAL_INVALID")
        utc(entry["startedAt"])
        fields={"seq","targetId","stage","request","state","startedAt"}
        if "sha256" in entry:
            fields|={"sha256","capturedAt"}
            if utc(entry["capturedAt"])<utc(entry["startedAt"]) or digest(read_bytes(folder/"raw"/f"{seq:03d}.bin"))!=entry["sha256"]:
                raise ResearchError("MEMBERSHIP_CORRECTION_RAW_TAMPERED")
        if entry["state"]=="CAPTURED": fields|={"sha256","capturedAt"}
        if entry["state"]=="FAILED":
            fields|={"diagnostic","finishedAt"}
            if utc(entry["finishedAt"])<utc(entry["startedAt"]): raise ResearchError("MEMBERSHIP_CORRECTION_JOURNAL_INVALID")
        if set(entry)!=fields: raise ResearchError("MEMBERSHIP_CORRECTION_JOURNAL_INVALID")
        latest[key]=entry
    expected={}
    for target in plan["targets"]: inspect_target(folder,target,latest,expected)
    if any(v["request"]!=expected.get((v["targetId"],v["stage"])) for v in journal["attempts"]):
        raise ResearchError("MEMBERSHIP_CORRECTION_REQUEST_TAMPERED")
    return plan,journal,latest


def inspect_target(folder,target,latest,expected=None):
    completed={}
    try:
        for stage,spec in requests_for(target,completed):
            key=(target["observationId"],stage)
            if expected is not None: expected[key]=spec
            entry=latest.get(key)
            if not entry: return stage,spec,completed,"PENDING"
            if entry["request"]!=spec: raise ResearchError("MEMBERSHIP_CORRECTION_REQUEST_TAMPERED")
            if entry["state"]!="CAPTURED": return None,None,completed,entry["state"]
            completed[stage]=read_bytes(folder/"raw"/f"{entry['seq']:03d}.bin")
        return None,None,completed,"PAIR_CAPTURED"
    except ResearchError as exc:
        if str(exc)=="MEMBERSHIP_CORRECTION_REQUEST_TAMPERED": raise
        return None,None,completed,str(exc)


def collect(folder,source_job,transport,max_new_requests,sleep=time.sleep):
    if type(max_new_requests) is not int or not 0<=max_new_requests<=48:
        raise ResearchError("MEMBERSHIP_CORRECTION_BUDGET_INVALID")
    with job_lock(folder):
        plan,journal,latest=load(folder,source_job)
        if transport.source_kind!=plan["sourceKind"]: raise ResearchError("MEMBERSHIP_CORRECTION_SOURCE_KIND_MISMATCH")
        used=0
        for target in plan["targets"]:
            while True:
                stage,spec,_,state=inspect_target(folder,target,latest)
                if not stage or used>=max_new_requests: break
                if journal["attempts"]:
                    elapsed=(utc(now())-utc(journal["attempts"][-1]["startedAt"])).total_seconds()
                    if elapsed<0: raise ResearchError("MEMBERSHIP_CORRECTION_CLOCK_REGRESSION")
                    if elapsed<1: sleep(1-elapsed)
                seq=len(journal["attempts"])+1
                if seq>plan["maxRequests"]: raise ResearchError("MEMBERSHIP_CORRECTION_BUDGET_EXHAUSTED")
                entry={"seq":seq,"targetId":target["observationId"],"stage":stage,"request":spec,"state":"RESERVED","startedAt":now()}
                journal["attempts"].append(entry); atomic_json(folder/"journal.json",journal)
                try:
                    raw=transport.fetch(spec); (folder/"raw"/f"{seq:03d}.bin").write_bytes(raw)
                    entry.update(state="CAPTURED",sha256=digest(raw),capturedAt=now()); atomic_json(folder/"journal.json",journal)
                except Exception as exc:
                    entry.update(state="FAILED",diagnostic=str(exc) if isinstance(exc,ResearchError) else "MEMBERSHIP_CORRECTION_CAPTURE_FAILED",finishedAt=now())
                    atomic_json(folder/"journal.json",journal)
                latest[(target["observationId"],stage)]=entry; used+=1
                if entry["state"]=="FAILED": break
        return {"requests":len(journal["attempts"]),"maxRequests":plan["maxRequests"],"states":{
            t["symbol"]:inspect_target(folder,t,latest)[3] for t in plan["targets"]}}


def apply(folder,source_job,supplement,contexts):
    plan,_,latest=load(folder,source_job)
    source_plan,_,_=acquisition.load(source_job)
    if supplement["planId"]!=source_plan["planId"] or supplement["parentSha256"]!=plan["parentSha256"]:
        raise ResearchError("MEMBERSHIP_CORRECTION_PARENT_MISMATCH")
    result=deepcopy(supplement)
    corrected_reviews=[]
    for target in plan["targets"]:
        _,_,completed,state=inspect_target(folder,target,latest)
        if state!="PAIR_CAPTURED": continue
        identity=target["observationId"]
        pending=[v for v in result["reviews"] if v["observationId"]==identity]
        if len(pending)!=1 or pending[0]["diagnostic"]!="MEMBERSHIP_EVIDENCE_CORRECTION_REVIEW":
            raise ResearchError("MEMBERSHIP_CORRECTION_TARGET_MISMATCH")
        try:
            original_view=viewer_document(completed["ORIGINAL_VIEWER"],target,target["originalReceipt"])
            corrected_view=viewer_document(completed["CORRECTION_VIEWER"],target,target["correctionReceipt"])
            if (original_view["document"]==corrected_view["document"]
                    or not {original_view["document"],corrected_view["document"]}<=set(corrected_view["documents"])):
                raise ResearchError("MEMBERSHIP_CORRECTION_VIEWER_LINEAGE_UNCONFIRMED")
            reviewed_versions={original_view["document"],corrected_view["document"]}
            if set(corrected_view["documents"])!=reviewed_versions or not set(original_view["documents"])<=reviewed_versions:
                raise ResearchError("MEMBERSHIP_CORRECTION_UNREVIEWED_VERSION_PRESENT")
            original_entry=latest[(identity,"ORIGINAL_BODY")]; corrected_entry=latest[(identity,"CORRECTION_BODY")]
            known=max([latest[(identity,s)]["capturedAt"] for s in STAGES],key=utc)
            original=facts.parse_fact(completed["ORIGINAL_BODY"],original_entry["request"]["url"],target,known,original_view["viewerIssuerName"],contexts.get(identity))
            corrected=facts.parse_fact(completed["CORRECTION_BODY"],corrected_entry["request"]["url"],target,known,corrected_view["viewerIssuerName"],contexts.get(identity),True)
            audit=review_industry_correction(completed["ORIGINAL_BODY"],completed["CORRECTION_BODY"],original,corrected,target)
            corrected["correctionReview"]={**audit,"originalSourceUrl":original["sourceUrl"],"originalSourceSha256":original["sourceSha256"],
                "originalDocument":original_view["document"],"correctedDocument":corrected_view["document"],
                "originalReceipt":target["originalReceipt"],"correctedReceipt":target["correctionReceipt"],
                "viewerLinkedVersions":True,"knownAt":known}
            corrected["acquisitionHashes"]={s:latest[(identity,s)]["sha256"] for s in STAGES}
            result["facts"].append(corrected)
            result["reviews"].remove(pending[0])
            corrected_reviews.append({"observationId":identity,**corrected["correctionReview"]})
        except (ResearchError,ValueError) as exc:
            pending[0]["diagnostic"]=str(exc) if isinstance(exc,ResearchError) else "MEMBERSHIP_CORRECTION_INPUT_INVALID"
    result.update(schemaVersion="SAGOPALGO_MEMBERSHIP_DISCLOSURE_FACTS_V2",verified=len(result["facts"]),reviewRequired=len(result["reviews"]),
                  correctionPlanId=plan["planId"],correctionReviews=corrected_reviews,
                  correctionHeaderDateIssues=sum(v["headerDateDiffersFromOriginalReceipt"] for v in corrected_reviews))
    return result


def review_industry_correction(original_raw,corrected_raw,original,corrected,target):
    fields=["kind","stockCode","historyIsin","sourceIsin","market","sourceShareClass","date"]
    if any(original[k]!=corrected[k] for k in fields):
        raise ResearchError("MEMBERSHIP_CORRECTION_MEMBERSHIP_FIELDS_CHANGED")
    def tables(raw):
        result=[]
        for table in acquisition.html(raw).walk("table"):
            if list(table.walk("table")): continue
            rows=[[v.text() for v in tr.children if isinstance(v,Node) and v.tag in {"td","th"}] for tr in table.walk("tr")]
            if rows: result.append(rows)
        return result
    before=tables(original_raw); after=tables(corrected_raw)
    original_tables=[v for v in before if v[0] and compact(v[0][0])=="1.회사명"]
    corrected_tables=[v for v in after if v[0] and compact(v[0][0])=="1.회사명"]
    headers=[v for v in after if v[0] and compact(v[0][0])=="1.정정관련공시서류:"]
    diffs=[v for v in after if v[0]==["항목","정정전","정정후"]]
    if len(original_tables)!=1 or len(corrected_tables)!=1 or len(headers)!=1 or len(diffs)!=1:
        raise ResearchError("MEMBERSHIP_CORRECTION_HEADER_AMBIGUOUS")
    a,b=original_tables[0],corrected_tables[0]
    if len(a)!=len(b) or any(not x or not y or compact(x[0])!=compact(y[0]) for x,y in zip(a,b)):
        raise ResearchError("MEMBERSHIP_CORRECTION_MAIN_LAYOUT_CHANGED")
    changed=[compact(x[0]) for x,y in zip(a,b) if list(map(compact,x))!=list(map(compact,y))]
    if changed!=["8.업종"] or len(diffs[0])!=2 or diffs[0][1][0]!="업종":
        raise ResearchError("MEMBERSHIP_CORRECTION_NONMEMBERSHIP_REVIEW_REQUIRED")
    header_date=one_row(headers[0],"2. 정정관련 공시서류 제출일 :")
    if len(header_date)!=2: raise ResearchError("MEMBERSHIP_CORRECTION_HEADER_DATE_AMBIGUOUS")
    declared=iso_date(header_date[1])
    original_date=target["originalReceipt"][:4]+"-"+target["originalReceipt"][4:6]+"-"+target["originalReceipt"][6:8]
    return {"membershipFieldsUnchanged":fields,"changedMainFields":changed,"declaredRelatedDocumentDate":declared,
            "originalReceiptDate":original_date,"headerDateDiffersFromOriginalReceipt":declared!=original_date,
            "headerRelatedDateMatchesOriginalReceipt":declared==original_date,"membershipDateOnlyConfirmed":True}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    for command in ["plan","collect","audit"]:
        p=sub.add_parser(command); p.add_argument("--job",type=Path,required=True); p.add_argument("--source-job",type=Path,required=True)
        if command=="collect": p.add_argument("--max-new-requests",type=int,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=="plan":
            plan=prepare(args.job,args.source_job)
            result={"planId":plan["planId"],"targets":len(plan["targets"]),"maxRequests":plan["maxRequests"]}
        elif args.command=="collect":
            result=collect(args.job,args.source_job,acquisition.Transport(),args.max_new_requests)
        else:
            plan,journal,latest=load(args.job,args.source_job)
            result={"planId":plan["planId"],"requests":len(journal["attempts"]),"maxRequests":plan["maxRequests"],
                    "states":{t["symbol"]:inspect_target(args.job,t,latest)[3] for t in plan["targets"]}}
        print(json.dumps(result,sort_keys=True),flush=True); return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({"diagnostic":str(exc) if isinstance(exc,ResearchError) else "MEMBERSHIP_CORRECTION_INPUT_INVALID"})); return 2


if __name__=="__main__": raise SystemExit(main())
