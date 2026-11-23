import '../models/paper_trading.dart';

/// 실제 주문과 분리된 모의매매 조회·체결 경계입니다.
abstract class PaperTradingRepository {
  Future<PaperTradingSnapshot> fetchSnapshot();

  Future<PaperTradingSnapshot> buyFromRecommendation(
    int recommendationId,
    double quantity, {
    required String requestId,
  });

  Future<PaperTradingSnapshot> sellPosition({
    required String stockCode,
    required String market,
    required double quantity,
    required String requestId,
  });
}

typedef UsPaperOrder = ({
  String stockCode,
  String market,
  String side,
  String quantity,
  String requestId,
});

abstract interface class UsPaperTradingRepository {
  Future<PaperTradingSnapshot> fetchUsSnapshot();
  Future<PaperTradingSnapshot> openUsAccount(String initialCapital);
  Future<PaperTradingSnapshot> tradeUs(UsPaperOrder order);
}

class PaperTradingRepositoryException implements Exception {
  const PaperTradingRepositoryException(this.message, {this.code});

  final String message;
  final String? code;

  @override
  String toString() => message;
}
