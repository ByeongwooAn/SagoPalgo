"""Evidence-based historical reference packs and offline date/coverage reconciliation."""
from datetime import timedelta, timezone
from decimal import Decimal
from pathlib import Path
import re
from typing import Literal

from pydantic import Field, model_validator

from .dataset import canonical, digest, read_bytes, read_json
from .history import audit, day, job_lock
from .local_use import load_local_use
from .models import Number, ResearchError, StrictModel, Timestamp


class CalendarDay(StrictModel):
    businessDate: str
    businessDay: bool
    tradingDay: bool
    openDay: bool
    settlementDay: bool

    @model_validator(mode="after")
    def valid_date(self):
        day(self.businessDate)
        return self


class Session(StrictModel):
    businessDate: str
    openAt: Timestamp
    closeAt: Timestamp
    knownAt: Timestamp
    evidence: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def valid_session(self):
        target = day(self.businessDate)
        kst = timezone(timedelta(hours=9))
        if self.openAt >= self.closeAt or self.openAt.astimezone(kst).date() != target or self.closeAt.astimezone(kst).date() != target:
            raise ValueError("session must be an evidenced interval on its Korean business date")
        return self


class ListingEvent(StrictModel):
    eventId: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,100}$")
    stockCode: str = Field(pattern=r"^[0-9]{6}$")
    effectiveDate: str
    eligible: bool
    knownAt: Timestamp
    evidence: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def valid_date(self):
        day(self.effectiveDate)
        return self


class CorporateAction(StrictModel):
    eventId: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,100}$")
    stockCode: str = Field(pattern=r"^[0-9]{6}$")
    kind: Literal["SPLIT", "DIVIDEND", "MERGER", "RIGHTS", "SUSPENSION", "OTHER"]
    effectiveDate: str
    knownAt: Timestamp
    ratio: Number | None = None
    evidence: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def valid_date(self):
        day(self.effectiveDate)
        if self.ratio is not None and Decimal(self.ratio) <= 0:
            raise ValueError("action ratio must be positive when specified")
        if self.kind == "SPLIT" and self.ratio is None:
            raise ValueError("split ratio required")
        return self


class Coverage(StrictModel):
    dimension: Literal["CALENDAR", "SESSION", "UNIVERSE", "CORPORATE_ACTIONS"]
    startDate: str
    endDate: str
    scope: Literal["STOCK", "MARKET"]
    stockCodes: list[str] = Field(default_factory=list, max_length=10000)
    status: Literal["COMPLETE", "PARTIAL", "UNKNOWN"]
    evidence: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def bounds(self):
        if day(self.startDate) > day(self.endDate):
            raise ValueError("coverage window reversed")
        if len(set(self.stockCodes)) != len(self.stockCodes) or any(not re.fullmatch(r"[0-9]{6}", v) for v in self.stockCodes):
            raise ValueError("invalid coverage stock codes")
        if self.scope == "STOCK" and not self.stockCodes:
            raise ValueError("stock-specific coverage needs its symbols")
        if self.scope == "MARKET" and self.stockCodes:
            raise ValueError("market-wide coverage must not be a current-survivor stock subset")
        return self


class ReferencePack(StrictModel):
    schemaVersion: Literal["SAGOPALGO_MARKET_REFERENCE_V1"]
    provider: str = Field(min_length=1, max_length=100)
    provenance: Literal["PROVIDER_OBSERVATIONS", "EVIDENCED_INPUT", "SYNTHETIC"]
    reference: str = Field(min_length=1, max_length=1000)
    observedAt: Timestamp
    calendar: list[CalendarDay] = Field(default_factory=list, max_length=20000)
    sessions: list[Session] = Field(default_factory=list, max_length=20000)
    listings: list[ListingEvent] = Field(default_factory=list, max_length=200000)
    actions: list[CorporateAction] = Field(default_factory=list, max_length=200000)
    coverage: list[Coverage] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def unique_keys(self):
        for values in [[v.businessDate for v in self.calendar], [v.businessDate for v in self.sessions],
                       [v.eventId for v in self.listings], [v.eventId for v in self.actions]]:
            if len(set(values)) != len(values):
                raise ValueError("duplicate reference identity")
        if any(v.knownAt > self.observedAt for v in [*self.sessions, *self.listings, *self.actions]):
            raise ValueError("cannot observe a reference before its knowledge time")
        return self


