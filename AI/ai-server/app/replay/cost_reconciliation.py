"""Offline statement observations; a matching hypothesis never confirms broker rules."""
import argparse
import json
import sys
from datetime import date, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from .cost_rules import Rounding, rounded
from .dataset import canonical, digest, read_bytes, read_json
from .models import Identifier, ResearchError, StrictModel, Timestamp, utc


Won = str  # Field patterns below keep amounts exact; null is distinct from zero.
MONEY = r'^(0|[1-9][0-9]{0,17})$'
QUANTITY = r'^(0|[1-9][0-9]{0,17})(\.[0-9]{1,20})?$'
SHA256 = r'^[a-f0-9]{64}$'
HYPOTHESIS = 'MTS_FRACTIONAL_12BPS_FLOOR10_SELL_EXTRA20BPS_FLOOR1'


class StatementObservation(StrictModel):
    observationId: Identifier
    sourceRef: str = Field(min_length=1, max_length=200)
    statementDate: str
    dateBasis: Literal['UNCONFIRMED', 'EXECUTION_DATE', 'SETTLEMENT_DATE']
    side: Literal['BUY', 'SELL']
    quantity: str | None = Field(default=None, pattern=QUANTITY)
    notionalWon: Won = Field(pattern=r'^[1-9][0-9]{0,17}$')
    settlementWon: Won = Field(pattern=MONEY)
    reportedFeeWon: Won | None = Field(default=None, pattern=MONEY)
    reportedTaxEtcWon: Won | None = Field(default=None, pattern=MONEY)
    reportedRuralVatWon: Won | None = Field(default=None, pattern=MONEY)
    # A manually normalized total of other charge columns, never a balancing plug.
    reportedOtherChargesWon: Won | None = Field(default=None, pattern=MONEY)
    channel: Literal['UNCONFIRMED', 'MTS', 'HTS', 'KB_OPENAPI']
    product: Literal['UNCONFIRMED', 'FRACTIONAL', 'COMMON_STOCK']
    instrumentRef: Identifier | None = None
    orderRef: Identifier | None = None
    executionRef: Identifier | None = None

    @model_validator(mode='after')
    def valid(self):
        if date.fromisoformat(self.statementDate).isoformat() != self.statementDate:
            raise ValueError('ISO date required')
        if self.quantity is not None and Decimal(self.quantity) <= 0:
            raise ValueError('positive quantity required')
        if self.product == 'COMMON_STOCK' and self.quantity is not None and Decimal(self.quantity) % 1:
            raise ValueError('whole-share product conflicts with quantity')
        return self


class StatementBatch(StrictModel):
    schemaVersion: Literal['SAGOPALGO_COST_OBSERVATIONS_V1']
    provenance: Literal['USER_STATEMENT', 'SYNTHETIC']
    evidenceSha256: str = Field(pattern=SHA256)
    recordedAt: Timestamp
    observations: list[StatementObservation] = Field(min_length=1, max_length=10000)

    @model_validator(mode='after')
    def unique(self):
        if len({r.observationId for r in self.observations}) != len(self.observations):
            raise ValueError('duplicate observation')
        if len({r.sourceRef for r in self.observations}) != len(self.observations):
            raise ValueError('duplicate source range')
        return self


def reconcile(batch, as_of, *, mts_fractional_hypothesis=False):
    if batch.recordedAt > as_of:
        raise ResearchError('COST_OBSERVATIONS_NOT_YET_RECORDED')
    korea_date = as_of.astimezone(timezone(timedelta(hours=9))).date()
    if any(date.fromisoformat(r.statementDate) > korea_date for r in batch.observations):
        raise ResearchError('COST_STATEMENT_DATE_AFTER_ASOF')
    with localcontext() as context:
        context.prec = 80
        return _reconcile(batch, as_of, mts_fractional_hypothesis)


