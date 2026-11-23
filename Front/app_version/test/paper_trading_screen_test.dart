import 'dart:async';

import 'package:app_version/models/paper_trading.dart';
import 'package:app_version/models/recommendation.dart';
import 'package:app_version/repositories/paper_trading_repository.dart';
import 'package:app_version/screens/paper_trading_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets(
    'US trading is reachable without KRW capital and retries the same order',
    (tester) async {
      final repository = _FakeUsPaperRepository();
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
      await tester.tap(find.text('미국주식 모의매매 (USD)'));
      await tester.pumpAndSettle();
      expect(find.text('USD 모의계좌 개설'), findsOneWidget);
      await tester.tap(find.text('USD 시작 자금 설정'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), '1000.25');
      await tester.tap(find.text('개설'));
      await tester.pumpAndSettle();
      expect(repository.capital, '1000.25');
      expect(find.text('1000.25 USD'), findsWidgets);

      await tester.tap(find.text('미국주식 모의매수'));
      await tester.pumpAndSettle();
      final inputs = find.byType(TextFormField);
      await tester.enterText(inputs.at(0), 'aapl');
      await tester.enterText(inputs.at(1), '.1234');
      await tester.tap(find.text('현재가로 모의매수'));
      await tester.pumpAndSettle();
      expect(repository.orders.single.stockCode, 'AAPL');
      expect(repository.orders.single.quantity, '.1234');
      await tester.tap(find.text('같은 주문으로 결과 확인'));
      await tester.pumpAndSettle();
      expect(repository.orders, hasLength(2));
      expect(repository.orders.last, repository.orders.first);
      expect(find.text('같은 주문으로 결과 확인'), findsNothing);
    },
  );

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
    final repository = _FakePaperTradingRepository()
      ..loseFirstBuyResponse = true;

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
    expect(find.text('삼성전자 · 매수 관찰'), findsOneWidget);
    expect(find.text('보유 포지션 1'), findsOneWidget);

    await tester.tap(find.text('AI 신호로 모의매수'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '3.5');
    await tester.tap(find.widgetWithText(FilledButton, '모의매수'));
    await tester.pumpAndSettle();

    expect(repository.buyRecommendationId, 11);
    expect(repository.buyQuantity, 3.5);
    await tester.tap(find.text('같은 주문으로 결과 확인'));
    await tester.pumpAndSettle();
    expect(repository.buyRequestIds, hasLength(2));
    expect(repository.buyRequestIds.toSet(), hasLength(1));
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

  testWidgets('expired daily signal disables the KRW buy action', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: PaperTradingScreen(
            repository: _FakePaperTradingRepository(),
            recommendation: _dailyRecommendation(
              DateTime.now().subtract(const Duration(seconds: 1)),
            ),
            active: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final buy = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'AI 신호로 모의매수'),
    );
    expect(buy.onPressed, isNull);
    expect(find.text('유효한 장 마감 모델 매수 관찰 신호가 필요합니다.'), findsOneWidget);
  });
}

class _FakeUsPaperRepository extends _FakePaperTradingRepository
    implements UsPaperTradingRepository {
  String? capital;
  final orders = <UsPaperOrder>[];

  @override
  Future<PaperTradingSnapshot> fetchSnapshot() async =>
      throw const PaperTradingRepositoryException(
        '원화 자본금 미설정',
        code: 'PAPER_CAPITAL_REQUIRED',
      );

  @override
  Future<PaperTradingSnapshot> fetchUsSnapshot() async {
    final amount = double.tryParse(capital ?? '') ?? 0;
    return PaperTradingSnapshot(
      currency: 'USD',
      summary: PaperTradingSummary(
        initialCapital: amount,
        cashBalance: amount,
        openPositionValue: 0,
        totalAsset: amount,
        realizedProfit: 0,
        unrealizedProfit: 0,
        totalProfit: 0,
        returnRate: 0,
        completedTrades: 0,
        winRate: 0,
        maxLoss: 0,
        turnoverRate: 0,
      ),
      positions: const [],
      trades: const [],
    );
  }

  @override
  Future<PaperTradingSnapshot> openUsAccount(String initialCapital) {
    capital = initialCapital;
    return fetchUsSnapshot();
  }

  @override
  Future<PaperTradingSnapshot> tradeUs(UsPaperOrder order) {
    orders.add(order);
    if (orders.length == 1) throw TimeoutException('unconfirmed');
    return fetchUsSnapshot();
  }
}

final _recommendation = _dailyRecommendation(
  DateTime.now().add(const Duration(hours: 1)),
);

InvestmentRecommendation _dailyRecommendation(DateTime expiry) =>
    InvestmentRecommendation(
      recommendationId: 11,
      stockName: '삼성전자',
      stockCode: '005930',
      market: 'KOSPI',
      status: '보유 유지',
      recommendationType: 'HOLD',
      score: 87,
      entryPrice: 70000,
      stopLossRate: -5,
      aiSummary: '테스트 추천',
      reasons: [],
      evidence: AnalysisEvidence(
        modelVersion: 'test',
        dailySignal: DailyModelSignal(
          decision: 'BUY_WATCH',
          basisDate: '2026-11-20',
          expiresAt: expiry,
          contributions: const {},
        ),
      ),
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
  bool loseFirstBuyResponse = false;
  final buyRequestIds = <String>[];
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
    double quantity, {
    required String requestId,
  }) async {
    buyRecommendationId = recommendationId;
    buyQuantity = quantity;
    buyRequestIds.add(requestId);
    if (loseFirstBuyResponse && buyRequestIds.length == 1) {
      throw TimeoutException('응답 유실');
    }
    return _snapshot;
  }

  @override
  Future<PaperTradingSnapshot> sellPosition({
    required String stockCode,
    required String market,
    required double quantity,
    required String requestId,
  }) async {
    sellStockCode = stockCode;
    sellQuantity = quantity;
    return _snapshot;
  }
}