def dates_between(start, end):
    cursor = day(start)
    last = day(end)
    while cursor <= last:
        yield cursor.isoformat()
        cursor += timedelta(days=1)


def combine(packs):
    result = {k: {} for k in ["calendar", "sessions", "listings", "actions"]}
    for pack in packs:
        for name in result:
            for item in getattr(pack, name):
                key = item.businessDate if name in {"calendar", "sessions"} else item.eventId
                if key in result[name] and result[name][key] != item:
                    raise ResearchError("REFERENCE_CONFLICT")
                result[name][key] = item
    return result


def references_as_of(packs, stock, at, business_date):
    combined = combine(packs)
    day(business_date)
    selected = _membership([v for v in combined["listings"].values() if v.stockCode == stock], at, business_date)
    session = combined["sessions"].get(business_date)
    return {
        "membership": selected.model_dump(mode="json") if selected else None,
        "session": session.model_dump(mode="json") if session and session.knownAt <= at else None,
        # Both known future events and completed events are facts visible at the cutoff; no auto-adjustment.
        "actions": [v.model_dump(mode="json") for _, v in sorted(combined["actions"].items()) if v.stockCode == stock and v.knownAt <= at],
    }


def _membership(events, at, business_date):
    listings = [v for v in events if v.knownAt <= at and v.effectiveDate <= business_date]
    newest = max((v.effectiveDate for v in listings), default=None)
    selected = [v for v in listings if v.effectiveDate == newest]
    if len(selected) > 1:
        raise ResearchError("REFERENCE_MEMBERSHIP_AMBIGUOUS")
    return selected[0] if selected else None


