from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_and_analysis_contract_use_camel_case() -> None:
    assert client.get("/health").json() == {"status": "UP"}

    response = client.post(
        "/internal/ai/analyze-investment",
        json={
            "stockCode": "005930",
            "stockName": "삼성전자",
            "market": "KOSPI",
            "currentPrice": 75200,
            "buyPrice": 70000,
            "profitRate": 7.43,
            "stopLossRate": -5,
            "takeProfitRate": 12,
            "candles": [],
            "news": [],
            "disclosures": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["modelVersion"] == "WEIGHTED_SIGNAL_V1"
    assert body["recommendationType"] == "HOLD"
    assert "reasons" in body


def test_watchlist_contract_accepts_no_holding_cost_basis() -> None:
    response = client.post(
        "/internal/ai/analyze-investment",
        json={
            "stockCode": "005930",
            "stockName": "삼성전자",
            "market": "KOSPI",
            "currentPrice": 75200,
            "analysisType": "WATCHLIST",
            "candles": [],
            "news": [],
            "disclosures": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "HOLD"
    assert "관심 종목 점수" in body["summary"]


def test_analysis_accepts_nonempty_candles_with_spring_iso_datetime_strings() -> None:
    response = client.post(
        "/internal/ai/analyze-investment",
        json={
            "stockCode": "000660",
            "stockName": "SK하이닉스",
            "market": "KOSPI",
            "currentPrice": 75200,
            "analysisType": "WATCHLIST",
            "candles": [
                {"dateTime": "2026-09-15T00:00:00", "closePrice": 74000, "volume": 1000},
                {"dateTime": "2026-09-16T12:34:56.123", "closePrice": 75200, "volume": 1200},
            ],
            "news": [],
            "disclosures": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["modelVersion"] == "WEIGHTED_SIGNAL_V1"


def test_analysis_rejects_array_datetime_before_analysis() -> None:
    response = client.post(
        "/internal/ai/analyze-investment",
        json={
            "stockCode": "000660",
            "stockName": "SK하이닉스",
            "market": "KOSPI",
            "currentPrice": 75200,
            "analysisType": "WATCHLIST",
            "candles": [{"dateTime": [2026, 9, 15, 0, 0], "closePrice": 74000, "volume": 1000}],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "candles", 0, "dateTime"]
