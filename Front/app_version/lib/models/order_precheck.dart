/// 주문 사전검증에 전달할 지정가 주문안입니다.
class OrderPrecheckInput {
  const OrderPrecheckInput({
    required this.stockCode,
    required this.stockName,
    required this.market,
    required this.side,
    required this.limitPrice,
    required this.quantity,
  });

  final String stockCode;
  final String stockName;
  final String market;
  final String side;
  final double limitPrice;
  final double quantity;

  Map<String, dynamic> toJson() => {
    'stockCode': stockCode,
    'stockName': stockName,
    'market': market,
    'side': side,
    'limitPrice': limitPrice,
    'quantity': quantity,
  };
}

/// 실제 주문 전송 없이 계산된 안전 검증 결과입니다.
class OrderPrecheckResult {
  const OrderPrecheckResult({
    required this.orderPrecheckId,
    required this.stockCode,
    required this.stockName,
    required this.market,
    required this.side,
    required this.orderType,
    required this.limitPrice,
    required this.quantity,
    required this.estimatedAmount,
    required this.quoteProvider,
    required this.currentPrice,
    required this.priceDeviationRate,
    required this.orderAvailableCash,
    required this.orderableQuantity,
    required this.maxOrderAmount,
    required this.maxPriceDeviationRate,
    required this.orderEnabled,
    required this.eligible,
    required this.canSubmit,
    required this.submissionMessage,
    required this.checks,
    required this.checkedAt,
  });

  final int orderPrecheckId;
  final String stockCode;
  final String stockName;
  final String market;
  final String side;
  final String orderType;
  final double limitPrice;
  final double quantity;
  final double estimatedAmount;
  final String quoteProvider;
  final double currentPrice;
  final double priceDeviationRate;
  final double orderAvailableCash;
  final double orderableQuantity;
  final double maxOrderAmount;
  final double maxPriceDeviationRate;
  final bool orderEnabled;
  final bool eligible;
  final bool canSubmit;
  final String submissionMessage;
  final List<OrderSafetyCheck> checks;
  final DateTime checkedAt;

  factory OrderPrecheckResult.fromJson(Map<String, dynamic> json) {
    return OrderPrecheckResult(
      orderPrecheckId: _readInt(json['orderPrecheckId']),
      stockCode: json['stockCode'] as String,
      stockName: json['stockName'] as String,
      market: json['market'] as String,
      side: json['side'] as String,
      orderType: json['orderType'] as String,
      limitPrice: _readDouble(json['limitPrice']),
      quantity: _readDouble(json['quantity']),
      estimatedAmount: _readDouble(json['estimatedAmount']),
      quoteProvider: json['quoteProvider'] as String,
      currentPrice: _readDouble(json['currentPrice']),
      priceDeviationRate: _readDouble(json['priceDeviationRate']),
      orderAvailableCash: _readDouble(json['orderAvailableCash']),
      orderableQuantity: _readDouble(json['orderableQuantity']),
      maxOrderAmount: _readDouble(json['maxOrderAmount']),
      maxPriceDeviationRate: _readDouble(json['maxPriceDeviationRate']),
      orderEnabled: json['orderEnabled'] as bool? ?? false,
      eligible: json['eligible'] as bool? ?? false,
      canSubmit: json['canSubmit'] as bool? ?? false,
      submissionMessage: json['submissionMessage'] as String,
      checks: (json['checks'] as List<dynamic>? ?? const [])
          .map(
            (item) => OrderSafetyCheck.fromJson(item as Map<String, dynamic>),
          )
          .toList(),
      checkedAt: DateTime.parse(json['checkedAt'] as String),
    );
  }
}

class OrderSafetyCheck {
  const OrderSafetyCheck({
    required this.code,
    required this.label,
    required this.passed,
    required this.message,
  });

  final String code;
  final String label;
  final bool passed;
  final String message;

  factory OrderSafetyCheck.fromJson(Map<String, dynamic> json) {
    return OrderSafetyCheck(
      code: json['code'] as String,
      label: json['label'] as String,
      passed: json['passed'] as bool? ?? false,
      message: json['message'] as String,
    );
  }
}

class OrderApprovalPreparation {
  const OrderApprovalPreparation({
    required this.approvalId,
    required this.token,
    required this.expiresAt,
    required this.precheck,
  });

  final int approvalId;
  final String token;
  final DateTime expiresAt;
  final OrderPrecheckResult precheck;

  factory OrderApprovalPreparation.fromJson(Map<String, dynamic> json) {
    return OrderApprovalPreparation(
      approvalId: _readInt(json['approvalId']),
      token: json['token'] as String,
      expiresAt: DateTime.parse(json['expiresAt'] as String),
      precheck: OrderPrecheckResult.fromJson(
        json['precheck'] as Map<String, dynamic>,
      ),
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
