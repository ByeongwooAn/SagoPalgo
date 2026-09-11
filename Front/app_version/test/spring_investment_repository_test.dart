import 'dart:convert';

import 'package:app_version/config/api_config.dart';
import 'package:app_version/models/app_alert.dart';
import 'package:app_version/models/recommendation.dart';
import 'package:app_version/repositories/spring_investment_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('fetchSnapshot maps dashboard API response into app models', () async {
    final repository = SpringInvestmentRepository(
      accessToken: 'access-token',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        expect(
          request.url.toString(),
          'http://localhost:8080/api/v1/dashboard/snapshot',
        );
        expect(request.headers['Authorization'], 'Bearer access-token');

        return http.Response(
          jsonEncode({
            'success': true,
            'data': {
              'marketSummary': {
                'availableCapital': 3000000,
                'monthlyReturnRate': 3.8,
                'recommendedPositionRange': '30~60만원',
                'marketTrend': '강세',
                'marketScore': 76,
                'newsSentiment': '긍정',
                'positiveNewsCount': 12,
                'marketBars': [0.42, 0.68],
              },
              'recommendation': {
                'stockName': '삼성전자',
                'stockCode': '005930',
                'market': 'KOSPI',
                'status': '강한 매수',
                'score': 87,
                'entryPrice': 72000,
                'stopLossRate': -5,
                'aiSummary': '시장 강세와 거래량 증가가 동시에 나타났습니다.',
                'reasons': [
                  {
                    'label': 'RSI',
                    'description': '과매도 구간에서 반등 신호가 확인되었습니다.',
                    'type': 'TECHNICAL',
                    'score': 20,
                  },
                  {
                    'label': '뉴스',
                    'description': '긍정 감성이 증가했습니다.',
                    'type': 'NEWS',
                    'score': 15,
                  },
                ],
              },
              'portfolioSummary': {
                'totalProfit': 128400,
                'profitRate': 4.2,
                'maxAllowedLoss': 60000,
                'riskUsageRate': 0.42,
              },
              'holdings': [
                {
                  'holdingId': 21,
                  'stockCode': '005930',
                  'stockName': '삼성전자',
                  'market': 'KOSPI',
                  'buyPrice': 69100,
                  'quantity': 12,
                  'currentPrice': 72000,
                  'profitRate': 4.2,
                  'stopLossRate': -5,
                  'takeProfitRate': 9,
                  'status': 'HOLDING',
                  'statusLabel': '보유',
                },
              ],
              'alerts': [
                {
                  'title': '삼성전자 매도 검토',
                  'body': '부분 익절 여부를 확인해 보세요.',
                  'timeLabel': '방금 전',
                  'type': 'SELL',
                },
              ],
            },
            'message': '대시보드 데이터가 조회되었습니다.',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    );

    final snapshot = await repository.fetchSnapshot();

    expect(snapshot.marketSummary.availableCapital, 3000000);
    expect(snapshot.recommendation!.stockCode, '005930');
    expect(snapshot.recommendation!.market, 'KOSPI');
    expect(
      snapshot.recommendation!.reasons.first.type,
      RecommendationReasonType.technical,
    );
    expect(
      snapshot.recommendation!.reasons.last.type,
      RecommendationReasonType.news,
    );
    expect(snapshot.portfolioSummary.totalProfit, 128400);
    expect(snapshot.holdings.single.status, '보유');
    expect(snapshot.alerts.single.type, AppAlertType.sell);
  });

  test('fetchSnapshot throws readable exception when API fails', () async {
    final repository = SpringInvestmentRepository(
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
      repository.fetchSnapshot(),
      throwsA(
        isA<InvestmentRepositoryException>().having(
          (exception) => exception.message,
          'message',
          '토큰이 만료되었습니다.',
        ),
      ),
    );
  });
}
