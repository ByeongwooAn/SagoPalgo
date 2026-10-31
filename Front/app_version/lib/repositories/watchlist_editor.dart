abstract interface class WatchlistEditor {
  Future<void> addStock({
    required String stockCode,
    required String stockName,
    required String market,
    required bool alertEnabled,
  });
}
