/// 모의매매 탭의 성과, 포지션, 거래 이력을 묶은 모델입니다.
class PaperTradingSnapshot {
  const PaperTradingSnapshot({
    required this.summary,
    required this.positions,
    required this.trades,
    this.currency = 'KRW',
  });

  final PaperTradingSummary summary;
  final List<PaperPosition> positions;
  final List<PaperTrade> trades;
  final String currency;

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
      currency: json['currency'] as String? ?? 'KRW',
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
    this.quoteProvider,
    this.quoteMarketAt,
    this.signalBasisDate,
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
  final String? quoteProvider;
  final DateTime? quoteMarketAt;
  final String? signalBasisDate;

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
      quoteProvider: json['quoteProvider'] as String?,
      quoteMarketAt: DateTime.tryParse(json['quoteMarketAt'] as String? ?? ''),
      signalBasisDate: json['signalBasisDate'] as String?,
    );
  }
}

class AutomatedPaperSnapshot {
  AutomatedPaperSnapshot.fromJson(
    Map<String, dynamic> json, {
    required this.online,
  }) : stockCode = json['stockCode'] as String,
       stockName = json['stockName'] as String,
       status = json['status'] as String,
       publishedAt = DateTime.parse(json['publishedAt'] as String),
       lastMarketAt = DateTime.tryParse(json['lastMarketAt'] as String? ?? ''),
       endDate = json['endDate'] as String,
       entry = AutomatedPaperEntry.fromJson(
         json['entry'] as Map<String, dynamic>,
       ),
       portfolio = AutomatedPaperPortfolio.fromJson(
         json['portfolio'] as Map<String, dynamic>,
       ),
       fillCount = _readInt(json['fillCount']),
       fills = (json['fills'] as List)
           .cast<Map<String, dynamic>>()
           .map(AutomatedPaperFill.fromJson)
           .toList(),
       closedDays = (json['closedDays'] as List)
           .cast<Map<String, dynamic>>()
           .map(AutomatedPaperDay.fromJson)
           .toList();

  final String stockCode;
  final String stockName;
  final String status;
  final DateTime publishedAt;
  final DateTime? lastMarketAt;
  final String endDate;
  final bool online;
  final AutomatedPaperEntry entry;
  final AutomatedPaperPortfolio portfolio;
  final int fillCount;
  final List<AutomatedPaperFill> fills;
  final List<AutomatedPaperDay> closedDays;
}

class AutomatedPaperEntry {
  AutomatedPaperEntry.fromJson(Map<String, dynamic> json)
    : rule = json['rule'] as String,
      appliesOn = json['appliesOn'] as String,
      eligible = json['eligible'] as bool,
      previousClose = _optionalDouble(json['previousClose']),
      averageClose = _optionalDouble(json['averageClose']),
      threshold = _optionalDouble(json['threshold']);

  final String rule;
  final String appliesOn;
  final bool eligible;
  final double? previousClose;
  final double? averageClose;
  final double? threshold;
}

class AutomatedPaperPortfolio {
  AutomatedPaperPortfolio.fromJson(Map<String, dynamic> json)
    : initialCash = _readDouble(json['initialCash']),
      cash = _readDouble(json['cash']),
      quantity = _readDouble(json['quantity']),
      realizedProfit = _readDouble(json['realizedProfit']),
      unrealizedProfit = _optionalDouble(json['unrealizedProfit']),
      netAsset = _optionalDouble(json['netAsset']),
      markPrice = _optionalDouble(json['markPrice']),
      markSource = json['markSource'] as String?;

  final double initialCash;
  final double cash;
  final double quantity;
  final double realizedProfit;
  final double? unrealizedProfit;
  final double? netAsset;
  final double? markPrice;
  final String? markSource;
}

class AutomatedPaperFill {
  AutomatedPaperFill.fromJson(Map<String, dynamic> json)
    : id = _readInt(json['id']),
      at = DateTime.parse(json['at'] as String),
      side = json['side'] as String,
      rule = json['rule'] as String,
      threshold = _readDouble(json['threshold']),
      price = _readDouble(json['price']),
      quantity = _readDouble(json['quantity']),
      costs = _readDouble(json['fee']) + _readDouble(json['tax']),
      realizedProfit = _readDouble(json['realized']);

  final int id;
  final DateTime at;
  final String side;
  final String rule;
  final double threshold;
  final double price;
  final double quantity;
  final double costs;
  final double realizedProfit;
}

class AutomatedPaperDay {
  AutomatedPaperDay.fromJson(Map<String, dynamic> json)
    : date = json['date'] as String,
      profit = _optionalDouble(json['profit']),
      buyCount = _readInt(json['buyCount']),
      sellCount = _readInt(json['sellCount']);

  final String date;
  final double? profit;
  final int buyCount;
  final int sellCount;
}

double? _optionalDouble(Object? value) =>
    value == null ? null : _readDouble(value);

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
