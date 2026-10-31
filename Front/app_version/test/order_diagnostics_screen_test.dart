import 'dart:async';
import 'dart:convert';
import 'package:app_version/config/api_config.dart';
import 'package:app_version/repositories/spring_order_precheck_repository.dart';
import 'package:app_version/screens/order_diagnostics_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  Future<void> mount(
    WidgetTester t,
    DiagnosticFake r, {
    bool allowNew = true,
  }) async {
    await t.pumpWidget(
      MaterialApp(
        home: OrderDiagnosticsScreen(
          summary: '삼성전자 005930 · 매수 · 2주',
          load: r.load,
          diagnose: r.diagnose,
          simulation: true,
          allowNew: allowNew,
        ),
      ),
    );
    await t.pumpAndSettle();
  }

  Future<void> enter(WidgetTester t) async {
    await t.enterText(find.byType(TextField), '0040000638');
    await t.tap(find.byType(CheckboxListTile));
    await t.pump();
  }

  FilledButton button(WidgetTester t) =>
      t.widget<FilledButton>(find.widgetWithText(FilledButton, '조회·진단 기록'));
  testWidgets(
    'opening only loads history and requires number and acknowledgment',
    (t) async {
      final r = DiagnosticFake();
      await mount(t, r);
      expect(r.posts, 0);
      expect(r.gets, 1);
      expect(button(t).onPressed, isNull);
      await t.enterText(find.byType(TextField), '0040000638');
      await t.pump();
      expect(button(t).onPressed, isNull);
      await t.tap(find.byType(CheckboxListTile));
      await t.pump();
      expect(button(t).onPressed, isNotNull);
      await t.enterText(find.byType(TextField), '0000000000');
      await t.pump();
      expect(button(t).onPressed, isNull);
    },
  );
  testWidgets(
    'one explicit read while busy and matched fields never expose unlock action',
    (t) async {
      final r = DiagnosticFake()..pending = Completer<Map<String, dynamic>>();
      await mount(t, r);
      await enter(t);
      await t.tap(find.text('조회·진단 기록'));
      await t.pump();
      expect(r.posts, 1);
      expect(button(t).onPressed, isNull);
      expect(
        r.ids.single,
        matches(
          RegExp(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
          ),
        ),
      );
      r.pending!.complete(record(r.ids.single));
      await t.pumpAndSettle();
      await t.ensureVisible(find.text('주문 항목 일치 · 전송 종료 확정 아님'));
      expect(find.text('주문 항목 일치 · 전송 종료 확정 아님'), findsOneWidget);
      expect(find.text('기록으로 결과 복구'), findsNothing);
      expect(find.text('실제 주문 전송'), findsNothing);
      expect(r.posts, 1);
    },
  );
  testWidgets(
    'lost response uses GET without automatically posting diagnostic again',
    (t) async {
      final r = DiagnosticFake()..lostResponse = true;
      await mount(t, r);
      await enter(t);
      await t.tap(find.text('조회·진단 기록'));
      await t.pumpAndSettle();
      expect(r.posts, 1);
      expect(button(t).onPressed, isNull);
      await t.tap(find.byTooltip('진단 이력 새로고침'));
      await t.pumpAndSettle();
      expect(r.posts, 1);
      expect(r.gets, 2);
      expect(button(t).onPressed, isNotNull);
    },
  );
  testWidgets('requested without completed result stays pending after reread', (
    t,
  ) async {
    final r = DiagnosticFake()
      ..lostResponse = true
      ..requested = true;
    await mount(t, r);
    await enter(t);
    await t.tap(find.text('조회·진단 기록'));
    await t.pumpAndSettle();
    await t.tap(find.byTooltip('진단 이력 새로고침'));
    await t.pumpAndSettle();
    expect(r.posts, 1);
    expect(button(t).onPressed, isNull);
    expect(find.textContaining('조회 진행·중단'), findsOneWidget);
  });
  testWidgets(
    'missing storage prevents new diagnosis and history view cannot submit',
    (t) async {
      final r = DiagnosticFake()..loadFailure = true;
      await mount(t, r);
      await enter(t);
      expect(button(t).onPressed, isNull);
      expect(find.textContaining('020'), findsOneWidget);
      expect(r.posts, 0);
      await t.pumpWidget(const SizedBox());
      r.loadFailure = false;
      await mount(t, r, allowNew: false);
      expect(find.byType(TextField), findsNothing);
      expect(find.text('조회·진단 기록'), findsNothing);
      expect(r.posts, 0);
    },
  );
  testWidgets('diagnosis report fits narrow window with enlarged text', (
    t,
  ) async {
    await t.binding.setSurfaceSize(const Size(360, 720));
    addTearDown(() => t.binding.setSurfaceSize(null));
    final r = DiagnosticFake()..records = [record('test-id')];
    await t.pumpWidget(
      MaterialApp(
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(textScaler: const TextScaler.linear(1.4)),
          child: child!,
        ),
        home: OrderDiagnosticsScreen(
          summary: '삼성전자 005930 · 매수 · 2주',
          load: r.load,
          diagnose: r.diagnose,
        ),
      ),
    );
    await t.pumpAndSettle();
    expect(t.takeException(), isNull);
    await t.drag(find.byType(ListView), const Offset(0, -650));
    await t.pumpAndSettle();
    expect(t.takeException(), isNull);
  });
  test(
    'HTTP diagnostic route uses its own acknowledgment and failure never retries',
    () async {
      final calls = <String>[];
      final r = SpringOrderPrecheckRepository(
        accessToken: '',
        config: ApiConfig(baseUrl: 'http://localhost:8080'),
        client: MockClient((request) async {
          calls.add('${request.method} ${request.url.path}');
          if (request.method == 'POST') {
            expect(jsonDecode(request.body), {
              'diagnosticId': 'test-id',
              'orderNo': '0040000638',
              'acknowledged': true,
              'confirmation': '잠금 유지 진단',
            });
            return http.Response(
              jsonEncode({
                'success': false,
                'error': {'message': 'diagnostic failed'},
              }),
              503,
            );
          }
          return http.Response(jsonEncode({'success': true, 'data': []}), 200);
        }),
      );
      await expectLater(
        r.diagnoseSending('command', 'test-id', '0040000638'),
        throwsException,
      );
      await r.diagnosticHistory('command');
      expect(calls, [
        'POST /api/v1/orders/manual/command/diagnostics',
        'GET /api/v1/orders/manual/command/diagnostics',
      ]);
    },
  );
}

