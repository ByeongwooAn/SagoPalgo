"""Synthetic public-tape diagnostics; no broker fills or independent provider fixtures."""
from copy import deepcopy
from decimal import Decimal
import hashlib

import pytest
from pydantic import ValidationError

import test_tick_audit as tape
import test_quote_execution as quotes
from app.replay import tick_quality
from app.replay.dataset import canonical, digest, read_json
from app.replay.execution_comparison import PublicTapeComparisonPolicy, compare_public_tape, main
from app.replay.models import ResearchError, utc
from app.replay.quote_execution import estimate_quotes
from app.replay.tick_rules import TickRulePack
from app.replay.intraday import ReplayIntraday, timeline_value
from test_tick_rules import pack

ASOF = utc('2025-11-03T00:05:00Z')


@pytest.fixture(autouse=True)
def synthetic_evidence(monkeypatch):
    raw = quotes.EVIDENCE
    monkeypatch.setattr(tick_quality, 'SESSION_BLOB', hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest())


def comparison_policy(**changes):
    value = dict(schemaVersion='SAGOPALGO_PUBLIC_TAPE_COMPARISON_POLICY_V1', contextBeforeMs=1000,
                 contextAfterMs=2000, marketTimeResolutionMs=1000, allowSynthetic=True,
                 selection='FIXED_TIME_WINDOW_ALL_PRICES', evidence='SYNTHETIC fixed window only')
    value.update(changes)
    return PublicTapeComparisonPolicy.model_validate(value)


def future_trade(at='2025-11-03T00:00:03Z', received='2025-11-03T00:00:03.500000Z', **changes):
    return tape.row(at=at, received=received, session='0', price='101', volume='6', cumulativeVolume='8', **changes)


def raw_data(*trades):
    second = tape.row(at='2025-11-03T00:00:04Z', received='2025-11-03T00:00:04.100000Z',
                      session='0', price='102', volume='3', cumulativeVolume='11')
    return canonical(tape.export(tape.row(session='0'), quotes.book(), *(trades or [future_trade(), second])))


def run(raw=None, orders=None, policy=None, quote_policy=None, config=None, **kw):
    return compare_public_tape(raw or raw_data(), config or quotes.cfg(), quotes.EVIDENCE,
                               quote_policy or quotes.policy(), orders or [quotes.order()],
                               policy or comparison_policy(), ASOF, **kw)


def test_price_quantity_diagnostics_are_not_account_fill_or_slippage():
    result = run()
    row = result['rows'][0]
    assert row['referenceStatus'] == 'OBSERVED_PUBLIC_CONTEXT'
    assert row['observedTradeCount'] == 2 and row['observedVolume'] == '9'
    assert row['estimatedVwap'] == '101.375'
    assert abs(Decimal(row['observedVwap']) - Decimal(912) / 9) < Decimal('1e-25')
    assert [(r['estimatedPrice'], r['estimatedQuantity'], r['observedAtPriceVolume'], r['estimatedMinusObservedVolume'])
            for r in row['priceDiagnostics']] == [('101', 5, '6', '-1'), ('102', 3, '3', '0')]
    assert len(row['iocContainedTradeIds']) == 1 and len(row['iocBoundaryAmbiguousTradeIds']) == 1
    assert row['exactQuantityDifference'] is None and row['realizedSlippage'] is None and row['actualCostDifference'] is None
    assert row['exactQuantityComparison'] == 'NOT_ASSESSABLE' and row['accountFillStatus'] == 'NOT_PROVEN'
    assert result['independentProviderConfirmed'] is False and result['accountReferenceAvailable'] is False
    assert not result['usableForTrading'] and not result['usableForStrategyValidation']


def test_reference_selection_is_fixed_all_prices_and_future_tape_does_not_change_estimates():
    original = raw_data()
    changed = read_json(original)
    for event in changed['streamEvents']:
        if event['type'] == 'TRADE' and event['marketAt'] >= '2025-11-03T00:00:03Z':
            tape.modify(event, price='777')
    result, alternate = run(original), run(canonical(changed))
    assert result['rows'][0]['estimate'] == alternate['rows'][0]['estimate']
    assert result['rows'][0]['referenceTradeEventIds'] == alternate['rows'][0]['referenceTradeEventIds']
    assert all(r['priceObservation'] == 'PRICE_NOT_OBSERVED' for r in alternate['rows'][0]['priceDiagnostics'])
    assert alternate['rows'][0]['observedVolume'] == '9'
    assert not alternate['referenceSelectionUsesEstimatedPrices']


