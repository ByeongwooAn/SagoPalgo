import 'dart:async';
import 'dart:convert';
import 'package:app_version/config/api_config.dart';
import 'package:app_version/models/order_precheck.dart';
import 'package:app_version/repositories/manual_order_repository.dart';
import 'package:app_version/repositories/order_precheck_repository.dart';
import 'package:app_version/repositories/spring_order_precheck_repository.dart';
import 'package:app_version/screens/manual_orders_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  Future<void> mount(WidgetTester t, FakeRepository r) async {
    await t.pumpWidget(
      MaterialApp(
        home: ManualOrdersScreen(repository: r, manual: r),
      ),
    );
    await t.pumpAndSettle();
  }

  Future<void> start(WidgetTester t) async {
    final fields = find.byType(TextField);
    await t.enterText(fields.at(0), '005930');
    await t.enterText(fields.at(1), '삼성전자');
    await t.enterText(fields.at(2), '100');
    await t.ensureVisible(find.text('안전 조건 검증 및 주문안 확인'));
    await t.tap(find.text('안전 조건 검증 및 주문안 확인'));
    await t.pump(const Duration(milliseconds: 400));
  }

  testWidgets('disabled readiness cannot prepare or submit', (t) async {
    final r = FakeRepository()..ready = false;
    await mount(t, r);
    expect(
      t
          .widget<FilledButton>(
            find.widgetWithText(FilledButton, '안전 조건 검증 및 주문안 확인'),
          )
          .onPressed,
      isNull,
    );
    expect(r.submits, 0);
  });
  testWidgets('cancel first approval leaves server untouched', (t) async {
    final r = FakeRepository();
    await mount(t, r);
    await start(t);
    await t.tap(find.text('취소'));
    await t.pumpAndSettle();
    expect(r.confirms, 0);
    expect(r.submits, 0);
  });
  testWidgets(
    'recording approval still needs separately checked actual confirmation',
    (t) async {
      final r = FakeRepository();
      await mount(t, r);
      await start(t);
      await t.tap(find.text('승인 기록 저장'));
      await t.pump(const Duration(milliseconds: 400));
      expect(r.confirms, 1);
      expect(r.submits, 0);
      expect(
        t
            .widget<FilledButton>(find.widgetWithText(FilledButton, '실제 주문 전송'))
            .onPressed,
        isNull,
      );
      await t.tap(find.text('취소'));
      await t.pumpAndSettle();
      expect(r.submits, 0);
    },
  );
  testWidgets(
    'one transmission blocks duplicate clicks and never retries unknown outcome',
    (t) async {
      final r = FakeRepository()..pending = Completer<ManualOrder>();
      await mount(t, r);
      await start(t);
      await t.tap(find.text('승인 기록 저장'));
      await t.pump(const Duration(milliseconds: 400));
      await t.tap(find.byType(CheckboxListTile));
      await t.pump(const Duration(milliseconds: 300));
      await t.tap(find.text('실제 주문 전송'));
      await t.pump();
      expect(r.submits, 1);
      expect(
        t
            .widget<FilledButton>(
              find.widgetWithText(FilledButton, '안전 조건 검증 및 주문안 확인'),
            )
            .onPressed,
        isNull,
      );
      // 전송 요청이 서버 기록에 아직 나타나지 않아도 새 주문을 열지 않습니다.
      r.orders = [];
      r.pending!.completeError(TimeoutException('test timeout'));
      await t.pumpAndSettle();
      expect(find.textContaining('재전송하지 말고'), findsWidgets);
      expect(r.submits, 1);
      expect(
        t
            .widget<FilledButton>(
              find.widgetWithText(FilledButton, '안전 조건 검증 및 주문안 확인'),
            )
            .onPressed,
        isNull,
      );
      r.orders = [order('UNKNOWN')];
      await t.tap(find.byTooltip('주문 기록 새로고침'));
      await t.pumpAndSettle();
      expect(r.submits, 1);
      expect(
        t
            .widget<FilledButton>(
              find.widgetWithText(FilledButton, '안전 조건 검증 및 주문안 확인'),
            )
            .onPressed,
        isNull,
      );
    },
  );
  testWidgets(
    'loading history failure blocks new order and shows safe migration message',
    (t) async {
      final r = FakeRepository()..historyError = true;
      await mount(t, r);
      expect(find.textContaining('016'), findsOneWidget);
      expect(
        t
            .widget<FilledButton>(
              find.widgetWithText(FilledButton, '안전 조건 검증 및 주문안 확인'),
            )
            .onPressed,
        isNull,
      );
    },
  );
  testWidgets(
    'cancel command requires its own final checkbox and preserves original order',
    (t) async {
      final r = FakeRepository()..orders = [order('ACCEPTED')];
      await mount(t, r);
      await t.ensureVisible(find.text('전부 취소'));
      await t.tap(find.text('전부 취소'));
      await t.pump(const Duration(milliseconds: 400));
      expect(find.text('실제 전부 취소'), findsOneWidget);
      expect(r.changeSubmits, 0);
      expect(
        t
            .widget<FilledButton>(find.widgetWithText(FilledButton, '실제 주문 전송'))
            .onPressed,
        isNull,
      );
      await t.tap(find.byType(CheckboxListTile));
      await t.pump(const Duration(milliseconds: 100));
      await t.tap(find.text('실제 주문 전송'));
      await t.pumpAndSettle();
      expect(r.changeSubmits, 1);
      expect(r.orders.single.status, 'ACCEPTED');
    },
  );

  test(
    'HTTP submission does not retry on failure and history only GETs',
    () async {
      final methods = <String>[];
      final r = SpringOrderPrecheckRepository(
        accessToken: '',
        config: ApiConfig(baseUrl: 'http://localhost:8080'),
        client: MockClient((request) async {
          methods.add(request.method);
          if (request.method == 'POST') {
            expect(jsonDecode(request.body), {
              'approvalId': 7,
              'acknowledged': true,
              'confirmation': '실제 주문 전송',
            });
            return http.Response(
              jsonEncode({
                'success': false,
                'error': {'message': 'test error'},
              }),
              503,
            );
          }
          return http.Response(jsonEncode({'success': true, 'data': []}), 200);
        }),
      );
      await expectLater(
        r.submitManualOrder(7),
        throwsA(isA<OrderPrecheckRepositoryException>()),
      );
      await r.manualOrderHistory();
      expect(methods, ['POST', 'GET']);
    },
  );
}

