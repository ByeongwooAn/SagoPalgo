from dataclasses import dataclass

from .models import AnalysisReason, InvestmentAnalysisRequest, InvestmentAnalysisResponse

MODEL_VERSION = "WEIGHTED_SIGNAL_V1"

POSITIVE_WORDS = (
    "성장",
    "증가",
    "확대",
    "수주",
    "흑자",
    "호조",
    "상승",
    "growth",
    "increase",
    "profit",
)
NEGATIVE_WORDS = (
    "감소",
    "적자",
    "하락",
    "소송",
    "제재",
    "리콜",
    "위험",
    "decrease",
    "loss",
    "risk",
)
POSITIVE_DISCLOSURES = ("수주", "계약", "배당", "자사주", "유상증자 결정 철회")
NEGATIVE_DISCLOSURES = ("유상증자", "소송", "횡령", "부도", "상장폐지", "회생절차")


@dataclass(frozen=True)
class Signal:
    label: str
    description: str
    type: str
    score: int

    def response(self) -> AnalysisReason:
        return AnalysisReason(
            label=self.label,
            description=self.description,
            type=self.type,
            score=self.score,
        )


def analyze(request: InvestmentAnalysisRequest) -> InvestmentAnalysisResponse:
    signals = [
        _risk_signal(request),
        _price_signal(request),
        _news_signal(request),
        _disclosure_signal(request),
    ]
    if request.analysis_type == "HOLDING" and request.portfolio_weight_rate is not None:
        signals.append(_portfolio_signal(request))
    score = max(0, min(100, 50 + sum(signal.score for signal in signals)))
    recommendation_type, status = _decision(request, score)
    summary = _summary(request, status, score)
    return InvestmentAnalysisResponse(
        model_version=MODEL_VERSION,
        recommendation_type=recommendation_type,
        status=status,
        score=score,
        summary=summary,
        reasons=[signal.response() for signal in signals],
    )


def _risk_signal(request: InvestmentAnalysisRequest) -> Signal:
    if request.analysis_type == "WATCHLIST":
        return Signal("비보유 종목", "보유 손익이나 손절·익절 기준 없이 관심 종목의 흐름만 분석했습니다.", "RISK", 0)
    assert request.profit_rate is not None
    assert request.take_profit_rate is not None
    assert request.stop_loss_rate is not None
    if request.profit_rate >= request.take_profit_rate - 1:
        return Signal(
            "익절 기준",
            f"현재 수익률 {request.profit_rate:.2f}%가 익절 기준에 근접했습니다.",
            "RISK",
            -8,
        )
    if request.profit_rate <= request.stop_loss_rate + 1:
        return Signal(
            "손절 기준",
            f"현재 수익률 {request.profit_rate:.2f}%가 손절 기준에 근접했습니다.",
            "RISK",
            -22,
        )
    contribution = max(-8, min(8, round(request.profit_rate)))
    return Signal(
        "보유 손익",
        f"현재 수익률 {request.profit_rate:.2f}%는 설정한 손절·익절 구간 안에 있습니다.",
        "RISK",
        contribution,
    )


def _portfolio_signal(request: InvestmentAnalysisRequest) -> Signal:
    assert request.portfolio_weight_rate is not None
    weight = request.portfolio_weight_rate
    capital_weight = request.capital_weight_rate
    limit = request.max_capital_weight_rate
    if capital_weight is not None and limit is not None and capital_weight > limit:
        return Signal(
            "매입 원금 비중",
            f"동일 종목 매입 원금은 설정 자본금의 {capital_weight:.2f}%로 권장 한도 {limit:.2f}%를 넘습니다. "
            f"등록 보유 종목 원금 중 비중은 {weight:.2f}%입니다.",
            "PORTFOLIO",
            -12,
        )
    capital_description = (
        f"설정 자본금의 {capital_weight:.2f}%입니다."
        if capital_weight is not None else "설정 자본금이 없어 자본금 대비 비중은 판단하지 않았습니다."
    )
    return Signal(
        "매입 원금 비중",
        f"동일 종목은 등록 보유 종목 매입 원금의 {weight:.2f}%, {capital_description}",
        "PORTFOLIO",
        0,
    )


def _price_signal(request: InvestmentAnalysisRequest) -> Signal:
    if len(request.candles) < 2:
        return Signal("가격 흐름", "비교할 가격 이력이 부족해 중립으로 반영했습니다.", "PRICE", 0)
    first = request.candles[0].close_price
    last = request.candles[-1].close_price
    change_rate = (last - first) / first * 100
    contribution = max(-18, min(18, round(change_rate * 1.5)))
    direction = "상승" if change_rate > 0 else "하락" if change_rate < 0 else "보합"
    return Signal(
        "가격 추세",
        f"분석 구간 종가는 {change_rate:+.2f}% {direction}했습니다.",
        "PRICE",
        contribution,
    )


