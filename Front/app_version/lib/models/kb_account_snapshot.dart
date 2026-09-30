/// KB증권 계좌 조회 화면에 표시할 보유 주식/잔고 묶음입니다.
class KbAccountSnapshot {
  /// 보유 주식, 결제기준 잔고, 체결기준 잔고를 함께 받습니다.
  const KbAccountSnapshot({
    required this.holdings,
    required this.settlementBalance,
    required this.executionBalance,
  });

  /// SSQM1801 보유 주식 조회 결과입니다.
  final KbHoldingsSnapshot holdings;

  /// SSQM2932 결제기준 잔고 조회 결과입니다.
  final KbBalanceSnapshot settlementBalance;

  /// SSQM2952 체결기준 잔고 조회 결과입니다.
  final KbBalanceSnapshot executionBalance;
}

/// KB 보유 주식 조회 결과입니다.
class KbHoldingsSnapshot {
  /// 요약과 종목별 보유 주식을 받습니다.
  const KbHoldingsSnapshot({required this.summary, required this.items});

  /// 보유 주식 요약입니다.
  final KbPortfolioSummary summary;

  /// 종목별 보유 주식 목록입니다.
  final List<KbHoldingItem> items;

  /// API JSON을 화면 모델로 변환합니다.
  factory KbHoldingsSnapshot.fromJson(Map<String, dynamic> json) {
    final items = json['items'] as List<dynamic>? ?? const [];
    return KbHoldingsSnapshot(
      summary: KbPortfolioSummary.fromJson(
        json['summary'] as Map<String, dynamic>? ?? const {},
      ),
      items: items
          .map((item) => KbHoldingItem.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}

/// KB 보유 주식 요약입니다.
class KbPortfolioSummary {
  /// 금액과 수익률 요약을 받습니다.
  const KbPortfolioSummary({
    required this.totalPurchaseAmount,
    required this.totalValuationAmount,
    required this.totalProfitAmount,
    required this.profitRate,
  });

  final int totalPurchaseAmount;
  final int totalValuationAmount;
  final int totalProfitAmount;
  final double profitRate;

  /// API JSON을 화면 모델로 변환합니다.
  factory KbPortfolioSummary.fromJson(Map<String, dynamic> json) {
    return KbPortfolioSummary(
      totalPurchaseAmount: _readInt(json['totalPurchaseAmount']),
      totalValuationAmount: _readInt(json['totalValuationAmount']),
      totalProfitAmount: _readInt(json['totalProfitAmount']),
      profitRate: _readDouble(json['profitRate']),
    );
  }
}

/// KB 보유 주식 한 줄입니다.
class KbHoldingItem {
  /// 화면에 표시할 종목 정보와 수량/손익 값을 받습니다.
  const KbHoldingItem({
    required this.stockCode,
    required this.stockName,
    required this.market,
    required this.quantity,
    required this.currentPrice,
    required this.valuationAmount,
    required this.profitAmount,
    required this.profitRate,
    this.weightRate,
  });

  final String stockCode;
  final String stockName;
  final String market;
  final double quantity;
  final int currentPrice;
  final int valuationAmount;
  final int profitAmount;
  final double profitRate;
  final double? weightRate;

  /// API JSON을 화면 모델로 변환합니다.
  factory KbHoldingItem.fromJson(Map<String, dynamic> json) {
    return KbHoldingItem(
      stockCode: _readString(json['stockCode']),
      stockName: _readString(json['stockName']),
      market: _readString(json['market'], fallback: 'KR'),
      quantity: _readDouble(json['quantity']),
      currentPrice: _readInt(json['currentPrice']),
      valuationAmount: _readInt(json['valuationAmount']),
      profitAmount: _readInt(json['profitAmount']),
      profitRate: _readDouble(json['profitRate']),
      weightRate: json['weightRate'] == null
          ? null
          : _readDouble(json['weightRate']),
    );
  }
}

/// KB 잔고 현황 조회 결과입니다.
class KbBalanceSnapshot {
  /// 요약과 종목별 상세 잔고를 받습니다.
  const KbBalanceSnapshot({required this.summary, required this.items});

  /// 계좌 잔고 요약입니다.
  final KbBalanceSummary summary;

  /// 종목별 잔고 상세입니다.
  final List<KbBalanceItem> items;

  /// API JSON을 화면 모델로 변환합니다.
  factory KbBalanceSnapshot.fromJson(Map<String, dynamic> json) {
    final items = json['items'] as List<dynamic>? ?? const [];
    return KbBalanceSnapshot(
      summary: KbBalanceSummary.fromJson(
        json['summary'] as Map<String, dynamic>? ?? const {},
      ),
      items: items
          .map((item) => KbBalanceItem.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}

/// KB 잔고 요약입니다.
class KbBalanceSummary {
  /// 결제/체결 기준별 계좌 요약값을 받습니다.
  const KbBalanceSummary({
    required this.basis,
    required this.cashDeposit,
    required this.withdrawalAvailableAmount,
    required this.orderAvailableCash,
    required this.netAssetValuationAmount,
    required this.securitiesNetValuationAmount,
    required this.totalPurchaseAmount,
    required this.totalValuationAmount,
    required this.totalProfitAmount,
    required this.totalYieldRate,
  });

  final String basis;
  final int cashDeposit;
  final int withdrawalAvailableAmount;
  final int orderAvailableCash;
  final int netAssetValuationAmount;
  final int securitiesNetValuationAmount;
  final int totalPurchaseAmount;
  final int totalValuationAmount;
  final int totalProfitAmount;
  final double totalYieldRate;

  /// API JSON을 화면 모델로 변환합니다.
  factory KbBalanceSummary.fromJson(Map<String, dynamic> json) {
    return KbBalanceSummary(
      basis: _readString(json['basis']),
      cashDeposit: _readInt(json['cashDeposit']),
      withdrawalAvailableAmount: _readInt(json['withdrawalAvailableAmount']),
      orderAvailableCash: _readInt(json['orderAvailableCash']),
      netAssetValuationAmount: _readInt(json['netAssetValuationAmount']),
      securitiesNetValuationAmount: _readInt(
        json['securitiesNetValuationAmount'],
      ),
      totalPurchaseAmount: _readInt(json['totalPurchaseAmount']),
      totalValuationAmount: _readInt(json['totalValuationAmount']),
      totalProfitAmount: _readInt(json['totalProfitAmount']),
      totalYieldRate: _readDouble(json['totalYieldRate']),
    );
  }
}

/// KB 종목별 잔고 상세입니다.
class KbBalanceItem {
  /// 화면 리스트에 필요한 종목명, 수량, 평가 손익을 받습니다.
  const KbBalanceItem({
    required this.stockCode,
    required this.stockName,
    required this.quantity,
    required this.orderableQuantity,
    required this.currentPrice,
    required this.averageBuyPrice,
    required this.valuationAmount,
    required this.profitAmount,
    required this.profitRate,
    this.valuationWeightRate,
  });

  final String stockCode;
  final String stockName;
  final double quantity;
  final double orderableQuantity;
  final int currentPrice;
  final int averageBuyPrice;
  final int valuationAmount;
  final int profitAmount;
  final double profitRate;
  final double? valuationWeightRate;

  /// API JSON을 화면 모델로 변환합니다.
  factory KbBalanceItem.fromJson(Map<String, dynamic> json) {
    return KbBalanceItem(
      stockCode: _readString(json['stockCode']),
      stockName: _readString(json['stockName']),
      quantity: _readDouble(json['quantity']),
      orderableQuantity: _readDouble(json['orderableQuantity']),
      currentPrice: _readInt(json['currentPrice']),
      averageBuyPrice: _readInt(json['averageBuyPrice']),
      valuationAmount: _readInt(json['valuationAmount']),
      profitAmount: _readInt(json['profitAmount']),
      profitRate: _readDouble(json['profitRate']),
      valuationWeightRate: json['valuationWeightRate'] == null
          ? null
          : _readDouble(json['valuationWeightRate']),
    );
  }
}

String _readString(Object? value, {String fallback = ''}) {
  final text = value?.toString().trim() ?? '';
  return text.isEmpty ? fallback : text;
}

int _readInt(Object? value) {
  return switch (value) {
    null => 0,
    int number => number,
    double number => number.round(),
    String text when text.trim().isEmpty => 0,
    String text => double.parse(text.replaceAll(',', '')).round(),
    _ => throw FormatException('정수로 변환할 수 없는 값입니다: $value'),
  };
}

double _readDouble(Object? value) {
  return switch (value) {
    null => 0,
    int number => number.toDouble(),
    double number => number,
    String text when text.trim().isEmpty => 0,
    String text => double.parse(text.replaceAll(',', '')),
    _ => throw FormatException('실수로 변환할 수 없는 값입니다: $value'),
  };
}
