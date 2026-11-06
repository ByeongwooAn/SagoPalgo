"""Explicit, bounded, two-subscription public sample; no account/order credentials."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import time
import uuid
import hashlib

from check_public_tick_readiness import public_get


COPY_KEYS = ("SAGOPALGO_DB_URL", "SAGOPALGO_DB_USERNAME", "SAGOPALGO_DB_PASSWORD",
             "SAGOPALGO_KIS_APP_KEY", "SAGOPALGO_KIS_APP_SECRET", "SAGOPALGO_KIS_BASE_URL")
DISABLED = ("SAGOPALGO_KB_ACCOUNT_ENABLED", "SAGOPALGO_KB_ORDER_ENABLED", "SAGOPALGO_KB_LIVE_ORDER_ENABLED",
            "SAGOPALGO_KB_MARKET_DATA_ENABLED", "SAGOPALGO_ACCOUNT_OBSERVATION_COLLECTION_ENABLED",
            "SAGOPALGO_ALERT_ANALYSIS_ENABLED", "SAGOPALGO_RESEARCH_SYNC_ENABLED", "SAGOPALGO_RESEARCH_INCREMENTAL_ENABLED",
            "SAGOPALGO_AI_ENABLED", "SAGOPALGO_TOSS_MARKET_DATA_ENABLED", "SAGOPALGO_PERSONAL_MODE_ENABLED")


def isolated_environment(source, stock):
    if source.get("SAGOPALGO_MARKET_STREAM_ENABLED") == "true":
        raise ValueError("PRODUCTION_COLLECTOR_ENABLED")
    if not re.fullmatch(r"[0-9]{6}", stock) or any(not source.get(k) for k in COPY_KEYS):
        raise ValueError("CAPTURE_CONFIGURATION_REQUIRED")
    result = {k: source[k] for k in COPY_KEYS}
    if result["SAGOPALGO_KIS_BASE_URL"].rstrip("/") != "https://openapi.koreainvestment.com:9443":
        raise ValueError("PUBLIC_PROVIDER_ORIGIN_REQUIRED")
    result.update({k: "false" for k in DISABLED})
    result.update(SAGOPALGO_SERVER_PORT="8080", SAGOPALGO_KIS_ENABLED="true",
                  SAGOPALGO_MARKET_STREAM_ENABLED="true", SAGOPALGO_MARKET_STREAM_RIGHTS_CONFIRMED="true",
                  SAGOPALGO_MARKET_STREAM_APPROVED_SUBSCRIPTIONS="2", SAGOPALGO_MARKET_STREAM_SYMBOLS=stock)
    if any("\n" in v or "\r" in v for v in result.values()):
        raise ValueError("ENV_FORMAT_INVALID")
    return result


def docker(args, **kwargs):
    return subprocess.run(["docker", *args], capture_output=True, timeout=40, **kwargs)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-code", required=True)
    parser.add_argument("--seconds", type=int, default=20, choices=range(5, 61), metavar="5..60")
    parser.add_argument("--availability-jar",type=Path)
    parser.add_argument("--personal-local-use-confirmed", action="store_true", required=True)
    parser.add_argument("--no-other-key-client-confirmed", action="store_true", required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9]{6}", args.stock_code): parser.error("six-digit stock code required")
    jar=None
    if args.availability_jar:
        jar=args.availability_jar.resolve()
        project=Path(__file__).resolve().parents[1]
        if args.availability_jar.is_symlink() or not jar.is_file() or jar.suffix!=".jar" or not jar.is_relative_to(project/"Back/spring-server") or "," in str(jar):
            parser.error("workspace backend jar required")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:8]
    out = Path(__file__).resolve().parents[1]/"Back/spring-server/build-codex-quote-samples"/(args.stock_code+"-"+stamp)
    out.mkdir(parents=True)
    env_path = out/"capture.env.local"
    container = None
    receipt = {"schemaVersion":"SAGOPALGO_PUBLIC_SAMPLE_V2", "stockCode":args.stock_code,
               "requestedObservationSeconds":args.seconds, "containerLifetimeLimitSeconds":args.seconds+50,
               "containerTerminationGraceSeconds":5, "containerHardLifetimeLimitSeconds":args.seconds+55,
               "subscriptions":2, "ordersEnabled":False, "startedAt":datetime.now(timezone.utc).isoformat(),
               "states":[], "status":"STARTING"}
    try:
        original = json.loads(docker(["inspect", "sagopalgo-spring-api"], check=True).stdout)[0]
        source = dict(x.split("=",1) for x in original["Config"]["Env"] if "=" in x)
        values = isolated_environment(source,args.stock_code)
        mount=[]
        if jar:
            values["SAGOPALGO_MARKET_AVAILABILITY_ENABLED"]="true"
            mount=["--mount","type=bind,source="+str(jar)+",target=/app/app.jar,readonly"]
            receipt["availabilityJarSha256"]=hashlib.sha256(jar.read_bytes()).hexdigest()
        networks = list(original["NetworkSettings"]["Networks"])
        if len(networks)!=1: raise ValueError("NETWORK_AMBIGUOUS")
        image = original["Image"]
        if docker(["image","inspect",image]).returncode:
            image = original["Config"]["Image"]
            if docker(["image","inspect",image]).returncode: raise ValueError("LOCAL_IMAGE_MISSING")
        with env_path.open("x",encoding="utf-8",newline="\n") as stream:
            stream.write("".join(k+"="+v+"\n" for k,v in values.items()))
        result = docker(["run","-d","--rm","--pull=never","--name","sagopalgo-bounded-public-sample",
                         "--label","sagopalgo.purpose=bounded-public-tick-sample","--network",networks[0],
                         "-p","127.0.0.1:18080:8080","--env-file",str(env_path),*mount,"--entrypoint","/usr/bin/timeout",image,
                         "--signal=TERM","--kill-after=5s",str(args.seconds+50)+"s","java","-jar","/app/app.jar"])
        if result.returncode: raise ValueError("CAPTURE_CONTAINER_START_FAILED")
        container=result.stdout.decode().strip()
        if not re.fullmatch(r"[a-f0-9]{64}",container): raise ValueError("CAPTURE_CONTAINER_ID_INVALID")
        env_path.unlink()
        startup_deadline=time.monotonic()+40
        observation_deadline=None
        while time.monotonic()<startup_deadline or observation_deadline is not None:
            try:
                response=public_get("http://127.0.0.1:18080/api/v1/market/realtime?stockCode="+args.stock_code)
                body=response["body"];current=body.get("data") if body.get("success") else None
            except ValueError:current=None
            if current:
                if observation_deadline is None:observation_deadline=time.monotonic()+args.seconds
                state={k:current.get(k) for k in ("connectionState","state","diagnostic","checkedAt")}
                state.update(hasTrade=current.get("trade") is not None,hasQuote=current.get("quote") is not None)
                receipt["states"].append(state)
                if state["diagnostic"] or state["connectionState"] in {"FAILED","RECONNECTING"}:
                    raise ValueError("CAPTURE_PROVIDER_OR_STORAGE_FAILURE")
            if observation_deadline is not None and time.monotonic()>=observation_deadline:
                receipt["status"]="OBSERVATION_COMPLETED";break
            if observation_deadline is not None and time.monotonic()>startup_deadline+args.seconds:
                raise ValueError("CAPTURE_TOTAL_DEADLINE")
            time.sleep(1)
        else:raise ValueError("CAPTURE_STARTUP_TIMEOUT")
    except Exception as error:
        receipt["status"]="FAILED"
        receipt["failureCode"]=str(error) if type(error) is ValueError else type(error).__name__
    finally:
        if env_path.exists():env_path.unlink()
        if container and re.fullmatch(r"[a-f0-9]{64}",container):
            receipt["stopExitCode"]=docker(["stop","--time","5",container]).returncode
        receipt["endedAt"]=datetime.now(timezone.utc).isoformat()
        with (out/"receipt.json").open("x",encoding="utf-8") as stream:json.dump(receipt,stream,indent=2)
        print(json.dumps({k:receipt[k] for k in ["status","stockCode","startedAt","endedAt"]}|{"receipt":str(out/"receipt.json")}))
    return 0 if receipt["status"]=="OBSERVATION_COMPLETED" and receipt.get("stopExitCode")==0 else 1


if __name__=="__main__":raise SystemExit(main())
