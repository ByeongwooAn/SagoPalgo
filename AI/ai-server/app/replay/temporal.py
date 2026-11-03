"""Explicit time windows with label-overlap purging; no random data splits."""
from datetime import timedelta
from pydantic import Field, model_validator

from .models import Identifier, ResearchError, StrictModel, Timestamp


class Sample(StrictModel):
    sampleId: Identifier
    decisionAt: Timestamp
    labelEndAt: Timestamp

    @model_validator(mode="after")
    def label_window(self):
        if self.labelEndAt <= self.decisionAt:
            raise ValueError("label must follow decision")
        return self


class SplitRequest(StrictModel):
    startAt: Timestamp
    validationStartAt: Timestamp
    testStartAt: Timestamp
    endAt: Timestamp
    embargoSeconds: int = Field(ge=0, le=31536000)
    samples: list[Sample] = Field(max_length=200000)

    @model_validator(mode="after")
    def ordered(self):
        if not self.startAt < self.validationStartAt < self.testStartAt < self.endAt:
            raise ValueError("unordered split windows")
        ids = [s.sampleId for s in self.samples]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate sample")
        return self


def temporal_split(request: SplitRequest) -> dict:
    result = {"train": [], "validation": [], "test": [], "excluded": []}
    for sample in sorted(request.samples, key=lambda s: (s.decisionAt, s.sampleId)):
        at = sample.decisionAt
        if not request.startAt <= at < request.endAt:
            result["excluded"].append({"sampleId": sample.sampleId, "reason": "OUTSIDE_WINDOW"})
            continue
        if at < request.validationStartAt:
            name, boundary = "train", request.validationStartAt - timedelta(seconds=request.embargoSeconds)
        elif at < request.testStartAt:
            name, boundary = "validation", request.testStartAt - timedelta(seconds=request.embargoSeconds)
        else:
            name, boundary = "test", request.endAt
        if sample.labelEndAt >= boundary:
            result["excluded"].append({"sampleId": sample.sampleId, "reason": "LABEL_OVERLAP_OR_EMBARGO"})
        else:
            result[name].append(sample.sampleId)
    if any(not result[name] for name in ["train", "validation", "test"]):
        raise ResearchError("EMPTY_TIME_SPLIT")
    return {"schemaVersion": "SAGOPALGO_TIME_SPLIT_V1", "request": request.model_dump(mode="json"), **result}
