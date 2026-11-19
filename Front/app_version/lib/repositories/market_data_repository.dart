import '../models/market_candle.dart';
import '../models/recommendation.dart';

/// 종목별 기간 시세를 화면에 제공하는 Repository 경계입니다.
abstract class MarketDataRepository {
  Future<MarketCandleSnapshot> fetchCandles({
    required String stockCode,
    required String market,
    required MarketCandleInterval interval,
    int count = 60,
  });
}

abstract interface class UsStockLookup {
  Future<({String provider, double price})> fetchUsQuote(
    String ticker,
    String market,
  );
  Future<String> fetchUsStockName(String ticker, String market);
}

abstract interface class UsDailySignalAccess {
  Future<DailyModelSignal> fetchUsDailySignal(String ticker, String market);
}

class MarketDataRepositoryException implements Exception {
  const MarketDataRepositoryException(this.message);

  final String message;

  @override
  String toString() => message;
}
