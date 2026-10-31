class StockIdentity {
  const StockIdentity({
    required this.stockCode,
    required this.stockName,
    required this.market,
    required this.provider,
  });
  final String stockCode;
  final String stockName;
  final String market;
  final String provider;

  factory StockIdentity.fromJson(Map<String, dynamic> json) {
    final code = json['stockCode'] as String? ?? '';
    final name = (json['stockName'] as String? ?? '').trim();
    final market = json['market'] as String? ?? '';
    if (!RegExp(r'^\d{6}$').hasMatch(code) ||
        name.isEmpty ||
        name.length > 100 ||
        !['KOSPI', 'KOSDAQ', 'KONEX'].contains(market)) {
      throw const FormatException('조회한 종목명·코드·시장을 확인할 수 없습니다.');
    }
    return StockIdentity(
      stockCode: code,
      stockName: name,
      market: market,
      provider: json['provider'] as String? ?? '',
    );
  }
}
