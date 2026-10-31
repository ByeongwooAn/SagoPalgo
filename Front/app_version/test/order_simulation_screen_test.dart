import 'dart:async';
import 'dart:convert';
import 'package:app_version/config/api_config.dart';
import 'package:app_version/models/paper_trading.dart';
import 'package:app_version/repositories/order_simulation_repository.dart';
import 'package:app_version/repositories/paper_trading_repository.dart';
import 'package:app_version/repositories/spring_paper_trading_repository.dart';
import 'package:app_version/screens/order_simulation_screen.dart';
import 'package:app_version/screens/order_diagnostics_screen.dart';
import 'package:app_version/screens/unknown_order_review_screen.dart';
import 'package:app_version/screens/paper_trading_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  Future<void> mount(WidgetTester t, FakeSimulation r) async {
    await t.binding.setSurfaceSize(const Size(1200, 900));
    addTearDown(() => t.binding.setSurfaceSize(null));
    await t.pumpWidget(MaterialApp(home: OrderSimulationScreen(repository: r)));
    await t.pumpAndSettle();
  }

  testWidgets(
    'simulation fields and selectors fit a narrow window with enlarged text',
    (t) async {
      await t.binding.setSurfaceSize(const Size(360, 720));
      addTearDown(() => t.binding.setSurfaceSize(null));
      final r = FakeSimulation();
      await t.pumpWidget(
        MaterialApp(
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(
              context,
            ).copyWith(textScaler: const TextScaler.linear(1.4)),
            child: child!,
          ),
          home: OrderSimulationScreen(repository: r),
        ),
      );
      await t.pumpAndSettle();
      expect(t.takeException(), isNull);
      await t.drag(find.byType(ListView), const Offset(0, -400));
      await t.pumpAndSettle();
      expect(t.takeException(), isNull);
    },
  );

  Future<void> prepare(WidgetTester t) async {
    await t.ensureVisible(find.text('모의 주문 검증·승인'));
    await t.tap(find.text('모의 주문 검증·승인'));
    await t.pump(const Duration(milliseconds: 400));
  }

  Future<void> approve(WidgetTester t) async {
    await t.tap(find.text('모의 승인 기록 저장'));
    await t.pump(const Duration(milliseconds: 400));
  }

  Future<void> transmit(WidgetTester t) async {
    await t.tap(find.byType(CheckboxListTile));
    await t.pump(const Duration(milliseconds: 100));
    await t.tap(find.text('모의 주문 전송'));
    await t.pump();
  }

  testWidgets(
    'unfinished simulation opens diagnosis without sending any mutation',
    (t) async {
      final r = FakeSimulation();
      r.commands.add(
        command('c1', 'SENDING')..['dispatchPhase'] = 'DISPATCHING',
      );
      r.state['blocked'] = true;
      await mount(t, r);
      await t.ensureVisible(find.text('가상 주문번호로 잠금 유지 진단'));
      await t.tap(find.text('가상 주문번호로 잠금 유지 진단'));
      await t.pumpAndSettle();
      expect(find.byType(OrderDiagnosticsScreen), findsOneWidget);
      expect(find.text('SIMULATION · 실제 KB 조회·주문 없음'), findsOneWidget);
      expect(r.actions, isEmpty);
      await t.pageBack();
      await t.pumpAndSettle();
      expect(r.commands.single['status'], 'SENDING');
      expect(r.state['blocked'], true);
    },
  );

  testWidgets(
    'unknown simulation opens review without mutation and remains blocked',
    (t) async {
      final r = FakeSimulation();
      r.commands.add(command('c1', 'UNKNOWN'));
      r.state['blocked'] = true;
      await mount(t, r);
      await t.ensureVisible(find.text('미체결·변경 주문 대조'));
      await t.tap(find.text('미체결·변경 주문 대조'));
      await t.pumpAndSettle();
      expect(find.byType(UnknownOrderReviewScreen), findsOneWidget);
      expect(r.actions, isEmpty);
      await t.pageBack();
      await t.pumpAndSettle();
      expect(r.commands.single['status'], 'UNKNOWN');
      expect(r.state['blocked'], true);
    },
  );
  for (final source in ['SIMULATION', 'KB']) {
    testWidgets(
      'lost terminal response rereads $source proof and never resends original order',
      (t) async {
        final r = CompletionFakeSimulation()
          ..source = source
          ..pending = Completer<Map<String, dynamic>>();
        await mount(t, r);
        await prepare(t);
        await approve(t);
        await transmit(t);
        r.commands.last.addAll({
          'status': 'UNKNOWN',
          'brokerStatus': 'FILLED',
          'filledQuantity': 2,
          'openQuantity': 0,
        });
        r.state['blocked'] = true;
        r.pending!.completeError(TimeoutException('lost submit response'));
        await t.pumpAndSettle();
        await t.ensureVisible(find.text('가상 주문 종결 대조'));
        await t.tap(find.text('가상 주문 종결 대조'));
        await t.pumpAndSettle();
        await t.enterText(find.byType(TextField), '0000000001');
        await t.pump();
        await t.tap(find.text('가상 종결 근거 확인'));
        await t.pumpAndSettle();
        expect(
          t
              .widget<FilledButton>(
                find.widgetWithText(FilledButton, '가상 종결 확정'),
              )
              .onPressed,
          isNull,
        );
        await t.ensureVisible(find.byType(CheckboxListTile));
        await t.tap(find.byType(CheckboxListTile));
        await t.pump();
        await t.ensureVisible(find.text('가상 종결 확정'));
        await t.tap(find.text('가상 종결 확정'));
        await t.pumpAndSettle();
        await t.pageBack();
        await t.pumpAndSettle();
        expect(r.actions.where((a) => a.endsWith('/submit')).length, 1);
        expect(
          r.actions.where((a) => a.endsWith('/completion/confirm')).length,
          1,
        );
        expect(r.commands.last['sendCount'], 1);
        final button = t.widget<FilledButton>(
          find.widgetWithText(FilledButton, '모의 주문 검증·승인'),
        );
        if (source == 'SIMULATION') {
          expect(button.onPressed, isNotNull);
          expect(find.text('가상 종결 이력'), findsOneWidget);
        } else {
          expect(button.onPressed, isNull);
        }
      },
    );
  }
  testWidgets('new session uses virtual cash and makes no order requests', (
    t,
  ) async {
    final r = FakeSimulation()..exists = false;
    await mount(t, r);
    expect(find.text('SIMULATION · 실제 주문 전송 없음'), findsOneWidget);
    await t.tap(find.text('새 가상 세션'));
    await t.pumpAndSettle();
    await t.tap(find.text('가상 세션 만들기'));
    await t.pumpAndSettle();
    expect(r.createdCash, 10000000);
    expect(r.actions, isEmpty);
    expect(find.textContaining('예약 제외 사용 가능'), findsOneWidget);
  });

  testWidgets(
    'simulation is accessible when existing PAPER capital is missing',
    (t) async {
      final r = FakeSimulation();
      await t.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PaperTradingScreen(
              repository: r,
              recommendation: null,
              active: true,
            ),
          ),
        ),
      );
      await t.pumpAndSettle();
      await t.tap(find.text('주문 시뮬레이션 · 실패/체결 시나리오 시험'));
      await t.pumpAndSettle();
      expect(find.text('SIMULATION · 실제 주문 전송 없음'), findsOneWidget);
      expect(r.actions, isEmpty);
    },
  );

  testWidgets('cancelled approval never confirms or sends', (t) async {
    final r = FakeSimulation();
    await mount(t, r);
    await prepare(t);
    await t.tap(find.text('취소').last);
    await t.pumpAndSettle();
    expect(r.actions.where((a) => a.endsWith('/confirm')), isEmpty);
    expect(r.actions.where((a) => a.endsWith('/submit')), isEmpty);
  });

  testWidgets(
    'recorded approval requires separate checked simulation confirmation',
    (t) async {
      final r = FakeSimulation();
      await mount(t, r);
      await prepare(t);
      await approve(t);
      expect(
        t
            .widget<FilledButton>(find.widgetWithText(FilledButton, '모의 주문 전송'))
            .onPressed,
        isNull,
      );
      await t.tap(find.text('취소').last);
      await t.pumpAndSettle();
      expect(r.actions.where((a) => a.endsWith('/confirm')).length, 1);
      expect(r.actions.where((a) => a.endsWith('/submit')), isEmpty);
    },
  );

  testWidgets(
    'pending transmission blocks clicks and unknown survives reload without repost',
    (t) async {
      final r = FakeSimulation()..pending = Completer<Map<String, dynamic>>();
      await mount(t, r);
      await prepare(t);
      await approve(t);
      await transmit(t);
      expect(r.actions.where((a) => a.endsWith('/submit')).length, 1);
      expect(
        t
            .widget<FilledButton>(
              find.widgetWithText(FilledButton, '모의 주문 검증·승인'),
            )
            .onPressed,
        isNull,
      );
      r.commands.last['status'] = 'UNKNOWN';
      r.state['blocked'] = true;
      r.pending!.complete(r.snapshot());
      await t.pumpAndSettle();
      await t.tap(find.byTooltip('모의 세션 새로고침'));
      await t.pumpAndSettle();
      expect(r.actions.where((a) => a.endsWith('/submit')).length, 1);
      expect(find.textContaining('UNKNOWN'), findsOneWidget);
      await t.pumpWidget(const SizedBox());
      await mount(t, r);
      expect(find.textContaining('UNKNOWN'), findsOneWidget);
      expect(
        t
            .widget<FilledButton>(
              find.widgetWithText(FilledButton, '모의 주문 검증·승인'),
            )
            .onPressed,
        isNull,
      );
    },
  );

  testWidgets('result failure shows durable SENDING without retry', (t) async {
    final r = FakeSimulation()..failResult = true;
    await mount(t, r);
    await prepare(t);
    await approve(t);
    await transmit(t);
    await t.pumpAndSettle();
    expect(find.textContaining('SENDING'), findsOneWidget);
    expect(r.actions.where((a) => a.endsWith('/submit')).length, 1);
    expect(
      t
          .widget<FilledButton>(
            find.widgetWithText(FilledButton, '모의 주문 검증·승인'),
          )
          .onPressed,
      isNull,
    );
  });

  testWidgets(
    'stored receipt recovery is checked and clears lost submit marker after reload',
    (t) async {
      final r = FakeSimulation()..failResult = true;
      await mount(t, r);
      await prepare(t);
      await approve(t);
      await transmit(t);
      await t.pumpAndSettle();
      await t.ensureVisible(find.text('기록으로 결과 복구'));
      await t.tap(find.text('기록으로 결과 복구'));
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
      await t.tap(find.widgetWithText(FilledButton, '기록으로 결과 복구'));
      await t.pumpAndSettle();
      expect(r.actions.where((a) => a.endsWith('/recover')).length, 1);
      expect(r.actions.where((a) => a.endsWith('/submit')).length, 1);
      expect(r.commands.last['sendCount'], 1);
      expect(
        t
            .widget<FilledButton>(
              find.widgetWithText(FilledButton, '모의 주문 검증·승인'),
            )
            .onPressed,
        isNotNull,
      );
    },
  );

  testWidgets(
    'lost recovery response uses GET proof to clear submit marker without repost',
    (t) async {
      final r = FakeSimulation()
        ..failResult = true
        ..loseRecoveryResponse = true;
      await mount(t, r);
      await prepare(t);
      await approve(t);
      await transmit(t);
      await t.pumpAndSettle();
      await t.ensureVisible(find.text('기록으로 결과 복구'));
      await t.tap(find.text('기록으로 결과 복구'));
      await t.pump(const Duration(milliseconds: 400));
      await t.tap(find.byType(CheckboxListTile));
      await t.pump(const Duration(milliseconds: 100));
      await t.tap(find.widgetWithText(FilledButton, '기록으로 결과 복구'));
      await t.pumpAndSettle();
      expect(r.actions.where((a) => a.endsWith('/recover')).length, 1);
      expect(r.commands.last['status'], 'ACCEPTED');
      expect(
        t
            .widget<FilledButton>(
              find.widgetWithText(FilledButton, '모의 주문 검증·승인'),
            )
            .onPressed,
        isNotNull,
      );
    },
  );

  for (final phase in ['RESERVED', 'DISPATCHING', 'LEGACY_UNVERIFIED']) {
    testWidgets('$phase simulation remains blocked without recovery button', (
      t,
    ) async {
      final r = FakeSimulation();
      r.commands.add(command('c1', 'SENDING')..['dispatchPhase'] = phase);
      r.state['blocked'] = true;
      await mount(t, r);
      await t.drag(find.byType(ListView), const Offset(0, -400));
      await t.pumpAndSettle();
      expect(find.text('기록으로 결과 복구'), findsNothing);
      expect(r.actions, isEmpty);
    });
  }

  testWidgets('manual fill and cancel use only the selected simulated order', (
    t,
  ) async {
    final r = FakeSimulation();
    r.commands.add(command('c1', 'ACCEPTED'));
    await mount(t, r);
    await t.ensureVisible(find.text('1주 가상 체결'));
    await t.tap(find.text('1주 가상 체결'));
    await t.pumpAndSettle();
    expect(r.actions.last, 'orders/0000000001/fill');
    await t.ensureVisible(find.text('전부 취소 검토'));
    await t.tap(find.text('전부 취소 검토'));
    await t.pump(const Duration(milliseconds: 400));
    expect(r.lastPreparation?['kind'], 'CANCEL');
    expect(r.lastPreparation?['parentId'], 'c1');
    await approve(t);
    await transmit(t);
    await t.pumpAndSettle();
    expect(r.actions.last, 'commands/c2/submit');
  });

  test(
    'HTTP simulation route stays separate and never retries failed POST',
    () async {
      final calls = <String>[];
      final r = SpringPaperTradingRepository(
        accessToken: '',
        config: ApiConfig(baseUrl: 'http://localhost:8080'),
        client: MockClient((request) async {
          calls.add('${request.method} ${request.url.path}');
          if (request.method == 'POST') {
            return http.Response(
              jsonEncode({
                'success': false,
                'error': {'message': 'SIMULATION failure'},
              }),
              503,
            );
          }
          return http.Response(jsonEncode({'success': true, 'data': []}), 200);
        }),
      );
      await expectLater(
        r.simulationAction('s1', 'commands/c1/submit', {
          'acknowledged': true,
          'confirmation': '모의 주문 전송',
        }),
        throwsException,
      );
      await r.simulationSessions();
      expect(calls, [
        'POST /api/v1/orders/simulations/s1/commands/c1/submit',
        'GET /api/v1/orders/simulations',
      ]);
    },
  );
}

