import 'dart:convert';

typedef PredictionQuality = ({double accuracy, double logLoss});
typedef TradingResult = ({double netReturn, double maxDrawdown, int trades});
typedef TradingCosts = ({int fee, int slippage, int sellTax});

class LearningEvaluation {
  const LearningEvaluation({
    required this.firstTargetDate,
    required this.lastTargetDate,
    required this.samples,
    required this.costs,
    required this.stocks,
  });

  static const scenarios = ['base', 'stress'];
  static const strategies = ['model', 'daily', 'trend5', 'cash'];
  static const stockNames = {'005930': '삼성전자', '000660': 'SK하이닉스'};

  final String firstTargetDate;
  final String lastTargetDate;
  final int samples;
  final Map<String, TradingCosts> costs;
  final List<StockLearningEvaluation> stocks;

  factory LearningEvaluation.parse(String raw) {
    final json = jsonDecode(raw) as Map<String, dynamic>;
    if (json['schemaVersion'] != 'SAGOPALGO_DAILY_LEARNING_SUMMARY_V1' ||
        json['purpose'] != 'PERSONAL_LOCAL_RESEARCH') {
      throw const FormatException('Unsupported evaluation summary');
    }
    final period = json['commonFinalPeriod'] as Map<String, dynamic>;
    final stocks = json['stocks'] as Map<String, dynamic>;
    final costs = json['costs'] as Map<String, dynamic>;
    return LearningEvaluation(
      firstTargetDate: period['firstTargetDate'] as String,
      lastTargetDate: period['lastTargetDate'] as String,
      samples: period['samples'] as int,
      costs: {
        for (final scenario in scenarios)
          scenario: _costs(costs[scenario] as Map<String, dynamic>),
      },
      stocks: [
        for (final code in stockNames.keys)
          StockLearningEvaluation.fromJson(
            code,
            stocks[code] as Map<String, dynamic>,
            period,
          ),
      ],
    );
  }

  static TradingCosts _costs(Map<String, dynamic> json) => (
    fee: json['feeBpsPerSide'] as int,
    slippage: json['slippageBpsPerSide'] as int,
    sellTax: json['sellTaxBps'] as int,
  );
}

class StockLearningEvaluation {
  const StockLearningEvaluation({
    required this.code,
    required this.version,
    required this.threshold,
    required this.model,
    required this.frequency,
    required this.strategies,
  });

  final String code;
  final String version;
  final double? threshold;
  final PredictionQuality model;
  final PredictionQuality frequency;
  final Map<String, Map<String, TradingResult>> strategies;

  factory StockLearningEvaluation.fromJson(
    String code,
    Map<String, dynamic> json,
    Map<String, dynamic> commonPeriod,
  ) {
    final period = json['period'] as Map<String, dynamic>;
    if (commonPeriod.entries.any((entry) => period[entry.key] != entry.value)) {
      throw const FormatException('Inconsistent evaluation period');
    }
    final prediction = json['prediction'] as Map<String, dynamic>;
    final strategies = json['strategies'] as Map<String, dynamic>;
    return StockLearningEvaluation(
      code: code,
      version: json['version'] as String,
      threshold: (json['threshold'] as num?)?.toDouble(),
      model: _quality(prediction['model'] as Map<String, dynamic>),
      frequency: _quality(
        prediction['trainingFrequency'] as Map<String, dynamic>,
      ),
      strategies: {
        for (final scenario in LearningEvaluation.scenarios)
          scenario: _strategies(strategies[scenario] as Map<String, dynamic>),
      },
    );
  }

  static Map<String, TradingResult> _strategies(Map<String, dynamic> json) => {
    for (final name in LearningEvaluation.strategies)
      name: _tradingResult(json[name] as Map<String, dynamic>),
  };

  static PredictionQuality _quality(Map<String, dynamic> json) => (
    accuracy: (json['accuracy'] as num).toDouble(),
    logLoss: (json['logLoss'] as num).toDouble(),
  );

  static TradingResult _tradingResult(Map<String, dynamic> json) => (
    netReturn: (json['netReturn'] as num).toDouble(),
    maxDrawdown: (json['maxDrawdown'] as num).toDouble(),
    trades: json['trades'] as int,
  );
}
