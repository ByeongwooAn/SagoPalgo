/// 사용자가 보유한 종목 한 줄을 표현하는 모델입니다.
///
/// 매도 추천은 보유 종목의 매수가, 수량, 손절/익절 기준에서 시작되므로
/// 이 모델은 단순 표시용이 아니라 이후 매도 추천 로직의 입력값이 됩니다.
class Holding {
  /// 보유 종목 화면의 리스트 한 행에 필요한 값을 모두 받습니다.
  const Holding({
    required this.stockName,
    required this.stockCode,
    required this.buyPrice,
    required this.quantity,
    required this.profitRate,
    required this.status,
  });

  /// 앱에 표시할 종목명입니다.
  final String stockName;

  /// API와 DB에서 사용할 종목 코드입니다.
  final String stockCode;

  /// 사용자가 기록한 평균 매수가입니다.
  final int buyPrice;

  /// 현재 보유 수량입니다.
  final int quantity;

  /// 현재가 기준 수익률입니다.
  final double profitRate;

  /// 보유, 부분 익절, 손절 감시 같은 운영 상태입니다.
  final String status;

  /// 백엔드 보유 종목 JSON을 앱 모델로 변환합니다.
  factory Holding.fromJson(Map<String, dynamic> json) {
    return Holding(
      stockName: json['stockName'] as String,
      stockCode: json['stockCode'] as String,
      buyPrice: _readInt(json['buyPrice']),
      quantity: _readInt(json['quantity']),
      profitRate: _readDouble(json['profitRate']),
      status: json['statusLabel'] as String? ?? json['status'] as String,
    );
  }
}

/// 보유 종목 화면 상단의 전체 손익 요약입니다.
class PortfolioSummary {
  /// 포트폴리오 전체 지표를 한 번에 주입합니다.
  const PortfolioSummary({
    required this.totalProfit,
    required this.profitRate,
    required this.maxAllowedLoss,
    required this.riskUsageRate,
  });

  /// 평가 손익 금액입니다.
  final int totalProfit;

  /// 전체 평가 수익률입니다.
  final double profitRate;

  /// 기획서의 1회 거래 손실 제한 기준을 금액으로 환산한 값입니다.
  final int maxAllowedLoss;

  /// 오늘 사용한 위험 한도 비율이며 0~1 사이 값으로 관리합니다.
  final double riskUsageRate;

  /// 백엔드 포트폴리오 요약 JSON을 앱 모델로 변환합니다.
  factory PortfolioSummary.fromJson(Map<String, dynamic> json) {
    return PortfolioSummary(
      totalProfit: _readInt(json['totalProfit']),
      profitRate: _readDouble(json['profitRate']),
      maxAllowedLoss: _readInt(json['maxAllowedLoss']),
      riskUsageRate: _readDouble(json['riskUsageRate']),
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
