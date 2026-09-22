import 'package:app_version/models/holding.dart';
import 'package:app_version/models/investment_snapshot.dart';
import 'package:app_version/models/market_summary.dart';
import 'package:app_version/models/recommendation.dart';
import 'package:app_version/models/watchlist_item.dart';
import 'package:app_version/screens/mini_widget_screen.dart';
import 'package:app_version/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('mini widget shows portfolio watchlist and AI signal', (
    tester,
  ) async {
    var expanded = false;
    var refreshed = false;
    var hidden = false;
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: SizedBox(
          width: 420,
          height: 600,
          child: MiniWidgetScreen(
            snapshot: _snapshot,
            watchlist: const [
              WatchlistItem(
                watchlistId: 1,
                stockCode: '005930',
                stockName: '삼성전자',
                market: 'KOSPI',
                alertEnabled: true,
                provider: 'KB',
                currentPrice: 75200,
                changeRate: 1.21,
              ),
            ],
            onExpand: () => expanded = true,
            onRefresh: () => refreshed = true,
            onHide: () => hidden = true,
          ),
        ),
      ),
    );

    expect(find.text('총 손익'), findsOneWidget);
    expect(find.text('+128,400원'), findsOneWidget);
    expect(find.text('삼성전자'), findsNWidgets(2));
    expect(find.text('75,200원'), findsOneWidget);
    expect(find.text('+1.2%'), findsOneWidget);
    expect(find.text('강한 매수'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.refresh_rounded));
    await tester.pump();
    await tester.tap(find.byIcon(Icons.open_in_full_rounded));
    await tester.pump();
    await tester.tap(find.byIcon(Icons.keyboard_arrow_down_rounded));
    await tester.pump(const Duration(milliseconds: 400));
    expect(refreshed, true);
    expect(expanded, true);
    expect(hidden, true);
  });
}

const _snapshot = InvestmentSnapshot(
  marketSummary: MarketSummary(
    availableCapital: 3000000,
    monthlyReturnRate: 3.8,
    recommendedPositionRange: '30~60만원',
    marketTrend: '강세',
    marketScore: 76,
    newsSentiment: '긍정',
    positiveNewsCount: 12,
    marketBars: [.42],
  ),
  recommendation: InvestmentRecommendation(
    stockName: '삼성전자',
    stockCode: '005930',
    market: 'KOSPI',
    status: '강한 매수',
    score: 87,
    entryPrice: 72000,
    stopLossRate: -5,
    aiSummary: '테스트 추천',
    reasons: [],
  ),
  portfolioSummary: PortfolioSummary(
    totalProfit: 128400,
    profitRate: 4.2,
    maxAllowedLoss: 60000,
    riskUsageRate: .42,
  ),
  holdings: [],
  alerts: [],
);
