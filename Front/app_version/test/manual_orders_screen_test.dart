import 'dart:async';
import 'dart:convert';
import 'package:app_version/config/api_config.dart';
import 'package:app_version/models/order_precheck.dart';
import 'package:app_version/repositories/manual_order_repository.dart';
import 'package:app_version/repositories/order_precheck_repository.dart';
import 'package:app_version/repositories/spring_order_precheck_repository.dart';
import 'package:app_version/screens/manual_orders_screen.dart';
import 'package:app_version/screens/order_diagnostics_screen.dart';
import 'package:app_version/screens/unknown_order_review_screen.dart';
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

  testWidgets(
    'unknown partial review opens while live switch is off and keeps main order blocked',
    (t) async {
      final r = ReviewNavigationFake()
        ..ready = false
        ..orders = [order('UNKNOWN')];
      await mount(t, r);
      await t.ensureVisible(find.text('미체결·부분체결 대조'));
      await t.tap(find.text('미체결·부분체결 대조'));
      await t.pumpAndSettle();
      expect(find.byType(UnknownOrderReviewScreen), findsOneWidget);
      expect(r.reads, 1);
      expect(r.submits, 0);
      expect(r.confirms, 0);
      await t.pageBack();
      await t.pumpAndSettle();
      expect(r.orders.single.status, 'UNKNOWN');
    },
  );
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

  testWidgets(
    'price increase shows old and new price and needs separate consent',
    (t) async {
      final r = FakeRepository()..orders = [order('ACCEPTED')];
      await mount(t, r);
      await t.ensureVisible(find.text('지정가 변경'));
      await t.tap(find.text('지정가 변경'));
      await t.pumpAndSettle();
      expect(find.textContaining('기존 예약금을 합산하지 않고'), findsOneWidget);
      await t.enterText(
        find.descendant(
          of: find.byType(AlertDialog),
          matching: find.byType(TextFormField),
        ),
        '101',
      );
      await t.tap(find.text('주문안 조회'));
      await t.pump(const Duration(milliseconds: 400));
      expect(r.changedPrice, 101);
      expect(find.text('실제 지정가 변경'), findsOneWidget);
      expect(find.textContaining('100원 → 101원'), findsOneWidget);
      expect(r.changeSubmits, 0);
      expect(
        t
            .widget<FilledButton>(find.widgetWithText(FilledButton, '실제 주문 전송'))
            .onPressed,
        isNull,
      );
      await t.tap(find.byType(CheckboxListTile));
      await t.pump();
      await t.tap(find.text('실제 주문 전송'));
      await t.pumpAndSettle();
      expect(r.changeSubmits, 1);
      expect(r.orders.single.price, 100);
    },
  );
  testWidgets('unchanged price and rejected cash check never submit change', (
    t,
  ) async {
    final r = FakeRepository()..orders = [order('ACCEPTED')];
    await mount(t, r);
    await t.ensureVisible(find.text('지정가 변경'));
    await t.tap(find.text('지정가 변경'));
    await t.pumpAndSettle();
    await t.tap(find.text('주문안 조회'));
    await t.pumpAndSettle();
    expect(r.changedPrice, isNull);
    expect(find.textContaining('기존과 다른 양수'), findsOneWidget);
    r.failChangePreparation = true;
    await t.ensureVisible(find.text('지정가 변경'));
    await t.tap(find.text('지정가 변경'));
    await t.pumpAndSettle();
    await t.enterText(
      find.descendant(
        of: find.byType(AlertDialog),
        matching: find.byType(TextFormField),
      ),
      '101',
    );
    await t.tap(find.text('주문안 조회'));
    await t.pumpAndSettle();
    expect(find.textContaining('새 주문 전체 금액'), findsOneWidget);
    expect(r.changeSubmits, 0);
    expect(r.orders.single.price, 100);
  });

  Future<void> openReconciliation(WidgetTester t, ReconciliationFake r) async {
    await mount(t, r);
    await t.ensureVisible(find.text('KB 주문번호로 전량 체결 대조'));
    await t.tap(find.text('KB 주문번호로 전량 체결 대조'));
    await t.pumpAndSettle();
    await t.enterText(
      find.descendant(
        of: find.byType(AlertDialog),
        matching: find.byType(TextField),
      ),
      '0040000638',
    );
    await t.tap(find.text('읽기 전용 대조'));
    await t.pump(const Duration(milliseconds: 400));
  }

  testWidgets(
    'reconciliation can be reviewed with live switch off and cancellation keeps lock',
    (t) async {
      final r = ReconciliationFake()..ready = false;
      await openReconciliation(t, r);
      expect(r.prepares, 1);
      expect(r.resolutions, 0);
      expect(
        t
            .widget<FilledButton>(find.widgetWithText(FilledButton, '대조 확정 저장'))
            .onPressed,
        isNull,
      );
      await t.tap(find.text('취소').last);
      await t.pumpAndSettle();
      expect(r.orders.single.unresolved, isTrue);
      expect(r.submits, 0);
      expect(r.resolutions, 0);
    },
  );

  testWidgets(
    'explicit filled reconciliation preserves UNKNOWN and clears only its pending block',
    (t) async {
      final r = ReconciliationFake();
      await openReconciliation(t, r);
      await t.tap(find.byType(CheckboxListTile));
      await t.pump(const Duration(milliseconds: 100));
      await t.tap(find.text('대조 확정 저장'));
      await t.pumpAndSettle();
      expect(r.resolutions, 1);
      expect(r.submits, 0);
      expect(r.orders.single.status, 'UNKNOWN');
      expect(r.orders.single.reconciled, isTrue);
      expect(find.textContaining('전량 체결 대조 확정 · KB 주문번호'), findsOneWidget);
      expect(
        t
            .widget<FilledButton>(
              find.widgetWithText(FilledButton, '안전 조건 검증 및 주문안 확인'),
            )
            .onPressed,
        isNotNull,
      );
    },
  );

  testWidgets('failed reconciliation save does not retry or unlock', (t) async {
    final r = ReconciliationFake()..failResolution = true;
    await openReconciliation(t, r);
    await t.tap(find.byType(CheckboxListTile));
    await t.pump(const Duration(milliseconds: 100));
    await t.tap(find.text('대조 확정 저장'));
    await t.pumpAndSettle();
    expect(r.resolutions, 1);
    expect(r.orders.single.unresolved, isTrue);
    expect(r.submits, 0);
    await t.tap(find.byTooltip('주문 기록 새로고침'));
    await t.pumpAndSettle();
    expect(r.resolutions, 1);
    expect(
      t
          .widget<FilledButton>(
            find.widgetWithText(FilledButton, '안전 조건 검증 및 주문안 확인'),
          )
          .onPressed,
      isNull,
    );
  });

  test(
    'reconciliation requests use read/confirm endpoints and never submission',
    () async {
      final paths = <String>[];
      final repository = SpringOrderPrecheckRepository(
        accessToken: '',
        config: ApiConfig(baseUrl: 'http://localhost:8080'),
        client: MockClient((request) async {
          paths.add(request.url.path);
          if (paths.length == 1) {
            expect(jsonDecode(request.body), {'orderNo': '0040000638'});
          } else {
            expect(jsonDecode(request.body), {
              'token': 'proof-token',
              'acknowledged': true,
              'confirmation': '전량 체결 대조 확정',
            });
          }
          return http.Response(jsonEncode({'success': true, 'data': {}}), 200);
        }),
      );
      await repository.prepareReconciliation('test', '0040000638');
      await repository.confirmReconciliation('test', 'proof-token');
      expect(paths, [
        '/api/v1/orders/manual/test/reconciliation/prepare',
        '/api/v1/orders/manual/test/reconciliation/confirm',
      ]);
    },
  );

  testWidgets(
    'unfinished dispatch opens read-only diagnostics without a recovery or order request',
    (t) async {
      final r = DiagnosticNavigationFake()
        ..ready = false
        ..phase = 'DISPATCHING'
        ..recoverable = false;
      await mount(t, r);
      await t.ensureVisible(find.text('전송 기록 확인·복구'));
      await t.tap(find.text('전송 기록 확인·복구'));
      await t.pump(const Duration(milliseconds: 400));
      expect(find.text('기록으로 결과 복구'), findsNothing);
      await t.tap(find.text('주문번호로 잠금 유지 진단'));
      await t.pumpAndSettle();
      expect(find.byType(OrderDiagnosticsScreen), findsOneWidget);
      expect(r.historyReads, 1);
      expect(r.diagnoses, 0);
      expect(r.submits, 0);
      expect(r.changeSubmits, 0);
      expect(r.recoveries, 0);
      await t.pageBack();
      await t.pumpAndSettle();
      expect(find.byType(OrderDiagnosticsScreen), findsNothing);
    },
  );

  for (final phase in ['RESERVED', 'DISPATCHING', 'LEGACY_UNVERIFIED']) {
    testWidgets(
      '$phase dispatch cannot show recovery action even with live switch off',
      (t) async {
        final r = DispatchFake()
          ..ready = false
          ..phase = phase
          ..recoverable = false;
        await mount(t, r);
        await t.ensureVisible(find.text('전송 기록 확인·복구'));
        await t.tap(find.text('전송 기록 확인·복구'));
        await t.pump(const Duration(milliseconds: 400));
        expect(find.textContaining(phase), findsOneWidget);
        expect(find.text('기록으로 결과 복구'), findsNothing);
        expect(find.byType(CheckboxListTile), findsNothing);
        await t.tap(find.text('닫기'));
        await t.pumpAndSettle();
        expect(r.recoveries, 0);
        expect(r.submits, 0);
        expect(r.changeSubmits, 0);
      },
    );
  }

  testWidgets(
    'dispatch recovery needs checkbox and never transmits with live switch off',
    (t) async {
      final r = DispatchFake()..ready = false;
      await mount(t, r);
      await t.ensureVisible(find.text('전송 기록 확인·복구'));
      await t.tap(find.text('전송 기록 확인·복구'));
      await t.pump(const Duration(milliseconds: 400));
      expect(
        t
            .widget<FilledButton>(
              find.widgetWithText(FilledButton, '기록으로 결과 복구'),
            )
            .onPressed,
        isNull,
      );
      await t.tap(find.byType(CheckboxListTile));
      await t.pump(const Duration(milliseconds: 100));
      await t.tap(find.text('기록으로 결과 복구'));
      await t.pumpAndSettle();
      expect(r.recoveries, 1);
      expect(r.submits, 0);
      expect(r.changeSubmits, 0);
      expect(find.textContaining('ACCEPTED'), findsOneWidget);
      await t.ensureVisible(find.text('전송 기록'));
      await t.tap(find.text('전송 기록'));
      await t.pump(const Duration(milliseconds: 400));
      expect(find.textContaining('2026-10-31T12:00:00'), findsOneWidget);
      expect(find.text('기록으로 결과 복구'), findsNothing);
      await t.tap(find.text('닫기'));
      await t.pumpAndSettle();
      expect(r.recoveries, 1);
    },
  );

  testWidgets(
    'lost recovery response rereads saved state without automatic repost',
    (t) async {
      final r = DispatchFake()..loseResponse = true;
      await mount(t, r);
      await t.ensureVisible(find.text('전송 기록 확인·복구'));
      await t.tap(find.text('전송 기록 확인·복구'));
      await t.pump(const Duration(milliseconds: 400));
      await t.tap(find.byType(CheckboxListTile));
      await t.pump(const Duration(milliseconds: 100));
      await t.tap(find.text('기록으로 결과 복구'));
      await t.pumpAndSettle();
      await t.tap(find.byTooltip('주문 기록 새로고침'));
      await t.pumpAndSettle();
      expect(r.recoveries, 1);
      expect(r.submits, 0);
      expect(r.orders.single.status, 'ACCEPTED');
      expect(
        t
            .widget<FilledButton>(
              find.widgetWithText(FilledButton, '안전 조건 검증 및 주문안 확인'),
            )
            .onPressed,
        isNotNull,
      );
    },
  );

  testWidgets('unknown stored result recovery keeps new order blocked', (
    t,
  ) async {
    final r = DispatchFake()..outcome = 'UNKNOWN';
    await mount(t, r);
    await t.ensureVisible(find.text('전송 기록 확인·복구'));
    await t.tap(find.text('전송 기록 확인·복구'));
    await t.pump(const Duration(milliseconds: 400));
    await t.tap(find.byType(CheckboxListTile));
    await t.pump(const Duration(milliseconds: 100));
    await t.tap(find.text('기록으로 결과 복구'));
    await t.pumpAndSettle();
    expect(r.recoveries, 1);
    expect(r.orders.single.status, 'UNKNOWN');
    expect(
      t
          .widget<FilledButton>(
            find.widgetWithText(FilledButton, '안전 조건 검증 및 주문안 확인'),
          )
          .onPressed,
      isNull,
    );
  });

  test(
    'HTTP recovery uses separate explicit acknowledgment and never retries',
    () async {
      final paths = <String>[];
      final r = SpringOrderPrecheckRepository(
        accessToken: '',
        config: ApiConfig(baseUrl: 'http://localhost:8080'),
        client: MockClient((request) async {
          paths.add('${request.method} ${request.url.path}');
          if (request.method == 'POST') {
            expect(jsonDecode(request.body), {
              'acknowledged': true,
              'confirmation': '저장된 전송 결과 복구',
            });
            return http.Response(
              jsonEncode({
                'success': false,
                'error': {'message': 'recovery result unavailable'},
              }),
              503,
            );
          }
          return http.Response(
            jsonEncode({
              'success': true,
              'data': {'phase': 'RETURNED'},
            }),
            200,
          );
        }),
      );
      await expectLater(
        r.recoverDispatch('test'),
        throwsA(isA<OrderPrecheckRepositoryException>()),
      );
      await r.fetchDispatch('test');
      expect(paths, [
        'POST /api/v1/orders/manual/test/dispatch/recover',
        'GET /api/v1/orders/manual/test/dispatch',
      ]);
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
  int? changedPrice;
  String? changedKind;
  bool failChangePreparation = false;
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
  ) async {
    changedPrice = price;
    changedKind = kind;
    if (failChangePreparation) {
      throw const OrderPrecheckRepositoryException(
        '매수 증액의 새 주문 전체 금액을 충당할 주문가능현금이 부족합니다.',
      );
    }
    return {
      'command': {
        ...order('PREPARED').data,
        'kind': kind,
        'commandId': 'child',
        'price': ?price,
      },
      'token': 'change-token',
    };
  }

  @override
  Future<ManualOrder> submitManualChange(String id, String token) async {
    expect(id, 'child');
    expect(token, 'change-token');
    changeSubmits++;
    return ManualOrder({
      ...order('ACCEPTED').data,
      'kind': changedKind ?? 'CANCEL',
      if (changedPrice != null) 'price': changedPrice,
      'commandId': 'child',
    });
  }
}

