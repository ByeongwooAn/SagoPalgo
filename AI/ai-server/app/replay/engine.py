"""Deterministic, explicit-intent bar estimates; not an exchange matching engine."""
from datetime import timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext

from .dataset import canonical, digest, known_at, membership, snapshot
from .models import ReplayConfig, ResearchError

# This version supports modern KRX records only, with an explicit UTC+09:00 day boundary.
KST = timezone(timedelta(hours=9))
BPS = Decimal(10000)


def money(value: Decimal) -> str:
    return format(value, "f")


def replay(manifest, spec, records, quality, config: ReplayConfig) -> dict:
    with localcontext() as context:
        context.prec = 60
        return _replay(manifest, spec, records, quality, config)


def _replay(manifest, spec, records, quality, config):
    sources = {s.sourceId: s for s in spec.sources}
    if config.barSourceId not in sources or config.universeSourceId not in sources:
        raise ResearchError("REPLAY_SOURCE_MISSING")
    if any(s.provenance == "SYNTHETIC" for s in spec.sources) and not config.allowSynthetic:
        raise ResearchError("SYNTHETIC_OPT_IN_REQUIRED")
    if any(s.availability == "PUBLICATION_ASSUMED" for s in spec.sources) and not config.allowAssumedAvailability:
        raise ResearchError("ASSUMED_AVAILABILITY_OPT_IN_REQUIRED")
    bars = [r for r in records if r.kind == "BAR" and r.sourceId == config.barSourceId and r.revision == 1]
    if not bars or any(r.payload.timeframe != "MINUTE_1" for r in bars):
        raise ResearchError("MINUTE_BARS_REQUIRED")
    bars.sort(key=lambda r: (r.payload.startAt, r.stockCode, r.itemId))
    # Validate every decision before producing any execution result.
    plan = []
    outcomes = []
    for intent in sorted(config.intents, key=lambda i: (i.decisionAt, i.intentId)):
        visible = snapshot(records, spec, intent.decisionAt)
        by_ref = {r.ref: r for r in visible}
        if any(ref not in by_ref or by_ref[ref].stockCode != intent.stockCode for ref in intent.evidence):
            raise ResearchError("EVIDENCE_NOT_VISIBLE_AT_DECISION")
        evidence_bars = [by_ref[ref] for ref in intent.evidence if by_ref[ref].kind == "BAR"
                         and by_ref[ref].sourceId == config.barSourceId]
        if not evidence_bars:
            raise ResearchError("PRICE_EVIDENCE_REQUIRED")
        last_signal = max(r.payload.endAt for r in evidence_bars)
        member = membership(visible, config.universeSourceId, intent.stockCode)
        if member is None or not member.payload.eligible:
            raise ResearchError("DECISION_OUTSIDE_KNOWN_UNIVERSE")
        eligible = [r for r in bars if r.stockCode == intent.stockCode
                    and r.payload.startAt > intent.decisionAt
                    and r.payload.startAt >= intent.decisionAt + timedelta(milliseconds=config.latencyMs)
                    and r.payload.startAt < intent.expiresAt
                    and r.payload.endAt <= config.endAt
                    and r.payload.startAt.astimezone(KST).date() == intent.decisionAt.astimezone(KST).date()]
        if not eligible:
            outcomes.append({"intentId": intent.intentId, "status": "NO_NEXT_BAR", "filledQuantity": 0})
        else:
            plan.append((eligible[0].payload.startAt, intent.decisionAt, intent.intentId, intent, eligible[0], last_signal))
    cash = Decimal(config.initialCash)
    positions = {}
    consumed = {}
    fills = []
    tick = Decimal(config.tickSize)
    friction = (Decimal(config.halfSpreadBps) + Decimal(config.slippageBps)) / BPS
    total_fees = Decimal(0)
    total_taxes = Decimal(0)
    for executed_at, _, _, intent, row, signal_end in sorted(plan, key=lambda p: p[:3]):
        bar = row.payload
        outcome = {"intentId": intent.intentId, "at": executed_at.isoformat(), "filledQuantity": 0}
        visible = snapshot(records, spec, executed_at)
        member = membership(visible, config.universeSourceId, intent.stockCode)
        status = None
        if (executed_at - signal_end).total_seconds() > config.maxSignalAgeSeconds:
            status = "STALE_SIGNAL"
        elif member is None or not member.payload.eligible:
            status = "NOT_ELIGIBLE_AT_EXECUTION"
        elif known_at(row, spec) > config.endAt:
            status = "EXECUTION_BAR_UNAVAILABLE"
        elif any(e.sourceId == config.barSourceId and e.stockCode == intent.stockCode
                 and (e.endAt - e.startAt).total_seconds() == 60
                 and intent.decisionAt < e.startAt < executed_at
                 and e.startAt >= intent.decisionAt + timedelta(milliseconds=config.latencyMs)
                 for e in spec.expectedBars):
            status = "MISSING_EXECUTION_BAR"
        elif bar.status != "TRADABLE":
            status = "HALTED"
        capacity = int((Decimal(bar.volume) * Decimal(config.participationRate)).to_integral_value(rounding=ROUND_FLOOR))
        capacity -= consumed.get(row.ref, 0)
        if status is None and capacity <= 0:
            status = "NO_LIQUIDITY"
        if status:
            outcomes.append({**outcome, "status": status})
            continue
        opened = Decimal(bar.open)
        buying = intent.side == "BUY"
        rounding = ROUND_CEILING if buying else ROUND_FLOOR
        price = ((opened * (1 + friction if buying else 1 - friction)) / tick).to_integral_value(rounding=rounding) * tick
        if price <= 0:
            outcomes.append({**outcome, "status": "INVALID_ESTIMATED_PRICE"})
            continue
        quantity = min(intent.quantity, capacity)
        quantity = min(quantity, int(Decimal(config.maxOrderNotional) // price))
        if not buying:
            quantity = min(quantity, positions.get(intent.stockCode, 0))
        else:
            # Exact binary search includes rounded fees in the affordability check.
            low, high = 0, quantity
            while low < high:
                middle = (low + high + 1) // 2
                notional = price * middle
                fee = (notional * Decimal(config.feeBps) / BPS).to_integral_value(rounding=ROUND_CEILING)
                if notional + fee <= cash:
                    low = middle
                else:
                    high = middle - 1
            quantity = low
        if quantity == 0:
            outcomes.append({**outcome, "status": "RESOURCE_OR_ORDER_LIMIT"})
            continue
        notional = price * quantity
        fee = (notional * Decimal(config.feeBps) / BPS).to_integral_value(rounding=ROUND_CEILING)
        tax = Decimal(0) if buying else (notional * Decimal(config.sellTaxBps) / BPS).to_integral_value(rounding=ROUND_CEILING)
        if not buying and cash + notional - fee - tax < 0:
            outcomes.append({**outcome, "status": "RESOURCE_OR_ORDER_LIMIT"})
            continue
        if buying:
            cash -= notional + fee
            positions[intent.stockCode] = positions.get(intent.stockCode, 0) + quantity
        else:
            cash += notional - fee - tax
            positions[intent.stockCode] -= quantity
        consumed[row.ref] = consumed.get(row.ref, 0) + quantity
        total_fees += fee
        total_taxes += tax
        fill = {"intentId": intent.intentId, "stockCode": intent.stockCode, "side": intent.side,
                "decisionAt": intent.decisionAt.isoformat(), "at": executed_at.isoformat(),
                "barRef": row.ref, "evidence": intent.evidence, "quantity": quantity,
                "referenceOpen": bar.open, "estimatedPrice": money(price), "notional": money(notional),
                "fee": money(fee), "sellTax": money(tax), "cashAfter": money(cash),
                "priceFrictionAmount": money(abs(price - opened) * quantity)}
        fills.append(fill)
        outcomes.append({**outcome, "status": "FILLED" if quantity == intent.quantity else "PARTIAL_CANCELLED",
                         "filledQuantity": quantity})
    final_visible = snapshot(records, spec, config.endAt)
    holdings = []
    equity = cash
    unpriced = False
    for stock, quantity in sorted(positions.items()):
        if quantity == 0:
            continue
        marks = [r for r in final_visible if r.kind == "BAR" and r.sourceId == config.barSourceId and r.stockCode == stock]
        mark = max(marks, key=lambda r: r.payload.endAt) if marks else None
        fresh = mark is not None and (config.endAt - mark.payload.endAt).total_seconds() <= config.maxMarkAgeSeconds
        value = Decimal(mark.payload.close) * quantity if fresh else None
        if value is None:
            unpriced = True
        else:
            equity += value
        holdings.append({"stockCode": stock, "quantity": quantity, "markRef": mark.ref if fresh else None,
                         "value": money(value) if value is not None else None})
    report = {
        "schemaVersion": "SAGOPALGO_INTENT_REPLAY_V1", "engineVersion": "R5_FOUNDATION_1",
        "datasetId": manifest["datasetId"], "configId": digest(canonical(config.model_dump(mode="json"))),
        "config": config.model_dump(mode="json"), "status": "BAR_ESTIMATE_ONLY", "usableForTrading": False,
        "usableForStrategyValidation": False, "initialCash": config.initialCash, "finalCash": money(cash),
        "finalEquity": None if unpriced else money(equity),
        "netPnl": None if unpriced else money(equity - Decimal(config.initialCash)),
        "totalFees": money(total_fees), "totalSellTax": money(total_taxes), "holdings": holdings,
        "fills": fills, "outcomes": sorted(outcomes, key=lambda o: o["intentId"]), "quality": quality,
        "limitations": ["Explicit intents, not a trained strategy or the live AI model.",
                        "First recorded minute-bar open estimates only; full-bar volume is an ex-post participation cap.",
                        "No orderbook queue, market impact, cancellations, dividends, splits, or real account resources.",
                        "Fixed user-supplied tick/cost assumptions; not a dated exchange tick or tax schedule.",
                        "One attempt per intent; partial remainder cancels. No overnight carry of pending intents.",
                        "Positions are not forcibly liquidated; stale/unavailable marks make equity and PnL unknown."],
    }
    report["reportId"] = digest(canonical(report))
    return report
