import '../models/paper_trading.dart';

/// 실제 주문과 분리된 모의매매 조회·체결 경계입니다.
abstract class PaperTradingRepository {
  Future<PaperTradingSnapshot> fetchSnapshot();

  Future<PaperTradingSnapshot> buyFromRecommendation(
    int recommendationId,
    double quantity,
  );

  Future<PaperTradingSnapshot> sellPosition({
    required String stockCode,
    required String market,
    required double quantity,
  });
}

class PaperTradingRepositoryException implements Exception {
  const PaperTradingRepositoryException(this.message);

  final String message;

  @override
  String toString() => message;
}
