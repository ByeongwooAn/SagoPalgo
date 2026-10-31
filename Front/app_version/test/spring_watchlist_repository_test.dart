import 'dart:convert';

import 'package:app_version/config/api_config.dart';
import 'package:app_version/models/recommendation.dart';
import 'package:app_version/repositories/spring_watchlist_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test(
    'code-only lookup requests identity and preserves leading zeroes',
    () async {
      final repository = SpringWatchlistRepository(
        accessToken: '',
        config: ApiConfig(baseUrl: 'http://localhost:8080'),
        client: MockClient((request) async {
          expect(request.method, 'GET');
          expect(request.url.path, '/api/v1/market/stocks/000660/identity');
          expect(request.url.query, isEmpty);
          return _success({
            'stockCode': '000660',
            'stockName': 'SK하이닉스',
            'market': 'KOSPI',
            'provider': 'KIS',
          });
        }),
      );
      final result = await repository.lookupStock('000660');
      expect(result.stockName, 'SK하이닉스');
      expect(result.market, 'KOSPI');
    },
  );

  test('identity for another code is rejected', () async {
    final repository = SpringWatchlistRepository(
      accessToken: '',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient(
        (_) async => _success({
          'stockCode': '005930',
          'stockName': '삼성전자',
          'market': 'KOSPI',
          'provider': 'KIS',
        }),
      ),
    );
    expect(
      repository.lookupStock('000660'),
      throwsA(isA<WatchlistRepositoryException>()),
    );
  });

  test('delete targets selected watchlist id and exposes rejection', () async {
    var rejected = false;
    final repository = SpringWatchlistRepository(
      accessToken: 'access-token',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        expect(request.method, 'DELETE');
        expect(request.url.path, '/api/v1/watchlist/11');
        expect(request.headers['Authorization'], 'Bearer access-token');
        return rejected
            ? http.Response(
                jsonEncode({
                  'success': false,
                  'error': {'message': '관심 종목을 찾을 수 없습니다.'},
                }),
                404,
                headers: {'content-type': 'application/json; charset=utf-8'},
              )
            : _success(null);
      }),
    );
    await repository.deleteStock(11);
    rejected = true;
    expect(
      repository.deleteStock(11),
      throwsA(isA<WatchlistRepositoryException>()),
    );
  });

  test(
    'manual registration posts identity and explicit notification preference without invented prices',
    () async {
      final repository = SpringWatchlistRepository(
        accessToken: '',
        config: ApiConfig(baseUrl: 'http://localhost:8080'),
        client: MockClient((request) async {
          expect(request.method, 'POST');
          expect(request.url.path, '/api/v1/watchlist');
          expect(request.headers.containsKey('Authorization'), isFalse);
          expect(jsonDecode(request.body), {
            'stockCode': '005930',
            'stockName': '삼성전자',
            'market': 'KOSPI',
            'alertEnabled': true,
          });
          return _success({'watchlistId': 12});
        }),
      );
      await repository.addStock(
        stockCode: '005930',
        stockName: '삼성전자',
        market: 'KOSPI',
        alertEnabled: true,
      );
    },
  );

  test('fetchWatchlist maps provider price and change rate', () async {
    final repository = SpringWatchlistRepository(
      accessToken: 'access-token',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        expect(request.method, 'GET');
        return _success([_watchlistItem(alertEnabled: true)]);
      }),
    );

    final items = await repository.fetchWatchlist();

    expect(items, hasLength(1));
    expect(items.single.provider, 'KB');
    expect(items.single.currentPrice, 75200);
    expect(items.single.changeRate, 1.21);
  });

  test(
    'addRecommendation creates watchlist item when it does not exist',
    () async {
      final requestedUrls = <String>[];
      final repository = SpringWatchlistRepository(
        accessToken: 'access-token',
        config: ApiConfig(baseUrl: 'http://localhost:8080'),
        client: MockClient((request) async {
          requestedUrls.add('${request.method} ${request.url}');
          expect(request.headers['Authorization'], 'Bearer access-token');

          if (request.method == 'GET') {
            return _success([]);
          }

          expect(request.method, 'POST');
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body['stockCode'], '005930');
          expect(body['stockName'], '삼성전자');
          expect(body['market'], 'KOSPI');
          expect(body['alertEnabled'], false);
          return _success({'watchlistId': 11});
        }),
      );

      final result = await repository.addRecommendation(_recommendation());

      expect(result.changed, true);
      expect(result.message, '삼성전자 관심 종목에 등록했습니다.');
      expect(requestedUrls, [
        'GET http://localhost:8080/api/v1/watchlist',
        'POST http://localhost:8080/api/v1/watchlist',
      ]);
    },
  );

  test(
    'addRecommendation returns already registered message when item exists',
    () async {
      var requestCount = 0;
      final repository = SpringWatchlistRepository(
        accessToken: 'access-token',
        config: ApiConfig(baseUrl: 'http://localhost:8080'),
        client: MockClient((request) async {
          requestCount++;
          expect(request.method, 'GET');
          return _success([_watchlistItem(alertEnabled: false)]);
        }),
      );

      final result = await repository.addRecommendation(_recommendation());

      expect(result.changed, false);
      expect(result.message, '삼성전자 이미 관심 종목에 등록되어 있습니다.');
      expect(requestCount, 1);
    },
  );

  test('enableAlert patches existing item when alert is off', () async {
    final requestedMethods = <String>[];
    final repository = SpringWatchlistRepository(
      accessToken: 'access-token',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        requestedMethods.add(request.method);

        if (request.method == 'GET') {
          return _success([_watchlistItem(alertEnabled: false)]);
        }

        expect(request.method, 'PATCH');
        expect(
          request.url.toString(),
          'http://localhost:8080/api/v1/watchlist/11/alert',
        );
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['alertEnabled'], true);
        return _success(_watchlistItem(alertEnabled: true));
      }),
    );

    final result = await repository.enableAlert(_recommendation());

    expect(result.changed, true);
    expect(result.message, '삼성전자 알림을 켰습니다.');
    expect(requestedMethods, ['GET', 'PATCH']);
  });

  test('enableAlert creates item with alert when it does not exist', () async {
    final requestedMethods = <String>[];
    final repository = SpringWatchlistRepository(
      accessToken: 'access-token',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        requestedMethods.add(request.method);

        if (request.method == 'GET') {
          return _success([]);
        }

        expect(request.method, 'POST');
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['alertEnabled'], true);
        return _success({'watchlistId': 11});
      }),
    );

    final result = await repository.enableAlert(_recommendation());

    expect(result.changed, true);
    expect(result.message, '삼성전자 관심 종목 등록과 알림 설정을 완료했습니다.');
    expect(requestedMethods, ['GET', 'POST']);
  });

  test(
    'enableAlert returns already enabled message without patching',
    () async {
      var requestCount = 0;
      final repository = SpringWatchlistRepository(
        accessToken: 'access-token',
        config: ApiConfig(baseUrl: 'http://localhost:8080'),
        client: MockClient((request) async {
          requestCount++;
          expect(request.method, 'GET');
          return _success([_watchlistItem(alertEnabled: true)]);
        }),
      );

      final result = await repository.enableAlert(_recommendation());

      expect(result.changed, false);
      expect(result.message, '삼성전자 알림이 이미 켜져 있습니다.');
      expect(requestCount, 1);
    },
  );

  test('watchlist API failure is exposed as readable exception', () async {
    final repository = SpringWatchlistRepository(
      accessToken: 'access-token',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        return http.Response(
          jsonEncode({
            'success': false,
            'error': {'code': 'AUTH_INVALID_TOKEN', 'message': '토큰이 만료되었습니다.'},
          }),
          401,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    expect(
      repository.addRecommendation(_recommendation()),
      throwsA(
        isA<WatchlistRepositoryException>().having(
          (exception) => exception.message,
          'message',
          '토큰이 만료되었습니다.',
        ),
      ),
    );
  });
}

InvestmentRecommendation _recommendation() {
  return const InvestmentRecommendation(
    stockName: '삼성전자',
    stockCode: '005930',
    market: 'KOSPI',
    status: '강한 매수',
    score: 87,
    entryPrice: 72000,
    stopLossRate: -5,
    aiSummary: '시장 강세와 거래량 증가가 동시에 나타났습니다.',
    reasons: [],
  );
}

Map<String, dynamic> _watchlistItem({required bool alertEnabled}) {
  return {
    'watchlistId': 11,
    'stockCode': '005930',
    'stockName': '삼성전자',
    'market': 'KOSPI',
    'alertEnabled': alertEnabled,
    'provider': 'KB',
    'currentPrice': 75200,
    'changeRate': 1.21,
    'createdAt': '2026-09-07T00:00:00Z',
  };
}

http.Response _success(Object? data) {
  return http.Response(
    jsonEncode({'success': true, 'data': data, 'message': '요청이 성공했습니다.'}),
    200,
    headers: {'content-type': 'application/json; charset=utf-8'},
  );
}