def test_second_bucket_boundaries_are_not_treated_as_exact_timestamps():
    row = run(orders=[quotes.order(expiresAt='2025-11-03T00:00:03.700000Z')])['rows'][0]
    assert row['iocContainedTradeIds'] == []
    assert len(row['iocBoundaryAmbiguousTradeIds']) == 1
    assert 'IOC_TIME_OVERLAPS_SECOND_BUCKET' in row['quantityReasons']


@pytest.mark.parametrize('side,kind,limit,quantity,status', [
    ('BUY', 'LIMIT', '102', 8, 'ESTIMATED_FILLED'),
    ('SELL', 'MARKET', None, 8, 'ESTIMATED_PARTIAL_IOC'),
    ('BUY', 'LIMIT', '100', 8, 'ESTIMATED_UNFILLED_IOC'),
])
def test_limit_partial_and_unfilled_remain_model_outcomes(side, kind, limit, quantity, status):
    row = run(orders=[quotes.order(side=side, orderType=kind, limitPrice=limit, quantity=quantity)])['rows'][0]
    assert row['estimate']['status'] == status
    assert row['exactQuantityComparison'] == 'NOT_ASSESSABLE'
    if status == 'ESTIMATED_UNFILLED_IOC':
        assert row['priceDiagnostics'] == [] and row['estimatedVwap'] is None
    if row['estimate']['remainderCancelled']:
        assert 'REMAINDER_CANCELLATION_NOT_ACCOUNT_CONFIRMED' in row['quantityReasons']


def test_default_historical_availability_block_is_not_a_real_zero_fill():
    row = run(quote_policy=quotes.policy(availabilityMode='EXPORT_KNOWN_AT'))['rows'][0]
    assert row['estimate']['status'] == 'NOT_ASSESSABLE'
    assert 'MODEL_NOT_ASSESSABLE' in row['quantityReasons']
    assert row['priceDiagnostics'] == [] and row['exactQuantityDifference'] is None


def test_no_public_trades_is_not_market_inactivity_or_fill_failure():
    raw = canonical(tape.export(tape.row(session='0'), quotes.book()))
    row = run(raw)['rows'][0]
    assert row['referenceStatus'] == 'NO_ELIGIBLE_PUBLIC_TRADES'
    assert row['observedVwap'] is None
    assert all(r['estimatedMinusObservedVolume'] is None for r in row['priceDiagnostics'])
    assert row['accountFillStatus'] == 'NOT_PROVEN'


@pytest.mark.parametrize('mutation,reason', [
    ({'receivedAt': '2025-11-03T00:00:02.900000Z'}, 'TRADE_CLOCK_INVERSION'),
    ({'session': 'X'}, 'TRADE_SESSION_UNCONFIRMED'),
    ({'dateBasis': 'RECEIVE_DATE_INFERRED'}, 'TRADE_DATE_UNCONFIRMED'),
    ({'volume': '0'}, 'ZERO_VOLUME_TRADE'),
])
def test_invalid_reference_quality_is_preserved_and_excluded(mutation, reason):
    event = future_trade()
    tape.modify(event, **mutation)
    if 'receivedAt' in mutation: event['receivedAt'] = mutation['receivedAt']
    row = run(raw_data(event))['rows'][0]
    assert row['referenceStatus'] == 'NO_ELIGIBLE_PUBLIC_TRADES'
    assert row['excludedTradeReasons'][reason] == 1
    assert row['excludedTradeReferences'][0]['eventId'] == event['eventId']


def test_context_edges_are_not_silently_clipped_or_price_compared():
    row = run(policy=comparison_policy(contextBeforeMs=10000))['rows'][0]
    assert row['referenceStatus'] == 'NOT_ASSESSABLE'
    assert row['referenceReasons'] == ['REFERENCE_WINDOW_OUTSIDE_EXPORT']
    assert row['observedVwap'] is None
    assert all(r['observedAtPriceVolume'] is None for r in row['priceDiagnostics'])


