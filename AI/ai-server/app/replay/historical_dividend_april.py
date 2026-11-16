"""Keep the archived 2024-04 dividend audit entry point available."""

from . import historical_dividend_month as month
from .historical_dividend_month import (
    IR_ID, POST_PAYMENT, SCHEMA, dates, decision_facts, manual_payment, plain, supplemental_field,
)


def build(manifest, artifacts, job):
    return month.build(manifest, artifacts, job, schema=SCHEMA)


def main():
    month.main(schema=SCHEMA)


if __name__ == "__main__":
    main()
