/// 관심 종목 API가 내려주는 단일 관심 종목 모델입니다.
class WatchlistItem {
  /// API 응답 필드를 앱에서 쓰기 쉬운 형태로 받습니다.
  const WatchlistItem({
    required this.watchlistId,
    required this.stockCode,
    required this.stockName,
    required this.market,
    required this.alertEnabled,
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

  /// 백엔드 관심 종목 JSON을 앱 모델로 변환합니다.
  factory WatchlistItem.fromJson(Map<String, dynamic> json) {
    return WatchlistItem(
      watchlistId: _readInt(json['watchlistId']),
      stockCode: json['stockCode'] as String,
      stockName: json['stockName'] as String,
      market: json['market'] as String,
      alertEnabled: json['alertEnabled'] as bool? ?? false,
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
