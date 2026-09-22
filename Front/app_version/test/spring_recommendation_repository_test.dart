import 'dart:convert';

import 'package:app_version/config/api_config.dart';
import 'package:app_version/repositories/spring_recommendation_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('fetchHistory maps recommendation page and query', () async {
    final repository = SpringRecommendationRepository(
      accessToken: 'token',
      config: ApiConfig(baseUrl: 'http://ubuntu-server:8081'),
      client: MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/api/v1/recommendations');
        expect(request.url.queryParameters, {
          'page': '1',
          'size': '10',
          'status': 'BUY_STRONG',
        });
        expect(request.headers['Authorization'], 'Bearer token');
        return _success({
          'items': [_recommendationJson()],
          'page': 1,
          'size': 10,
          'total': 11,
        });
      }),
    );

    final page = await repository.fetchHistory(
      status: 'BUY_STRONG',
      page: 1,
      size: 10,
    );

    expect(page.total, 11);
    expect(page.items.single.recommendationId, 41);
    expect(page.items.single.status, '강한 매수');
    expect(page.items.single.machineStatus, 'BUY_STRONG');
    expect(page.items.single.takeProfitRate, 9.5);
  });

  test('fetchDetail requests selected recommendation', () async {
    final repository = SpringRecommendationRepository(
      accessToken: '',
      config: ApiConfig(baseUrl: 'http://ubuntu-server:8081'),
      client: MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/api/v1/recommendations/41');
        return _success(_recommendationJson());
      }),
    );

    final detail = await repository.fetchDetail(41);

    expect(detail.stockCode, '005930');
    expect(detail.reasons.single.label, '추세');
  });

  test('analyzeHolding posts holding id and maps new result', () async {
    final repository = SpringRecommendationRepository(
      accessToken: '',
      config: ApiConfig(baseUrl: 'http://ubuntu-server:8081'),
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/recommendations/analyze/7');
        return _success(_recommendationJson());
      }),
    );

    final result = await repository.analyzeHolding(7);

    expect(result.score, 86);
    expect(result.createdAt, DateTime.parse('2026-09-22T11:30:00'));
  });
}

http.Response _success(Object data) {
  return http.Response(
    jsonEncode({'success': true, 'data': data}),
    200,
    headers: {'content-type': 'application/json; charset=utf-8'},
  );
}

Map<String, Object> _recommendationJson() {
  return {
    'recommendationId': 41,
    'stockCode': '005930',
    'stockName': '삼성전자',
    'market': 'KOSPI',
    'recommendationType': 'BUY',
    'status': 'BUY_STRONG',
    'statusLabel': '강한 매수',
    'score': 86,
    'entryPrice': 75200,
    'stopLossRate': -5.0,
    'takeProfitRate': 9.5,
    'aiSummary': '가격 추세와 뉴스 흐름이 긍정적입니다.',
    'createdAt': '2026-09-22T11:30:00',
    'reasons': [
      {
        'type': 'TREND',
        'label': '추세',
        'description': '최근 종가가 상승했습니다.',
        'score': 20,
      },
    ],
  };
}
