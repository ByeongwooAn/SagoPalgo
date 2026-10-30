/// 사용자가 보유한 종목 한 줄을 표현하는 모델입니다.
///
/// 매도 추천은 보유 종목의 매수가, 수량, 손절/익절 기준에서 시작되므로
/// 이 모델은 단순 표시용이 아니라 이후 매도 추천 로직의 입력값이 됩니다.
class Holding {
  /// 보유 종목 화면의 리스트 한 행에 필요한 값을 모두 받습니다.
  const Holding({
    required this.holdingId,
    required this.stockName,
    required this.stockCode,
    required this.market,
    required this.buyPrice,
    required this.quantity,
    required this.buyDate,
    required this.currentPrice,
    required this.profitRate,
    required this.stopLossRate,
    required this.takeProfitRate,
    required this.status,
    this.priceProvider,
    this.priceReceivedAt,
    this.priceFallback = false,
    this.source = 'MANUAL',
    this.sourceSyncedAt,
    this.buyPriceExact,
    this.currentPriceExact,
  });

  /// 보유 종목 수정/삭제 API에서 사용할 PK입니다.
  final int holdingId;

  /// 앱에 표시할 종목명입니다.
  final String stockName;

  /// API와 DB에서 사용할 종목 코드입니다.
  final String stockCode;

  /// KOSPI, KOSDAQ, NASDAQ 같은 시장 코드입니다.
  final String market;

  /// 사용자가 기록한 평균 매수가입니다.
  final int buyPrice;

  /// 현재 보유 수량입니다.
  final double quantity;

  /// 사용자가 기록한 매수일입니다.
  final DateTime? buyDate;

  /// 현재가입니다. 서버의 실제 시세 API 설정에 따라 외부 현재가 또는 매수가 기준값을 내려줍니다.
  final int currentPrice;

  /// 현재가 기준 수익률입니다.
  final double profitRate;

  /// 사용자가 정한 손절 기준 수익률입니다.
  final double stopLossRate;

  /// 사용자가 정한 익절 기준 수익률입니다.
  final double takeProfitRate;

  /// 보유, 부분 익절, 손절 감시 같은 운영 상태입니다.
  final String status;
  final String? priceProvider;
  final DateTime? priceReceivedAt;
  final bool priceFallback;
  final String source;
  final DateTime? sourceSyncedAt;
  final double? buyPriceExact;
  final double? currentPriceExact;

  bool get isKbImport => source == 'KB';

  /// 백엔드 보유 종목 JSON을 앱 모델로 변환합니다.
  factory Holding.fromJson(Map<String, dynamic> json) {
    return Holding(
      holdingId: _readInt(json['holdingId']),
      stockName: json['stockName'] as String,
      stockCode: json['stockCode'] as String,
      market: json['market'] as String? ?? 'KOSPI',
      buyPrice: _readInt(json['buyPrice']),
      quantity: _readDouble(json['quantity']),
      buyDate: json['buyDate'] == null
          ? null
          : DateTime.parse(json['buyDate'] as String),
      currentPrice: _readInt(json['currentPrice']),
      profitRate: _readDouble(json['profitRate']),
      stopLossRate: _readDouble(json['stopLossRate']),
      takeProfitRate: _readDouble(json['takeProfitRate']),
      status: json['statusLabel'] as String? ?? json['status'] as String,
      priceProvider: json['priceProvider'] as String?,
      priceReceivedAt: json['priceReceivedAt'] == null
          ? null
          : DateTime.parse(json['priceReceivedAt'] as String),
      priceFallback: json['priceFallback'] as bool? ?? false,
      source: json['source'] as String? ?? 'MANUAL',
      sourceSyncedAt: _readUtcTimestamp(json['sourceSyncedAt']),
      buyPriceExact: _readDouble(json['buyPrice']),
      currentPriceExact: _readDouble(json['currentPrice']),
    );
  }
}

/// 보유 종목 등록/수정 API 요청값입니다.
class HoldingInput {
  /// 사용자가 입력한 보유 종목 정보를 받습니다.
  const HoldingInput({
    required this.stockCode,
    required this.stockName,
    required this.market,
    required this.buyPrice,
    required this.quantity,
    required this.buyDate,
    required this.stopLossRate,
    required this.takeProfitRate,
  });

  final String stockCode;
  final String stockName;
  final String market;
  final int buyPrice;
  final double quantity;
  final DateTime buyDate;
  final double stopLossRate;
  final double takeProfitRate;

