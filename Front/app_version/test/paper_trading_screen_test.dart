import 'package:app_version/models/paper_trading.dart';
import 'package:app_version/models/recommendation.dart';
import 'package:app_version/repositories/paper_trading_repository.dart';
import 'package:app_version/screens/paper_trading_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('inactive paper trading tab does not request data', (
    tester,
  ) async {
    final repository = _FakePaperTradingRepository();

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: PaperTradingScreen(
            repository: repository,
            recommendation: _recommendation,
            active: false,
          ),
        ),
      ),
    );

    expect(repository.fetchCount, 0);
    expect(find.text('AI 모의매매'), findsNothing);
  });

  testWidgets('paper trading screen renders metrics and executes trades', (
    tester,
  ) async {
    final repository = _FakePaperTradingRepository();

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: PaperTradingScreen(
            repository: repository,
            recommendation: _recommendation,
            active: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('AI 모의매매'), findsOneWidget);
    expect(find.text('1,010,000원'), findsOneWidget);
    expect(find.text('삼성전자 · 강한 매수'), findsOneWidget);
    expect(find.text('보유 포지션 1'), findsOneWidget);

    await tester.tap(find.text('AI 신호로 모의매수'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '3.5');
    await tester.tap(find.widgetWithText(FilledButton, '모의매수'));
    await tester.pumpAndSettle();

    expect(repository.buyRecommendationId, 11);
    expect(repository.buyQuantity, 3.5);
    expect(find.text('삼성전자 모의매수가 체결되었습니다.'), findsOneWidget);

    await tester.ensureVisible(find.text('모의매도'));
    await tester.tap(find.text('모의매도'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '2');
    await tester.tap(find.widgetWithText(FilledButton, '모의매도'));
    await tester.pumpAndSettle();

    expect(repository.sellStockCode, '005930');
    expect(repository.sellQuantity, 2);
    expect(find.text('삼성전자 모의매도가 체결되었습니다.'), findsOneWidget);
  });
}

const _recommendation = InvestmentRecommendation(
  recommendationId: 11,
  stockName: '삼성전자',
  stockCode: '005930',
  market: 'KOSPI',
  status: '강한 매수',
  recommendationType: 'BUY',
  score: 87,
  entryPrice: 70000,
  stopLossRate: -5,
  aiSummary: '테스트 추천',
  reasons: [],
);

final _snapshot = PaperTradingSnapshot(
  summary: const PaperTradingSummary(
    initialCapital: 1000000,
    cashBalance: 250000,
    openPositionValue: 760000,
    totalAsset: 1010000,
    realizedProfit: 4000,
    unrealizedProfit: 6000,
    totalProfit: 10000,
    returnRate: 1,
    completedTrades: 2,
    winRate: 50,
    maxLoss: 2000,
    turnoverRate: 125,
  ),
  positions: const [
    PaperPosition(
      stockCode: '005930',
      stockName: '삼성전자',
      market: 'KOSPI',
      provider: 'KB',
      quantity: 10,
      averagePrice: 70000,
      currentPrice: 76000,
      valuationAmount: 760000,
      unrealizedProfit: 60000,
      profitRate: 8.57,
    ),
  ],
  trades: [
    PaperTrade(
      tradeRecordId: 1,
      recommendationId: 11,
      stockCode: '005930',
      stockName: '삼성전자',
      market: 'KOSPI',
      tradeType: 'BUY',
      tradePrice: 70000,
      quantity: 10,
      tradeAmount: 700000,
      realizedProfit: 0,
      tradeDate: DateTime(2026, 9, 23, 10, 30),
      memo: 'AI 강한 매수 신호 모의매수',
    ),
  ],
);

class _FakePaperTradingRepository implements PaperTradingRepository {
  int fetchCount = 0;
  int? buyRecommendationId;
  double? buyQuantity;
  String? sellStockCode;
  double? sellQuantity;

  @override
  Future<PaperTradingSnapshot> fetchSnapshot() async {
    fetchCount++;
    return _snapshot;
  }

  @override
  Future<PaperTradingSnapshot> buyFromRecommendation(
    int recommendationId,
    double quantity,
  ) async {
    buyRecommendationId = recommendationId;
    buyQuantity = quantity;
    return _snapshot;
  }

  @override
  Future<PaperTradingSnapshot> sellPosition({
    required String stockCode,
    required String market,
    required double quantity,
  }) async {
    sellStockCode = stockCode;
    sellQuantity = quantity;
    return _snapshot;
  }
}