Map<String, dynamic> command(String id, String status) => {
  'id': id,
  'kind': 'NEW',
  'status': status,
  'scenario': 'WAIT',
  'changed': false,
  'sendCount': status == 'ACCEPTED' ? 1 : 0,
  'brokerOrderNo': '0000000001',
  'brokerStatus': 'OPEN',
  'filledQuantity': 0,
  'openQuantity': 2,
  'plan': {
    'stockCode': '005930',
    'stockName': '삼성전자',
    'market': 'KOSPI',
    'side': 'BUY',
    'limitPrice': 75000,
    'quantity': 2,
  },
};

class CompletionFakeSimulation extends FakeSimulation {
  String source = 'SIMULATION';
  Map<String, dynamic> proof() => {
    'source': source,
    'kind': 'NEW',
    'outcome': 'FILLED',
    'stockCode': '005930',
    'side': 'BUY',
    'price': 75000,
    'quantity': 2,
    'filledQuantity': 2,
    'openQuantity': 0,
    'orderNo': '0000000001',
    'parentOrderNo': '',
    'parentState': '',
  };
  @override
  Future<Map<String, dynamic>> simulationAction(
    String id,
    String path,
    Map<String, dynamic> body,
  ) async {
    if (path.endsWith('/completion/prepare')) {
      actions.add(path);
      expect(body, {'orderNo': '0000000001'});
      return {
        'resolutionId': 'resolution',
        'token': 'terminal-token',
        'expiresAt': '2026-11-01T09:01:30',
        'evidence': proof(),
      };
    }
    if (path.endsWith('/completion/confirm')) {
      actions.add(path);
      expect(body, {
        'resolutionId': 'resolution',
        'token': 'terminal-token',
        'acknowledged': true,
        'confirmation': '가상 주문 종결 확정',
      });
      commands.last['resolved'] = true;
      commands.last['completion'] = {
        'resolutionId': 'resolution',
        'source': source,
        'evidence': proof(),
        'confirmedAt': '2026-11-01T09:00:01',
      };
      state['blocked'] = false;
      throw TimeoutException('lost completion response');
    }
    return super.simulationAction(id, path, body);
  }
}

