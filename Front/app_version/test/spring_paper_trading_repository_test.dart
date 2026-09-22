import 'dart:convert';

import 'package:app_version/config/api_config.dart';
import 'package:app_version/repositories/paper_trading_repository.dart';
import 'package:app_version/repositories/spring_paper_trading_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('fetchSnapshot maps paper trading metrics and positions', () async {
    final repository = SpringPaperTradingRepository(
      accessToken: 'test-token',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/api/v1/paper-trading');
        expect(request.headers['Authorization'], 'Bearer test-token');
        return _successResponse();
      }),
    );

    final snapshot = await repository.fetchSnapshot();

    expect(snapshot.summary.totalAsset, 1010000);
    expect(snapshot.summary.returnRate, 1);
    expect(snapshot.positions.single.provider, 'KB');
    expect(snapshot.trades.single.recommendationId, 11);
  });

  test('buyFromRecommendation posts quantity to the signal endpoint', () async {
    final repository = SpringPaperTradingRepository(
      accessToken: '',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(
          request.url.path,
          '/api/v1/paper-trading/recommendations/11/buy',
        );
        expect(jsonDecode(request.body), {'quantity': 3.5});
        return _successResponse();
      }),
    );

    final snapshot = await repository.buyFromRecommendation(11, 3.5);

    expect(snapshot.positions.single.quantity, 10);
  });

  test('sellPosition posts the selected position and quantity', () async {
    final repository = SpringPaperTradingRepository(
      accessToken: '',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/paper-trading/sell');
        expect(jsonDecode(request.body), {
          'stockCode': '005930',
          'market': 'KOSPI',
          'quantity': 2,
        });
        return _successResponse();
      }),
    );

    await repository.sellPosition(
      stockCode: '005930',
      market: 'KOSPI',
      quantity: 2,
    );
  });

  test('API error message is exposed to the screen', () {
    final repository = SpringPaperTradingRepository(
      accessToken: '',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        return http.Response.bytes(
          utf8.encode(
            jsonEncode({
              'success': false,
              'error': {'message': '실제 현재가를 확인할 수 없습니다.'},
            }),
          ),
          503,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    expect(
      repository.fetchSnapshot(),
      throwsA(
        isA<PaperTradingRepositoryException>().having(
          (error) => error.message,
          'message',
          '실제 현재가를 확인할 수 없습니다.',
        ),
      ),
    );
  });
}

http.Response _successResponse() {
  return http.Response(
    jsonEncode({
      'success': true,
      'data': {
        'summary': {
          'initialCapital': 1000000,
          'cashBalance': 250000,
          'openPositionValue': 760000,
          'totalAsset': 1010000,
          'realizedProfit': 4000,
          'unrealizedProfit': 6000,
          'totalProfit': 10000,
          'returnRate': 1,
          'completedTrades': 2,
          'winRate': 50,
          'maxLoss': 2000,
          'turnoverRate': 125,
        },
        'positions': [
          {
            'stockCode': '005930',
            'stockName': '삼성전자',
            'market': 'KOSPI',
            'provider': 'KB',
            'quantity': 10,
            'averagePrice': 70000,
            'currentPrice': 76000,
            'valuationAmount': 760000,
            'unrealizedProfit': 60000,
            'profitRate': 8.57,
          },
        ],
        'trades': [
          {
            'tradeRecordId': 1,
            'recommendationId': 11,
            'stockCode': '005930',
            'stockName': '삼성전자',
            'market': 'KOSPI',
            'tradeType': 'BUY',
            'tradePrice': 70000,
            'quantity': 10,
            'tradeAmount': 700000,
            'realizedProfit': 0,
            'tradeDate': '2026-09-23T10:30:00',
            'memo': 'AI 강한 매수 신호 모의매수',
          },
        ],
      },
    }),
    200,
    headers: {'content-type': 'application/json; charset=utf-8'},
  );
}
