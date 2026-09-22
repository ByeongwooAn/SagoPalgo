import 'dart:convert';

import 'package:app_version/config/api_config.dart';
import 'package:app_version/models/market_candle.dart';
import 'package:app_version/repositories/market_data_repository.dart';
import 'package:app_version/repositories/spring_market_data_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('fetchCandles maps candles and sends the selected interval', () async {
    final repository = SpringMarketDataRepository(
      accessToken: 'test-token',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/api/v1/market/candles');
        expect(request.url.queryParameters['stockCode'], '005930');
        expect(request.url.queryParameters['market'], 'KOSPI');
        expect(request.url.queryParameters['interval'], 'WEEKLY');
        expect(request.url.queryParameters['count'], '20');
        expect(request.headers['Authorization'], 'Bearer test-token');
        return http.Response(
          jsonEncode({
            'success': true,
            'data': {
              'provider': 'KB',
              'stockCode': '005930',
              'market': 'KOSPI',
              'interval': 'WEEKLY',
              'count': 1,
              'candles': [
                {
                  'provider': 'KB',
                  'stockCode': '005930',
                  'market': 'KOSPI',
                  'dateTime': '2026-09-21T00:00:00',
                  'interval': 'WEEKLY',
                  'openPrice': 74800,
                  'highPrice': 75300,
                  'lowPrice': 74700,
                  'closePrice': 75200,
                  'volume': 1122334,
                },
              ],
            },
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    final snapshot = await repository.fetchCandles(
      stockCode: '005930',
      market: 'KOSPI',
      interval: MarketCandleInterval.weekly,
      count: 20,
    );

    expect(snapshot.provider, 'KB');
    expect(snapshot.interval, MarketCandleInterval.weekly);
    expect(snapshot.candles.single.closePrice, 75200);
    expect(snapshot.candles.single.volume, 1122334);
  });

  test('fetchCandles exposes an API error message', () {
    final repository = SpringMarketDataRepository(
      accessToken: '',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        return http.Response.bytes(
          utf8.encode(
            jsonEncode({
              'success': false,
              'error': {'message': '캔들 시세 Provider가 응답하지 않습니다.'},
            }),
          ),
          502,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    expect(
      repository.fetchCandles(
        stockCode: '005930',
        market: 'KOSPI',
        interval: MarketCandleInterval.daily,
      ),
      throwsA(
        isA<MarketDataRepositoryException>().having(
          (error) => error.message,
          'message',
          '캔들 시세 Provider가 응답하지 않습니다.',
        ),
      ),
    );
  });
}
