"""Ex-post public-trade diagnostics for quote estimates, never account-fill proof."""
import argparse
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal, localcontext
import json
from pathlib import Path
import sys
from typing import Literal

from pydantic import Field, ValidationError

from .dataset import canonical, digest, read_bytes, read_json
from .intraday import load_policy
from .models import ResearchError, StrictModel, utc
from .quote_execution import QuoteExecutionPolicy, QuoteOrder, estimate_quotes
from .stored import precise_time
from .tick_quality import quality_profile
from .tick_rules import TickRulePack
from .ticks import TickAuditConfig, audit_ticks


class PublicTapeComparisonPolicy(StrictModel):
    schemaVersion: Literal['SAGOPALGO_PUBLIC_TAPE_COMPARISON_POLICY_V1']
    contextBeforeMs: int = Field(ge=0, le=60000)
    contextAfterMs: int = Field(gt=0, le=60000)
    marketTimeResolutionMs: Literal[1000]
    allowSynthetic: bool = False
    selection: Literal['FIXED_TIME_WINDOW_ALL_PRICES']
    evidence: str = Field(min_length=1, max_length=1000)


def compare_public_tape(raw, config, evidence_raw, quote_policy, orders, policy, as_of,
                        intraday=None, tick_rules=None, rules_known_at=None):
    if not orders or len(orders) > 1000:
        raise ResearchError('COMPARISON_ORDER_COUNT_INVALID')
    if config.provenance == 'SYNTHETIC' and not policy.allowSynthetic:
        raise ResearchError('COMPARISON_SYNTHETIC_OPT_IN_REQUIRED')
    if rules_known_at is not None and rules_known_at > as_of:
        raise ResearchError('COMPARISON_RULE_KNOWLEDGE_AFTER_ASOF')
    records, audit = audit_ticks(raw, config, [])
    value = read_json(raw)
    exported_at = precise_time((value['data'] if 'success' in value else value)['exportedAt'])
    if exported_at > as_of:
        raise ResearchError('COMPARISON_EXPORT_NOT_YET_KNOWN')
    # The estimator sees its existing causal gates. Future tape is used only below.
    estimate = estimate_quotes(raw, config, evidence_raw, quote_policy, orders,
                               intraday, tick_rules, rules_known_at)
    records, _ = quality_profile(records, evidence_raw)
    with localcontext() as context:
        context.prec = 96
        return _compare(records, audit, estimate, config, orders, policy, as_of, evidence_raw)