class DispatchFake extends FakeRepository
    implements ManualOrderDispatchRepository {
  DispatchFake() {
    orders = [order('SENDING')];
  }
  String phase = 'RETURNED';
  String outcome = 'ACCEPTED';
  bool recoverable = true;
  bool loseResponse = false;
  int recoveries = 0;
  @override
  Future<Map<String, dynamic>> fetchDispatch(String id) async => {
    'commandStatus': orders.single.status,
    'phase': phase,
    'recoverable': recoverable && orders.single.status == 'SENDING',
    'recoveredAt': recoveries > 0 ? '2026-10-31T12:00:00' : null,
    'receipt': {
      'status': outcome,
      'orderNo': outcome == 'ACCEPTED' ? '0040000638' : '',
    },
    'message': '저장 결과 확인',
  };
  @override
  Future<Map<String, dynamic>> recoverDispatch(String id) async {
    recoveries++;
    orders = [order(outcome)];
    if (loseResponse) throw TimeoutException('test lost recovery response');
    return fetchDispatch(id);
  }
}

class DiagnosticNavigationFake extends DispatchFake
    implements ManualOrderDiagnosticRepository {
  int historyReads = 0;
  int diagnoses = 0;
  @override
  Future<List<Map<String, dynamic>>> diagnosticHistory(String id) async {
    historyReads++;
    return [];
  }

  @override
  Future<Map<String, dynamic>> diagnoseSending(
    String id,
    String diagnosticId,
    String orderNo,
  ) async {
    diagnoses++;
    return {};
  }
}

