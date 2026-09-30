import 'dart:convert';

import 'package:app_version/config/api_config.dart';
import 'package:app_version/repositories/kb_account_repository.dart';
import 'package:app_version/repositories/spring_kb_account_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('fetchSnapshot calls KB holdings and balance endpoints', () async {
    final requestedUrls = <String>[];
    final repository = SpringKbAccountRepository(
      accessToken: '',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        requestedUrls.add(request.url.toString());
        expect(request.headers.containsKey('Authorization'), isFalse);

        if (request.url.path.endsWith('/holdings')) {
          return _ok({
            'summary': {
              'totalPurchaseAmount': 4800000,
              'totalValuationAmount': 5200000,
              'totalProfitAmount': 400000,
              'profitRate': 8.3,
            },
            'items': [
              {
                'stockCode': '005930',
                'stockName': '삼성전자',
                'market': 'KRX',
                'quantity': 10,
                'currentPrice': 76000,
                'valuationAmount': 760000,
                'profitAmount': 69000,
                'profitRate': 10,
                'weightRate': 14.62,
              },
            ],
          });
        }

        if (request.url.path.endsWith('/settlement')) {
          return _ok({
            'summary': {
              'basis': 'SETTLEMENT',
              'cashDeposit': 1200000,
              'withdrawalAvailableAmount': 1100000,
              'orderAvailableCash': 1000000,
              'totalPurchaseAmount': 4800000,
              'totalValuationAmount': 5200000,
              'totalProfitAmount': 400000,
              'totalYieldRate': 8.3,
              'totalDataCount': '2',
            },
            'items': [
              {
                'stockCode': '005930',
                'stockName': '삼성전자',
                'quantity': 10,
                'valuationAmount': 770000,
                'valuationWeightRate': 68.14,
              },
            ],
          });
        }

        return _ok({
          'summary': {
            'basis': 'EXECUTION',
            'netAssetValuationAmount': 5200000,
            'securitiesNetValuationAmount': 5200000,
            'totalPurchaseAmount': 4800000,
            'totalValuationAmount': 5200000,
            'totalProfitAmount': 400000,
            'totalYieldRate': 8.3,
          },
          'items': [],
        });
      }),
    );

    final snapshot = await repository.fetchSnapshot();

    expect(requestedUrls, [
      'http://localhost:8080/api/v1/kb/accounts/primary/holdings',
      'http://localhost:8080/api/v1/kb/accounts/primary/balances/settlement',
      'http://localhost:8080/api/v1/kb/accounts/primary/balances/execution',
    ]);
    expect(snapshot.holdings.items.single.stockName, '삼성전자');
    expect(snapshot.holdings.items.single.weightRate, 14.62);
    expect(snapshot.settlementBalance.items.single.valuationWeightRate, 68.14);
    expect(snapshot.settlementBalance.summary.cashDeposit, 1200000);
    expect(snapshot.settlementBalance.summary.reportedItemCount, 2);
    expect(snapshot.executionBalance.summary.netAssetValuationAmount, 5200000);
  });

  test('fetchSnapshot throws readable exception when API fails', () {
    final repository = SpringKbAccountRepository(
      accessToken: '',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        return http.Response(
          jsonEncode({
            'success': false,
            'error': {'code': 'EXTERNAL_DATA_ERROR', 'message': 'KB 조회 실패'},
          }),
          502,
          headers: {'content-type': 'application/json'},
        );
      }),
    );

    expect(
      repository.fetchSnapshot(),
      throwsA(
        isA<KbAccountRepositoryException>().having(
          (exception) => exception.message,
          'message',
          'KB 조회 실패',
        ),
      ),
    );
  });
}

http.Response _ok(Map<String, dynamic> data) {
  return http.Response(
    jsonEncode({'success': true, 'data': data}),
    200,
    headers: {'content-type': 'application/json'},
  );
}