def _compare(records, audit, estimate, config, orders, policy, as_of, evidence_raw):
    trades = [r for r in records if r['type'] == 'TRADE']
    by_order = {o.orderId: o for o in orders}
    usages = Counter()
    rows = []
    references = {}
    gaps = quote_policy_gaps(estimate)
    for outcome in estimate['outcomes']:
        order = by_order[outcome['orderId']]
        at = precise_time(outcome['at'])
        start = at - timedelta(milliseconds=policy.contextBeforeMs)
        end = at + timedelta(milliseconds=policy.contextAfterMs)
        reasons = []
        if config.rights != 'PERMITTED':
            reasons.append('REFERENCE_RIGHTS_UNCONFIRMED')
        if not config.startAt <= start < end <= config.endAt:
            reasons.append('REFERENCE_WINDOW_OUTSIDE_EXPORT')
        if end > as_of:
            reasons.append('REFERENCE_WINDOW_AFTER_ASOF')
        if any(g.startAt < end and start < g.endAt for g in gaps):
            reasons.append('CAPTURE_GAP_IN_REFERENCE_WINDOW')
        selected, excluded, excluded_refs, boundary, ioc, ioc_boundary = [], Counter(), [], [], [], []
        for trade in trades:
            label = precise_time(trade['marketAt'])
            bucket_end = label + timedelta(milliseconds=policy.marketTimeResolutionMs)
            in_context = start <= label and bucket_end <= end
            overlap = label < end and start < bucket_end
            ioc_overlap = label < order.expiresAt and at < bucket_end
            if not overlap and not ioc_overlap:
                continue
            flags = []
            if trade['dateBasis'] != 'PROVIDER_DATE': flags.append('TRADE_DATE_UNCONFIRMED')
            if trade['sessionMeaning'] != 'INTRADAY_REPORTED': flags.append('TRADE_SESSION_UNCONFIRMED')
            if trade['clockQuality'] != 'ORDERED_OBSERVATION': flags.append('TRADE_CLOCK_INVERSION')
            if label.microsecond: flags.append('TRADE_SECOND_LABEL_UNCONFIRMED')
            if int(trade['volume']) <= 0: flags.append('ZERO_VOLUME_TRADE')
            if flags:
                if overlap:
                    excluded.update(flags)
                    excluded_refs.append(dict(eventId=trade['eventId'], rawSha256=trade['rawSha256'], reasons=flags))
                continue
            references[trade['eventId']] = {k: trade[k] for k in (
                'eventId', 'rawSha256', 'marketAt', 'receivedAt', 'price', 'volume', 'cumulativeVolume')}
            if overlap and not in_context:
                boundary.append(trade['eventId'])
            if in_context:
                selected.append(trade)
            if ioc_overlap:
                (ioc if at <= label and bucket_end <= order.expiresAt else ioc_boundary).append(trade['eventId'])
        selected.sort(key=lambda r: (r['marketAt'], int(r['cumulativeVolume']), r['eventId']))
        ids = [r['eventId'] for r in selected]
        usages.update(ids)
        reference_status = ('NOT_ASSESSABLE' if reasons else
                            'OBSERVED_PUBLIC_CONTEXT' if selected else 'NO_ELIGIBLE_PUBLIC_TRADES')
        volume = sum(int(r['volume']) for r in selected)
        reference_notional = sum((Decimal(r['price']) * int(r['volume']) for r in selected), Decimal(0))
        reference_vwap = reference_notional / volume if volume and not reasons else None
        estimated_quantity = outcome['quantityEstimated']
        estimated_vwap = (Decimal(outcome['notional']) / estimated_quantity
                          if estimated_quantity else None)
        price_diagnostics = []
        fills = defaultdict(int)
        for fill in outcome['fills']:
            fills[Decimal(fill['price'])] += fill['quantity']
        for price, quantity in sorted(fills.items()):
            coincident = [r for r in selected if Decimal(r['price']) == price]
            observed_volume = sum(int(r['volume']) for r in coincident)
            comparable = reference_status == 'OBSERVED_PUBLIC_CONTEXT'
            price_diagnostics.append(dict(
                estimatedPrice=format(price, 'f'), estimatedQuantity=quantity,
                priceObservation=('PRICE_OBSERVED' if coincident else 'PRICE_NOT_OBSERVED') if comparable else 'NOT_ASSESSABLE',
                observedAtPriceVolume=str(observed_volume) if comparable else None,
                estimatedMinusObservedVolume=str(quantity - observed_volume) if comparable else None,
                tradeEventIds=[r['eventId'] for r in coincident],
            ))
        price_difference = (estimated_vwap - reference_vwap
                            if estimated_vwap is not None and reference_vwap is not None else None)
        quantity_reasons = ['PUBLIC_TAPE_HAS_NO_ACCOUNT_ORDER_ID', 'TRADE_AGGRESSOR_SIDE_UNAVAILABLE',
                            'QUEUE_POSITION_UNAVAILABLE', 'OBSERVED_ONLY_NOT_COMPLETE_TAPE']
        if ioc_boundary: quantity_reasons.append('IOC_TIME_OVERLAPS_SECOND_BUCKET')
        if outcome['status'] == 'NOT_ASSESSABLE': quantity_reasons.append('MODEL_NOT_ASSESSABLE')
        if not estimated_quantity: quantity_reasons.append('UNFILLED_RESULT_NOT_PROVABLE_FROM_PUBLIC_TAPE')
        if outcome['remainderCancelled']: quantity_reasons.append('REMAINDER_CANCELLATION_NOT_ACCOUNT_CONFIRMED')
        rows.append(dict(
            orderId=order.orderId, side=order.side, estimate=outcome,
            contextStart=start.isoformat(), contextEnd=end.isoformat(),
            referenceStatus=reference_status, referenceReasons=reasons,
            referenceTradeEventIds=ids, excludedTradeReasons=dict(sorted(excluded.items())),
            excludedTradeReferences=sorted(excluded_refs, key=lambda r: r['eventId']),
            boundaryAmbiguousContextTradeIds=sorted(boundary),
            observedTradeCount=len(selected), observedVolume=str(volume),
            observedPriceMinimum=format(min(Decimal(r['price']) for r in selected), 'f') if selected and not reasons else None,
            observedPriceMaximum=format(max(Decimal(r['price']) for r in selected), 'f') if selected and not reasons else None,
            observedVwap=None if reference_vwap is None else format(reference_vwap, 'f'),
            estimatedVwap=None if estimated_vwap is None else format(estimated_vwap, 'f'),
            estimatedMinusObservedVwap=None if price_difference is None else format(price_difference, 'f'),
            priceDiagnostics=price_diagnostics,
            iocContainedTradeIds=sorted(ioc), iocBoundaryAmbiguousTradeIds=sorted(ioc_boundary),
            exactQuantityComparison='NOT_ASSESSABLE', exactQuantityDifference=None,
            quantityReasons=sorted(quantity_reasons), accountFillStatus='NOT_PROVEN',
            realizedSlippage=None, actualCostDifference=None,
        ))
    report = dict(
        schemaVersion='SAGOPALGO_PUBLIC_TAPE_COMPARISON_V1', status='EX_POST_OBSERVATION_DIAGNOSTICS',
        asOf=as_of.isoformat(), sourceExportSha256=audit['sourceExportSha256'],
        configSha256=digest(canonical(config.model_dump(mode='json'))),
        comparisonPolicy=policy.model_dump(mode='json'),
        comparisonPolicySha256=digest(canonical(policy.model_dump(mode='json'))),
        sessionEvidenceSha256=digest(evidence_raw), estimateReportId=estimate['reportId'],
        estimateReportSha256=digest(canonical(estimate)), ordersSha256=estimate['ordersSha256'],
        quotePolicy=estimate['policy'], quotePolicySha256=digest(canonical(estimate['policy'])),
        causalAvailability=estimate['causalAvailability'],
        costAndTickEvidence=estimate['costAndTickEvidence'],
        liquidityRefreshPolicy=estimate['liquidityRefreshPolicy'], orderDuration=estimate['orderDuration'],
        tickRuleBinding=estimate.get('tickRuleBinding'), intradayBinding=estimate.get('intradayBinding'),
        provenance=config.provenance, market=config.market, stockCode=config.stockCode,
        referenceRelationship='SAME_PROVIDER_SEPARATE_TRADE_AND_QUOTE_FEEDS',
        independentProviderConfirmed=False, accountReferenceAvailable=False,
        continuousMatchingConfirmed=False, utcSynchronizationConfirmed=False,
        referenceSelectionUsesEstimatedPrices=False, referenceCoverage='OBSERVED_ONLY',
        priceDifferenceMeaning='CONTEXT_DIAGNOSTIC_NOT_REALIZED_SLIPPAGE',
        publicReferenceVolumesAreNotAllocatableToOrders=True,
        reusedReferenceTradeCount=sum(count > 1 for count in usages.values()),
        uniqueSelectedTradeCount=len(usages),
        references=[references[key] for key in sorted(references)], rows=rows,
        comparisonCounts=dict(Counter(r['referenceStatus'] for r in rows)),
        estimateStatusCounts=estimate['statusCounts'], inputIssues=audit['issues'],
        exactQuantityComparison='NOT_ASSESSABLE', actualCostComparison='NOT_ASSESSABLE',
        accountFillStatus='NOT_PROVEN', usableForTrading=False, usableForStrategyValidation=False,
    )
    report['reportId'] = digest(canonical(report))
    return report


