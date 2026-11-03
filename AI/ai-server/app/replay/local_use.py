"""Explicit personal-local scope; keeps original acquisition declarations unchanged."""
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .dataset import canonical, digest, read_bytes, read_json
from .history import audit, job_lock, now
from .models import ResearchError, StrictModel, Timestamp

FAQ = "https://apiportal.koreainvestment.com/community/10000000-0000-0011-0000-000000000002/post/1f422ddb-7a9c-4279-9ecb-21eb750a4b7a"


class LocalUse(StrictModel):
    schemaVersion: Literal["SAGOPALGO_LOCAL_RESEARCH_USE_V1"]
    historyPlanId: str = Field(pattern=r"^[a-f0-9]{64}$")
    dailySha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    acceptedAt: Timestamp
    evidenceUrl: str
    basis: Literal["PERSONAL_ANALYSIS_INTERPRETATION"]
    purpose: Literal["SELF_ASSET_INVESTMENT"]
    localStorageOnly: bool
    externalAiTransfer: bool
    thirdPartyProvision: bool
    providerExplicitAiGrant: bool

    @model_validator(mode="after")
    def personal_scope(self):
        if not self.localStorageOnly or self.externalAiTransfer or self.thirdPartyProvision or self.providerExplicitAiGrant:
            raise ValueError("this profile supports personal local analysis only")
        if self.evidenceUrl != FAQ:
            raise ValueError("expected reviewed FAQ reference")
        return self


def bind_local_use(job: Path, output: Path):
    with job_lock(job):
        report, _ = audit(job, check_daily=True)
        if report["status"] != "COLLECTED":
            raise ResearchError("LOCAL_USE_REQUIRES_AUDITED_COLLECTION")
        value = LocalUse.model_validate({
            "schemaVersion": "SAGOPALGO_LOCAL_RESEARCH_USE_V1", "historyPlanId": report["planId"],
            "dailySha256": digest(read_bytes(job / "daily.jsonl")), "acceptedAt": now(), "evidenceUrl": FAQ,
            "basis": "PERSONAL_ANALYSIS_INTERPRETATION", "purpose": "SELF_ASSET_INVESTMENT",
            "localStorageOnly": True, "externalAiTransfer": False, "thirdPartyProvision": False,
            "providerExplicitAiGrant": False,
        }).model_dump(mode="json")
        value["policyId"] = digest(canonical(value))
        with output.open("xb") as stream:
            stream.write(canonical(value))
        return value


def load_local_use(path: Path, report, daily_raw: bytes):
    if report.get("status") != "COLLECTED":
        raise ResearchError("LOCAL_USE_REQUIRES_AUDITED_COLLECTION")
    value = read_json(read_bytes(path))
    if not isinstance(value, dict) or "policyId" not in value:
        raise ResearchError("LOCAL_USE_PROFILE_INVALID")
    body = {k: v for k, v in value.items() if k != "policyId"}
    if digest(canonical(body)) != value["policyId"]:
        raise ResearchError("LOCAL_USE_PROFILE_TAMPERED")
    policy = LocalUse.model_validate(body)
    if policy.historyPlanId != report["planId"] or policy.dailySha256 != digest(daily_raw):
        raise ResearchError("LOCAL_USE_DATASET_MISMATCH")
    return policy
