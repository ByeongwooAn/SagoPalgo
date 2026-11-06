"""Evidence-bound intraday code and conditional date/clock diagnostics, no backdating."""
from collections import Counter
from bisect import bisect_left, bisect_right
from datetime import timedelta, timezone
import hashlib

from .dataset import canonical, digest
from .models import ResearchError
from .stored import precise_time

SESSION_BLOB = "34b9c5ace597132a601d7b591e5a3534646535fd"
SESSION_URL = "https://github.com/koreainvestment/open-trading-api/blob/main/legacy/Sample01/kis_domstk_ws.py"
KST = timezone(timedelta(hours=9))


def session_evidence(raw):
    blob = hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
    if blob != SESSION_BLOB or raw.decode("utf-8").count("시간 구분 코드(0 : 장중 )") != 2:
        raise ResearchError("SESSION_SOURCE_EVIDENCE_MISMATCH")
    return {"url":SESSION_URL, "blobSha1":blob, "sha256":digest(raw), "code":"0",
            "meaning":"INTRADAY_REPORTED", "continuousMatchingConfirmed":False}


def quality_profile(records, evidence_raw, anchor_age_ms=5000):
    evidence = session_evidence(evidence_raw)
    if not isinstance(anchor_age_ms,int) or not 0 <= anchor_age_ms <= 60000:
        raise ResearchError("ANCHOR_AGE_INVALID")
    times={r["eventId"]:(precise_time(r["marketAt"]),precise_time(r["receivedAt"])) for r in records}
    trades=sorted([r for r in records if r["type"]=="TRADE" and r["dateBasis"]=="PROVIDER_DATE"],
                  key=lambda r:times[r["eventId"]][1])
    arrivals=[times[r["eventId"]][1] for r in trades]
    profiled = []
    dates = Counter()
    lags = []
    for item in records:
        at, received = times[item["eventId"]]
        lag = (received-at).total_seconds()*1000
        lags.append(lag)
        date = {"status":"PROVIDER_DATE" if item["dateBasis"]=="PROVIDER_DATE" else "UNCONFIRMED",
                "businessDate":at.astimezone(KST).date().isoformat(), "anchorEventId":None,
                "knownAt":item["knownAt"]}
        if item["dateBasis"]!="PROVIDER_DATE":
            start=bisect_left(arrivals,received-timedelta(milliseconds=anchor_age_ms))
            end=bisect_right(arrivals,received)
            anchors = [t for t in trades[start:end] if t["stockCode"]==item["stockCode"] and t["market"]==item["market"]
                       and abs(at-times[t["eventId"]][0])<=timedelta(milliseconds=anchor_age_ms)
                       and times[t["eventId"]][0].astimezone(KST).date()==received.astimezone(KST).date()
                       and at.astimezone(KST).date()==received.astimezone(KST).date()]
            if anchors:
                anchor=max(anchors,key=lambda r:(precise_time(r["receivedAt"]),r["eventId"]))
                date.update(status="CROSS_FEED_ANCHORED_ONLY",anchorEventId=anchor["eventId"],
                            knownAt=max(item["knownAt"],anchor["knownAt"]))
        dates[date["status"]]+=1
        profiled.append({**item,"dateEvidence":date,"sessionMeaning":evidence["meaning"] if item["session"]=="0" else "UNCONFIRMED",
                         "clockQuality":"RECEIPT_BEFORE_MARKET_TIME" if lag<0 else "ORDERED_OBSERVATION",
                         "receiptLagMs":lag})
    return profiled,{"schemaVersion":"SAGOPALGO_TICK_QUALITY_V1", "sessionEvidence":evidence,
                     "dateEvidenceCounts":dict(dates), "receiptBeforeMarketCount":sum(x<0 for x in lags),
                     "receiptLagMs":{"minimum":min(lags) if lags else None,"maximum":max(lags) if lags else None},
                     "originalDateBasisAndFlagsPreserved":True,"historicalClockCorrectionApplied":False,
                     "providerSecondLabelsAreNotNanosecondTimestamps":True,"usableForTrading":False,
                     "usableForStrategyValidation":False}
