import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:app_version/config/api_config.dart';
import 'package:app_version/repositories/spring_order_precheck_repository.dart';
import 'package:app_version/repositories/spring_paper_trading_repository.dart';
import 'package:app_version/screens/manual_orders_screen.dart';
import 'package:app_version/screens/order_simulation_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:integration_test/integration_test.dart';

/// 실제 Windows 엔진 → 제품 HTTP repository → 격리 Spring → MySQL.
/// 기본 테스트에서는 실행하지 않으며 전용 runner의 고정 loopback만 허용합니다.
const enabled = bool.fromEnvironment('SAGOPALGO_ORDER_ACCEPTANCE');
const phase = String.fromEnvironment('SAGOPALGO_ACCEPTANCE_PHASE');
const artifactDirectory = String.fromEnvironment(
  'SAGOPALGO_ACCEPTANCE_ARTIFACTS',
);
const origin = 'http://127.0.0.1:18082';

class AcceptanceClient extends http.BaseClient {
  final http.Client inner = http.Client();
  final List<String> requests = [];
  final List<String> created = [];
  String? loseNextSuffix;
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final uri = request.url;
    final simulation = uri.path.startsWith('/api/v1/orders/simulations');
    final readOnlyManual =
        request.method == 'GET' &&
        [
          '/api/v1/orders/manual',
          '/api/v1/orders/readiness',
        ].contains(uri.path);
    if (!enabled || uri.origin != origin || (!simulation && !readOnlyManual)) {
      throw StateError('Acceptance transport refuses this destination/action.');
    }
    request.followRedirects = false;
    requests.add('${request.method} ${uri.path}');
    final response = await http.Response.fromStream(await inner.send(request));
    if (request.method == 'POST' &&
        uri.path == '/api/v1/orders/simulations' &&
        response.statusCode == 200) {
      created.add((jsonDecode(response.body)['data']['sessionId']) as String);
    }
    if (loseNextSuffix != null && uri.path.endsWith(loseNextSuffix!)) {
      loseNextSuffix = null;
      throw TimeoutException(
        'Acceptance: response discarded after real server commit',
      );
    }
    return http.StreamedResponse(
      Stream.value(response.bodyBytes),
      response.statusCode,
      headers: response.headers,
    );
  }

  @override
  void close() {
    inner.close();
    super.close();
  }
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  WidgetController.hitTestWarningShouldBeFatal = true;
  final client = AcceptanceClient();
  final config = ApiConfig(baseUrl: origin);
  final repository = SpringPaperTradingRepository(
    accessToken: '',
    config: config,
    client: client,
  );
  final cases = <String, dynamic>{};
  tearDownAll(client.close);

  Future<void> idle(WidgetTester t) async {
    final deadline = DateTime.now().add(const Duration(seconds: 20));
    do {
      await t.pump(const Duration(milliseconds: 50));
      await Future<void>.delayed(const Duration(milliseconds: 30));
      if (find.byType(AlertDialog).evaluate().isNotEmpty) {
        // 승인 대화상자 동안 배경의 진행 막대가 계속 애니메이션하므로 settle을 기다리지 않습니다.
        await t.pump(const Duration(milliseconds: 350));
        expect(t.takeException(), isNull);
        return;
      }
      if (find.byType(LinearProgressIndicator).evaluate().isEmpty) {
        await t.pumpAndSettle(const Duration(milliseconds: 50));
        expect(t.takeException(), isNull);
        return;
      }
    } while (DateTime.now().isBefore(deadline));
    fail('UI/API did not become idle within 20 seconds');
  }

  Future<void> tap(WidgetTester t, Finder finder) async {
    await t.ensureVisible(finder);
    await t.pump(const Duration(milliseconds: 100));
    await t.tap(finder);
    await idle(t);
  }

  Future<void> screen(WidgetTester t) async {
    await t.pumpWidget(
      MaterialApp(home: OrderSimulationScreen(repository: repository)),
    );
    await idle(t);
  }

  Future<String> create(WidgetTester t, int cash) async {
    await screen(t);
    await tap(t, find.text('새 가상 세션'));
    await t.enterText(find.byType(TextFormField), '$cash');
    await tap(t, find.text('가상 세션 만들기'));
    return client.created.last;
  }

  Future<void> scenario(WidgetTester t, String value) async {
    final dropdown = find.byWidgetPredicate(
      (w) =>
          w is DropdownButton<String> && w.items!.any((i) => i.value == value),
    );
    await tap(t, dropdown);
    final item = find
        .byWidgetPredicate(
          (w) => w is DropdownMenuItem<String> && w.value == value,
        )
        .last;
    await tap(t, find.descendant(of: item, matching: find.byType(Text)).last);
  }

  Future<void> consent(WidgetTester t, String action) async {
    expect(
      t
          .widget<FilledButton>(find.widgetWithText(FilledButton, action))
          .onPressed,
      isNull,
    );
    await tap(t, find.byType(CheckboxListTile));
    await tap(t, find.widgetWithText(FilledButton, action));
  }

  Future<void> submit(WidgetTester t) async {
    await tap(t, find.text('모의 주문 검증·승인'));
    await tap(t, find.text('모의 승인 기록 저장'));
    await consent(t, '모의 주문 전송');
  }

  Map<String, dynamic> command(Map<String, dynamic> state, [int index = 0]) =>
      (state['commands'] as List).cast<Map<String, dynamic>>()[index];
  Future<Map<String, dynamic>> remember(String label, String id) async {
    final state = await repository.simulation(id);
    cases[label] = {'sessionId': id, 'state': state};
    return state;
  }

  Finder card(String kind, int price) => find
      .ancestor(
        of: find.byWidgetPredicate(
          (w) =>
              w is SelectableText &&
              (w.data ?? '').startsWith('$kind · ACCEPTED') &&
              (w.data ?? '').contains('지정가 $price'),
        ),
        matching: find.byType(Card),
      )
      .first;
  Future<void> change(
    WidgetTester t,
    Finder parent,
    String kind,
    int quantity, [
    int? price,
  ]) async {
    await tap(
      t,
      find.descendant(
        of: parent,
        matching: find.text(kind == 'AMEND' ? '지정가 변경 검토' : '수량 취소 검토'),
      ),
    );
    if (price != null) {
      await t.enterText(
        find.byKey(const Key('simulation-change-price')),
        '$price',
      );
    }
    await t.enterText(
      find.byKey(const Key('simulation-change-quantity')),
      '$quantity',
    );
    await tap(t, find.text('검증'));
    await tap(t, find.text('모의 승인 기록 저장'));
    await consent(t, '모의 주문 전송');
  }

  testWidgets(
    'normal UI buy, partial/full fill, sell conserve virtual resources',
    (t) async {
      final id = await create(t, 1000000);
      await submit(t);
      var state = await repository.simulation(id);
      expect(state['availableCash'], 850000);
      expect(state['cash'], 1000000);
      await tap(t, find.text('1주 가상 체결'));
      state = await repository.simulation(id);
      expect(state['cash'], 925000);
      expect(state['positions']['KOSPI:005930'], 1);
      await tap(t, find.text('잔량 가상 체결'));
      state = await repository.simulation(id);
      expect(state['cash'], 850000);
      expect(state['positions']['KOSPI:005930'], 2);
      await tap(t, find.text('매수'));
      await tap(t, find.text('매도').last);
      await scenario(t, 'FULL_FILL');
      await submit(t);
      state = await remember('normal', id);
      expect(state['cash'], 1000000);
      expect(state['positions']['KOSPI:005930'] ?? 0, 0);
      expect(state['blocked'], false);
      expect(
        (state['commands'] as List).every((c) => c['sendCount'] == 1),
        true,
      );
    },
    skip: !enabled || phase != 'before',
  );

  testWidgets(
    'UI partial changes, additional amendment and selected reservation reuse',
    (t) async {
      final id = await create(t, 375000);
      await t.enterText(find.widgetWithText(TextField, '정수 수량'), '5');
      await submit(t);
      await change(t, card('NEW', 75000), 'AMEND', 2, 74000);
      var state = await repository.simulation(id);
      expect(state['availableCash'], 2000);
      await change(t, card('AMEND', 74000), 'AMEND', 1, 76000);
      state = await repository.simulation(id);
      expect(state['availableCash'], 0);
      await change(t, card('NEW', 75000), 'CANCEL', 1);
      state = await remember('partial-changes', id);
      expect(state['cash'], 375000);
      expect(state['availableCash'], 75000);
      expect(state['positions'], isEmpty);
      expect((state['commands'] as List).length, 4);
      expect(
        (state['commands'] as List).every((c) => c['sendCount'] == 1),
        true,
      );
    },
    skip: !enabled || phase != 'before',
  );

  const expected = <String, List<dynamic>>{
    'WAIT': ['ACCEPTED', 'RETURNED', 1, false],
    'PARTIAL_FILL': ['ACCEPTED', 'RETURNED', 1, false],
    'FULL_FILL': ['ACCEPTED', 'RETURNED', 1, false],
    'REJECT': ['REJECTED', 'RETURNED', 1, false],
    'TIMEOUT_BEFORE_ACCEPT': ['UNKNOWN', 'RETURNED', 1, true],
    'TIMEOUT_AFTER_ACCEPT': ['UNKNOWN', 'RETURNED', 1, true],
    'SAVE_FAILURE': ['SENDING', 'RETURNED', 1, true],
    'STOP_BEFORE_SEND': ['SENDING', 'RESERVED', 0, true],
    'JOURNAL_FAILURE': ['SENDING', 'DISPATCHING', 1, true],
    'TIMEOUT_AFTER_OPEN': ['UNKNOWN', 'RETURNED', 1, true],
    'TIMEOUT_AFTER_PARTIAL': ['UNKNOWN', 'RETURNED', 1, true],
  };
  for (final entry in expected.entries) {
    testWidgets('real UI/API/DB scenario ${entry.key}', (t) async {
      final id = await create(t, 1000000);
      await scenario(t, entry.key);
      await submit(t);
      var state = await repository.simulation(id);
      var c = command(state);
      expect([
        c['status'],
        c['dispatchPhase'],
        c['sendCount'],
        state['blocked'],
      ], entry.value);
      final sends = client.requests.where((p) => p.endsWith('/submit')).length;
      await tap(t, find.byTooltip('모의 세션 새로고침'));
      expect(client.requests.where((p) => p.endsWith('/submit')).length, sends);
      if (entry.key == 'SAVE_FAILURE') {
        await tap(t, find.text('기록으로 결과 복구'));
        await consent(t, '기록으로 결과 복구');
        state = await repository.simulation(id);
        expect(command(state)['status'], 'ACCEPTED');
        expect(state['blocked'], false);
      }
      if (entry.key == 'STOP_BEFORE_SEND') {
        await tap(t, find.text('전송 전 가상 예약 중단'));
        await consent(t, '전송 전 예약 중단');
        state = await repository.simulation(id);
        expect(command(state)['dispatchPhase'], 'ABORTED');
        expect(state['blocked'], false);
      }
      if (entry.key == 'TIMEOUT_AFTER_ACCEPT') {
        final cash = state['cash'];
        final positions = Map<String, dynamic>.from(state['positions'] as Map);
        await tap(t, find.text('가상 주문 종결 대조'));
        await t.enterText(find.byType(TextField), c['brokerOrderNo'] as String);
        await tap(t, find.text('가상 종결 근거 확인'));
        await consent(t, '가상 종결 확정');
        await t.pageBack();
        await idle(t);
        state = await repository.simulation(id);
        expect(command(state)['status'], 'UNKNOWN');
        expect(command(state)['resolved'], true);
        expect(state['blocked'], false);
        expect(state['cash'], cash);
        expect(state['positions'], positions);
      }
      if (entry.key == 'TIMEOUT_AFTER_PARTIAL') {
        await tap(t, find.text('미체결·변경 주문 대조'));
        await t.enterText(find.byType(TextField), c['brokerOrderNo'] as String);
        await tap(t, find.text('읽기 전용 대조 준비'));
        await consent(t, '대조 관찰 저장');
        await t.pageBack();
        await idle(t);
        state = await repository.simulation(id);
        expect(command(state)['reviews'], hasLength(1));
        expect(state['blocked'], true);
      }
      if (entry.key == 'JOURNAL_FAILURE') {
        await tap(t, find.text('가상 주문번호로 잠금 유지 진단'));
        await t.enterText(find.byType(TextField), c['brokerOrderNo'] as String);
        await consent(t, '조회·진단 기록');
        await t.pageBack();
        await idle(t);
        state = await repository.simulation(id);
        expect(command(state)['diagnostics'], hasLength(1));
        expect(state['blocked'], true);
      }
      state = await remember(entry.key, id);
      c = command(state);
      expect(c['sendCount'], entry.value[2]);
      final button = t.widget<FilledButton>(
        find.widgetWithText(FilledButton, '모의 주문 검증·승인'),
      );
      expect(button.onPressed == null, state['blocked']);
    }, skip: !enabled || phase != 'before');
  }
  testWidgets(
    'discarded actual submit response rereads saved result without retry',
    (t) async {
      final id = await create(t, 1000000);
      client.loseNextSuffix = '/submit';
      await submit(t);
      final state = await remember('lost-http-response', id);
      expect(command(state)['status'], 'ACCEPTED');
      expect(command(state)['sendCount'], 1);
      expect(
        client.requests
            .where(
              (p) =>
                  p.startsWith('POST ') &&
                  p.contains('/$id/') &&
                  p.endsWith('/submit'),
            )
            .length,
        1,
      );
      expect(
        t
            .widget<FilledButton>(
              find.widgetWithText(FilledButton, '모의 주문 검증·승인'),
            )
            .onPressed,
        isNotNull,
      );
    },
    skip: !enabled || phase != 'before',
  );

  testWidgets(
    'live order OFF screen only reads and blocks approval and transport',
    (t) async {
      final count = client.requests.length;
      final manual = SpringOrderPrecheckRepository(
        accessToken: '',
        config: config,
        client: client,
      );
      await t.pumpWidget(
        MaterialApp(
          home: ManualOrdersScreen(repository: manual, manual: manual),
        ),
      );
      await idle(t);
      expect(
        t
            .widget<FilledButton>(
              find.widgetWithText(FilledButton, '안전 조건 검증 및 주문안 확인'),
            )
            .onPressed,
        isNull,
      );
      expect(
        client.requests.skip(count).every((p) => p.startsWith('GET ')),
        true,
      );
    },
    skip: !enabled || phase != 'before',
  );

  testWidgets('save persisted acceptance evidence', (t) async {
    expect(cases.length, 14);
    final current = <String, dynamic>{};
    for (final entry in cases.entries) {
      final row = entry.value as Map<String, dynamic>;
      current[entry.key] = {
        'sessionId': row['sessionId'],
        'state': await repository.simulation(row['sessionId'] as String),
      };
    }
    await Directory(artifactDirectory).create(recursive: true);
    await File(
      '$artifactDirectory/before-restart.json',
    ).writeAsString(jsonEncode(current));
  }, skip: !enabled || phase != 'before');

  testWidgets(
    'new Windows process reads exactly the persisted sessions after JVM restart',
    (t) async {
      final before =
          jsonDecode(
                await File(
                  '$artifactDirectory/before-restart.json',
                ).readAsString(),
              )
              as Map<String, dynamic>;
      for (final entry in before.entries) {
        final row = entry.value as Map<String, dynamic>;
        final actual = await repository.simulation(row['sessionId'] as String);
        expect(actual, equals(row['state']), reason: entry.key);
      }
      await screen(t);
      expect(find.text('SIMULATION · 실제 주문 전송 없음'), findsOneWidget);
      for (final label in [
        'normal',
        'JOURNAL_FAILURE',
        'STOP_BEFORE_SEND',
        'TIMEOUT_AFTER_PARTIAL',
      ]) {
        final row = before[label] as Map<String, dynamic>;
        final id = row['sessionId'] as String;
        final dropdown = find.byWidgetPredicate(
          (w) =>
              w is DropdownButton<String> && w.items!.any((i) => i.value == id),
        );
        final selector = t.widget<DropdownButton<String>>(dropdown);
        final targetIndex = selector.items!.indexWhere((i) => i.value == id);
        final currentIndex = selector.items!.indexWhere(
          (i) => i.value == selector.value,
        );
        await tap(t, dropdown);
        await t.scrollUntilVisible(
          find.textContaining(id.split('-').first),
          targetIndex < currentIndex ? -180 : 180,
          scrollable: find.byType(Scrollable).last,
          maxScrolls: 25,
        );
        await tap(t, find.textContaining(id.split('-').first).last);
        final button = t.widget<FilledButton>(
          find.widgetWithText(FilledButton, '모의 주문 검증·승인'),
        );
        expect(
          button.onPressed == null,
          row['state']['blocked'],
          reason: label,
        );
      }
      expect(client.requests.every((p) => p.startsWith('GET ')), true);
      await File('$artifactDirectory/after-restart.json').writeAsString(
        jsonEncode({'sessions': before.length, 'getOnly': true, 'equal': true}),
      );
    },
    skip: !enabled || phase != 'after',
  );
}
