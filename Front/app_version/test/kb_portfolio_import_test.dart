import 'dart:convert';

import 'package:app_version/config/api_config.dart';
import 'package:app_version/models/holding.dart';
import 'package:app_version/models/kb_portfolio_import.dart';
import 'package:app_version/models/provider_setting.dart';
import 'package:app_version/repositories/kb_portfolio_importer.dart';
import 'package:app_version/repositories/spring_portfolio_repository.dart';
import 'package:app_version/screens/kb_portfolio_import_sheet.dart';
import 'package:app_version/screens/portfolio_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('KB account reads remain independent from missing market paths', () {
    ProviderSetting setting(bool? accountConfigured) =>
        ProviderSetting.fromJson({
          'code': 'KB',
          'displayName': 'KB증권',
          'accountEnabled': true,
          'configured': false,
          'accountConfigured': accountConfigured,
          'roleDescription': '계좌 조회',
        });
    expect(setting(true).accountQueryConfigured, isTrue);
    expect(setting(false).accountQueryConfigured, isFalse);
    expect(setting(null).accountQueryConfigured, isFalse);
  });

  testWidgets(
    'successful capital-only import closes preview with refresh result',
    (tester) async {
      tester.view.physicalSize = const Size(720, 1300);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      KbPortfolioImportResult? result;
      final importer = _Importer(succeed: true);
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: FilledButton(
                onPressed: () async {
                  result = await showModalBottomSheet<KbPortfolioImportResult>(
                    context: context,
                    isScrollControlled: true,
                    builder: (_) => KbPortfolioImportSheet(importer: importer),
                  );
                },
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('KB 주문가능 현금을 앱 투자 가능 자본금으로 반영'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('선택한 데이터 반영'));
      await tester.tap(find.text('선택한 데이터 반영'));
      await tester.pumpAndSettle();
      expect(result?.capitalImported, isTrue);
      expect(importer.applyCount, 1);
      expect(importer.lastMarkets, isEmpty);
      expect(find.byType(KbPortfolioImportSheet), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
  test(
    'preview is GET and apply sends selection and signed preview, not client balances',
    () async {
      final methods = <String>[];
      final repository = SpringPortfolioRepository(
        accessToken: '',
        config: ApiConfig(baseUrl: 'http://localhost:8080'),
        client: MockClient((request) async {
          methods.add(request.method);
          expect(request.headers.containsKey('Authorization'), isFalse);
          if (request.method == 'GET') {
            expect(request.url.path, '/api/v1/kb/portfolio-import/preview');
            return _success(_previewJson());
          }
          expect(request.url.path, '/api/v1/kb/portfolio-import');
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body['previewToken'], 'signed-preview');
          expect(body['importCapital'], isFalse);
          expect(body['importHoldings'], isTrue);
          expect(body['markets'], {'005930': 'KOSPI'});
          expect(body.containsKey('orderAvailableCash'), isFalse);
          expect(body.containsKey('items'), isFalse);
          return _success({
            'capitalImported': false,
            'createdCount': 1,
            'updatedCount': 0,
            'skippedCount': 0,
          });
        }),
      );
      final preview = await repository.previewKbImport();
      expect(preview.orderAvailableCash, 100000);
      expect(preview.items.single.averageBuyPrice, 70000.25);
      final result = await repository.applyKbImport(
        preview: preview,
        importCapital: false,
        importHoldings: true,
        markets: {'005930': 'KOSPI'},
        stopLossRate: -5,
        takeProfitRate: 9,
      );
      expect(result.createdCount, 1);
      expect(methods, ['GET', 'POST']);
    },
  );

  testWidgets(
    'import needs opt-in and explicit market, and only submits chosen scope',
    (tester) async {
      tester.view.physicalSize = const Size(720, 1300);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final importer = _Importer();
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: KbPortfolioImportSheet(importer: importer)),
        ),
      );
      await tester.pumpAndSettle();
      final button = find.widgetWithText(FilledButton, '선택한 데이터 반영');
      expect(tester.widget<FilledButton>(button).onPressed, isNull);
      expect(importer.applyCount, 0);
      await tester.tap(find.text('KB 보유 종목을 앱에 추가·갱신'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(button);
      await tester.tap(button);
      await tester.pumpAndSettle();
      expect(find.text('삼성전자의 실제 시장을 선택하세요.'), findsOneWidget);
      expect(importer.applyCount, 0);
      await tester.ensureVisible(find.byType(DropdownButtonFormField<String>));
      await tester.tap(find.byType(DropdownButtonFormField<String>));
      await tester.pumpAndSettle();
      await tester.tap(find.text('KOSPI').last);
      await tester.pumpAndSettle();
      await tester.ensureVisible(button);
      await tester.tap(button);
      await tester.pumpAndSettle();
      expect(importer.applyCount, 1);
      expect(importer.lastCapital, isFalse);
      expect(importer.lastMarkets, {'005930': 'KOSPI'});
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'missing cash cannot be selected, and changed preview can be reloaded',
    (tester) async {
      tester.view.physicalSize = const Size(720, 1300);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final importer = _Importer(cash: null);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: KbPortfolioImportSheet(importer: importer)),
        ),
      );
      await tester.pumpAndSettle();
      final boxes = tester
          .widgetList<CheckboxListTile>(find.byType(CheckboxListTile))
          .toList();
      expect(boxes.first.onChanged, isNull);
      expect(find.textContaining('미제공 (반영 불가)'), findsOneWidget);
      await tester.ensureVisible(find.text('KB 미리보기 다시 조회'));
      await tester.tap(find.text('KB 미리보기 다시 조회'));
      await tester.pumpAndSettle();
      expect(importer.previewCount, 2);
      expect(importer.applyCount, 0);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'portfolio shows exact averages, source, fallback and imported read-only menu',
    (tester) async {
      tester.view.physicalSize = const Size(1100, 750);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final holding = Holding.fromJson({
        'holdingId': 7,
        'stockCode': '005930',
        'stockName': '삼성전자',
        'market': 'KOSPI',
        'buyPrice': 70000.25,
        'quantity': 10.1256,
        'buyDate': null,
        'currentPrice': 70000.25,
        'profitRate': 0,
        'stopLossRate': -5,
        'takeProfitRate': 9,
        'status': 'HOLDING',
        'source': 'KB',
        'sourceSyncedAt': '2026-10-30T01:00:00',
        'priceProvider': 'FALLBACK',
        'priceReceivedAt': null,
        'priceFallback': true,
      });
      expect(holding.buyDate, isNull);
      expect(holding.sourceSyncedAt, DateTime.utc(2026, 10, 30, 1));
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PortfolioRow(
              holding: holding,
              onChart: () {},
              onOrderPrecheck: () {},
              onEdit: () {},
              onDelete: () {},
            ),
          ),
        ),
      );
      expect(find.textContaining('70,000.25'), findsNWidgets(2));
      expect(find.textContaining('시세 미확인 · 매수가 대체'), findsOneWidget);
      expect(find.textContaining('KB 스냅샷 · 매수일 미제공'), findsOneWidget);
      await tester.tap(find.byTooltip('보유 종목 메뉴'));
      await tester.pumpAndSettle();
      expect(find.text('수정'), findsNothing);
      expect(find.text('삭제'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}

Map<String, dynamic> _previewJson({num? cash = 100000}) => {
  'previewToken': 'signed-preview',
  'expiresAt': '2026-10-30T01:05:00Z',
  'checkedAt': '2026-10-30T01:00:00Z',
  'currentCapital': 3000000,
  'orderAvailableCash': cash,
  'retainedImportedCount': 0,
  'items': [
    {
      'stockCode': '005930',
      'stockName': '삼성전자',
      'market': 'KRX',
      'quantity': 10.1256,
      'averageBuyPrice': 70000.25,
      'action': 'CREATE',
      'message': '새 KB 보유분으로 추가',
    },
  ],
};

http.Response _success(Object data) => http.Response(
  jsonEncode({'success': true, 'data': data}),
  200,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

class _Importer implements KbPortfolioImporter {
  _Importer({this.cash = 100000, this.succeed = false});
  final num? cash;
  final bool succeed;
  int previewCount = 0;
  int applyCount = 0;
  bool? lastCapital;
  Map<String, String>? lastMarkets;

  @override
  Future<KbPortfolioPreview> previewKbImport() async {
    previewCount++;
    return KbPortfolioPreview.fromJson(_previewJson(cash: cash));
  }

  @override
  Future<KbPortfolioImportResult> applyKbImport({
    required KbPortfolioPreview preview,
    required bool importCapital,
    required bool importHoldings,
    required Map<String, String> markets,
    required double stopLossRate,
    required double takeProfitRate,
  }) async {
    applyCount++;
    lastCapital = importCapital;
    lastMarkets = markets;
    if (succeed) {
      return KbPortfolioImportResult(
        capitalImported: importCapital,
        createdCount: 0,
        updatedCount: 0,
        skippedCount: 0,
      );
    }
    // 재조회 가능한 오류 흐름을 유지하여 테스트 호스트 라우트를 닫지 않습니다.
    throw Exception('KB 잔고가 변경되었습니다. 미리보기를 다시 확인하세요.');
  }
}