def _reconcile(batch, as_of, hypothesis):
    rows = []
    fields = ('reportedFeeWon', 'reportedTaxEtcWon', 'reportedRuralVatWon', 'reportedOtherChargesWon')
    for r in sorted(batch.observations, key=lambda row: row.observationId):
        value, settled = Decimal(r.notionalWon), Decimal(r.settlementWon)
        net_charge = settled - value if r.side == 'BUY' else value - settled
        unknown = [name for name in fields if getattr(r, name) is None]
        known = sum((Decimal(getattr(r, name)) for name in fields if getattr(r, name) is not None), Decimal(0))
        residual = net_charge - known
        if net_charge < 0 or residual != 0:
            arithmetic = 'UNEXPLAINED_DIFFERENCE'
        elif unknown:
            arithmetic = 'MATCH_WITH_UNREPORTED_COMPONENTS'
        else:
            arithmetic = 'MATCH'
        # This is a sample-compatible MTS/fractional scenario, never an API profile.
        applicable = (hypothesis and r.channel in ('UNCONFIRMED', 'MTS')
                      and r.product in ('UNCONFIRMED', 'FRACTIONAL')
                      and r.quantity is not None and Decimal(r.quantity) < 1)
        base = extra = expected = difference = None
        state = 'NOT_REQUESTED' if not hypothesis else 'SCOPE_NOT_ESTABLISHED'
        if applicable:
            base = rounded(value * Decimal('0.0012'), Rounding(unitWon=10, mode='DOWN'))
            extra = rounded(value * Decimal('0.002'), Rounding(unitWon=1, mode='DOWN')) if r.side == 'SELL' else Decimal(0)
            expected = base + extra
            if r.reportedFeeWon is None:
                state = 'REPORTED_FEE_MISSING'
            else:
                difference = Decimal(r.reportedFeeWon) - expected
                state = 'MATCH' if difference == 0 else 'MISMATCH'
        rows.append(dict(
            observationId=r.observationId, sourceRef=r.sourceRef,
            observation=r.model_dump(mode='json'), unknownChargeFields=unknown,
            netChargeFromSettlementWon=format(net_charge, 'f'), knownReportedChargesWon=format(known, 'f'),
            unexplainedDifferenceWon=format(residual, 'f'), arithmeticStatus=arithmetic,
            hypothesisStatus=state, hypothesisBaseFeeWon=None if base is None else format(base, 'f'),
            hypothesisSellExtraWon=None if extra is None else format(extra, 'f'),
            hypothesisFeeWon=None if expected is None else format(expected, 'f'),
            reportedMinusHypothesisFeeWon=None if difference is None else format(difference, 'f'),
        ))
    return dict(
        schemaVersion='SAGOPALGO_COST_RECONCILIATION_V1', status='OBSERVATIONS_ONLY',
        provenance=batch.provenance, evidenceSha256=batch.evidenceSha256,
        observationsSha256=digest(canonical(batch.model_dump(mode='json'))),
        recordedAt=batch.recordedAt.isoformat(), asOf=as_of.isoformat(), rows=rows,
        observationCount=len(rows),
        settlementArithmeticMatchCount=sum(r['arithmeticStatus'].startswith('MATCH') for r in rows),
        unexplainedDifferenceCount=sum(r['arithmeticStatus'] == 'UNEXPLAINED_DIFFERENCE' for r in rows),
        unreportedComponentRowCount=sum(bool(r['unknownChargeFields']) for r in rows),
        hypothesisId=HYPOTHESIS if hypothesis else None,
        hypothesisMatchCount=sum(r['hypothesisStatus'] == 'MATCH' for r in rows),
        hypothesisMismatchCount=sum(r['hypothesisStatus'] == 'MISMATCH' for r in rows),
        hypothesisNotComparedCount=sum(r['hypothesisStatus'] not in ('MATCH', 'MISMATCH') for r in rows),
        accountFeeConfirmed=False, taxCollectionConfirmed=False, aggregationConfirmed=False,
        minimumFeeConfirmed=False, roundingRuleConfirmed=False, brokerReconciled=False,
        openApiReconciliationCount=0, confirmedTotalCostWon=None,
        usableForTrading=False, usableForStrategyValidation=False,
    )


def _main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('observations', 'as-of', 'output'):
        parser.add_argument('--' + key, required=True)
    parser.add_argument('--evidence-file', help='Verify the local original against evidenceSha256; never copied.')
    parser.add_argument('--mts-fractional-hypothesis', action='store_true')
    args = parser.parse_args(argv)
    batch = StatementBatch.model_validate(read_json(read_bytes(Path(args.observations))))
    if args.evidence_file and digest(read_bytes(Path(args.evidence_file))) != batch.evidenceSha256:
        raise ResearchError('COST_EVIDENCE_HASH_MISMATCH')
    report = reconcile(batch, utc(args.as_of), mts_fractional_hypothesis=args.mts_fractional_hypothesis)
    report['evidenceFileHashVerified'] = args.evidence_file is not None
    with Path(args.output).open('xb') as output:
        output.write(canonical(report) + b'\n')
    # Successful offline observations are not permission to trade. Differences remain visible.
    return 1 if report['unexplainedDifferenceCount'] or report['hypothesisMismatchCount'] else 0


def main(argv=None):
    try:
        return _main(argv)
    except ResearchError as error:
        code = str(error)
    except ValidationError:
        code = 'COST_OBSERVATION_SCHEMA_INVALID'
    except (ValueError, TypeError, KeyError, OverflowError):
        code = 'COST_OBSERVATION_INPUT_INVALID'
    except OSError:
        code = 'COST_OBSERVATION_FILE_OPERATION_FAILED'
    print(json.dumps({'status': 'FAILED', 'code': code}), file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
