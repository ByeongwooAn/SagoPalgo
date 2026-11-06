import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .dataset import build_bundle, canonical, known_at, load_bundle, read_bytes, read_json, snapshot
from .engine import replay
from .models import ReplayConfig, ResearchError, utc
from .temporal import SplitRequest, temporal_split
from .stored import convert_file
from .intraday import load_policy
from .ticks import audit_tick_files
from .ticks import TickAuditConfig, audit_ticks, observed_snapshot
from .tick_quality import quality_profile
from .quote_execution import QuoteExecutionPolicy, QuoteOrder, estimate_quotes


def write_report(path: Path, report):
    # Exclusive create prevents replacing an earlier research result.
    with path.open("xb") as stream:
        stream.write(canonical(report) + b"\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SagoPalgo offline historical research (no API/order calls)")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--spec", required=True, type=Path)
    build.add_argument("--input", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--dataset", required=True, type=Path)
    view = commands.add_parser("snapshot")
    view.add_argument("--dataset", required=True, type=Path)
    view.add_argument("--at", required=True)
    view.add_argument("--output", required=True, type=Path)
    run = commands.add_parser("replay")
    run.add_argument("--dataset", required=True, type=Path)
    run.add_argument("--config", required=True, type=Path)
    run.add_argument("--output", required=True, type=Path)
    run.add_argument('--intraday-timeline', type=Path)
    run.add_argument('--timeline-sha256')
    run.add_argument('--market', choices=['KOSPI', 'KOSDAQ'])
    run.add_argument('--order-class', choices=['ORDINARY', 'PROGRAM'])
    split = commands.add_parser("split")
    split.add_argument("--config", required=True, type=Path)
    split.add_argument("--output", required=True, type=Path)
    stored = commands.add_parser("convert-stored")
    stored.add_argument("--input", required=True, type=Path)
    stored.add_argument("--config", required=True, type=Path)
    stored.add_argument("--output", required=True, type=Path)
    ticks = commands.add_parser("audit-ticks")
    ticks.add_argument("--input", required=True, type=Path)
    ticks.add_argument("--config", required=True, type=Path)
    ticks.add_argument("--claims", type=Path)
    ticks.add_argument("--output", required=True, type=Path)
    publication=commands.add_parser("snapshot-inputs")
    publication.add_argument("--input",required=True,type=Path)
    publication.add_argument("--config",required=True,type=Path)
    publication.add_argument("--at",required=True)
    publication.add_argument("--clock-domain",required=True)
    publication.add_argument("--output",required=True,type=Path)
    for command in ["profile-ticks", "quote-scenario"]:
        command_parser = commands.add_parser(command)
        command_parser.add_argument("--input", required=True, type=Path)
        command_parser.add_argument("--config", required=True, type=Path)
        command_parser.add_argument("--session-evidence", required=True, type=Path)
        command_parser.add_argument("--output", required=True, type=Path)
        if command == "quote-scenario":
            command_parser.add_argument("--policy", required=True, type=Path)
            command_parser.add_argument("--orders", required=True, type=Path)
            command_parser.add_argument('--intraday-timeline', type=Path)
            command_parser.add_argument('--timeline-sha256')
            command_parser.add_argument('--market', choices=['KOSPI', 'KOSDAQ'])
            command_parser.add_argument('--order-class', choices=['ORDINARY', 'PROGRAM'])
    args = parser.parse_args(argv)
    if args.command in {'replay', 'quote-scenario'}:
        binding = [args.intraday_timeline, args.timeline_sha256, args.market, args.order_class]
        if any(binding) and not all(binding):parser.error('intraday replay requires --intraday-timeline --timeline-sha256 --market --order-class together')
    try:
        if args.command=="snapshot-inputs":
            report=observed_snapshot(read_bytes(args.input),TickAuditConfig.model_validate(read_json(read_bytes(args.config))),utc(args.at),args.clock_domain)
            write_report(args.output,report)
            result={"status":"CREATED","records":len(report["records"]),"clockDomain":report["clockDomain"]}
        elif args.command in {"profile-ticks", "quote-scenario"}:
            raw = read_bytes(args.input)
            config = TickAuditConfig.model_validate(read_json(read_bytes(args.config)))
            evidence = read_bytes(args.session_evidence)
            if args.command == "quote-scenario":
                values = read_json(read_bytes(args.orders))
                if not isinstance(values, list) or len(values) > 10000: raise ResearchError("ORDER_ID_OR_COUNT_INVALID")
                report = estimate_quotes(raw, config, evidence,
                    QuoteExecutionPolicy.model_validate(read_json(read_bytes(args.policy))),
                    [QuoteOrder.model_validate(value) for value in values],
                    load_policy(args.intraday_timeline,args.timeline_sha256,args.market,args.order_class) if args.intraday_timeline else None)
                result = {"status": "CREATED", "statusCounts": report["statusCounts"], "reportId": report["reportId"]}
            else:
                records, audit_report = audit_ticks(raw, config, [])
                records, report = quality_profile(records, evidence)
                report.update(sourceExportSha256=audit_report["sourceExportSha256"], records=records)
                result = {"status": "CREATED", "records": len(records), "dateEvidenceCounts": report["dateEvidenceCounts"]}
            write_report(args.output, report)
        elif args.command == "audit-ticks":
            report = audit_tick_files(args.input, args.config, args.output, args.claims)
            result = {k: report[k] for k in ["status", "counts", "comparisonCounts", "reportId"]}
        elif args.command == "convert-stored":
            report = convert_file(args.input, args.config, args.output)
            result = {k: report[k] for k in ["status", "outputRecordCount", "excludedCounts"]}
        elif args.command == "build":
            manifest = build_bundle(args.spec, args.input, args.output)
            result = {"status": "CREATED", "datasetId": manifest["datasetId"]}
        elif args.command == "split":
            report = temporal_split(SplitRequest.model_validate(read_json(read_bytes(args.config))))
            write_report(args.output, report)
            result = {"status": "CREATED", "counts": {k: len(report[k]) for k in ["train", "validation", "test", "excluded"]}}
        else:
            manifest, spec, records, quality = load_bundle(args.dataset)
            if args.command == "inspect":
                result = {"datasetId": manifest["datasetId"], "quality": quality}
            elif args.command == "snapshot":
                at = utc(args.at)
                items = snapshot(records, spec, at)
                write_report(args.output, {"datasetId": manifest["datasetId"], "at": at.isoformat(),
                                          "records": [{**r.model_dump(mode="json"), "knownAt": known_at(r, spec).isoformat()} for r in items]})
                result = {"status": "CREATED", "records": len(items)}
            else:
                config = ReplayConfig.model_validate(read_json(read_bytes(args.config)))
                intraday = load_policy(args.intraday_timeline, args.timeline_sha256, args.market, args.order_class) if args.intraday_timeline else None
                report = replay(manifest, spec, records, quality, config, intraday)
                write_report(args.output, report)
                result = {"status": report["status"], "reportId": report["reportId"], "fills": len(report["fills"])}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except ResearchError as error:
        code = str(error)
    except ValidationError:
        code = "INPUT_SCHEMA_INVALID"
    except (UnicodeError, json.JSONDecodeError, ValueError, TypeError, KeyError, OverflowError):
        code = "INPUT_INVALID"
    except OSError:
        code = "FILE_OPERATION_FAILED"
    print(json.dumps({"status": "FAILED", "code": code}), file=sys.stderr)
    return 2


if __name__ == "__main__":
    # Windows redirected stdout can otherwise be encoded in a legacy code page.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
