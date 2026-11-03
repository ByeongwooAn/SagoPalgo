import 'dart:async';
import 'dart:convert';
import 'package:app_version/config/api_config.dart';
import 'package:app_version/models/market_realtime.dart';
import 'package:app_version/models/market_candle.dart';
import 'package:app_version/models/research_feed.dart';
import 'package:app_version/repositories/market_data_repository.dart';
import 'package:app_version/repositories/realtime_market_repository.dart';
import 'package:app_version/repositories/spring_realtime_market_repository.dart';
import 'package:app_version/repositories/spring_research_feed_repository.dart';
import 'package:app_version/screens/market_realtime_screen.dart';
import 'package:app_version/screens/market_candle_screen.dart';
import 'package:app_version/screens/research_changes_screen.dart';
import 'package:app_version/screens/research_timeline_screen.dart';
import 'package:app_version/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'fixtures/realtime_pipeline_fixtures.dart';

void main() {
  final config = ApiConfig(baseUrl: 'http://localhost:8080');
  test(
    'real-time model preserves decimal strings, integer volume and timestamps',
    () {
      final snapshot = MarketRealtimeSnapshot.fromJson(realtimeJson());
      expect(snapshot.trade!.price, '100.123456');
      expect(snapshot.minutes.single.volume, '100000000000000000001');
      expect(snapshot.quote!.asks.length, 10);
      expect(snapshot.checkedAt.isUtc, isTrue);
    },
  );
  test('unsafe real-time contract and symbol mismatch fail closed', () {
    for (final change in <Map<String, dynamic>>[
      {'usableForTrading': true},
      {'exchange': 'NXT'},
      {'state': 'UNKNOWN'},
      {'enabled': 'false'},
      {'contractVersion': 'OTHER'},
      {'checkedAt': '2026-11-03T01:00:00'},
      {'trade': null},
    ]) {
      expect(
        () => MarketRealtimeSnapshot.fromJson({...realtimeJson(), ...change}),
        throwsA(isA<Object>()),
      );
    }
    final json = realtimeJson();
    (json['trade'] as Map)['price'] = 100.5;
    expect(() => MarketRealtimeSnapshot.fromJson(json), throwsFormatException);
  });
  test(
    'split UTF8 SSE frames decode, use GET and cancel the connection',
    () async {
      var bodyCancelled = false;
      final body = StreamController<List<int>>(
        onCancel: () => bodyCancelled = true,
      );
      final client = _StreamClient(body.stream);
      final repo = SpringRealtimeMarketRepository(
        accessToken: 'token',
        config: config,
        clientFactory: () => client,
      );
      final future = repo.watch('005930').first;
      final bytes = utf8.encode(
        'event: snapshot\r\ndata: ${jsonEncode({...realtimeJson(), 'diagnostic': '정상'})}\r\n\r\n',
      );
      for (var i = 0; i < bytes.length; i += 7) {
        body.add(bytes.sublist(i, (i + 7).clamp(0, bytes.length)));
      }
      final value = await future;
      expect(value.trade!.price, '100.123456');
      expect(client.requests.single.method, 'GET');
      expect(client.requests.single.headers['Authorization'], 'Bearer token');
      await Future<void>.delayed(Duration.zero);
      expect(client.closed, isTrue);
      expect(bodyCancelled, isTrue);
      await body.close();
    },
  );
  test(
    'SSE invalid response is reduced to fixed error and never POSTed',
    () async {
      final client = _StreamClient(
        Stream.value(
          utf8.encode(
            'event: snapshot\ndata: {"secret":"private-message"}\n\n',
          ),
        ),
      );
      final repo = SpringRealtimeMarketRepository(
        accessToken: '',
        config: config,
        clientFactory: () => client,
      );
      await expectLater(
        repo.watch('005930').first,
        throwsA(
          isA<MarketDataRepositoryException>().having(
            (e) => e.message,
            'message',
            isNot(contains('private-message')),
          ),
        ),
      );
      expect(client.requests.single.method, 'GET');
    },
  );
  test('invalid stream stock never opens HTTP', () async {
    var requests = 0;
    final repo = SpringRealtimeMarketRepository(
      accessToken: '',
      config: config,
      clientFactory: () {
        requests++;
        return _StreamClient(const Stream.empty());
      },
    );
    await expectLater(
      repo.watch('../bad').first,
      throwsA(isA<MarketDataRepositoryException>()),
    );
    expect(requests, 0);
  });
  test('research changes checks monotonic cursor and never writes', () async {
    final methods = <String>[];
    var bad = false;
    final repo = SpringResearchFeedRepository(
      accessToken: '',
      config: config,
      client: MockClient((request) async {
        methods.add(request.method);
        expect(request.url.path, '/api/v1/research/changes');
        final data = researchChangesJson();
        if (bad) data['nextAfterId'] = 0;
        return http.Response(
          jsonEncode({'success': true, 'data': data}),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );
    expect((await repo.changes('005930')).items.single.revision, 1);
    bad = true;
    await expectLater(repo.changes('005930'), throwsA(isA<Exception>()));
    expect(methods, ['GET', 'GET']);
  });

  Future<void> openRealtime(
    WidgetTester tester,
    _Live repo, {
    Size size = const Size(1000, 1200),
    double scale = 1,
    DateTime Function()? now,
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
        home: MarketRealtimeScreen(
          stockCode: '005930',
          stockName: '삼성전자',
          repository: repo,
          now: now,
        ),
      ),
    );
    await tester.pump();
  }

  testWidgets(
    'screen updates price, marks delayed transport and cancels on disposal',
    (tester) async {
      final repo = _Live();
      var now = DateTime.now();
      await openRealtime(tester, repo, now: () => now);
      repo.values.add(MarketRealtimeSnapshot.fromJson(realtimeJson()));
      await tester.pumpAndSettle();
      expect(find.text('현재 관측 가격: 100.123456'), findsOneWidget);
      repo.values.add(
        MarketRealtimeSnapshot.fromJson(realtimeJson(price: '101')),
      );
      await tester.pumpAndSettle();
      expect(find.text('현재 관측 가격: 101'), findsOneWidget);
      now = now.add(const Duration(seconds: 7));
      await tester.pump(const Duration(seconds: 7));
      expect(find.text('화면 수신 지연'), findsOneWidget);
      expect(find.text('마지막 관측 가격: 101'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
      expect(repo.cancelled, 1);
      await repo.values.close();
    },
  );
  testWidgets(
    'stream error removes current prices and OFF never shows a live quote',
    (tester) async {
      final repo = _Live();
      await openRealtime(tester, repo);
      repo.values.add(MarketRealtimeSnapshot.fromJson(realtimeJson()));
      await tester.pumpAndSettle();
      repo.values.addError(StateError('private'));
      await tester.pumpAndSettle();
      expect(find.text('현재 관측 가격: 100.123456'), findsNothing);
      repo.values.add(
        MarketRealtimeSnapshot.fromJson(realtimeJson(state: 'DISABLED')),
      );
      await tester.pumpAndSettle();
      expect(find.text('서버 실시간 수집 OFF'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
      await repo.values.close();
    },
  );
  testWidgets('narrow large text quote and minute view does not overflow', (
    tester,
  ) async {
    final repo = _Live();
    await openRealtime(tester, repo, size: const Size(380, 1000), scale: 1.4);
    repo.values.add(MarketRealtimeSnapshot.fromJson(realtimeJson()));
    await tester.pumpAndSettle();
    await tester.drag(find.byType(ListView), const Offset(0, -600));
    await tester.pump();
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    await repo.values.close();
  });
  testWidgets(
    'existing candle detail opens live view through injected capability',
    (tester) async {
      final repo = _Chart();
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light,
          home: MarketCandleScreen(
            stockCode: '005930',
            stockName: '삼성전자',
            market: 'KOSPI',
            repository: repo,
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('실시간 체결·호가'));
      await tester.pumpAndSettle();
      expect(find.text('삼성전자 · KRX 실시간'), findsOneWidget);
      expect(repo.live.listened, 1);
      await tester.pumpWidget(const SizedBox());
      await repo.live.values.close();
    },
  );
  testWidgets('research revision screen reports OFF without external sync', (
    tester,
  ) async {
    final methods = <String>[];
    final repo = SpringResearchFeedRepository(
      accessToken: '',
      config: config,
      client: MockClient((request) async {
        methods.add(request.method);
        return http.Response(
          jsonEncode({
            'success': true,
            'data': researchChangesJson(enabled: false),
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: ResearchChangesScreen(
          stockCode: '005930',
          stockName: '삼성전자',
          repository: repo,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('증분·변경 이력 수집이 OFF'), findsOneWidget);
    expect(methods, ['GET']);
  });
  testWidgets('revision refresh failure preserves loaded versions', (
    tester,
  ) async {
    var fail = false;
    final repo = SpringResearchFeedRepository(
      accessToken: '',
      config: config,
      client: MockClient(
        (request) async => fail
            ? http.Response('{}', 503)
            : http.Response(
                jsonEncode({'success': true, 'data': researchChangesJson()}),
                200,
                headers: {'content-type': 'application/json; charset=utf-8'},
              ),
      ),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: ResearchChangesScreen(
          stockCode: '005930',
          stockName: '삼성전자',
          repository: repo,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('수정 전 뉴스'), findsOneWidget);
    fail = true;
    await tester.tap(find.byTooltip('변경 이력 새로고침'));
    await tester.pumpAndSettle();
    expect(find.text('수정 전 뉴스'), findsOneWidget);
    expect(find.textContaining('기존 기록은 유지'), findsOneWidget);
  });
  testWidgets(
    'active research timeline refreshes stored GET only and stops when hidden',
    (tester) async {
      final methods = <String>[];
      final repo = SpringResearchFeedRepository(
        accessToken: '',
        config: config,
        client: MockClient((request) async {
          methods.add(request.method);
          final data = request.url.path.endsWith('/status')
              ? {
                  'enabled': false,
                  'cron': '0 0/30 * * * *',
                  'zone': 'Asia/Seoul',
                }
              : {
                  'stockCode': '005930',
                  'stockName': '삼성전자',
                  'fromDate': '2026-11-01',
                  'toDate': '2026-11-03',
                  'news': [],
                  'disclosures': [],
                  'providers': [],
                };
          return http.Response(
            jsonEncode({'success': true, 'data': data}),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }),
      );
      Widget app(bool active) => MaterialApp(
        home: Scaffold(
          body: ResearchTimelineScreen(
            repository: repo,
            stocks: const [
              ResearchStock(stockCode: '005930', stockName: '삼성전자'),
            ],
            active: active,
            onHoldingSetupOpen: () {},
          ),
        ),
      );
      await tester.pumpWidget(app(true));
      await tester.pumpAndSettle();
      final initial = methods.length;
      await tester.pump(const Duration(seconds: 31));
      await tester.pumpAndSettle();
      expect(methods.length, initial + 2);
      expect(methods.every((m) => m == 'GET'), isTrue);
      await tester.pumpWidget(app(false));
      await tester.pumpAndSettle();
      final hidden = methods.length;
      await tester.pump(const Duration(seconds: 31));
      await tester.pumpAndSettle();
      expect(methods.length, hidden);
      await tester.pumpWidget(const SizedBox());
    },
  );
}

class _StreamClient extends http.BaseClient {
  _StreamClient(this.body);
  final Stream<List<int>> body;
  final requests = <http.BaseRequest>[];
  bool closed = false;
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    requests.add(request);
    return http.StreamedResponse(
      body,
      200,
      headers: {'content-type': 'text/event-stream'},
    );
  }

  @override
  void close() {
    closed = true;
  }
}

class _Live implements RealtimeMarketRepository {
  late final values = StreamController<MarketRealtimeSnapshot>.broadcast(
    onListen: () => listened++,
    onCancel: () => cancelled++,
  );
  int listened = 0, cancelled = 0;
  @override
  Stream<MarketRealtimeSnapshot> watch(String code) => values.stream;
}

class _Chart implements MarketDataRepository, RealtimeMarketAccess {
  final live = _Live();
  @override
  RealtimeMarketRepository get realtime => live;
  @override
  Future<MarketCandleSnapshot> fetchCandles({
    required String stockCode,
    required String market,
    required MarketCandleInterval interval,
    int count = 60,
  }) async => MarketCandleSnapshot(
    provider: 'KB',
    stockCode: stockCode,
    market: market,
    interval: interval,
    candles: [],
  );
}
