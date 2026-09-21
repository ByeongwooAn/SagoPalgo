import 'dart:convert';

import 'package:app_version/config/api_config.dart';
import 'package:app_version/models/research_feed.dart';
import 'package:app_version/repositories/research_feed_repository.dart';
import 'package:app_version/repositories/spring_research_feed_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  const stock = ResearchStock(stockCode: '005930', stockName: '삼성전자');

  test('fetchFeed maps the stored research feed response', () async {
    final repository = SpringResearchFeedRepository(
      accessToken: '',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/api/v1/research/feed');
        expect(request.url.queryParameters['stockCode'], '005930');
        expect(request.url.queryParameters['stockName'], '삼성전자');
        expect(request.headers.containsKey('Authorization'), isFalse);
        return http.Response(
          jsonEncode(_responseData(provider: 'LOCAL_DB', dataType: 'CACHE')),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    );

    final feed = await repository.fetchFeed(stock);

    expect(feed.stockName, '삼성전자');
    expect(feed.news.single.title, '반도체 투자 확대');
    expect(feed.news.single.publishedAt, isNotNull);
    expect(feed.disclosures.single.receiptNumber, '20260921000123');
    expect(feed.providers.single.provider, 'LOCAL_DB');
  });

  test('syncFeed posts to the provider synchronization endpoint', () async {
    final repository = SpringResearchFeedRepository(
      accessToken: 'test-token',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/research/feed/sync');
        expect(request.headers['Authorization'], 'Bearer test-token');
        return http.Response(
          jsonEncode(_responseData(provider: 'NAVER_NEWS', dataType: 'NEWS')),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    );

    final feed = await repository.syncFeed(stock);

    expect(feed.providers.single.provider, 'NAVER_NEWS');
    expect(feed.news, hasLength(1));
  });

  test('fetchFeed exposes an API error message', () {
    final repository = SpringResearchFeedRepository(
      accessToken: '',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        return http.Response.bytes(
          utf8.encode(
            jsonEncode({
              'success': false,
              'error': {'message': '뉴스 저장소 조회 실패'},
            }),
          ),
          500,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    expect(
      repository.fetchFeed(stock),
      throwsA(
        isA<ResearchFeedRepositoryException>().having(
          (error) => error.message,
          'message',
          '뉴스 저장소 조회 실패',
        ),
      ),
    );
  });

  test(
    'fetchSyncStatus maps scheduler configuration and last result',
    () async {
      final repository = SpringResearchFeedRepository(
        accessToken: '',
        config: ApiConfig(baseUrl: 'http://localhost:8080'),
        client: MockClient((request) async {
          expect(request.method, 'GET');
          expect(request.url.path, '/api/v1/research/sync/status');
          expect(request.url.queryParameters['stockCode'], '005930');
          return http.Response(
            jsonEncode({
              'success': true,
              'data': {
                'enabled': true,
                'cron': '0 0/30 * * * *',
                'zone': 'Asia/Seoul',
                'item': {
                  'stockCode': '005930',
                  'stockName': '삼성전자',
                  'triggerType': 'SCHEDULED',
                  'status': 'PARTIAL',
                  'newsCount': 3,
                  'disclosureCount': 2,
                  'providerSuccessCount': 1,
                  'providerFailureCount': 1,
                  'providerDisabledCount': 0,
                  'message': '부분 성공',
                  'lastAttemptedAt': '2026-09-22T00:00:00Z',
                  'lastSucceededAt': '2026-09-22T00:00:00Z',
                },
              },
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }),
      );

      final overview = await repository.fetchSyncStatus(stock);

      expect(overview.enabled, isTrue);
      expect(overview.item?.status, 'PARTIAL');
      expect(overview.item?.newsCount, 3);
      expect(overview.item?.lastAttemptedAt, isNotNull);
    },
  );
}

Map<String, dynamic> _responseData({
  required String provider,
  required String dataType,
}) {
  return {
    'success': true,
    'data': {
      'stockCode': '005930',
      'stockName': '삼성전자',
      'fromDate': '2026-08-22',
      'toDate': '2026-09-21',
      'news': [
        {
          'provider': 'NAVER_NEWS',
          'stockCode': '005930',
          'title': '반도체 투자 확대',
          'link': 'https://news.test/article',
          'summary': '기사 요약',
          'publishedAt': '2026-09-21T01:00:00Z',
        },
      ],
      'disclosures': [
        {
          'provider': 'OPEN_DART',
          'stockCode': '005930',
          'corpCode': '00126380',
          'corpName': '삼성전자',
          'reportName': '주요사항보고서',
          'receiptNumber': '20260921000123',
          'submitterName': '삼성전자',
          'receiptDate': '2026-09-21',
          'link': 'https://dart.test/report',
        },
      ],
      'providers': [
        {
          'provider': provider,
          'dataType': dataType,
          'status': 'SUCCESS',
          'message': '조회 성공',
        },
      ],
    },
  };
}
