from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.replay.cost_reconciliation import StatementBatch, StatementObservation, main, reconcile
from app.replay.dataset import canonical, digest, read_json
from app.replay.models import ResearchError, utc

AT = utc('2026-11-06T12:00:00Z')


def observation(**changes):
    # Deliberately synthetic amounts, not personal trade history.
    value = dict(observationId='sample-1', sourceRef='Synthetic!A3:F4',
                 statementDate='2026-03-02', dateBasis='UNCONFIRMED', side='BUY',
                 quantity='0.25', notionalWon='123456', settlementWon='123596',
                 reportedFeeWon='140', reportedTaxEtcWon=None, reportedRuralVatWon='0',
                 channel='UNCONFIRMED', product='UNCONFIRMED')
    value.update(changes)
    return StatementObservation.model_validate(value)


def batch(rows=None, **changes):
    value = dict(schemaVersion='SAGOPALGO_COST_OBSERVATIONS_V1', provenance='SYNTHETIC',
                 evidenceSha256='a' * 64, recordedAt='2026-11-06T11:00:00Z',
                 observations=[r.model_dump(mode='json') for r in (rows or [observation()])])
    value.update(changes)
    return StatementBatch.model_validate(value)


def test_arithmetic_match_preserves_blank_tax_and_does_not_confirm_costs():
    result = reconcile(batch(), AT)
    row = result['rows'][0]
    assert row['arithmeticStatus'] == 'MATCH_WITH_UNREPORTED_COMPONENTS'
    assert 'reportedTaxEtcWon' in row['unknownChargeFields']
    assert row['observation']['reportedTaxEtcWon'] is None
    assert row['unexplainedDifferenceWon'] == '0'
    assert row['hypothesisFeeWon'] is None
    assert result['settlementArithmeticMatchCount'] == 1
    assert result['openApiReconciliationCount'] == 0
    assert result['confirmedTotalCostWon'] is None
    for key in ('accountFeeConfirmed', 'taxCollectionConfirmed', 'aggregationConfirmed',
                'minimumFeeConfirmed', 'roundingRuleConfirmed', 'brokerReconciled',
                'usableForTrading', 'usableForStrategyValidation'):
        assert result[key] is False


def test_explicit_zero_is_distinct_from_missing():
    result = reconcile(batch([observation(reportedTaxEtcWon='0', reportedOtherChargesWon='0')]), AT)
    assert result['rows'][0]['unknownChargeFields'] == []
    assert result['rows'][0]['arithmeticStatus'] == 'MATCH'
    assert not result['taxCollectionConfirmed']


@pytest.mark.parametrize('side,settled,base,extra', [
    ('BUY', '123596', '140', '0'), ('SELL', '123070', '140', '246'),
])
def test_conditional_mts_fractional_hypothesis(side, settled, base, extra):
    fee = str(int(base) + int(extra))
    result = reconcile(batch([observation(side=side, settlementWon=settled, reportedFeeWon=fee)]), AT,
                       mts_fractional_hypothesis=True)
    row = result['rows'][0]
    assert (row['hypothesisBaseFeeWon'], row['hypothesisSellExtraWon']) == (base, extra)
    assert row['hypothesisStatus'] == 'MATCH'
    assert result['hypothesisMatchCount'] == 1
    assert result['confirmedTotalCostWon'] is None


@pytest.mark.parametrize('changes', [
    {'channel': 'KB_OPENAPI'}, {'channel': 'HTS'}, {'product': 'COMMON_STOCK', 'quantity': '1'},
    {'quantity': '1'}, {'quantity': None},
])
def test_scenario_cannot_be_used_for_api_or_whole_share_or_unknown_quantity(changes):
    row = reconcile(batch([observation(**changes)]), AT, mts_fractional_hypothesis=True)['rows'][0]
    assert row['hypothesisStatus'] == 'SCOPE_NOT_ESTABLISHED'
    assert row['hypothesisFeeWon'] is None


def test_missing_fee_and_mismatch_are_visible_not_fitted():
    result = reconcile(batch([observation(reportedFeeWon=None)]), AT, mts_fractional_hypothesis=True)
    assert result['rows'][0]['hypothesisStatus'] == 'REPORTED_FEE_MISSING'
    result = reconcile(batch([observation(reportedFeeWon='141')]), AT, mts_fractional_hypothesis=True)
    row = result['rows'][0]
    assert row['hypothesisStatus'] == 'MISMATCH'
    assert row['reportedMinusHypothesisFeeWon'] == '1'
    assert row['arithmeticStatus'] == 'UNEXPLAINED_DIFFERENCE'


