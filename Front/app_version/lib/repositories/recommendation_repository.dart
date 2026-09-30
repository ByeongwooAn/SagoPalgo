import '../models/recommendation.dart';

/// 저장 추천 이력 조회와 보유 종목 재분석을 제공하는 경계입니다.
abstract class RecommendationRepository {
  Future<RecommendationPage> fetchHistory({
    String? status,
    int page = 0,
    int size = 20,
  });

  Future<InvestmentRecommendation> fetchDetail(int recommendationId);

  Future<InvestmentRecommendation> analyzeHolding(int holdingId);

  Future<InvestmentRecommendation> analyzeWatchlist(int watchlistId);
}

class RecommendationRepositoryException implements Exception {
  const RecommendationRepositoryException(this.message);

  final String message;

  @override
  String toString() => message;
}