def test_capture_gap_in_reference_window_blocks_diagnostic_comparison():
    row = run(quote_policy=quotes.policy(captureGaps=[dict(startAt='2025-11-03T00:00:04Z', endAt='2025-11-03T00:00:04.100000Z')]))['rows'][0]
    assert row['estimate']['status'] == 'ESTIMATED_FILLED'
    assert row['referenceReasons'] == ['CAPTURE_GAP_IN_REFERENCE_WINDOW']
    assert row['observedVwap'] is None


def test_shared_market_print_is_not_allocated_as_two_account_fills():
    result = run(orders=[quotes.order(orderId='a', quantity=1), quotes.order(orderId='b', quantity=1)])
    assert result['uniqueSelectedTradeCount'] == 2 and result['reusedReferenceTradeCount'] == 2
    assert result['publicReferenceVolumesAreNotAllocatableToOrders']
    assert all(r['accountFillStatus'] == 'NOT_PROVEN' for r in result['rows'])


def test_export_knowledge_synthetic_opt_in_rights_and_empty_orders():
    with pytest.raises(ResearchError, match='EXPORT_NOT_YET_KNOWN'):
        compare_public_tape(raw_data(), quotes.cfg(), quotes.EVIDENCE, quotes.policy(), [quotes.order()],
                            comparison_policy(), utc('2025-11-03T00:04:59Z'))
    with pytest.raises(ResearchError, match='SYNTHETIC_OPT_IN'):
        run(policy=comparison_policy(allowSynthetic=False))
    with pytest.raises(ResearchError, match='ORDER_COUNT'):
        compare_public_tape(raw_data(), quotes.cfg(), quotes.EVIDENCE, quotes.policy(), [], comparison_policy(), ASOF)
    row = run(config=quotes.cfg(rights='UNCONFIRMED'))['rows'][0]
    assert row['referenceReasons'] == ['REFERENCE_RIGHTS_UNCONFIRMED']


def test_source_hash_and_session_pin_tampering_fail():
    raw = read_json(raw_data()); raw['streamEvents'][-1]['contentHash'] = 'f' * 64
    with pytest.raises(ResearchError, match='HASH_MISMATCH'): run(canonical(raw))
    with pytest.raises(ResearchError, match='SESSION_SOURCE'):
        compare_public_tape(raw_data(), quotes.cfg(), b'tampered', quotes.policy(), [quotes.order()], comparison_policy(), ASOF)


def test_official_grid_binding_keeps_future_evidence_blocked_and_expost_explicit():
    value = pack()
    for r in value['rules']:
        r.update(validFrom='2025-11-03', validTo='2025-11-04', knownAt='2025-11-03T00:00:04Z')
    rules = TickRulePack.model_validate(value)
    blocked = run(tick_rules=rules)
    assert blocked['rows'][0]['estimate']['reasons'] == ['TICK_RULE_NOT_YET_KNOWN']
    result = run(tick_rules=rules, rules_known_at=ASOF)
    assert result['rows'][0]['estimate']['status'] == 'ESTIMATED_FILLED'
    assert result['tickRuleBinding']['exPostEvidence']
    with pytest.raises(ResearchError, match='RULE_KNOWLEDGE_AFTER_ASOF'):
        run(tick_rules=rules, rules_known_at=utc('2025-11-03T00:05:01Z'))


def test_known_halt_passes_through_without_becoming_zero_confirmed_fill():
    timeline = timeline_value(dict(schemaVersion='SAGOPALGO_INTRADAY_TIMELINE_V1', sourceDecisionSha256='0' * 64,
        provenance='SYNTHETIC', createdAt='2025-11-03T00:04:00Z', allIntradayInterruptionsComplete=False,
        usableForTrading=False, usableForStrategyValidation=False,
        days=[dict(market='KOSPI', businessDate='2025-11-03', coverage='COMPLETE', knownAt='2025-11-02T00:00:00Z',
                   openAt='2025-11-03T00:00:00Z', closeAt='2025-11-03T06:00:00Z')],
        phases=[dict(phaseId='halt-1', market='KOSPI', businessDate='2025-11-03', kind='HALT',
                     startAt='2025-11-03T00:00:03Z', endAt='2025-11-03T00:00:04Z', knownAt='2025-11-02T00:00:00Z',
                     evidence=['https://synthetic.test/halt'], bodySha256s=['a' * 64])]))
    binding = ReplayIntraday.model_validate(dict(timeline=timeline.model_dump(mode='json'),
        timelineSha256=digest(canonical(timeline.model_dump(mode='json'))), market='KOSPI', orderClass='ORDINARY'))
    result = run(intraday=binding)
    row = result['rows'][0]
    assert row['estimate']['reasons'] == ['MARKET_HALTED']
    assert row['exactQuantityDifference'] is None
    assert result['intradayBinding']['timelineSha256'] == binding.timelineSha256


