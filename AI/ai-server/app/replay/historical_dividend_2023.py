"""Keep the archived H05 2023 dividend audit entry point available."""

from . import historical_dividend_followup as followup
from .historical_dividend_followup import SCHEMA, assess, validate_ir_url


def build(manifest, artifacts, job):
    return followup.build(manifest, artifacts, job, schema=SCHEMA)


def main():
    followup.main(schema=SCHEMA)


if __name__ == "__main__":
    main()