class ReviewNavigationFake extends FakeRepository
    implements UnknownOrderReviewRepository {
  int reads = 0;
  @override
  Future<List<Map<String, dynamic>>> unknownReviewHistory(String id) async {
    reads++;
    return [];
  }

  @override
  Future<Map<String, dynamic>> prepareUnknownReview(
    String id,
    String orderNo,
  ) async => {};
  @override
  Future<void> confirmUnknownReview(
    String id,
    String reviewId,
    String token,
  ) async {
    confirms++;
  }
}

class ReconciliationFake extends FakeRepository
    implements ManualOrderReconciliationRepository {
  ReconciliationFake() {
    orders = [order('UNKNOWN')];
  }
  int prepares = 0;
  int resolutions = 0;
  bool failResolution = false;
  @override
  Future<Map<String, dynamic>> prepareReconciliation(
    String id,
    String orderNo,
  ) async {
    prepares++;
    return {
      'command': orders.single.data,
      'orderNo': orderNo,
      'orderTime': '090001',
      'filledQuantity': 1,
      'token': 'proof-token',
    };
  }

  @override
  Future<void> confirmReconciliation(String id, String token) async {
    expect(id, 'test');
    expect(token, 'proof-token');
    resolutions++;
    if (failResolution) {
      throw const OrderPrecheckRepositoryException('대조 저장 실패');
    }
    orders = [
      ManualOrder({
        ...orders.single.data,
        'reconciliation': {
          'orderDate': '20261031',
          'orderNo': '0040000638',
          'orderTime': '090001',
          'filledQuantity': 1,
          'confirmedAt': '2026-10-31T10:00:00',
        },
      }),
    ];
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
