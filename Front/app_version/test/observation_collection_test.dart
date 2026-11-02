import 'dart:async';
import 'dart:convert';

import 'package:app_version/config/api_config.dart';
import 'package:app_version/models/account_observation.dart';
import 'package:app_version/repositories/account_observation_repository.dart';
import 'package:app_version/repositories/spring_account_observation_repository.dart';
import 'package:app_version/screens/observation_collection_panel.dart';
import 'package:app_version/services/observation_request_journal.dart';
import 'package:app_version/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'fixtures/account_observation_fixtures.dart';

void main() {
  test(
    'status reads metadata only and resume posts the exact receipt once',
    () async {
      final server = _Server();
      final repo = server.repository;
      final status = await repo.collectionStatus();
      expect(status.canResume, isTrue);
      expect(status.enabled, isFalse);
      expect(server.requests.single.method, 'GET');
      expect(
        server.requests.single.url.path,
        '/api/v1/kb/accounts/primary/observations/collection',
      );
      expect(
        server.requests.single.headers['Authorization'],
        'Bearer test-token',
      );
      final resumed = await repo.resumeCollection(beforeObservationId);
      expect(resumed.state, 'IDLE');
      expect(resumed.enabled, isFalse);
      final request = server.requests.last;
      expect(request.method, 'POST');
      expect(
        request.url.path,
        '/api/v1/kb/accounts/primary/observations/collection/resume',
      );
      expect(jsonDecode(request.body), {'lastRequestId': beforeObservationId});
      expect(await repo.outstanding(), isEmpty);
      expect(server.requests, hasLength(2));
    },
  );

  test(
    'resume validates ID before HTTP and prevents concurrent POSTs',
    () async {
      final server = _Server()..wait = Completer<void>();
      final repo = server.repository;
      await expectLater(
        repo.resumeCollection('invalid'),
        throwsA(isA<ObservationRepositoryException>()),
      );
      expect(server.requests, isEmpty);
      final first = repo.resumeCollection(beforeObservationId);
      await expectLater(
        repo.resumeCollection(beforeObservationId),
        throwsA(
          isA<ObservationRepositoryException>().having(
            (e) => e.code,
            'code',
            'BUSY',
          ),
        ),
      );
      server.wait!.complete();
      await first;
      expect(server.requests, hasLength(1));
    },
  );

  test(
    'timeout never retries resume and later verification is GET only',
    () async {
      final requests = <String>[];
      final completer = Completer<http.Response>();
      final repo = SpringAccountObservationRepository(
        accessToken: '',
        localUserId: 1,
        config: ApiConfig(baseUrl: 'http://localhost:8080'),
        journal: MemoryObservationRequestJournal(),
        timeout: const Duration(milliseconds: 10),
        client: MockClient((request) async {
          requests.add(request.method);
          return request.method == 'POST'
              ? completer.future
              : _ok(observationCollectionJson(state: 'IDLE'));
        }),
      );
      await expectLater(
        repo.resumeCollection(beforeObservationId),
        throwsA(
          isA<ObservationRepositoryException>().having(
            (e) => e.code,
            'code',
            'CONNECTION_ERROR',
          ),
        ),
      );
      expect((await repo.collectionStatus()).state, 'IDLE');
      completer.complete(_ok(observationCollectionJson(state: 'IDLE')));
      expect(requests, ['POST', 'GET']);
    },
  );

  test(
    'untrusted collection flags, types, timestamps and states fail closed',
    () {
      for (final change in <Map<String, dynamic>>[
        {'readOnly': false},
        {'usableForTrading': true},
        {'enabled': 'false'},
        {'personalModeEnabled': null},
        {'intervalSeconds': 59},
        {'intervalSeconds': 86401},
        {'intervalSeconds': 900.0},
        {'state': 'FUTURE_STATE'},
        {'activeRequestId': 'invalid'},
        {'activeOrderDate': '20260230'},
        {'lastRequestId': 'invalid'},
        {'lastStorageState': 'NEW'},
        {'lastSnapshotStatus': 'NEW'},
        {'nextDueAt': '2026-11-03T00:16:00'},
      ]) {
        expect(
          () => ObservationCollection.fromJson({
            ...observationCollectionJson(),
            ...change,
          }),
          throwsFormatException,
          reason: change.toString(),
        );
      }
      for (final change in <Map<String, dynamic>>[
        {'state': 'ACTIVE'},
        {'lastStorageState': 'PENDING'},
        {'lastRequestId': null},
        {'completedAt': null},
        {'lastSnapshotStatus': null},
        {'failureCode': 'UNKNOWN'},
        {'connectionConfigured': false},
        {'activeRequestId': afterObservationId},
        {'activeOrderDate': '20261103'},
        {'lastStorageState': 'FAILED', 'lastSnapshotStatus': 'PARTIAL'},
      ]) {
        expect(
          ObservationCollection.fromJson({
            ...observationCollectionJson(state: 'PAUSED'),
            ...change,
          }).canResume,
          isFalse,
          reason: change.toString(),
        );
      }
      expect(
        ObservationCollection.fromJson({
          ...observationCollectionJson(state: 'PAUSED'),
          'lastStorageState': 'FAILED',
          'lastSnapshotStatus': null,
          'failureCode': 'OBSERVATION_FAILED',
        }).canResume,
        isTrue,
      );
    },
  );

  test('mismatched resume receipt does not confirm success', () async {
    final server = _Server()
      ..resumeData = {
        ...observationCollectionJson(state: 'IDLE'),
        'lastRequestId': afterObservationId,
      };
    await expectLater(
      server.repository.resumeCollection(beforeObservationId),
      throwsA(
        isA<ObservationRepositoryException>().having(
          (e) => e.code,
          'code',
          'INVALID_RESPONSE',
        ),
      ),
    );
    expect(server.requests, hasLength(1));
  });

  test(
    'storage and HTTP errors expose fixed messages without upstream text',
    () async {
      for (final entry in <(int, String?, String)>[
        (503, 'OBSERVATION_COLLECTION_STORAGE_UNAVAILABLE', '024'),
        (503, 'OBSERVATION_STORAGE_UNAVAILABLE', '023'),
        (409, null, '변경'),
        (404, null, '배포'),
        (403, null, '권한'),
      ]) {
        final server = _Server()
          ..errorStatus = entry.$1
          ..errorCode = entry.$2;
        try {
          await server.repository.resumeCollection(beforeObservationId);
          fail('must fail');
        } on ObservationRepositoryException catch (e) {
          expect(e.message, contains(entry.$3));
          expect(e.message, isNot(contains('private-upstream')));
        }
        expect(server.requests, hasLength(1));
      }
    },
  );

  Future<void> open(
    WidgetTester tester,
    _Server server, {
    Size size = const Size(1000, 1000),
    double scale = 1,
    ValueChanged<String>? onDetail,
  }) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(textScaler: TextScaler.linear(scale)),
          child: child!,
        ),
        home: Scaffold(
          body: SingleChildScrollView(
            child: ObservationCollectionPanel(
              repository: server.repository,
              refreshRevision: 0,
              onDetail: onDetail,
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  for (final entry in <(String, String)>[
    ('NOT_STARTED', '시작 기록 없음'),
    ('IDLE', '다음 주기 대기'),
    ('ACTIVE', '실행 중 또는 결과 미확정'),
    ('PAUSED', '중단'),
    ('UNCONFIGURED', '연결 설정 필요'),
  ]) {
    testWidgets(
      '${entry.$1} loads GET only and keeps OFF separate from execution',
      (tester) async {
        final server = _Server()
          ..data = observationCollectionJson(state: entry.$1);
        await open(tester, server);
        expect(find.text('서버 수집 설정: OFF'), findsOneWidget);
        expect(find.text('실행 상태: ${entry.$2}'), findsOneWidget);
        expect(server.requests.map((e) => e.method), ['GET']);
        expect(
          find.text('수집 재개'),
          entry.$1 == 'PAUSED' ? findsOneWidget : findsNothing,
        );
        if (entry.$1 == 'IDLE') {
          expect(
            find.text('다음 실행 가능 시각: 2026-11-03 09:16:00 (한국)'),
            findsOneWidget,
          );
        }
        if (entry.$1 == 'ACTIVE') {
          expect(find.textContaining('종료 결과가 미확정'), findsOneWidget);
          await tester.pump(const Duration(days: 10));
          expect(find.text('수집 재개'), findsNothing);
          expect(server.requests, hasLength(1));
        }
        expect(tester.takeException(), isNull);
      },
    );
  }

  testWidgets(
    'explicit resume disables duplicate clicks and keeps server OFF',
    (tester) async {
      final server = _Server()..wait = Completer<void>();
      await open(tester, server);
      expect(find.text('중단 사유: 일부 자료만 확인됐습니다.'), findsOneWidget);
      await tester.tap(find.text('수집 재개'));
      await tester.pump();
      expect(find.text('수집 재개'), findsNothing);
      expect(
        tester
            .widget<TextButton>(find.widgetWithText(TextButton, '수집 상태 확인'))
            .onPressed,
        isNull,
      );
      server.wait!.complete();
      await tester.pumpAndSettle();
      expect(find.text('실행 상태: 다음 주기 대기'), findsOneWidget);
      expect(find.text('서버 수집 설정: OFF'), findsOneWidget);
      expect(server.requests.map((e) => e.method), ['GET', 'POST']);
    },
  );

  testWidgets(
    'lost resume response requires GET confirmation and never repeats POST',
    (tester) async {
      final server = _Server()..loseResponse = true;
      await open(tester, server);
      await tester.tap(find.text('수집 재개'));
      await tester.pumpAndSettle();
      expect(find.textContaining('재개 결과를 확정하지 못했습니다'), findsOneWidget);
      expect(find.text('수집 재개'), findsNothing);
      expect(server.requests.map((e) => e.method), ['GET', 'POST']);
      await tester.tap(find.text('수집 상태 확인'));
      await tester.pumpAndSettle();
      expect(find.text('실행 상태: 다음 주기 대기'), findsOneWidget);
      expect(find.textContaining('현재 다음 주기 대기 상태'), findsOneWidget);
      expect(server.requests.map((e) => e.method), ['GET', 'POST', 'GET']);
    },
  );

  testWidgets('refresh error drops stale PAUSED and retry reads status only', (
    tester,
  ) async {
    final server = _Server();
    await open(tester, server);
    server.errorStatus = 503;
    server.errorCode = 'OBSERVATION_COLLECTION_STORAGE_UNAVAILABLE';
    await tester.tap(find.text('수집 상태 확인'));
    await tester.pumpAndSettle();
    expect(find.textContaining('024'), findsOneWidget);
    expect(find.text('수집 재개'), findsNothing);
    server.errorStatus = null;
    await tester.tap(find.text('수집 상태 확인'));
    await tester.pumpAndSettle();
    expect(find.text('수집 재개'), findsOneWidget);
    expect(server.requests.map((e) => e.method), ['GET', 'GET', 'GET']);
  });

  testWidgets(
    'stale receipt conflict requires status check, not another POST',
    (tester) async {
      final server = _Server();
      await open(tester, server);
      server.errorStatus = 409;
      await tester.tap(find.text('수집 재개'));
      await tester.pumpAndSettle();
      expect(find.textContaining('재개 대상 또는 계좌 연결이 변경'), findsOneWidget);
      expect(find.text('수집 재개'), findsNothing);
      server.errorStatus = null;
      server.data = observationCollectionJson(state: 'ACTIVE');
      await tester.tap(find.text('수집 상태 확인'));
      await tester.pumpAndSettle();
      expect(find.text('실행 상태: 실행 중 또는 결과 미확정'), findsOneWidget);
      expect(find.text('수집 재개'), findsNothing);
      expect(server.requests.map((e) => e.method), ['GET', 'POST', 'GET']);
    },
  );

  testWidgets(
    'unconfirmed terminal metadata disables resume and detail uses existing ID',
    (tester) async {
      final ids = <String>[];
      final server = _Server()
        ..data = {
          ...observationCollectionJson(state: 'PAUSED'),
          'lastStorageState': 'PENDING',
        };
      await open(tester, server, onDetail: ids.add);
      expect(
        tester
            .widget<FilledButton>(find.widgetWithText(FilledButton, '수집 재개'))
            .onPressed,
        isNull,
      );
      await tester.tap(find.text('마지막 관찰 상세'));
      expect(ids, [beforeObservationId]);
      expect(server.requests.map((e) => e.method), ['GET']);
    },
  );

  testWidgets(
    'narrow window with large Korean text and UUID does not overflow',
    (tester) async {
      final server = _Server();
      await open(tester, server, size: const Size(380, 1000), scale: 1.4);
      await tester.ensureVisible(find.text('수집 재개'));
      expect(tester.takeException(), isNull);
      await tester.tap(find.text('수집 재개'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(server.requests.where((e) => e.method == 'POST'), hasLength(1));
    },
  );
}

http.Response _ok(dynamic data) => http.Response(
  jsonEncode({'success': true, 'data': data}),
  200,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

class _Server {
  Map<String, dynamic> data = observationCollectionJson(state: 'PAUSED');
  Map<String, dynamic>? resumeData;
  final requests = <http.Request>[];
  int? errorStatus;
  String? errorCode;
  bool loseResponse = false;
  Completer<void>? wait;
  late final repository = SpringAccountObservationRepository(
    accessToken: 'test-token',
    localUserId: 1,
    config: ApiConfig(baseUrl: 'http://localhost:8080'),
    journal: MemoryObservationRequestJournal(),
    client: MockClient((request) async {
      requests.add(request);
      if (errorStatus != null) {
        return http.Response(
          jsonEncode({
            'error': {'code': errorCode, 'message': 'private-upstream'},
          }),
          errorStatus!,
        );
      }
      if (request.method == 'POST') {
        await wait?.future;
        data = resumeData ?? observationCollectionJson(state: 'IDLE');
        if (loseResponse) throw http.ClientException('private-upstream');
      }
      return _ok(data);
    }),
  );
}
