import 'package:app_version/models/kb_account_snapshot.dart';
import 'package:app_version/screens/kb_holdings_detail_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('missing KB weight remains unknown instead of becoming zero', () {
    final item = KbHoldingItem.fromJson({
      'stockCode': '005930',
      'stockName': '삼성전자',
    });

    expect(item.weightRate, isNull);
    expect(
      KbBalanceItem.fromJson({'stockCode': '005930'}).valuationWeightRate,
      isNull,
    );
  });

  testWidgets('shows all KB holdings and the stock-only weight basis', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: KbHoldingsDetailDialog(snapshot: _snapshot())),
      ),
    );

    expect(find.text('KB 계좌 상세'), findsOneWidget);
    expect(find.textContaining('예수금·순자산 제외'), findsOneWidget);
    expect(find.text('40.0%'), findsOneWidget);
    await tester.ensureVisible(find.text('네번째 종목'));
    expect(find.text('네번째 종목'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('prefers KB settlement weight and keeps sources separate', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: KbHoldingsDetailDialog(
            snapshot: _snapshot(
              settlementItems: [
                const KbBalanceItem(
                  stockCode: '005930',
                  stockName: '삼성전자',
                  quantity: 10,
                  orderableQuantity: 8,
                  currentPrice: 77000,
                  averageBuyPrice: 70000,
                  valuationAmount: 770000,
                  profitAmount: 70000,
                  profitRate: 10,
                  valuationWeightRate: 68.14,
                ),
              ],
            ),
          ),
        ),
      ),
    );

    expect(find.textContaining('KB 결제기준 잔고 응답'), findsOneWidget);
    expect(find.text('68.1%'), findsOneWidget);
    await tester.tap(find.text('보유 주식'));
    await tester.pumpAndSettle();
    expect(find.textContaining('예수금·순자산 제외'), findsOneWidget);
    expect(find.text('40.0%'), findsOneWidget);
  });

  testWidgets('zero valuation does not display a calculated weight', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: KbHoldingsDetailDialog(
            snapshot: _snapshot(
              holdings: KbHoldingsSnapshot(
                summary: const KbPortfolioSummary(
                  totalPurchaseAmount: 0,
                  totalValuationAmount: 0,
                  totalProfitAmount: 0,
                  profitRate: 0,
                ),
                items: [_item('005930', '삼성전자', 0, 0, 100)],
              ),
            ),
          ),
        ),
      ),
    );

    expect(find.text('산정 불가'), findsOneWidget);
    expect(find.text('100.0%'), findsNothing);
  });

  testWidgets('narrow window keeps the source and weight readable', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(360, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: KbHoldingsDetailDialog(snapshot: _snapshot())),
      ),
    );

    expect(find.text('40.0%'), findsOneWidget);
    expect(find.textContaining('예수금·순자산 제외'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

KbAccountSnapshot _snapshot({
  KbHoldingsSnapshot? holdings,
  List<KbBalanceItem> settlementItems = const [],
}) => KbAccountSnapshot(
  holdings: holdings ?? _holdings(),
  settlementBalance: KbBalanceSnapshot(
    summary: _balanceSummary,
    items: settlementItems,
  ),
  executionBalance: const KbBalanceSnapshot(
    summary: _balanceSummary,
    items: [],
  ),
);

const _balanceSummary = KbBalanceSummary(
  basis: 'SETTLEMENT',
  cashDeposit: 0,
  withdrawalAvailableAmount: 0,
  orderAvailableCash: 0,
  netAssetValuationAmount: 0,
  securitiesNetValuationAmount: 0,
  totalPurchaseAmount: 0,
  totalValuationAmount: 0,
  totalProfitAmount: 0,
  totalYieldRate: 0,
);

KbHoldingsSnapshot _holdings() => KbHoldingsSnapshot(
  summary: const KbPortfolioSummary(
    totalPurchaseAmount: 900000,
    totalValuationAmount: 1000000,
    totalProfitAmount: 100000,
    profitRate: 11.11,
  ),
  items: [
    _item('005930', '삼성전자', 400000, 40000, 40),
    _item('000660', '두번째 종목', 300000, 30000, 30),
    _item('035420', '세번째 종목', 200000, 20000, 20),
    _item('035720', '네번째 종목', 100000, 10000, 10),
  ],
);

KbHoldingItem _item(
  String code,
  String name,
  int valuation,
  int profit,
  double weight,
) => KbHoldingItem(
  stockCode: code,
  stockName: name,
  market: 'KRX',
  quantity: 10,
  currentPrice: valuation ~/ 10,
  valuationAmount: valuation,
  profitAmount: profit,
  profitRate: 10,
  weightRate: weight,
);
