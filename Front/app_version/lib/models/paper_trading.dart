/// 모의매매 탭의 성과, 포지션, 거래 이력을 묶은 모델입니다.
class PaperTradingSnapshot {
  const PaperTradingSnapshot({
    required this.summary,
    required this.positions,
    required this.trades,
  });

  final PaperTradingSummary summary;
  final List<PaperPosition> positions;
  final List<PaperTrade> trades;

  factory PaperTradingSnapshot.fromJson(Map<String, dynamic> json) {
    return PaperTradingSnapshot(
      summary: PaperTradingSummary.fromJson(
        json['summary'] as Map<String, dynamic>,
      ),
      positions: (json['positions'] as List<dynamic>? ?? const [])
          .map((item) => PaperPosition.fromJson(item as Map<String, dynamic>))
          .toList(),
      trades: (json['trades'] as List<dynamic>? ?? const [])
          .map((item) => PaperTrade.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}

class PaperTradingSummary {
  const PaperTradingSummary({
    required this.initialCapital,
    required this.cashBalance,
    required this.openPositionValue,
    required this.totalAsset,
    required this.realizedProfit,
    required this.unrealizedProfit,
    required this.totalProfit,
    required this.returnRate,
    required this.completedTrades,
    required this.winRate,
    required this.maxLoss,
    required this.turnoverRate,
  });

  final double initialCapital;
  final double cashBalance;
  final double openPositionValue;
  final double totalAsset;
  final double realizedProfit;
  final double unrealizedProfit;
  final double totalProfit;
  final double returnRate;
  final int completedTrades;
  final double winRate;
  final double maxLoss;
  final double turnoverRate;

  factory PaperTradingSummary.fromJson(Map<String, dynamic> json) {
    return PaperTradingSummary(
      initialCapital: _readDouble(json['initialCapital']),
      cashBalance: _readDouble(json['cashBalance']),
      openPositionValue: _readDouble(json['openPositionValue']),
      totalAsset: _readDouble(json['totalAsset']),
      realizedProfit: _readDouble(json['realizedProfit']),
      unrealizedProfit: _readDouble(json['unrealizedProfit']),
      totalProfit: _readDouble(json['totalProfit']),
      returnRate: _readDouble(json['returnRate']),
      completedTrades: _readInt(json['completedTrades']),
      winRate: _readDouble(json['winRate']),
      maxLoss: _readDouble(json['maxLoss']),
      turnoverRate: _readDouble(json['turnoverRate']),
    );
  }
}

class PaperPosition {
  const PaperPosition({
    required this.stockCode,
    required this.stockName,
    required this.market,
    required this.provider,
    required this.quantity,
    required this.averagePrice,
    required this.currentPrice,
    required this.valuationAmount,
    required this.unrealizedProfit,
    required this.profitRate,
  });

  final String stockCode;
  final String stockName;
  final String market;
  final String provider;
  final double quantity;
  final double averagePrice;
  final double currentPrice;
  final double valuationAmount;
  final double unrealizedProfit;
  final double profitRate;

  factory PaperPosition.fromJson(Map<String, dynamic> json) {
    return PaperPosition(
      stockCode: json['stockCode'] as String,
      stockName: json['stockName'] as String,
      market: json['market'] as String,
      provider: json['provider'] as String,
      quantity: _readDouble(json['quantity']),
      averagePrice: _readDouble(json['averagePrice']),
      currentPrice: _readDouble(json['currentPrice']),
      valuationAmount: _readDouble(json['valuationAmount']),
      unrealizedProfit: _readDouble(json['unrealizedProfit']),
      profitRate: _readDouble(json['profitRate']),
    );
  }
}

class PaperTrade {
  const PaperTrade({
    required this.tradeRecordId,
    required this.recommendationId,
    required this.stockCode,
    required this.stockName,
    required this.market,
    required this.tradeType,
    required this.tradePrice,
    required this.quantity,
    required this.tradeAmount,
    required this.realizedProfit,
    required this.tradeDate,
    required this.memo,
  });

  final int tradeRecordId;
  final int? recommendationId;
  final String stockCode;
  final String stockName;
  final String market;
  final String tradeType;
  final double tradePrice;
  final double quantity;
  final double tradeAmount;
  final double realizedProfit;
  final DateTime tradeDate;
  final String? memo;

  factory PaperTrade.fromJson(Map<String, dynamic> json) {
    return PaperTrade(
      tradeRecordId: _readInt(json['tradeRecordId']),
      recommendationId: json['recommendationId'] == null
          ? null
          : _readInt(json['recommendationId']),
      stockCode: json['stockCode'] as String,
      stockName: json['stockName'] as String,
      market: json['market'] as String,
      tradeType: json['tradeType'] as String,
      tradePrice: _readDouble(json['tradePrice']),
      quantity: _readDouble(json['quantity']),
      tradeAmount: _readDouble(json['tradeAmount']),
      realizedProfit: _readDouble(json['realizedProfit']),
      tradeDate: DateTime.parse(json['tradeDate'] as String),
      memo: json['memo'] as String?,
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
