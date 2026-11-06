"""Independent cached KIS/KRX daily reference comparison, never a tick-fill check."""
import argparse
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .dataset import canonical, digest, read_bytes, read_json
from .history import audit as audit_history
from .krx_baseline_validation import audit_receipt, parse_daily
from .models import ResearchError

FIELDS = {"open": "TDD_OPNPRC", "high": "TDD_HGPRC", "low": "TDD_LWPRC",
          "close": "TDD_CLSPRC", "volume": "ACC_TRDVOL"}


def compare_daily_rows(kis_rows, krx_rows):
    left = {(r["stockCode"], r["businessDate"]): r for r in kis_rows}
    right = {(r["ISU_CD"], r["BAS_DD"][:4]+"-"+r["BAS_DD"][4:6]+"-"+r["BAS_DD"][6:]): r for r in krx_rows}
    if len(left) != len(kis_rows) or len(right) != len(krx_rows):
        raise ResearchError("DAILY_REFERENCE_DUPLICATE")
    comparisons = []
    for key in sorted(left.keys() & right.keys()):
        a, b = left[key], right[key]
        fields = {}
        for name, other in FIELDS.items():
            try:
                x, y = Decimal(a[name]), Decimal(b[other])
                if not x.is_finite() or not y.is_finite() or x < 0 or y < 0:
                    raise InvalidOperation
                if name == "volume" and (x != x.to_integral_value() or y != y.to_integral_value()):
                    raise InvalidOperation
                fields[name] = {"kis": a[name], "krx": b[other], "status": "MATCH" if x == y else "MISMATCH"}
            except (InvalidOperation, KeyError, ValueError, TypeError):
                fields[name] = {"status": "NOT_ASSESSABLE", "reason": "INVALID_OR_MISSING_NUMBER"}
        statuses = {v["status"] for v in fields.values()}
        comparisons.append({"stockCode": key[0], "businessDate": key[1], "fields": fields,
                            "kisRowSha256": digest(canonical(a)), "krxRowSha256": digest(canonical(b)),
                            "status": "NOT_ASSESSABLE" if "NOT_ASSESSABLE" in statuses else
                                      "MISMATCH" if "MISMATCH" in statuses else "MATCH"})
    return {"schemaVersion": "SAGOPALGO_DAILY_REFERENCE_V1", "resolution": "DAY", "comparisons": comparisons,
            "status": "NO_COMMON_DAILY_REFERENCE" if not comparisons else "COMPARED_DAILY_ONLY",
            "kisRowCount": len(left), "krxRowCount": len(right), "commonRowCount": len(comparisons),
            "tickComparisonStatus": "NOT_ASSESSABLE", "reason": "DAILY_OHLCV_IS_NOT_TAPE_OR_ORDER_BOOK",
            "usableForTrading": False, "usableForStrategyValidation": False}


def compare_daily_jobs(kis_job: Path, krx_job: Path, market: str):
    kis_audit, kis_rows = audit_history(kis_job, check_daily=True)
    plan = read_json(read_bytes(krx_job / "plan.json"))
    receipt, raw = audit_receipt(krx_job / market, market, plan)
    parse_daily(raw, market, plan["basisDate"], receipt["capturedAt"])
    result = compare_daily_rows(kis_rows, read_json(raw)["OutBlock_1"])
    result.update(provenance=kis_audit["provenance"], krxSourceKind=plan["sourceKind"],
                  sourceHashes={"kisDaily": digest(read_bytes(kis_job / "daily.jsonl")),
                                "krxBody": digest(raw), "krxReceipt": digest(read_bytes(krx_job / market / "receipt.json"))})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kis-job", required=True, type=Path)
    parser.add_argument("--krx-daily-job", required=True, type=Path)
    parser.add_argument("--market", required=True, choices=["KOSPI", "KOSDAQ"])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = compare_daily_jobs(args.kis_job, args.krx_daily_job, args.market)
    with args.output.open("xb") as stream:
        stream.write(canonical(result) + b"\n")
    print(canonical({"status": result["status"], "commonRowCount": result["commonRowCount"]}).decode())


if __name__ == "__main__":
    main()
