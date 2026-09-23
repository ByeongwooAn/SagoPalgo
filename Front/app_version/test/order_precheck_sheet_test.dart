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
    expect(find.text('승인 기록만 저장 · 실제 주문 전송 미지원'), findsOneWidget);

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

  testWidgets(
    'eligible order requires explicit confirmation and never submits',
    (tester) async {
      final repository = _FakeOrderPrecheckRepository(eligible: true);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: OrderPrecheckSheet(holding: _holding, repository: repository),
          ),
        ),
      );

      await tester.tap(find.text('안전 조건 검증'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('수동 승인 기록'));
      await tester.pumpAndSettle();

      expect(find.textContaining('실제 주문은 전송되지 않습니다.'), findsOneWidget);
      expect(repository.prepareCount, 1);
      expect(repository.confirmCount, 0);

      await tester.tap(find.text('기록 승인'));
      await tester.pumpAndSettle();
      expect(repository.confirmCount, 1);
      expect(find.text('승인 기록만 저장되었습니다. 실제 주문은 전송되지 않았습니다.'), findsOneWidget);
      await tester.tap(find.text('안전 조건 검증'));
      await tester.pumpAndSettle();
      expect(find.text('수동 승인 기록'), findsOneWidget);
    },
  );
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

class _FakeOrderPrecheckRepository extends OrderPrecheckRepository {
  _FakeOrderPrecheckRepository({this.eligible = false});

  final bool eligible;
  OrderPrecheckInput? input;
  int prepareCount = 0;
  int confirmCount = 0;

  @override
  Future<OrderPrecheckResult> precheck(OrderPrecheckInput input) async {
    this.input = input;
    return eligible ? _eligibleResult : _result;
  }

  @override
  Future<OrderApprovalPreparation> prepareApproval(
    OrderPrecheckInput input,
  ) async {
    prepareCount++;
    return OrderApprovalPreparation(
      approvalId: 7,
      token: 'one-time-token',
      expiresAt: DateTime(2026, 9, 23, 12, 1),
      precheck: _eligibleResult,
    );
  }

  @override
  Future<String> confirmApproval(OrderApprovalPreparation preparation) async {
    confirmCount++;
    return '승인 기록만 저장되었습니다. 실제 주문은 전송되지 않았습니다.';
  }
}

final _eligibleResult = OrderPrecheckResult(
  orderPrecheckId: 32,
  stockCode: _result.stockCode,
  stockName: _result.stockName,
  market: _result.market,
  side: _result.side,
  orderType: _result.orderType,
  limitPrice: _result.limitPrice,
  quantity: _result.quantity,
  estimatedAmount: _result.estimatedAmount,
  quoteProvider: _result.quoteProvider,
  currentPrice: _result.currentPrice,
  priceDeviationRate: _result.priceDeviationRate,
  orderAvailableCash: _result.orderAvailableCash,
  orderableQuantity: _result.orderableQuantity,
  maxOrderAmount: _result.maxOrderAmount,
  maxPriceDeviationRate: _result.maxPriceDeviationRate,
  orderEnabled: true,
  eligible: true,
  canSubmit: false,
  submissionMessage: _result.submissionMessage,
  checks: const [],
  checkedAt: DateTime(2026, 9, 23, 12),
);