def quote_policy_gaps(estimate):
    from .quote_execution import CaptureGap
    return [CaptureGap.model_validate(gap) for gap in estimate['policy']['captureGaps']]


def _main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('input', 'config', 'session-evidence', 'quote-policy', 'orders', 'comparison-policy', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--tick-rules', type=Path)
    parser.add_argument('--rules-known-at')
    parser.add_argument('--intraday-timeline', type=Path)
    parser.add_argument('--timeline-sha256')
    parser.add_argument('--market', choices=['KOSPI', 'KOSDAQ'])
    parser.add_argument('--order-class', choices=['ORDINARY', 'PROGRAM'])
    args = parser.parse_args(argv)
    binding = [args.intraday_timeline, args.timeline_sha256, args.market, args.order_class]
    if any(binding) and not all(binding):
        raise ResearchError('COMPARISON_INTRADAY_BINDING_INCOMPLETE')
    values = read_json(read_bytes(args.orders))
    if not isinstance(values, list) or not 1 <= len(values) <= 1000:
        raise ResearchError('COMPARISON_ORDER_COUNT_INVALID')
    report = compare_public_tape(
        read_bytes(args.input), TickAuditConfig.model_validate(read_json(read_bytes(args.config))),
        read_bytes(args.session_evidence), QuoteExecutionPolicy.model_validate(read_json(read_bytes(args.quote_policy))),
        [QuoteOrder.model_validate(value) for value in values],
        PublicTapeComparisonPolicy.model_validate(read_json(read_bytes(args.comparison_policy))), utc(args.as_of),
        load_policy(args.intraday_timeline, args.timeline_sha256, args.market, args.order_class) if args.intraday_timeline else None,
        TickRulePack.model_validate(read_json(read_bytes(args.tick_rules))) if args.tick_rules else None,
        utc(args.rules_known_at) if args.rules_known_at else None)
    with args.output.open('xb') as output:
        output.write(canonical(report) + b'\n')
    return 0


def main(argv=None):
    try:
        return _main(argv)
    except ResearchError as error:
        code = str(error)
    except ValidationError:
        code = 'EXECUTION_COMPARISON_SCHEMA_INVALID'
    except (ValueError, TypeError, KeyError, OverflowError):
        code = 'EXECUTION_COMPARISON_INPUT_INVALID'
    except OSError:
        code = 'EXECUTION_COMPARISON_FILE_OPERATION_FAILED'
    print(json.dumps({'status': 'FAILED', 'code': code}), file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