  /// 기존 보유 종목을 수정 폼의 초기값으로 변환합니다.
  factory HoldingInput.fromHolding(Holding holding) {
    return HoldingInput(
      stockCode: holding.stockCode,
      stockName: holding.stockName,
      market: holding.market,
      buyPrice: holding.buyPrice,
      quantity: holding.quantity,
      buyDate:
          holding.buyDate ?? (throw StateError('KB 조회는 실제 매수일을 제공하지 않습니다.')),
      stopLossRate: holding.stopLossRate,
      takeProfitRate: holding.takeProfitRate,
    );
  }

  /// Spring Boot 보유 종목 등록/수정 요청 JSON으로 변환합니다.
  Map<String, dynamic> toJson() {
    return {
      'stockCode': stockCode,
      'stockName': stockName,
      'market': market,
      'buyPrice': buyPrice,
      'quantity': quantity,
      'buyDate': _formatDate(buyDate),
      'stopLossRate': stopLossRate,
      'takeProfitRate': takeProfitRate,
    };
  }
}

/// 포트폴리오 화면에서 자본금과 보유 종목을 함께 다루기 위한 데이터 묶음입니다.
class PortfolioSnapshot {
  /// API에서 따로 내려오는 자본금 설정, 손익 요약, 보유 종목 목록을 함께 받습니다.
  const PortfolioSnapshot({
    required this.capital,
    required this.summary,
    required this.holdings,
  });

  /// 투자 가능 자본금과 종목당 권장 투자금 설정입니다.
  final CapitalSettings capital;

  /// 보유 종목 전체 손익 요약입니다.
  final PortfolioSummary summary;

  /// 사용자가 현재 보유한 종목 목록입니다.
  final List<Holding> holdings;
}

/// 사용자 자본금과 리스크 설정입니다.
class CapitalSettings {
  /// 포트폴리오 화면에서 표시할 자본금/리스크 기준을 받습니다.
  const CapitalSettings({
    required this.availableCapital,
    required this.recommendedMinPosition,
    required this.recommendedMaxPosition,
    required this.riskPerTradeRate,
  });

  /// 사용자가 투자 가능하다고 설정한 총 자본금입니다.
  final int availableCapital;

  /// 종목당 최소 권장 투자금입니다.
  final int recommendedMinPosition;

  /// 종목당 최대 권장 투자금입니다.
  final int recommendedMaxPosition;

  /// 1회 거래에서 허용할 손실 비율입니다. 예: 0.02는 2%입니다.
  final double riskPerTradeRate;

  /// 백엔드 자본금 JSON을 앱 모델로 변환합니다.
  factory CapitalSettings.fromJson(Map<String, dynamic> json) {
    return CapitalSettings(
      availableCapital: _readInt(json['availableCapital']),
      recommendedMinPosition: _readInt(json['recommendedMinPosition']),
      recommendedMaxPosition: _readInt(json['recommendedMaxPosition']),
      riskPerTradeRate: _readDouble(json['riskPerTradeRate']),
    );
  }
}

/// 자본금 수정 API 요청값입니다.
class CapitalInput {
  /// 투자 가능 자본금과 1회 거래 리스크 비율을 받습니다.
  const CapitalInput({
    required this.availableCapital,
    required this.riskPerTradeRate,
  });

  final int availableCapital;
  final double riskPerTradeRate;

  /// 기존 자본금 설정을 수정 폼의 초기값으로 변환합니다.
  factory CapitalInput.fromSettings(CapitalSettings capital) {
    return CapitalInput(
      availableCapital: capital.availableCapital,
      riskPerTradeRate: capital.riskPerTradeRate,
    );
  }

  /// Spring Boot 자본금 수정 요청 JSON으로 변환합니다.
  Map<String, dynamic> toJson() {
    return {
      'availableCapital': availableCapital,
      'riskPerTradeRate': riskPerTradeRate,
    };
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

  /// 현재 미실현 손실이 최대 허용 손실에서 차지하는 비율입니다.
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

String _formatDate(DateTime value) {
  final year = value.year.toString().padLeft(4, '0');
  final month = value.month.toString().padLeft(2, '0');
  final day = value.day.toString().padLeft(2, '0');
  return '$year-$month-$day';
}

DateTime? _readUtcTimestamp(Object? value) {
  if (value == null) return null;
  final text = value as String;
  return DateTime.parse(
    RegExp(r'(Z|[+-]\d\d:\d\d)$').hasMatch(text) ? text : '${text}Z',
  );
}
