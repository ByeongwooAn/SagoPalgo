import pytest

from app.replay.historical_dividend_followup import assess
from app.replay.models import ResearchError


def test_2024_payment_completion_keeps_issuer_and_seibro_dates():
    marker = "배당금 지급 완료일 2024-03-28 2024-03-28"
    sources = {"quarter": ("000100", marker, {"reportedOn": "2024-05-16"})}
    field = {"value": "2024-03-28", "evidence": [{"source": "quarter", "markers": [marker]}]}

    result = assess("actualPaymentDate", field, "2024-03-29", "000100", sources)

    assert (result["status"], result["issuerValue"], result["seibroValue"]) == (
        "DIFFERS", "2024-03-28", "2024-03-29",
    )


@pytest.mark.parametrize("heading", ["배당 내역", "배당 예정"])
def test_only_retrospective_issuer_history_can_confirm_undated_ir_payment(heading):
    header = f"{heading} 배당기준일 정기 주주총회 소집일 주당배당금(원) 배당지급일"
    row = "2023 8기 2023-11-29 2023-11-30 2024-02-29 137 2024-03-15"
    sources = {"history": ("365550", f"{header} {row}", {"reportedOn": None, "observedAt": "2026-11-16T11:20:00Z"})}
    field = {"value": "2024-03-15", "evidence": [{"source": "history", "markers": [header, row]}]}

    if heading == "배당 예정":
        with pytest.raises(ResearchError, match="DIVIDEND_2023_ACTUAL_PAYMENT"):
            assess("actualPaymentDate", field, "2024-03-15", "365550", sources)
    else:
        result = assess("actualPaymentDate", field, "2024-03-15", "365550", sources)
        assert result["status"] == "MATCH"
