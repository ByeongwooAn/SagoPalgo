import 'dart:convert';

import 'package:app_version/config/api_config.dart';
import 'package:app_version/models/order_precheck.dart';
import 'package:app_version/repositories/order_precheck_repository.dart';
import 'package:app_version/repositories/spring_order_precheck_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('precheck posts a limit order plan and maps safety checks', () async {
    final repository = SpringOrderPrecheckRepository(
      accessToken: 'test-token',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/orders/precheck');
        expect(request.headers['Authorization'], 'Bearer test-token');
        expect(jsonDecode(request.body), {
          'stockCode': '005930',
          'stockName': '삼성전자',
          'market': 'KOSPI',
          'side': 'SELL',
          'limitPrice': 76000.0,
          'quantity': 2.0,
        });
        return _successResponse();
      }),
    );

    final result = await repository.precheck(
      const OrderPrecheckInput(
        stockCode: '005930',
        stockName: '삼성전자',
        market: 'KOSPI',
        side: 'SELL',
        limitPrice: 76000,
        quantity: 2,
      ),
    );

    expect(result.orderPrecheckId, 31);
    expect(result.eligible, isFalse);
    expect(result.canSubmit, isFalse);
    expect(result.checks, hasLength(2));
    expect(result.checks.first.code, 'ORDER_SWITCH');
  });

  test('precheck exposes an API error message', () {
    final repository = SpringOrderPrecheckRepository(
      accessToken: '',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        return http.Response.bytes(
          utf8.encode(
            jsonEncode({
              'success': false,
              'error': {'message': 'KB 계좌 조회에 실패했습니다.'},
            }),
          ),
          502,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    expect(
      repository.precheck(
        const OrderPrecheckInput(
          stockCode: '005930',
          stockName: '삼성전자',
          market: 'KOSPI',
          side: 'SELL',
          limitPrice: 76000,
          quantity: 2,
        ),
      ),
      throwsA(
        isA<OrderPrecheckRepositoryException>().having(
          (error) => error.message,
          'message',
          'KB 계좌 조회에 실패했습니다.',
        ),
      ),
    );
  });

  test(
    'approval endpoints keep the one-time token and report no submission',
    () async {
      final calls = <String>[];
      final repository = SpringOrderPrecheckRepository(
        accessToken: 'test-token',
        config: ApiConfig(baseUrl: 'http://localhost:8080'),
        client: MockClient((request) async {
          calls.add(request.url.path);
          expect(request.headers['Authorization'], 'Bearer test-token');
          if (request.url.path.endsWith('/prepare')) {
            return http.Response.bytes(
              utf8.encode(
                jsonEncode({
                  'success': true,
                  'data': {
                    'approvalId': 7,
                    'token': 'one-time-token',
                    'expiresAt': '2026-09-23T12:01:30',
                    'precheck':
                        (jsonDecode(_successResponse().body)
                            as Map<String, dynamic>)['data'],
                  },
                }),
              ),
              200,
              headers: {'content-type': 'application/json; charset=utf-8'},
            );
          }
          expect(jsonDecode(request.body), {
            'approvalId': 7,
            'token': 'one-time-token',
            'acknowledged': true,
          });
          return http.Response.bytes(
            utf8.encode(
              jsonEncode({
                'success': true,
                'data': {
                  'approvalId': 7,
                  'status': 'ACKNOWLEDGED',
                  'orderSubmitted': false,
                  'message': '실제 주문은 전송되지 않았습니다.',
                },
              }),
            ),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }),
      );

      final preparation = await repository.prepareApproval(
        const OrderPrecheckInput(
          stockCode: '005930',
          stockName: '삼성전자',
          market: 'KOSPI',
          side: 'SELL',
          limitPrice: 76000,
          quantity: 2,
        ),
      );
      final message = await repository.confirmApproval(preparation);

      expect(preparation.token, 'one-time-token');
      expect(message, contains('전송되지'));
      expect(calls, [
        '/api/v1/orders/approvals/prepare',
        '/api/v1/orders/approvals/confirm',
      ]);
    },
  );
}

http.Response _successResponse() {
  return http.Response(
    jsonEncode({
      'success': true,
      'data': {
        'orderPrecheckId': 31,
        'stockCode': '005930',
        'stockName': '삼성전자',
        'market': 'KOSPI',
        'side': 'SELL',
        'orderType': 'LIMIT',
        'limitPrice': 76000,
        'quantity': 2,
        'estimatedAmount': 152000,
        'quoteProvider': 'KB',
        'currentPrice': 75800,
        'priceDeviationRate': 0.26,
        'orderAvailableCash': 0,
        'orderableQuantity': 10,
        'maxOrderAmount': 1000000,
        'maxPriceDeviationRate': 5,
        'orderEnabled': false,
        'eligible': false,
        'canSubmit': false,
        'submissionMessage': '사전검증 전용 단계로 실제 주문 전송은 구현되어 있지 않습니다.',
        'checks': [
          {
            'code': 'ORDER_SWITCH',
            'label': '주문 스위치',
            'passed': false,
            'message': 'KB 주문 기능이 OFF입니다.',
          },
          {
            'code': 'SELLABLE_QUANTITY',
            'label': '주문가능수량',
            'passed': true,
            'message': '요청 수량을 매도할 수 있습니다.',
          },
        ],
        'checkedAt': '2026-09-23T12:00:00',
      },
    }),
    200,
    headers: {'content-type': 'application/json; charset=utf-8'},
  );
}
