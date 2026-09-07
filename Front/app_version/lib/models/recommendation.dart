/// 추천 상세 화면에서 보여줄 매수/매도 추천 데이터입니다.
///
/// 추천 자체와 추천 이유를 분리해 두면, 이후 API에서
/// `recommendation`과 `recommendation_reasons` 테이블을 따로 내려줘도
/// 화면 코드를 크게 바꾸지 않고 연결할 수 있습니다.
class InvestmentRecommendation {
  /// 추천 카드에 필요한 핵심 정보와 설명을 모두 받습니다.
  const InvestmentRecommendation({
    required this.stockName,
    required this.stockCode,
    required this.status,
    required this.score,
    required this.entryPrice,
    required this.stopLossRate,
    required this.aiSummary,
    required this.reasons,
  });

  /// 사용자가 보는 종목명입니다.
  final String stockName;

  /// 실제 API 호출과 DB 저장에 사용할 종목 코드입니다.
  final String stockCode;

  /// 80점 이상일 때의 "강한 매수" 같은 추천 상태입니다.
  final String status;

  /// 기획서의 점수 시스템에 따른 0~100 추천 점수입니다.
  final int score;

  /// 사용자가 진입을 검토할 기준 가격입니다.
  final int entryPrice;

  /// 리스크 관리를 위해 추천 상세에서 항상 노출할 손절 기준입니다.
  final double stopLossRate;

  /// AI가 추천 이유를 자연어로 요약한 문장입니다.
  final String aiSummary;

  /// RSI, MACD, 뉴스처럼 점수를 만든 세부 근거 목록입니다.
  final List<RecommendationReason> reasons;
}

/// 추천 점수에 영향을 준 단일 근거입니다.
class RecommendationReason {
  /// 라벨과 설명을 분리해 두어 UI에서 라벨은 강조색으로, 설명은 본문으로 그립니다.
  const RecommendationReason({
    required this.label,
    required this.description,
    required this.type,
  });

  /// 예: RSI, MACD, 뉴스.
  final String label;

  /// 사용자가 이해할 수 있는 추천 근거 설명입니다.
  final String description;

  /// 화면에서 어떤 색상으로 강조할지 결정하는 분류값입니다.
  final RecommendationReasonType type;
}

/// 추천 근거별 강조색을 안정적으로 고르기 위한 타입입니다.
enum RecommendationReasonType {
  /// 메인 컬러를 쓰는 기술 지표 근거입니다.
  technical,

  /// 서브 컬러를 쓰는 추세 또는 위험 관련 근거입니다.
  trend,

  /// 포인트 컬러를 쓰는 뉴스/호재 근거입니다.
  news,
}
