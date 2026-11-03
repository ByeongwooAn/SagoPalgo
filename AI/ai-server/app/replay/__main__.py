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
    split = commands.add_parser("split")
    split.add_argument("--config", required=True, type=Path)
    split.add_argument("--output", required=True, type=Path)
    stored = commands.add_parser("convert-stored")
    stored.add_argument("--input", required=True, type=Path)
    stored.add_argument("--config", required=True, type=Path)
    stored.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "convert-stored":
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
                report = replay(manifest, spec, records, quality, config)
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
