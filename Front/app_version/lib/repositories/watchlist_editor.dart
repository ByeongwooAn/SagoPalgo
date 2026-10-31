import '../models/stock_identity.dart';

abstract interface class WatchlistEditor {
  Future<StockIdentity> lookupStock(String stockCode);
  Future<void> deleteStock(int watchlistId);

  Future<void> addStock({
    required String stockCode,
    required String stockName,
    required String market,
    required bool alertEnabled,
  });
}
