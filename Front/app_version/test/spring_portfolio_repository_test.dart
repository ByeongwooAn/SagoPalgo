import 'dart:convert';

import 'package:app_version/config/api_config.dart';
import 'package:app_version/repositories/portfolio_repository.dart';
import 'package:app_version/repositories/spring_portfolio_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('fetchPortfolio combines capital and holdings API responses', () async {
    final requestedUrls = <String>[];
    final repository = SpringPortfolioRepository(
      accessToken: 'access-token',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        requestedUrls.add(request.url.toString());
        expect(request.headers['Authorization'], 'Bearer access-token');

        if (request.url.path == '/api/v1/capital') {
          return _success({
            'availableCapital': 3000000,
            'recommendedMinPosition': 300000,
            'recommendedMaxPosition': 600000,
            'riskPerTradeRate': 0.02,
          });
        }

        return _success({
          'summary': {
            'totalProfit': 74400,
            'profitRate': 8.97,
            'maxAllowedLoss': 60000,
            'riskUsageRate': 0.4,
          },
          'items': [
            {
              'holdingId': 21,
              'stockCode': '005930',
              'stockName': '삼성전자',
              'market': 'KOSPI',
              'buyPrice': 69100,
              'quantity': 12,
              'currentPrice': 75300,
              'profitRate': 8.97,
              'stopLossRate': -5,
              'takeProfitRate': 9,
              'status': 'HOLDING',
              'statusLabel': '보유',
            },
          ],
        });
      }),
    );

    final portfolio = await repository.fetchPortfolio();

    expect(requestedUrls, [
      'http://localhost:8080/api/v1/capital',
      'http://localhost:8080/api/v1/holdings',
    ]);
    expect(portfolio.capital.availableCapital, 3000000);
    expect(portfolio.capital.recommendedMaxPosition, 600000);
    expect(portfolio.summary.totalProfit, 74400);
    expect(portfolio.holdings.single.stockCode, '005930');
    expect(portfolio.holdings.single.profitRate, 8.97);
  });

  test('fetchPortfolio throws readable exception when an API fails', () async {
    final repository = SpringPortfolioRepository(
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
      repository.fetchPortfolio(),
      throwsA(
        isA<PortfolioRepositoryException>().having(
          (exception) => exception.message,
          'message',
          '토큰이 만료되었습니다.',
        ),
      ),
    );
  });
}

http.Response _success(Object? data) {
  return http.Response(
    jsonEncode({'success': true, 'data': data, 'message': '요청이 성공했습니다.'}),
    200,
    headers: {'content-type': 'application/json; charset=utf-8'},
  );
}