class FakeSimulation
    implements OrderSimulationRepository, PaperTradingRepository {
  bool exists = true;
  bool failResult = false;
  bool loseRecoveryResponse = false;
  num? createdCash;
  final actions = <String>[];
  Map<String, dynamic>? lastPreparation;
  Completer<Map<String, dynamic>>? pending;
  final Map<String, dynamic> state = {
    'mode': 'SIMULATION',
    'sessionId': 's1',
    'revision': 1,
    'cash': 10000000,
    'availableCash': 10000000,
    'positions': <String, dynamic>{},
    'quotes': {'KOSPI:005930': 75000},
    'commands': <Map<String, dynamic>>[],
    'events': [],
    'blocked': false,
  };
  List<Map<String, dynamic>> get commands =>
      state['commands'] as List<Map<String, dynamic>>;
  Map<String, dynamic> snapshot() =>
      jsonDecode(jsonEncode(state)) as Map<String, dynamic>;
  @override
  Future<List<Map<String, dynamic>>> simulationSessions() async => exists
      ? [
          {'sessionId': 's1', 'createdAt': '2026-10-31T12:00:00'},
        ]
      : [];
  @override
  Future<Map<String, dynamic>> createSimulation(num cash) async {
    exists = true;
    createdCash = cash;
    return snapshot();
  }

  @override
  Future<Map<String, dynamic>> simulation(String id) async => snapshot();
  @override
  Future<Map<String, dynamic>> simulationAction(
    String id,
    String path,
    Map<String, dynamic> body,
  ) async {
    actions.add(path);
    if (path == 'commands/prepare') {
      lastPreparation = body;
      final c = command('c${commands.length + 1}', 'PREPARED')
        ..['plan'] = body['plan']
        ..['kind'] = body['kind'];
      commands.add(c);
      return {
        'mode': 'SIMULATION',
        'commandId': c['id'],
        'token': 'test-token',
        'snapshot': snapshot(),
      };
    }
    if (path.endsWith('/confirm')) commands.last['status'] = 'READY';
    if (path.endsWith('/submit')) {
      commands.last['sendCount'] = 1;
      if (failResult) {
        commands.last['status'] = 'SENDING';
        commands.last['dispatchPhase'] = 'RETURNED';
        commands.last['recoverable'] = true;
        commands.last['receipt'] = {
          'status': 'ACCEPTED',
          'orderNo': '0000000001',
        };
        state['blocked'] = true;
        throw Exception('SIMULATION result failure');
      }
      if (pending != null) return pending!.future;
      commands.last['status'] = 'ACCEPTED';
    }
    if (path.endsWith('/recover')) {
      expect(body, {'acknowledged': true, 'confirmation': '저장된 전송 결과 복구'});
      commands.last['status'] = 'ACCEPTED';
      commands.last['recoverable'] = false;
      state['blocked'] = false;
      if (loseRecoveryResponse) throw TimeoutException('test lost response');
    }
    return snapshot();
  }

  @override
  Future<PaperTradingSnapshot> fetchSnapshot() async =>
      throw const PaperTradingRepositoryException(
        '자본금 설정 필요',
        code: 'PAPER_CAPITAL_REQUIRED',
      );
  @override
  Future<PaperTradingSnapshot> buyFromRecommendation(
    int recommendationId,
    double quantity,
  ) => throw UnimplementedError();
  @override
  Future<PaperTradingSnapshot> sellPosition({
    required String stockCode,
    required String market,
    required double quantity,
  }) => throw UnimplementedError();
}