Map<String, dynamic> record(String id) => {
  'diagnosticId': id,
  'commandId': 'command',
  'orderNo': '0040000638',
  'phaseBefore': 'DISPATCHING',
  'state': 'COMPLETED',
  'createdAt': '2026-10-31T12:00:00',
  'completedAt': '2026-10-31T12:00:01',
  'report': {
    'assessment': 'FIELDS_MATCH',
    'phaseAfter': 'DISPATCHING',
    'commandStatusAfter': 'SENDING',
    'pagesScanned': 1,
    'checks': [
      {'code': 'QUANTITY', 'passed': true},
    ],
    'observation': {
      'stockCode': '005930',
      'status': 'FILLED',
      'orderTime': '120000',
      'price': 75000,
      'quantity': 2,
      'filledQuantity': 2,
      'openQuantity': 0,
    },
    'message': '진단만 저장했습니다. 주문 상태와 잠금은 변경하지 않습니다.',
  },
};

class DiagnosticFake {
  int gets = 0;
  int posts = 0;
  bool lostResponse = false;
  bool requested = false;
  bool loadFailure = false;
  final ids = <String>[];
  List<Map<String, dynamic>> records = [];
  Completer<Map<String, dynamic>>? pending;
  Future<List<Map<String, dynamic>>> load() async {
    gets++;
    if (loadFailure) throw Exception('020 저장소 확인');
    return records;
  }

  Future<Map<String, dynamic>> diagnose(String id, String number) async {
    posts++;
    ids.add(id);
    expect(number, '0040000638');
    if (pending != null) return pending!.future;
    final result = record(id);
    if (requested) {
      result['state'] = 'REQUESTED';
      result['report'] = null;
      result['completedAt'] = null;
    }
    records = [result];
    if (lostResponse) throw TimeoutException('test lost response');
    return result;
  }
}
