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
