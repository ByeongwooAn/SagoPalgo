from dataclasses import replace
from datetime import date, timedelta
from math import exp
from statistics import fmean, pstdev

import pytest

from app.replay import daily_learning as learning
from app.replay.dataset import digest, read_json
from app.replay.models import ResearchError
from app.replay.samsung_daily_training import freeze_dates


def sample(forward_return):
    return learning.Sample("2026-04-02", "2026-04-03", (0.0,) * 7, forward_return)


def test_features_use_21_bars_and_previous_volume_only():
    bars = [learning.Bar(str(i), 98 + i, 104 + i, 97 + i, 100 + i, 1000 + i)
            for i in range(21)]
    assert learning.daily_features(bars) == pytest.approx((
        120 / 118 - 1, 120 / 119 - 1, 120 / 115 - 1, 120 / 100 - 1,
        7 / 118, pstdev((i + 1) / i - 1 for i in range(100, 120)), 1020 / 1009.5,
    ))
    with pytest.raises(ResearchError, match="INVALID_LOOKBACK"):
        learning.daily_features(bars[:-1])


def test_costs_charge_both_fills_and_drawdown_starts_at_initial_equity():
    costs = learning.COSTS["base"]
    losing = costs.net_return(-0.05)
    winning = costs.net_return(0.10)
    cash_out = 100 * 1.0005 * 1.0005
    cash_in = 95 * 0.9995 * (1 - 0.0005 - 0.002)
    assert losing == pytest.approx(cash_in / cash_out - 1)
    result = learning.performance([sample(-0.05), sample(-0.5), sample(0.10)],
                                  [True, False, True], costs)
    assert result == pytest.approx({"netReturn": (1 + losing) * (1 + winning) - 1,
                                    "maxDrawdown": -losing, "trades": 2})


def test_threshold_can_select_cash_and_includes_equal_probability():
    assert learning.select_threshold([sample(-0.01)], [0.8])[0] is None
    assert learning.select_threshold([sample(0.01)], [0.5])[0] == 0.5
    assert learning.select_threshold([sample(0.01)], [0.55])[0] == 0.55


@pytest.fixture
def snapshot():
    dates = [(date(2023, 11, 1) + timedelta(days=i)).isoformat() for i in range(730)]
    calendar = [{"businessDate": day, "openDay": True, "basis": "SYNTHETIC"} for day in dates]
    days = freeze_dates(calendar, dates, {})
    for day in days:
        day["commonSample"] = day["sampleUse"] in learning.COUNTS
    bars = []
    for i, day in enumerate(dates):
        opened = 1000 + i + i % 5
        closed = opened + (i % 7) * 12 - 30
        bars.append(learning.Bar(day, opened, max(opened, closed) + i % 5,
                                 min(opened, closed) - 1, closed, 1000 + 100 * (i % 11)))
    return bars, days


def test_final_perturbation_cannot_change_preprocessing_weights_or_threshold(monkeypatch, snapshot):
    stock = "005930"
    monkeypatch.setattr(learning, "load_snapshot", lambda *_: snapshot)
    original, _ = learning.run(None)
    evaluation = read_json(original["evaluation.json"])
    validation = evaluation["details"][stock]
    assert [fold["trainingCount"] for fold in validation["folds"]] == [424, 470, 517]
    assert all(fold["lastTrainingTargetDate"] < fold["firstSignalDate"] for fold in validation["folds"])
    assert len(evaluation["commonFinalPairs"]) == 142
    model = read_json(original[f"{stock}-model.json"])
    train = learning.samples_for(snapshot, learning.TRAIN)
    assert model["means"] == pytest.approx([fmean(column) for column in zip(*(row.features for row in train))])

    bars, days = snapshot
    first_final = next(i for i, day in enumerate(days) if day["sampleUse"] == learning.FINAL)
    # The next bar can change its target and later features, but cannot change its own signal.
    bar = bars[first_final + 1]
    bars[first_final + 1] = replace(bar, high=bar.opened * 2, closed=bar.opened * 2)
    mutated, _ = learning.run(None)
    after = read_json(mutated["evaluation.json"])
    for code in learning.INPUTS:
        assert original[f"{code}-model.json"] == mutated[f"{code}-model.json"]
        assert after["stocks"][code]["modelSha256"] == digest(original[f"{code}-model.json"])
        for key in ("folds", "thresholdCandidates", "rows"):
            assert evaluation["details"][code][key] == after["details"][code][key]
    first_before = evaluation["details"][stock]["finalRows"][0]
    first_after = after["details"][stock]["finalRows"][0]
    assert first_before["upProbability"] == first_after["upProbability"]
    assert first_before["grossReturn"] != first_after["grossReturn"]
    features = learning.samples_for(snapshot, learning.FINAL)[0].features
    score = model["intercept"] + sum(
        weight * (value - mean) / scale
        for weight, value, mean, scale in zip(model["coefficients"], features, model["means"], model["scales"])
    )
    assert first_before["upProbability"] == pytest.approx(1 / (1 + exp(-score)))


def test_target_date_must_be_the_next_session(snapshot):
    _, days = snapshot
    first = next(day for day in days if day["sampleUse"] == learning.TRAIN)
    first["targetDate"] = "2100-01-01"
    with pytest.raises(ResearchError, match="FROZEN_DATE_MISMATCH"):
        learning.samples_for(snapshot, learning.TRAIN)


def test_changed_pinned_file_and_existing_output_are_rejected(tmp_path, capsys):
    path = tmp_path / "input.json"
    path.write_bytes(b"{}")
    assert learning.pinned_input(tmp_path, (path.name, digest(b"{}"))) == b"{}"
    with pytest.raises(ResearchError, match="PINNED_INPUT_CHANGED"):
        learning.pinned_input(tmp_path, (path.name, digest(b"[]")))
    assert learning.main(["--artifacts", str(tmp_path), "--output", str(tmp_path)]) == 2
    assert "OUTPUT_EXISTS" in capsys.readouterr().out
    assert path.read_bytes() == b"{}"
