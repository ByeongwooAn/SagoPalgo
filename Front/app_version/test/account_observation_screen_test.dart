import 'dart:async';
import 'dart:convert';

import 'package:app_version/config/api_config.dart';
import 'package:app_version/models/account_observation.dart';
import 'package:app_version/repositories/spring_account_observation_repository.dart';
import 'package:app_version/screens/account_observation_screen.dart';
import 'package:app_version/services/observation_request_journal.dart';
import 'package:app_version/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'fixtures/account_observation_fixtures.dart';

void main() {
  Future<void> open(
    WidgetTester tester,
    _Server server, {
    Size size = const Size(1000, 1600),
    Key? key,
  }) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: AccountObservationScreen(
          key: key,
          repository: server.repository(),
          initialDate: DateTime(2026, 11, 2),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets(
    'opening empty history performs GET and does not capture automatically',
    (tester) async {
      final server = _Server();
      await open(tester, server);
      expect(find.textContaining('저장 이력이 없습니다'), findsOneWidget);
      expect(server.posts, 0);
      expect(server.methods, ['GET']);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('capture disables duplicate clicks and opens stored detail', (
    tester,
  ) async {
    final server = _Server()..wait = Completer<void>();
    await open(tester, server);
    await tester.tap(find.text('새 관찰 저장'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 30));
    expect(
      tester
          .widget<FilledButton>(find.widgetWithText(FilledButton, '새 관찰 저장'))
          .onPressed,
      isNull,
    );
    expect(server.posts, 1);
    server.wait!.complete();
    await tester.pumpAndSettle();
    expect(find.text('관찰 상세'), findsOneWidget);
    expect(find.text('저장 상태: 저장 완료'), findsOneWidget);
    expect(server.posts, 1);
    expect(await server.repository().outstanding(), isEmpty);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'lost response survives screen recreation and stored status recovery uses GET only',
    (tester) async {
      final server = _Server()..loseResponse = true;
      await open(tester, server);
      await tester.tap(find.text('새 관찰 저장'));
      await tester.pumpAndSettle();
      expect(find.text('결과 확인이 필요한 요청 1건'), findsOneWidget);
      final request = (await server.repository().outstanding()).single;
      await open(tester, server, key: const ValueKey('reopened'));
      expect(find.text('결과 확인이 필요한 요청 1건'), findsOneWidget);
      await tester.tap(find.text('저장 상태 확인'));
      await tester.pumpAndSettle();
      expect(find.text('관찰 상세'), findsOneWidget);
      expect(server.detailIds.last, request.requestId);
      await tester.tap(find.text('체결기준 잔고'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('삼성전자 · 005930'));
      await tester.tap(find.text('삼성전자 · 005930'));
      await tester.pumpAndSettle();
      expect(find.text('보유수량(P6): 0.123456'), findsOneWidget);
      expect(find.text('현재가: 값 미제공'), findsOneWidget);
      await tester.pageBack();
      await tester.pumpAndSettle();
      expect(find.text('결과 확인이 필요한 요청 1건'), findsNothing);
      expect(server.posts, 1);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'pending and not found retain request and retry status never submits POST',
    (tester) async {
      final server = _Server()..pending = true;
      await open(tester, server);
      await tester.tap(find.text('새 관찰 저장'));
      await tester.pumpAndSettle();
      expect(find.text('저장 상태: 결과 대기'), findsOneWidget);
      server.missingDetail = true;
      await tester.tap(find.byTooltip('저장 상태 다시 확인'));
      await tester.pumpAndSettle();
      expect(find.textContaining('현재 연결에서 관찰 기록을 찾지 못했습니다'), findsOneWidget);
      await tester.tap(find.widgetWithText(FilledButton, '저장 상태 다시 확인'));
      await tester.pumpAndSettle();
      expect(server.posts, 1);
      expect(server.detailIds, hasLength(2));
      expect(await server.repository().outstanding(), hasLength(1));
    },
  );

  testWidgets(
    'two selected observations show partial blocking and exact numeric change',
    (tester) async {
      final server = _Server()..seed();
      await open(tester, server);
      final selectors = find.byType(DropdownButtonFormField<String>);
      await tester.ensureVisible(selectors.first);
      await tester.tap(selectors.first);
      await tester.pumpAndSettle();
      await tester.tap(
        find.textContaining(beforeObservationId.substring(0, 8)).last,
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(selectors.last);
      await tester.tap(selectors.last);
      await tester.pumpAndSettle();
      await tester.tap(
        find.textContaining(afterObservationId.substring(0, 8)).last,
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('선택한 관찰 비교'));
      await tester.tap(find.text('선택한 관찰 비교'));
      await tester.pumpAndSettle();
      expect(find.text('관찰 비교'), findsOneWidget);
      expect(find.text('조회 날짜·필터·기준 등 조회 범위가 다릅니다.'), findsOneWidget);
      await tester.tap(find.text('체결기준 잔고'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('같은 행의 필드 변화'));
      await tester.tap(find.text('같은 행의 필드 변화'));
      await tester.pumpAndSettle();
      expect(find.text('변화량: 0.000001'), findsOneWidget);
      expect(find.text('이전: 필드 없음 → 이후: 값 미제공'), findsOneWidget);
      expect(server.posts, 0);
      expect(server.comparisons, 1);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'pagination uses server cursor, preserves list on failure, and can retry',
    (tester) async {
      final server = _Server()..paginate = true;
      await open(tester, server);
      expect(find.text('이전 이력 더 보기'), findsOneWidget);
      server.failMore = true;
      await tester.ensureVisible(find.text('이전 이력 더 보기'));
      await tester.tap(find.text('이전 이력 더 보기'));
      await tester.pumpAndSettle();
      expect(find.text('관찰 상세'), findsOneWidget);
      server.failMore = false;
      await tester.ensureVisible(find.text('이전 이력 더 보기'));
      await tester.tap(find.text('이전 이력 더 보기'));
      await tester.pumpAndSettle();
      expect(find.text('관찰 상세'), findsNWidgets(2));
      expect(server.cursors, [null, '5', '5']);
      expect(server.posts, 0);
    },
  );

  testWidgets('narrow detail renders long decimal values without overflow', (
    tester,
  ) async {
    final server = _Server()
      ..details[beforeObservationId] = observationDetailJson(
        beforeObservationId,
        quantity: '999999999999999999999999999999.123456',
      );
    tester.view.physicalSize = const Size(380, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.dark,
        home: ObservationDetailScreen(
          repository: server.repository(),
          requestId: beforeObservationId,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('체결기준 잔고'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('삼성전자 · 005930'));
    await tester.tap(find.text('삼성전자 · 005930'));
    await tester.pumpAndSettle();
    expect(
      find.text('보유수량(P6): 999999999999999999999999999999.123456'),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'journal unavailable disables new capture while keeping history readable',
    (tester) async {
      final server = _Server()..journal = _UnavailableJournal();
      await open(tester, server);
      expect(
        tester
            .widget<FilledButton>(find.widgetWithText(FilledButton, '새 관찰 저장'))
            .onPressed,
        isNull,
      );
      expect(find.textContaining('복구 기록을 읽을 수 없습니다'), findsOneWidget);
      expect(server.posts, 0);
    },
  );
}

class _UnavailableJournal extends MemoryObservationRequestJournal {
  @override
  Future<List<ObservationRequest>> load(String context) async =>
      throw StateError('private path');
}

class _Server {
  ObservationRequestJournal journal = MemoryObservationRequestJournal();
  final details = <String, Map<String, dynamic>>{};
  final methods = <String>[], detailIds = <String>[];
  final cursors = <String?>[];
  int posts = 0, comparisons = 0;
  bool loseResponse = false,
      pending = false,
      missingDetail = false,
      paginate = false,
      failMore = false;
  Completer<void>? wait;
  void seed() {
    details[beforeObservationId] = observationDetailJson(beforeObservationId);
    details[afterObservationId] = observationDetailJson(
      afterObservationId,
      minute: 1,
    );
  }

  SpringAccountObservationRepository repository() =>
      SpringAccountObservationRepository(
        accessToken: '',
        localUserId: 1,
        config: ApiConfig(baseUrl: 'http://localhost:8080'),
        journal: journal,
        client: MockClient((request) async {
          methods.add(request.method);
          if (request.method == 'POST') {
            posts++;
            await wait?.future;
            final id = (jsonDecode(request.body) as Map)['requestId'] as String;
            details[id] = observationDetailJson(
              id,
              state: pending ? 'PENDING' : 'COMPLETED',
            );
            if (loseResponse) throw http.ClientException('lost response');
            return _ok(details[id]);
          }
          if (request.url.path.endsWith('/comparison')) {
            comparisons++;
            return _ok(observationComparisonJson(blocked: true));
          }
          if (request.url.path.endsWith('/observations')) {
            final cursor = request.url.queryParameters['beforeId'];
            cursors.add(cursor);
            if (paginate) {
              if (cursor != null && failMore) return http.Response('{}', 503);
              return _ok({
                'items': [
                  observationSummaryJson(
                    cursor == null ? afterObservationId : beforeObservationId,
                  ),
                ],
                if (cursor == null) 'nextBeforeId': 5,
              });
            }
            return _ok({
              'items': details.values
                  .toList()
                  .reversed
                  .map(
                    (value) =>
                        Map<String, dynamic>.from(value)..remove('observation'),
                  )
                  .toList(),
            });
          }
          final id = request.url.pathSegments.last;
          detailIds.add(id);
          if (missingDetail || !details.containsKey(id)) {
            return http.Response('{}', 404);
          }
          return _ok(details[id]);
        }),
      );
  http.Response _ok(dynamic data) => http.Response(
    jsonEncode({'success': true, 'data': data}),
    200,
    headers: {'content-type': 'application/json; charset=utf-8'},
  );
}
