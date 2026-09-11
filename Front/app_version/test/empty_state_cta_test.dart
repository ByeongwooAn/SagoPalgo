import 'package:app_version/models/holding.dart';
import 'package:app_version/models/investment_snapshot.dart';
import 'package:app_version/models/market_summary.dart';
import 'package:app_version/repositories/watchlist_repository.dart';
import 'package:app_version/screens/dashboard_screen.dart';
import 'package:app_version/screens/recommendation_screen.dart';
import 'package:app_version/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('dashboard empty state exposes setup actions', (tester) async {
    var capitalTapped = false;
    var holdingTapped = false;

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: Scaffold(
          body: DashboardScreen(
            snapshot: _emptySnapshot,
            onCapitalSetupOpen: () => capitalTapped = true,
            onHoldingSetupOpen: () => holdingTapped = true,
          ),
        ),
      ),
    );

    expect(find.text('실제 데이터 시작하기'), findsOneWidget);

    await tester.tap(find.text('자본금 설정하기'));
    expect(capitalTapped, isTrue);

    await tester.tap(find.text('보유 종목 추가하기'));
    expect(holdingTapped, isTrue);
  });

  testWidgets('recommendation empty state exposes setup actions', (
    tester,
  ) async {
    var capitalTapped = false;
    var holdingTapped = false;

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: Scaffold(
          body: RecommendationScreen(
            recommendation: null,
            watchlistRepository: const _NoopWatchlistRepository(),
            onCapitalSetupOpen: () => capitalTapped = true,
            onHoldingSetupOpen: () => holdingTapped = true,
          ),
        ),
      ),
    );

    expect(find.text('추천 데이터 없음'), findsOneWidget);

    await tester.tap(find.text('자본금 설정하기'));
    expect(capitalTapped, isTrue);

    await tester.tap(find.text('보유 종목 추가하기'));
    expect(holdingTapped, isTrue);
  });
}

const _emptySnapshot = InvestmentSnapshot(
  marketSummary: MarketSummary(
    availableCapital: 0,
    monthlyReturnRate: 0,
    recommendedPositionRange: '0원~0원',
    marketTrend: '데이터 없음',
    marketScore: 0,
    newsSentiment: '데이터 없음',
    positiveNewsCount: 0,
    marketBars: [],
  ),
  recommendation: null,
  portfolioSummary: PortfolioSummary(
    totalProfit: 0,
    profitRate: 0,
    maxAllowedLoss: 0,
    riskUsageRate: 0,
  ),
  holdings: [],
  alerts: [],
);

class _NoopWatchlistRepository implements WatchlistRepository {
  const _NoopWatchlistRepository();

  @override
  Future<WatchlistActionResult> addRecommendation(recommendation) async {
    return const WatchlistActionResult(message: 'noop');
  }

  @override
  Future<WatchlistActionResult> enableAlert(recommendation) async {
    return const WatchlistActionResult(message: 'noop');
  }
}
