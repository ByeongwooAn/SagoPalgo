/// 홈 대시보드가 보여줘야 하는 시장과 사용자 자본 요약 데이터입니다.
///
/// 지금은 Mock 데이터로 채우지만, 나중에 Spring Boot API의
/// `/capital`, `/market-summary` 같은 응답을 그대로 매핑할 수 있도록
/// 화면 표시값과 계산값을 하나의 모델로 묶어 둡니다.
class MarketSummary {
  /// 모든 필드를 필수로 받게 해서 화면이 비어 보이는 상황을 미리 막습니다.
  const MarketSummary({
    required this.availableCapital,
    required this.monthlyReturnRate,
    required this.recommendedPositionRange,
    required this.marketTrend,
    required this.marketScore,
    required this.newsSentiment,
    required this.positiveNewsCount,
    required this.marketBars,
  });

  /// 사용자가 설정한 투자 가능 자본금입니다.
  final int availableCapital;

  /// 이번 달 전체 포트폴리오 수익률입니다.
  final double monthlyReturnRate;

  /// 기획서의 리스크 관리 기준인 종목당 권장 투자금 범위입니다.
  final String recommendedPositionRange;

  /// 코스피/나스닥/업종 흐름을 요약한 표시 텍스트입니다.
  final String marketTrend;

  /// 시장 강세 조건을 추천 점수에 반영하기 위한 0~100 점수입니다.
  final int marketScore;

  /// 뉴스 감성 분석 결과를 사람이 읽기 쉬운 단어로 표현한 값입니다.
  final String newsSentiment;

  /// 긍정 뉴스 개수는 뉴스 감성 근거를 짧게 보여줄 때 사용합니다.
  final int positiveNewsCount;

  /// 대시보드 막대 그래프에 사용할 0~1 사이의 시장 지표 값들입니다.
  final List<double> marketBars;
}