def _news_signal(request: InvestmentAnalysisRequest) -> Signal:
    if not request.news:
        return Signal("뉴스 흐름", "저장된 최신 뉴스가 없어 중립으로 반영했습니다.", "NEWS", 0)
    sentiment = sum(_keyword_score(f"{item.title} {item.summary}") for item in request.news)
    contribution = max(-12, min(12, sentiment * 3))
    return Signal(
        "뉴스 흐름",
        f"최신 뉴스 {len(request.news)}건의 핵심어 점수를 종합했습니다.",
        "NEWS",
        contribution,
    )


def _disclosure_signal(request: InvestmentAnalysisRequest) -> Signal:
    if not request.disclosures:
        return Signal("공시 흐름", "분석 기간의 공시가 없어 중립으로 반영했습니다.", "DISCLOSURE", 0)
    score = 0
    for item in request.disclosures:
        text = item.report_name.lower()
        score += sum(1 for word in POSITIVE_DISCLOSURES if word.lower() in text)
        score -= sum(1 for word in NEGATIVE_DISCLOSURES if word.lower() in text)
    contribution = max(-10, min(10, score * 4))
    return Signal(
        "공시 흐름",
        f"최근 공시 {len(request.disclosures)}건의 사건 유형을 반영했습니다.",
        "DISCLOSURE",
        contribution,
    )


def _keyword_score(text: str) -> int:
    lowered = text.lower()
    positive = sum(1 for word in POSITIVE_WORDS if word.lower() in lowered)
    negative = sum(1 for word in NEGATIVE_WORDS if word.lower() in lowered)
    return positive - negative


def _decision(request: InvestmentAnalysisRequest, score: int) -> tuple[str, str]:
    if request.analysis_type == "HOLDING":
        assert request.profit_rate is not None
        assert request.stop_loss_rate is not None
        assert request.take_profit_rate is not None
        if request.profit_rate <= request.stop_loss_rate + 1:
            return "SELL", "STOP_LOSS_WATCH"
        if request.profit_rate >= request.take_profit_rate - 1:
            return "SELL", "TAKE_PROFIT"
        if (
            request.capital_weight_rate is not None
            and request.max_capital_weight_rate is not None
            and request.capital_weight_rate > request.max_capital_weight_rate
        ):
            return "HOLD", "RISK"
    if score >= 75:
        return "BUY", "BUY_STRONG"
    if score >= 62:
        return "BUY", "BUY_WATCH"
    if score <= 35:
        return ("HOLD" if request.analysis_type == "WATCHLIST" else "SELL"), "RISK"
    return "HOLD", "HOLD"


def _summary(request: InvestmentAnalysisRequest, status: str, score: int) -> str:
    if request.analysis_type == "WATCHLIST":
        messages = {
            "BUY_STRONG": "가격·뉴스·공시 신호가 긍정적이지만 진입 전 위험을 별도로 확인하세요.",
            "BUY_WATCH": "긍정 신호가 있으나 진입 전 추가 확인이 필요합니다.",
            "RISK": "부정 신호가 우세해 신규 진입을 보류하는 편이 안전합니다.",
            "HOLD": "신호가 중립이므로 관심 종목으로 관찰하며 다음 변화를 확인하세요.",
        }
        return f"{request.stock_name} 관심 종목 점수는 {score}점입니다. {messages[status]}"
    if (
        status == "RISK"
        and request.capital_weight_rate is not None
        and request.max_capital_weight_rate is not None
        and request.capital_weight_rate > request.max_capital_weight_rate
    ):
        return (
            f"{request.stock_name} 종합 점수는 {score}점입니다. "
            "설정 자본금 대비 동일 종목 매입 원금이 권장 한도를 넘어 추가 매수 신호를 보류합니다."
        )
    messages = {
        "STOP_LOSS_WATCH": "손절 기준 접근 신호가 우선입니다. 추가 매수보다 손실 제한 계획을 확인하세요.",
        "TAKE_PROFIT": "익절 기준 접근 신호가 우선입니다. 일부 수익 실현과 잔여 물량 관리를 검토하세요.",
        "BUY_STRONG": "가격·뉴스·공시 흐름이 긍정적입니다. 기존 리스크 한도 안에서 진입을 검토하세요.",
        "BUY_WATCH": "긍정 신호가 우세하지만 추가 확인이 필요합니다. 분할 접근을 우선하세요.",
        "RISK": "부정 신호가 우세합니다. 신규 진입보다 위험 축소를 우선하세요.",
        "HOLD": "신호가 중립 구간입니다. 기존 손절·익절 계획을 유지하며 다음 변화를 관찰하세요.",
    }
    return f"{request.stock_name} 종합 점수는 {score}점입니다. {messages[status]}"
