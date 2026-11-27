import 'dart:convert';

import 'package:app_version/config/api_config.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:app_version/repositories/spring_paper_trading_repository.dart';
import 'package:app_version/screens/paper_trading_screen.dart';

void main() {
  testWidgets('opens the automated ledger from the paper trading tab', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1150, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var dashboardRequests = 0;
    final repository = SpringPaperTradingRepository(
      accessToken: 'test',
      config: ApiConfig(baseUrl: 'https://example.test'),
      client: MockClient((request) async {
        final data = request.url.path.endsWith('/automated')
            ? _dashboard(online: ++dashboardRequests == 1)
            : null;
        return http.Response(
          jsonEncode({
            'success': data != null,
            'data': data,
            if (data == null) 'error': {'message': '수동 모의매매 확인 대기'},
          }),
          data == null ? 409 : 200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: PaperTradingScreen(
            repository: repository,
            recommendation: null,
            active: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('AI 자동 모의매매'));
    await tester.pumpAndSettle();
    expect(find.text('SK하이닉스 (000660)'), findsOneWidget);
    expect(find.text('매수 기준가 1,053,000원 이하'), findsOneWidget);
    expect(find.text('자동 체결 1건'), findsOneWidget);
    expect(find.textContaining('0.0500주 × 1,050,000원'), findsOneWidget);
    expect(find.textContaining('2026-11-27 · 매수 0건'), findsOneWidget);
    expect(dashboardRequests, 1);

    await tester.pump(const Duration(seconds: 15));
    await tester.pumpAndSettle();
    expect(find.text('업데이트 지연'), findsOneWidget);
    expect(find.text('자동 체결 1건'), findsOneWidget);
    expect(dashboardRequests, 2);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  test('returns an empty snapshot when the trial is unavailable', () async {
    final repository = SpringPaperTradingRepository(
      accessToken: 'test',
      config: ApiConfig(baseUrl: 'https://example.test'),
      client: MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/api/v1/paper-trading/automated');
        return http.Response(
          '{"success":true,"data":{"available":false,"online":false}}',
          200,
        );
      }),
    );
    expect(await repository.fetchAutomatedSnapshot(), isNull);
  });
}

Map<String, Object> _dashboard({required bool online}) => {
  'available': true,
  'online': online,
  'snapshot': {
    'stockCode': '000660',
    'stockName': 'SK하이닉스',
    'status': '정규장 관측',
    'publishedAt': '2026-11-30T09:15:10+09:00',
    'lastMarketAt': '2026-11-30T09:15:09+09:00',
    'endDate': '2026-12-04',
    'entry': {
      'rule': '직전 5거래일 종가 평균의 98%와 전일 종가 중 낮은 가격 이하',
      'appliesOn': '2026-11-30',
      'eligible': true,
      'threshold': '1053000',
      'averageClose': '1087800',
      'previousClose': '1053000',
    },
    'portfolio': {
      'initialCash': '1000000',
      'cash': '947473',
      'quantity': '0.0500',
      'realizedProfit': '0',
      'unrealizedProfit': '-160',
      'netAsset': '999840',
      'markPrice': '1050000',
      'markSource': '장중 관측가',
    },
    'fillCount': 1,
    'fills': [
      {
        'id': 1,
        'at': '2026-11-30T09:15:09+09:00',
        'side': 'BUY',
        'rule': '최초 매수',
        'threshold': '1053000',
        'price': '1050000',
        'quantity': '0.0500',
        'fee': '27',
        'tax': '0',
        'realized': '0',
      },
    ],
    'closedDays': [
      {'date': '2026-11-27', 'profit': '0', 'buyCount': 0, 'sellCount': 0},
    ],
  },
};
