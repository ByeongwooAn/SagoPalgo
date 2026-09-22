/// 백엔드 기간별 시세 API가 지원하는 캔들 주기입니다.
enum MarketCandleInterval {
  daily(apiValue: 'DAILY', label: '일'),
  weekly(apiValue: 'WEEKLY', label: '주'),
  monthly(apiValue: 'MONTHLY', label: '월');

  const MarketCandleInterval({required this.apiValue, required this.label});

  /// API 쿼리에 전달하는 대문자 주기 코드입니다.
  final String apiValue;

  /// 화면의 주기 선택기에 표시하는 짧은 라벨입니다.
  final String label;

  static MarketCandleInterval fromApiValue(String value) {
    return MarketCandleInterval.values.firstWhere(
      (interval) => interval.apiValue == value.toUpperCase(),
      orElse: () => MarketCandleInterval.daily,
    );
  }
}

/// 단일 시점의 시가·고가·저가·종가·거래량입니다.
class MarketCandle {
  const MarketCandle({
    required this.provider,
    required this.stockCode,
    required this.market,
    required this.dateTime,
    required this.interval,
    required this.openPrice,
    required this.highPrice,
    required this.lowPrice,
    required this.closePrice,
    required this.volume,
  });

  final String provider;
  final String stockCode;
  final String market;
  final DateTime dateTime;
  final MarketCandleInterval interval;
  final double openPrice;
  final double highPrice;
  final double lowPrice;
  final double closePrice;
  final double volume;

  bool get isRising => closePrice >= openPrice;

  factory MarketCandle.fromJson(Map<String, dynamic> json) {
    return MarketCandle(
      provider: json['provider'] as String? ?? '',
      stockCode: json['stockCode'] as String? ?? '',
      market: json['market'] as String? ?? '',
      dateTime: DateTime.parse(json['dateTime'] as String),
      interval: MarketCandleInterval.fromApiValue(
        json['interval'] as String? ?? 'DAILY',
      ),
      openPrice: _readDouble(json['openPrice']),
      highPrice: _readDouble(json['highPrice']),
      lowPrice: _readDouble(json['lowPrice']),
      closePrice: _readDouble(json['closePrice']),
      volume: _readDouble(json['volume']),
    );
  }
}

/// 캔들 목록과 실제 응답 Provider 정보를 묶은 조회 결과입니다.
class MarketCandleSnapshot {
  const MarketCandleSnapshot({
    required this.provider,
    required this.stockCode,
    required this.market,
    required this.interval,
    required this.candles,
  });

  final String provider;
  final String stockCode;
  final String market;
  final MarketCandleInterval interval;
  final List<MarketCandle> candles;

  factory MarketCandleSnapshot.fromJson(Map<String, dynamic> json) {
    final items = json['candles'];
    if (items is! List<dynamic>) {
      throw const FormatException('캔들 목록 형식이 올바르지 않습니다.');
    }
    return MarketCandleSnapshot(
      provider: json['provider'] as String? ?? '',
      stockCode: json['stockCode'] as String? ?? '',
      market: json['market'] as String? ?? '',
      interval: MarketCandleInterval.fromApiValue(
        json['interval'] as String? ?? 'DAILY',
      ),
      candles: items
          .map((item) => MarketCandle.fromJson(item as Map<String, dynamic>))
          .toList(growable: false),
    );
  }
}

double _readDouble(Object? value) {
  return switch (value) {
    int number => number.toDouble(),
    double number => number,
    String text => double.parse(text),
    _ => throw FormatException('숫자로 변환할 수 없는 값입니다: $value'),
  };
}
