/// 관심 종목 API가 내려주는 단일 관심 종목 모델입니다.
class WatchlistItem {
  /// API 응답 필드를 앱에서 쓰기 쉬운 형태로 받습니다.
  const WatchlistItem({
    required this.watchlistId,
    required this.stockCode,
    required this.stockName,
    required this.market,
    required this.alertEnabled,
    required this.provider,
    required this.currentPrice,
    required this.changeRate,
  });

  /// 관심 종목 PK입니다.
  final int watchlistId;

  /// 종목 코드입니다.
  final String stockCode;

  /// 종목명입니다.
  final String stockName;

  /// 시장 코드입니다.
  final String market;

  /// 추천/가격 알림 수신 여부입니다.
  final bool alertEnabled;

  /// 현재가를 제공한 시세 Provider 코드입니다.
  final String provider;

  /// 외부 시세 Provider가 반환한 현재가입니다.
  final int currentPrice;

  /// 전일 종가 대비 등락률입니다.
  final double changeRate;

  /// 백엔드 관심 종목 JSON을 앱 모델로 변환합니다.
  factory WatchlistItem.fromJson(Map<String, dynamic> json) {
    return WatchlistItem(
      watchlistId: _readInt(json['watchlistId']),
      stockCode: json['stockCode'] as String,
      stockName: json['stockName'] as String,
      market: json['market'] as String,
      alertEnabled: json['alertEnabled'] as bool? ?? false,
      provider: json['provider'] as String? ?? 'FALLBACK',
      currentPrice: _readInt(json['currentPrice'] ?? 0),
      changeRate: _readDouble(json['changeRate'] ?? 0),
    );
  }
}

int _readInt(Object? value) {
  return switch (value) {
    int number => number,
    double number => number.round(),
    String text => double.parse(text).round(),
    _ => throw FormatException('정수로 변환할 수 없는 값입니다: $value'),
  };
}

double _readDouble(Object? value) {
  return switch (value) {
    int number => number.toDouble(),
    double number => number,
    String text => double.parse(text),
    _ => throw FormatException('실수로 변환할 수 없는 값입니다: $value'),
  };
}
