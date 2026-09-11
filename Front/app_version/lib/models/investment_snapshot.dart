import 'app_alert.dart';
import 'holding.dart';
import 'market_summary.dart';
import 'recommendation.dart';

/// 앱 첫 화면을 구성하는 데 필요한 모든 투자 데이터를 한 번에 묶은 모델입니다.
///
/// 지금은 Mock Repository가 이 스냅샷을 반환하지만, 나중에는 Spring Boot가
/// 여러 API를 제공하더라도 앱 계층에서는 이 모양으로 조합해서 쓰면 됩니다.
class InvestmentSnapshot {
  /// 화면별 데이터 묶음을 명시적으로 받습니다.
  const InvestmentSnapshot({
    required this.marketSummary,
    required this.recommendation,
    required this.portfolioSummary,
    required this.holdings,
    required this.alerts,
  });

  /// 홈 대시보드에 표시되는 시장/자본 요약입니다.
  final MarketSummary marketSummary;

  /// 추천 탭과 홈의 실시간 후보 카드에 표시되는 대표 추천입니다.
  final InvestmentRecommendation recommendation;

  /// 보유 탭 상단에 표시되는 전체 손익 요약입니다.
  final PortfolioSummary portfolioSummary;

  /// 보유 종목 리스트입니다.
  final List<Holding> holdings;

  /// 알림 탭에 표시되는 최근 추천/시장 알림 목록입니다.
  final List<AppAlert> alerts;

  /// 백엔드 `/api/v1/dashboard/snapshot`의 `data` JSON을 앱 모델로 변환합니다.
  factory InvestmentSnapshot.fromJson(Map<String, dynamic> json) {
    return InvestmentSnapshot(
      marketSummary: MarketSummary.fromJson(
        json['marketSummary'] as Map<String, dynamic>,
      ),
      recommendation: InvestmentRecommendation.fromJson(
        json['recommendation'] as Map<String, dynamic>,
      ),
      portfolioSummary: PortfolioSummary.fromJson(
        json['portfolioSummary'] as Map<String, dynamic>,
      ),
      holdings: (json['holdings'] as List<dynamic>)
          .map((holding) => Holding.fromJson(holding as Map<String, dynamic>))
          .toList(),
      alerts: (json['alerts'] as List<dynamic>)
          .map((alert) => AppAlert.fromJson(alert as Map<String, dynamic>))
          .toList(),
    );
  }
}
