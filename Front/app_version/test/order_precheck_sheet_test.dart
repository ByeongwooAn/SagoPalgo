import 'package:app_version/models/holding.dart';
import 'package:app_version/models/order_precheck.dart';
import 'package:app_version/repositories/order_precheck_repository.dart';
import 'package:app_version/screens/order_precheck_sheet.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('order precheck displays blockers without a submit action', (
    tester,
  ) async {
    final repository = _FakeOrderPrecheckRepository();

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: OrderPrecheckSheet(holding: _holding, repository: repository),
        ),
      ),
    );

    expect(find.text('삼성전자 주문 사전검토'), findsOneWidget);
    expect(find.text('실제 주문 전송 미지원'), findsOneWidget);

    await tester.tap(find.text('안전 조건 검증'));
    await tester.pumpAndSettle();

    expect(repository.input?.side, 'SELL');
    expect(repository.input?.limitPrice, 75300);
    expect(repository.input?.quantity, 12);
    expect(find.text('주문안 차단'), findsOneWidget);
    expect(find.text('주문 스위치'), findsOneWidget);
    expect(find.text('KB 주문 기능이 OFF입니다.'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, '실제 주문'), findsNothing);
  });
}

final _holding = Holding(
  holdingId: 21,
  stockName: '삼성전자',
  stockCode: '005930',
  market: 'KOSPI',
  buyPrice: 70000,
  quantity: 12,
  buyDate: DateTime(2026, 9, 1),
  currentPrice: 75300,
  profitRate: 7.57,
  stopLossRate: -5,
  takeProfitRate: 9,
  status: '보유',
);

final _result = OrderPrecheckResult(
  orderPrecheckId: 31,
  stockCode: '005930',
  stockName: '삼성전자',
  market: 'KOSPI',
  side: 'SELL',
  orderType: 'LIMIT',
  limitPrice: 75300,
  quantity: 12,
  estimatedAmount: 903600,
  quoteProvider: 'KB',
  currentPrice: 75300,
  priceDeviationRate: 0,
  orderAvailableCash: 0,
  orderableQuantity: 12,
  maxOrderAmount: 1000000,
  maxPriceDeviationRate: 5,
  orderEnabled: false,
  eligible: false,
  canSubmit: false,
  submissionMessage: '사전검증 전용 단계로 실제 주문 전송은 구현되어 있지 않습니다.',
  checks: const [
    OrderSafetyCheck(
      code: 'ORDER_SWITCH',
      label: '주문 스위치',
      passed: false,
      message: 'KB 주문 기능이 OFF입니다.',
    ),
  ],
  checkedAt: DateTime(2026, 9, 23, 12),
);

class _FakeOrderPrecheckRepository implements OrderPrecheckRepository {
  OrderPrecheckInput? input;

  @override
  Future<OrderPrecheckResult> precheck(OrderPrecheckInput input) async {
    this.input = input;
    return _result;
  }
}