def test_tax_and_other_charges_remain_separate_from_reported_fee():
    result = reconcile(batch([observation(side='SELL', settlementWon='123200', reportedFeeWon='140',
                                         reportedTaxEtcWon='100', reportedRuralVatWon='10', reportedOtherChargesWon='6')]), AT)
    row = result['rows'][0]
    assert row['arithmeticStatus'] == 'MATCH'
    assert row['netChargeFromSettlementWon'] == '256'


def test_negative_deduction_remains_unexplained():
    row = reconcile(batch([observation(settlementWon='123455', reportedFeeWon='0')]), AT)['rows'][0]
    assert row['arithmeticStatus'] == 'UNEXPLAINED_DIFFERENCE'


@pytest.mark.parametrize('changes', [
    {'notionalWon': 123456}, {'reportedFeeWon': '-1'}, {'quantity': '0'},
    {'statementDate': '2026-02-30'}, {'product': 'COMMON_STOCK'}, {'unexpected': 'private'},
])
def test_invalid_observation_rejected(changes):
    with pytest.raises(ValidationError):
        observation(**changes)


@pytest.mark.parametrize('changes', [{'observationId': 'sample-1', 'sourceRef': 'Synthetic!A5:F6'},
                                     {'observationId': 'sample-2'}])
def test_duplicate_ids_and_source_ranges_rejected(changes):
    with pytest.raises(ValidationError):
        batch([observation(), observation(**changes)])


def test_future_recorded_at_and_statement_date_rejected():
    with pytest.raises(ResearchError, match='NOT_YET_RECORDED'):
        reconcile(batch(recordedAt='2026-11-07T00:00:00Z'), AT)
    with pytest.raises(ResearchError, match='DATE_AFTER_ASOF'):
        reconcile(batch([observation(statementDate='2026-11-07')]), AT)


def test_korean_date_boundary_does_not_use_utc_day():
    result = reconcile(batch([observation(statementDate='2026-11-07')]), utc('2026-11-06T15:00:00Z'))
    assert result['observationCount'] == 1


def test_large_values_keep_decimal_precision():
    row = reconcile(batch([observation(notionalWon='999999999999999999',
                         settlementWon='999999999999999999', reportedFeeWon=None)]), AT,
                         mts_fractional_hypothesis=True)['rows'][0]
    assert Decimal(row['hypothesisFeeWon']) == Decimal('1199999999999990')


def cli_files(tmp_path, **changes):
    original = tmp_path / 'original.bin'
    original.write_bytes(b'synthetic original, no account information')
    b = batch(evidenceSha256=digest(original.read_bytes()), **changes)
    source = tmp_path / 'observations.json'
    source.write_bytes(canonical(b.model_dump(mode='json')))
    output = tmp_path / 'report.json'
    args = ['--observations', str(source), '--as-of', AT.isoformat(), '--output', str(output),
            '--evidence-file', str(original)]
    return source, original, output, args


def test_cli_hash_verification_input_preservation_and_exclusive_output(tmp_path):
    source, original, output, args = cli_files(tmp_path)
    before = source.read_bytes(), original.read_bytes()
    assert main(args + ['--mts-fractional-hypothesis']) == 0
    saved = output.read_bytes()
    assert read_json(saved)['evidenceFileHashVerified'] is True
    assert main(args) == 2 and output.read_bytes() == saved
    assert before == (source.read_bytes(), original.read_bytes())


def test_cli_hash_mismatch_does_not_write_or_echo_private_values(tmp_path, capsys):
    _, original, output, args = cli_files(tmp_path)
    original.write_bytes(b'private replacement')
    assert main(args) == 2 and not output.exists()
    assert 'private replacement' not in capsys.readouterr().err


def test_cli_difference_report_and_missing_original_verification(tmp_path):
    _, _, output, args = cli_files(tmp_path, rows=[observation(reportedFeeWon='141')])
    assert main(args[:-2] + ['--mts-fractional-hypothesis']) == 1
    report = read_json(output.read_bytes())
    assert report['evidenceFileHashVerified'] is False
    assert report['hypothesisMismatchCount'] == 1


def test_cli_validation_error_does_not_echo_input(tmp_path, capsys):
    source, _, output, args = cli_files(tmp_path)
    value = read_json(source.read_bytes())
    value['observations'][0]['reportedFeeWon'] = 'private-invalid-value'
    source.write_bytes(canonical(value))
    assert main(args) == 2 and not output.exists()
    assert 'private-invalid-value' not in capsys.readouterr().err