def reconcile(report, rows, packs):
    combined = combine(packs)
    wanted = set(dates_between(report["requestStart"], report["requestEnd"]))
    calendar = {key: value for key, value in combined["calendar"].items() if key in wanted}
    # KIS explicitly documents opnd_yn for market-open/order-day checks. Preserve tr_day_yn separately.
    expected = {key for key, value in calendar.items() if value.openDay}
    observed = {row["businessDate"] for row in rows}
    unknown = sorted(wanted - set(calendar))
    missing = sorted(expected - observed)
    unexpected = sorted(key for key in observed if key in calendar and not calendar[key].openDay)
    no_session = sorted(expected - set(combined["sessions"]))
    invalid_session = sorted(key for key in combined["sessions"] if key in calendar and not calendar[key].openDay)
    stock = rows[0]["stockCode"] if rows else None
    declared = {}
    for dimension in ["CALENDAR", "SESSION", "UNIVERSE", "CORPORATE_ACTIONS"]:
        covered = set()
        for pack in packs:
            for item in pack.coverage:
                if item.dimension == dimension and item.status == "COMPLETE" and (item.scope == "MARKET" or stock in item.stockCodes):
                    first, last = max(item.startDate, report["requestStart"]), min(item.endDate, report["requestEnd"])
                    if first <= last:
                        covered.update(dates_between(first, last))
        declared[dimension] = len(wanted - covered)
    market_covered = set()
    for pack in packs:
        for item in pack.coverage:
            if item.dimension == "UNIVERSE" and item.scope == "MARKET" and item.status == "COMPLETE":
                first, last = max(item.startDate, report["requestStart"]), min(item.endDate, report["requestEnd"])
                if first <= last:
                    market_covered.update(dates_between(first, last))
    market_universe = wanted <= market_covered
    issues = []
    for code, values in [("CALENDAR_UNKNOWN", unknown), ("NO_PRICE_ON_DECLARED_OPEN_DAY", missing), ("PRICE_ON_DECLARED_CLOSED_DAY", unexpected),
                         ("SESSION_MISSING", no_session), ("SESSION_ON_CLOSED_DAY", invalid_session)]:
        if values:
            issues.append({"code": code, "count": len(values), "dates": values[:100]})
    for dimension, count in declared.items():
        if count:
            issues.append({"code": dimension + "_COVERAGE_UNCONFIRMED", "count": count})
    if not market_universe:
        issues.append({"code": "MARKET_UNIVERSE_UNCONFIRMED"})
    if report["provenance"] != "SYNTHETIC" and any(p.provenance == "SYNTHETIC" for p in packs):
        issues.append({"code": "SYNTHETIC_REFERENCE_WITH_REAL_HISTORY"})
    missing_membership, ineligible, late_sessions = [], [], []
    relevant_listings = [v for v in combined["listings"].values() if v.stockCode == stock]
    for row in rows:
        stamp = row["businessDate"]
        session = combined["sessions"].get(stamp)
        if session is None:
            missing_membership.append(stamp)
            continue
        if session.knownAt > session.closeAt:
            late_sessions.append(stamp)
        visible = _membership(relevant_listings, session.closeAt, stamp)
        if visible is None:
            missing_membership.append(stamp)
        elif not visible.eligible:
            ineligible.append(stamp)
    for code, values in [("HISTORICAL_MEMBERSHIP_MISSING", missing_membership),
                         ("PRICE_WHILE_INELIGIBLE", ineligible), ("SESSION_KNOWLEDGE_AFTER_CLOSE", late_sessions)]:
        if values:
            issues.append({"code": code, "count": len(values), "dates": values[:100]})
    return {"schemaVersion": "SAGOPALGO_REFERENCE_RECONCILIATION_V1", "historyPlanId": report["planId"],
            "historyRecords": len(rows), "requestedCalendarDates": len(wanted), "knownCalendarDates": len(calendar),
            "knownTradingDates": sum(v.tradingDay for v in calendar.values()), "knownOpenDates": len(expected),
            "expectedPriceDayBasis": "OPEN_DAY",
            "calendarFlagDifferences": sorted(k for k, v in calendar.items() if v.openDay != v.tradingDay),
            "calendarCompleteness": "COMPLETE" if not unknown else "PARTIAL",
            "status": "REFERENCE_GAPS" if issues else "EVIDENCE_SCOPES_RECONCILED",
            "issues": issues, "declaredCoverageOnly": True, "marketUniverseDeclaredComplete": market_universe,
            "syntheticSources": [p.provider for p in packs if p.provenance == "SYNTHETIC"],
            "referenceScopeReady": not issues, "usableForTraining": False,
            "usableForTrading": False, "usableForStrategyValidation": False,
            "priceAdjustmentApplied": False, "limitations": [
                "No calendar gaps, timestamps, historic survivors or corporate actions are synthesized.",
                "Coverage is an evidence declaration, not an independent proof of source completeness.",
                "Known-at filtering and effective-date filtering are distinct; no automatic past price adjustment."]}


def check_reference_files(job: Path, local_use: Path, paths: list[Path], output: Path):
    with job_lock(job):
        report, rows = audit(job, check_daily=True)
        raw = read_bytes(job / "daily.jsonl")
        policy = load_local_use(local_use, report, raw)
        packs, hashes = [], []
        for path in paths:
            data = read_bytes(path)
            packs.append(ReferencePack.model_validate(read_json(data)))
            hashes.append(digest(data))
        result = reconcile(report, rows, packs)
        result.update(localUseAccepted=True, useBasis=policy.basis, referenceHashes=hashes, dailySha256=digest(raw))
        result["reportId"] = digest(canonical(result))
        with output.open("xb") as stream:
            stream.write(canonical(result))
        return result