ManualOrder order(String status) => ManualOrder({
  'commandId': 'test',
  'kind': 'NEW',
  'stockCode': '005930',
  'stockName': '삼성전자',
  'side': 'BUY',
  'price': 100,
  'quantity': 1,
  'status': status,
  'orderNo': '',
  'orderDate': '20261031',
  'message': 'KB 앱에서 확인하세요.',
  'changeUsed': false,
});

class FakeRepository extends OrderPrecheckRepository
    implements ManualOrderRepository {
  bool ready = true;
  bool historyError = false;
  int confirms = 0;
  int submits = 0;
  int changeSubmits = 0;
  List<ManualOrder> orders = [];
  Completer<ManualOrder>? pending;
  @override
  Future<bool> manualOrderReady() async => ready;
  @override
  Future<List<ManualOrder>> manualOrderHistory() async {
    if (historyError) {
      throw const OrderPrecheckRepositoryException('DB 마이그레이션 016을 확인하세요.');
    }
    return orders;
  }

  @override
  Future<ManualOrder> submitManualOrder(int approvalId) async {
    submits++;
    return pending?.future ?? order('ACCEPTED');
  }

  @override
  Future<OrderPrecheckResult> precheck(OrderPrecheckInput input) async =>
      result;
  @override
  Future<OrderApprovalPreparation> prepareApproval(
    OrderPrecheckInput input,
  ) async => OrderApprovalPreparation(
    approvalId: 7,
    token: 'test',
    expiresAt: DateTime.now().add(const Duration(seconds: 90)),
    precheck: result,
  );
  @override
  Future<String> confirmApproval(OrderApprovalPreparation p) async {
    confirms++;
    return '저장';
  }

  @override
  Future<Map<String, dynamic>> observeManualOrder(String id) async => {};
  @override
  Future<List<Map<String, dynamic>>> manualOrderObservations(String id) async =>
      [];
  @override
  Future<Map<String, dynamic>> prepareManualChange(
    String id,
    String kind,
    int? price,
  ) async => {
    'command': {...order('PREPARED').data, 'kind': kind, 'commandId': 'child'},
    'token': 'change-token',
  };
  @override
  Future<ManualOrder> submitManualChange(String id, String token) async {
    expect(id, 'child');
    expect(token, 'change-token');
    changeSubmits++;
    return ManualOrder({
      ...order('ACCEPTED').data,
      'kind': 'CANCEL',
      'commandId': 'child',
    });
  }
}

final result = OrderPrecheckResult(
  orderPrecheckId: 1,
  stockCode: '005930',
  stockName: '삼성전자',
  market: 'KOSPI',
  side: 'BUY',
  orderType: 'LIMIT',
  limitPrice: 100,
  quantity: 1,
  estimatedAmount: 100,
  quoteProvider: 'KB',
  currentPrice: 100,
  priceDeviationRate: 0,
  orderAvailableCash: 1000,
  orderableQuantity: 0,
  maxOrderAmount: 1000000,
  maxPriceDeviationRate: 5,
  orderEnabled: true,
  eligible: true,
  canSubmit: false,
  submissionMessage: '미전송',
  checks: [],
  checkedAt: DateTime.now(),
);
