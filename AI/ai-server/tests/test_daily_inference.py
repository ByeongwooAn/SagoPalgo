from datetime import date, timedelta
from hashlib import sha256
import json
from os import environ
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app import daily_inference
from app.main import app
from app.replay.daily_learning import FINAL, load_snapshot
from app.replay.us_daily_learning import audit_capture


PATH = "/internal/ai/infer-daily"


@pytest.fixture
def client():
    with TestClient(app) as session:
        yield session


def payload(code="005930"):
    start = date(2026, 10, 1)
    rows = [{"businessDate": (start + timedelta(days=i)).isoformat(),
             "opened": 98 + i, "high": 104 + i, "low": 97 + i,
             "closed": 100 + i, "volume": 1000 + i} for i in range(21)]
    return {"stockCode": code, "market": "KOSPI", "provider": "KIS", "priceBasis": "RAW",
            "signalDate": rows[-1]["businessDate"], "bars": rows}


def test_matching_model_is_selected_and_changed_file_is_unavailable(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SAGOPALGO_DAILY_MODEL_DIR", str(tmp_path))
    for code, intercept in [("005930", 0), ("000660", 1)]:
        model = {"intercept": intercept, "means": [0] * 7, "scales": [1] * 7,
                 "coefficients": [0] * 7, "trainedOn": {"lastTargetDate": "2025-08-28"},
                 "threshold": 0.5}
        raw = json.dumps(model).encode()
        monkeypatch.setitem(daily_inference.MODELS, code, sha256(raw).hexdigest())
        (tmp_path / f"{code}-model.json").write_bytes(raw)

    assert client.post(PATH, json=payload()).json()["probability"] == 0.5
    assert client.post(PATH, json=payload("000660")).json()["probability"] == pytest.approx(0.73105857863)
    (tmp_path / "005930-model.json").write_text("{}")
    assert client.post(PATH, json=payload()).status_code == 503
    assert client.post(PATH, json=payload("000660")).status_code == 200


@pytest.mark.parametrize("problem", ["adjusted", "duplicate", "stale", "zeroVolume", "invalidHigh"])
def test_rejects_unusable_input_before_loading_the_model(client, problem):
    request = payload()
    rows = request["bars"]
    match problem:
        case "adjusted": request["priceBasis"] = "ADJUSTED"
        case "duplicate": rows[0]["businessDate"] = rows[1]["businessDate"]
        case "stale": request["signalDate"] = "2026-10-22"
        case "zeroVolume": rows[-1]["volume"] = 0
        case "invalidHigh": rows[-1]["high"] = 1
    assert client.post(PATH, json=request).status_code == 422


def test_market_mismatch_and_krx_fractional_price_are_rejected(client):
    request = payload("AAPL")
    assert client.post(PATH, json=request).status_code == 422
    request = payload()
    request["bars"][0]["opened"] += 0.125
    assert client.post(PATH, json=request).status_code == 422


@pytest.mark.skipif(environ.get("SAGOPALGO_VERIFY_FROZEN_DAILY") != "1", reason="requires private local artifacts")
@pytest.mark.parametrize("code", ["AAPL", "NVDA"])
def test_us_frozen_model_matches_all_offline_probabilities(client, code, monkeypatch):
    artifacts = Path("research-artifacts")
    models = artifacts / "us-daily-learning-v1"
    monkeypatch.setenv("SAGOPALGO_US_DAILY_MODEL_DIR", str(models))
    report = json.loads((models / "evaluation.json").read_bytes())["stocks"][code]
    sessions, records, _, _ = audit_capture(artifacts / "us-daily-capture-20261119")
    indices = {str(day): index for index, day in enumerate(sessions)}
    threshold = report["threshold"]
    rows = report["details"]["finalRows"]
    errors = []
    for offline in rows:
        index = indices[offline["signalDate"]]
        bars = [records[code][day] for day in sessions[index - 20:index + 1]]
        assert str(sessions[index + 1]) == offline["targetDate"]
        response = client.post(PATH, json={
            "stockCode": code, "market": "NASDAQ", "provider": "KIS", "priceBasis": "RAW",
            "signalDate": offline["signalDate"], "bars": [
                {"businessDate": bar.date, "opened": bar.opened, "high": bar.high,
                 "low": bar.low, "closed": bar.closed, "volume": bar.volume}
                for bar in bars
            ],
        })
        assert response.status_code == 200
        result = response.json()
        assert result["stockCode"] == code and result["signalDate"] == offline["signalDate"]
        assert result["modelVersion"] == daily_inference.US_MODEL_VERSION
        assert result["modelSha256"] == report["modelSha256"] and result["threshold"] == threshold
        actual, expected = result["probability"], offline["upProbability"]
        assert (threshold is not None and actual >= threshold) == (threshold is not None and expected >= threshold)
        errors.append(abs(actual - expected))
    assert len(errors) == 143
    assert max(errors) < 1e-12
    print(f"{code} {len(errors)} dates · max |Δp|={max(errors):.3g}")


@pytest.mark.skipif(environ.get("SAGOPALGO_VERIFY_FROZEN_DAILY") != "1", reason="requires private local artifacts")
@pytest.mark.parametrize("code", ["005930", "000660"])
def test_frozen_model_matches_all_same_date_offline_probabilities(client, code, monkeypatch):
    artifacts = Path("research-artifacts")
    models = artifacts / "daily-learning-v1"
    monkeypatch.setenv("SAGOPALGO_DAILY_MODEL_DIR", str(models))
    report = json.loads((models / "evaluation.json").read_bytes())
    bars, days = load_snapshot(artifacts, code)
    rows = report["details"][code]["finalRows"]
    threshold = report["stocks"][code]["threshold"]
    final_dates = [i for i, day in enumerate(days) if day["sampleUse"] == FINAL]
    assert len(final_dates) == len(rows) == 142

    max_error = 0
    last_result = None
    for i, offline in zip(final_dates, rows, strict=True):
        assert bars[i].date == offline["signalDate"] and bars[i + 1].date == offline["targetDate"]
        request = {"stockCode": code, "market": "KOSPI", "provider": "KIS", "priceBasis": "RAW",
                   "signalDate": bars[i].date, "bars": [
                       {"businessDate": bar.date, "opened": bar.opened, "high": bar.high,
                        "low": bar.low, "closed": bar.closed, "volume": bar.volume}
                       for bar in bars[i - 20:i + 1]
                   ]}
        response = client.post(PATH, json=request)
        assert response.status_code == 200
        last_result = response.json()
        assert last_result["stockCode"] == code and last_result["signalDate"] == offline["signalDate"]
        assert last_result["modelSha256"] == report["stocks"][code]["modelSha256"]
        assert last_result["threshold"] == threshold
        actual, expected = last_result["probability"], offline["upProbability"]
        assert (actual >= threshold) == (expected >= threshold)
        max_error = max(max_error, abs(actual - expected))

    assert max_error < 1e-12
    print(f"{code} {len(rows)} dates · max |Δp|={max_error:.3g} · {last_result['signalDate']} → "
          f"{rows[-1]['targetDate']} · API p={last_result['probability']:.15f} · offline p={rows[-1]['upProbability']:.15f}")