def test_fractional_market_time_label_is_not_silently_rounded():
    event = future_trade(at='2025-11-03T00:00:03.500000Z', received='2025-11-03T00:00:03.600000Z')
    row = run(raw_data(event))['rows'][0]
    assert row['excludedTradeReasons'] == {'TRADE_SECOND_LABEL_UNCONFIRMED': 1}


def test_boundary_references_keep_event_hash_lineage_and_missing_prints_are_not_filled():
    boundary = tape.row(at='2025-11-03T00:00:02Z', received='2025-11-03T00:00:02.900000Z',
                        session='0', price='110', volume='1', cumulativeVolume='3')
    result = run(raw_data(boundary, future_trade()))
    row = result['rows'][0]
    assert boundary['eventId'] in row['boundaryAmbiguousContextTradeIds']
    refs = {r['eventId']: r for r in result['references']}
    assert refs[boundary['eventId']]['rawSha256'] == boundary['contentHash']
    assert row['observedTradeCount'] == 1 and row['observedVolume'] == '6'
    assert result['inputIssues']['POSSIBLE_TRADE_GAP'] == 1


def test_deterministic_ordering_integrity_and_no_changes_to_legacy_estimator():
    raw = raw_data(); before = deepcopy(read_json(raw))
    first = run(raw)
    legacy = estimate_quotes(raw, quotes.cfg(), quotes.EVIDENCE, quotes.policy(), [quotes.order()])
    assert first['rows'][0]['estimate'] == legacy['outcomes'][0]
    assert first['estimateReportId'] == legacy['reportId']
    assert first == run(raw) and read_json(raw) == before
    changed = dict(first); report_id = changed.pop('reportId')
    assert digest(canonical(changed)) == report_id


@pytest.mark.parametrize('changes', [{'contextBeforeMs': -1}, {'contextAfterMs': 0},
                                    {'marketTimeResolutionMs': 1}, {'selection': 'CLOSEST_PRICE'}])
def test_invalid_or_price_selected_policy_is_rejected(changes):
    with pytest.raises(ValidationError): comparison_policy(**changes)


def cli_files(tmp_path):
    inputs = {'input': raw_data(), 'config': canonical(quotes.cfg().model_dump(mode='json')),
              'quote-policy': canonical(quotes.policy().model_dump(mode='json')),
              'orders': canonical([quotes.order().model_dump(mode='json')]),
              'session-evidence': quotes.EVIDENCE, 'comparison-policy': canonical(comparison_policy().model_dump(mode='json'))}
    args = []
    for key, raw in inputs.items():
        path = tmp_path / key; path.write_bytes(raw)
        args += ['--' + key, str(path)]
    output = tmp_path / 'report.json'
    return args + ['--as-of', ASOF.isoformat(), '--output', str(output)], output


def test_cli_exclusive_report_and_source_preservation(tmp_path):
    args, output = cli_files(tmp_path)
    original = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert main(args) == 0
    saved = output.read_bytes()
    assert read_json(saved)['accountFillStatus'] == 'NOT_PROVEN'
    assert main(args) == 2 and output.read_bytes() == saved
    assert all((tmp_path / name).read_bytes() == raw for name, raw in original.items())


def test_cli_partial_intraday_binding_and_private_input_error_are_safe(tmp_path, capsys):
    args, output = cli_files(tmp_path)
    assert main(args + ['--market', 'KOSPI']) == 2 and not output.exists()
    path = tmp_path / 'comparison-policy'; value = read_json(path.read_bytes())
    value['marketTimeResolutionMs'] = 'private-invalid-value'; path.write_bytes(canonical(value))
    assert main(args) == 2 and not output.exists()
    assert 'private-invalid-value' not in capsys.readouterr().err
