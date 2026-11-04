"""Reviewed entry/exit forms confirm exchange dates, not first-ever IPO or legal merger effects."""
import json
import re

from . import kind_membership_evidence as capture
from .dataset import canonical,digest,read_bytes
from .distribution_facts import Node,XForms
from .kind_cases import compact,iso_date,one_row,scalar_date
from .models import ResearchError,utc

FORMS = {
    "70760":("KOSDAQ","ADDED_OBSERVED","신규상장","10.상장일(매매개시일)",None),
    "70769":("KOSDAQ","REMOVED_OBSERVED","상장폐지","7.상장폐지일","8.근거규정"),
    "70718":("KOSDAQ","ADDED_OBSERVED","주권 등 신규상장 기준가격 안내 (SPAC소멸합병상장)","4.적용일","5.근거규정"),
    "68051":("KOSPI","REMOVED_OBSERVED","상장폐지","6.상장폐지일","7.근거규정"),
}


def parse_fact(raw,url,target,captured_at,viewer_name,instrument_context=None,reviewed_correction=False):
    utc(captured_at)
    capture.validate_url(url)
    form=url.rsplit("/",1)[1].removesuffix(".htm")
    if form=="68152":
        return parse_kospi_text(raw,url,target,captured_at,viewer_name)
    if form not in FORMS:
        raise ResearchError("MEMBERSHIP_FACT_FORM_REVIEW_REQUIRED")
    market,kind,title,date_field,rule=FORMS[form]
    if (market,kind)!=(target["market"],target["kind"]):
        raise ResearchError("MEMBERSHIP_FACT_MARKET_OR_DIRECTION_MISMATCH")
    if len(raw)>capture.LIMIT:
        raise ResearchError("MEMBERSHIP_FACT_SIZE_LIMIT")
    text=raw.decode("utf-8-sig")
    text=re.sub(r'\A\s*<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1\.0 Transitional//EN" '
                r'"http://www\.w3\.org/TR/xhtml1/DTD/xhtml1-transitional\.dtd">',"",text,count=1)
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)",text,re.I):
        raise ResearchError("MEMBERSHIP_FACT_DECLARATION_UNSUPPORTED")
    x=XForms(); x.feed(text); x.close()
    root=x.root
    if len(x.stack)!=1 or len(list(root.walk("html")))!=1:
        raise ResearchError("MEMBERSHIP_FACT_HTML_INVALID")
    titles=[v.text() for v in root.walk("a") if v.attrs.get("name")=="#2"]
    titles += [v.text() for v in root.walk("div") if v.attrs.get("class")=="xforms_title"]
    if reviewed_correction:
        if sum(compact(v)=="정정신고(보고)" for v in titles)!=1:
            raise ResearchError("MEMBERSHIP_FACT_CORRECTION_HEADER_INVALID")
        titles=[v for v in titles if compact(v)!="정정신고(보고)"]
    if titles!=[title]:
        raise ResearchError("MEMBERSHIP_FACT_TITLE_MISMATCH")
    if not reviewed_correction and ("정정신고" in compact(root.text()) or "정정공시" in compact(root.text())):
        raise ResearchError("MEMBERSHIP_FACT_CORRECTION_REVIEW_REQUIRED")
    tables=[]
    for table in root.walk("table"):
        rows=[[v.text() for v in tr.children if isinstance(v,Node) and v.tag in {"td","th"}] for tr in table.walk("tr")]
        if rows and rows[0] and compact(rows[0][0])=="1.회사명":
            if list(table.walk("table")) or len(rows)>1000:
                raise ResearchError("MEMBERSHIP_FACT_TABLE_AMBIGUOUS")
            tables.append(rows)
    if len(tables)!=1:
        raise ResearchError("MEMBERSHIP_FACT_TABLE_AMBIGUOUS")
    rows=tables[0]
    issuer=rows[0][-1] if form=="70760" else rows[0][1]
    if not issuer or len(issuer)>200:
        raise ResearchError("MEMBERSHIP_FACT_ISSUER_INVALID")
    code="A"+target["symbol"]
    coded=[r for r in rows if code in r]
    if len(coded)!=1 or coded[0][0] not in {"보통주","보통주식","KDR"}:
        raise ResearchError("MEMBERSHIP_FACT_FULL_CODE_OR_SHARE_CLASS_MISMATCH")
    if coded[0][0]=="KDR":
        if (instrument_context is None or instrument_context.get("symbol")!=target["symbol"]
                or instrument_context.get("isin")!=target["isin"] or instrument_context.get("securityType")!="주식예탁증권"
                or instrument_context.get("shareType")!="보통주"):
            raise ResearchError("MEMBERSHIP_FACT_KDR_CONTEXT_REQUIRED")
    codes=re.findall(r"(?<![A-Za-z0-9])A([A-Z0-9]{6})(?![A-Za-z0-9])"," ".join(" ".join(r) for r in rows))
    if codes.count(target["symbol"])!=1:
        raise ResearchError("MEMBERSHIP_FACT_FULL_CODE_OR_SHARE_CLASS_MISMATCH")
    isins=[v for v in coded[0] if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{10}",v)]
    if len(isins)>1 or isins and isins[0]!=target["isin"]:
        raise ResearchError("MEMBERSHIP_FACT_ISIN_MISMATCH")
    if rule:
        expected="유가증권시장" if market=="KOSPI" else "코스닥시장"
        if expected not in compact(" ".join(one_row(rows,rule)[1:])):
            raise ResearchError("MEMBERSHIP_FACT_MARKET_RULE_MISMATCH")
    if form=="70718" and one_row(rows,"3.사유")[1:]!=["SPAC소멸합병상장"]:
        raise ResearchError("MEMBERSHIP_FACT_REASON_MISMATCH")
    stamp=scalar_date(rows,date_field)
    if not target["observedFrom"]<stamp<=target["observedTo"]:
        raise ResearchError("MEMBERSHIP_FACT_DATE_CONFLICT")
    return {"observationId":target["observationId"],"kind":"MEMBERSHIP_ENTRY" if kind=="ADDED_OBSERVED" else "MEMBERSHIP_EXIT",
            "stockCode":target["symbol"],"historyIsin":target["isin"],"sourceIsin":isins[0] if isins else None,
            "isinProvided":bool(isins),"market":market,"issuerName":issuer,"viewerIssuerName":viewer_name,
            "date":stamp,"dateBasis":"EXCHANGE_ENTRY_APPLICATION_DATE" if form=="70718" else "EXCHANGE_LISTING_DATE" if kind=="ADDED_OBSERVED" else "EXCHANGE_DELISTING_DATE",
            "marketBasis":"EXPLICIT_MARKET_RULE" if rule else "REVIEWED_KOSDAQ_FORM_CODE",
            "identityBasis":"VIEWER_AND_SOURCE_FULL_STOCK_CODE","form":form,
            "knownAt":max([captured_at,(instrument_context or {}).get("knownAt",captured_at)],key=utc),
            "sourceShareClass":coded[0][0],"instrumentContext":instrument_context if coded[0][0]=="KDR" else None,
            "reviewedCorrection":reviewed_correction,
            "knowledgeBasis":"FETCH_TIME_ONLY","sourceUrl":url,"sourceSha256":digest(raw),
            "legalMergerCompletionConfirmed":False,"firstEverIpoConfirmed":False,"exchangeRatio":None}


def parse_kospi_text(raw,url,target,captured_at,viewer_name):
    if (target["market"],target["kind"])!=("KOSPI","ADDED_OBSERVED"):
        raise ResearchError("MEMBERSHIP_FACT_MARKET_OR_DIRECTION_MISMATCH")
    text=capture.html(raw).text()
    if any(v in compact(text) for v in ["정정신고","정정공시"]):
        raise ResearchError("MEMBERSHIP_FACT_CORRECTION_REVIEW_REQUIRED")
    names=re.findall(r"^◎ (.+?) 주권 신규상장 상장내역 ◎ ① 상장종목 - 한글종목명 : (.+?) - 영문종목명 :",text)
    dates=re.findall(r"② 상장일 : ([0-9]{4})년 ([0-9]{1,2})월 ([0-9]{1,2})일 ③",text)
    identities=re.findall(r"④ 표준코드 : ([A-Z]{2}[A-Z0-9]{10}) \(단축코드 :A([A-Z0-9]{6})\)",text)
    if (len(names)!=1 or len(dates)!=1 or len(identities)!=1 or identities[0]!=(target["isin"],target["symbol"])
            or "⑤ 주식의 종류와 수 : 보통주 " not in text):
        raise ResearchError("MEMBERSHIP_FACT_KOSPI_TEXT_IDENTITY_INVALID")
    stamp="%04d-%02d-%02d"%tuple(map(int,dates[0]))
    iso_date(stamp)
    if not target["observedFrom"]<stamp<=target["observedTo"]:
        raise ResearchError("MEMBERSHIP_FACT_DATE_CONFLICT")
    return {"observationId":target["observationId"],"kind":"MEMBERSHIP_ENTRY","stockCode":target["symbol"],
            "historyIsin":target["isin"],"sourceIsin":identities[0][0],"isinProvided":True,"market":"KOSPI",
            "issuerName":names[0][0],"viewerIssuerName":viewer_name,"date":stamp,"dateBasis":"EXCHANGE_LISTING_DATE",
            "marketBasis":"REVIEWED_KOSPI_PLAIN_TEXT_FORM_CODE","identityBasis":"VIEWER_FULL_STOCK_CODE_AND_SOURCE_ISIN",
            "form":"68152","knownAt":captured_at,"knowledgeBasis":"FETCH_TIME_ONLY","sourceUrl":url,"sourceSha256":digest(raw),
            "sourceShareClass":"보통주","instrumentContext":None,"reviewedCorrection":False,
            "legalMergerCompletionConfirmed":False,"firstEverIpoConfirmed":False,"exchangeRatio":None}


def build(folder,contexts=None):
    plan,journal,latest=capture.load(folder)
    facts,reviews=[],[]
    for target in plan["targets"]:
        _,_,completed,state=capture.inspect_target(folder,target,latest)
        if state!="BODY_CAPTURED":
            reviews.append({"observationId":target["observationId"],"symbol":target["symbol"],"diagnostic":state})
            continue
        entry=latest[(target["observationId"],"BODY")]
        viewer=capture.viewer_result(completed["VIEWER"],target)
        known=max([latest[(target["observationId"],stage)]["capturedAt"] for stage in capture.STAGES],key=utc)
        try:
            fact=parse_fact(completed["BODY"],entry["request"]["url"],target,known,viewer["viewerIssuerName"],(contexts or {}).get(target["observationId"]))
            fact["acquisitionHashes"]={stage:latest[(target["observationId"],stage)]["sha256"] for stage in capture.STAGES}
            facts.append(fact)
        except (ResearchError,ValueError) as exc:
            reviews.append({"observationId":target["observationId"],"symbol":target["symbol"],"sourceUrl":entry["request"]["url"],
                            "sourceSha256":entry["sha256"],"diagnostic":str(exc) if isinstance(exc,ResearchError) else "MEMBERSHIP_FACT_INPUT_INVALID"})
    return {"schemaVersion":"SAGOPALGO_MEMBERSHIP_DISCLOSURE_FACTS_V1","planId":plan["planId"],"parentSha256":plan["parentSha256"],
            "sourceKind":plan["sourceKind"],"targets":len(plan["targets"]),"facts":facts,"reviews":reviews,
            "verified":len(facts),"reviewRequired":len(reviews),"marketUniverseComplete":False,
            "usableForTraining":False,"usableForTrading":False}
