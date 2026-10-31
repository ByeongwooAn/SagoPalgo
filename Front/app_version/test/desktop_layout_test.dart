import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:app_version/main.dart';
import 'package:app_version/models/investment_snapshot.dart';
import 'package:app_version/models/market_summary.dart';
import 'package:app_version/models/holding.dart';
import 'package:app_version/models/recommendation.dart';
import 'package:app_version/repositories/investment_repository.dart';
import 'package:app_version/repositories/recommendation_repository.dart';
import 'package:app_version/screens/dashboard_screen.dart';
import 'package:app_version/screens/alerts_screen.dart';
import 'package:app_version/screens/paper_trading_screen.dart';
import 'package:app_version/screens/recommendation_screen.dart';
import 'package:app_version/screens/mini_widget_screen.dart';
import 'package:app_version/widgets/bottom_nav.dart';
import 'widget_test.dart' as fixtures;

Widget buildDesktopTestApp({
  InvestmentRepository? investment,
  RecommendationRepository? recommendations,
}) => SagoPalgoApp(
  investmentRepositoryBuilder: (_) =>
      investment ?? const fixtures.FakeInvestmentRepository(),
  watchlistRepositoryBuilder: (_) => const fixtures.FakeWatchlistRepository(),
  portfolioRepositoryBuilder: (_) => const fixtures.FakePortfolioRepository(),
  providerSettingsRepositoryBuilder: (_) =>
      const fixtures.FakeProviderSettingsRepository(),
  recommendationRepositoryBuilder: (_) =>
      recommendations ?? const fixtures.FakeRecommendationRepository(),
  researchFeedRepositoryBuilder: (_) =>
      const fixtures.FakeResearchFeedRepository(),
  kbAccountRepositoryBuilder: (_) => const fixtures.FakeKbAccountRepository(),
  marketDataRepositoryBuilder: (_) => const fixtures.FakeMarketDataRepository(),
  orderPrecheckRepositoryBuilder: (_) =>
      const fixtures.FakeOrderPrecheckRepository(),
  paperTradingRepositoryBuilder: (_) =>
      const fixtures.FakePaperTradingRepository(),
);

void main() {
  void window(WidgetTester tester, Size size) {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = size;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  for (final size in [
    const Size(360, 720),
    const Size(800, 600),
    const Size(1280, 720),
    const Size(1920, 1080),
  ]) {
    testWidgets(
      'all tabs fit ${size.width} x ${size.height} and use matching navigation',
      (tester) async {
        window(tester, size);
        await tester.pumpWidget(buildDesktopTestApp());
        await tester.pumpAndSettle();
        final desktop = size.width >= 1100;
        expect(
          find.byType(DesktopNav),
          desktop ? findsOneWidget : findsNothing,
        );
        expect(find.byType(BottomNav), desktop ? findsNothing : findsOneWidget);
        expect(
          tester.getSize(find.byType(CapitalCard)).width,
          lessThanOrEqualTo(1280),
        );
        final candidate = tester.getRect(find.byType(CandidateCard));
        final graph = tester.getRect(find.byType(MarketBarsCard));
        if (size.width >= 1280) {
          expect(candidate.top, graph.top);
          expect(candidate.right, lessThan(graph.left));
        } else {
          expect(candidate.bottom, lessThan(graph.top));
        }
        for (final destination in appDestinations) {
          final nav = desktop
              ? find.byType(DesktopNav)
              : find.byType(BottomNav);
          await tester.tap(
            find.descendant(of: nav, matching: find.text(destination.label)),
          );
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull, reason: destination.label);
        }
      },
    );
  }

  testWidgets('large text keeps every tab usable in a medium window', (
    tester,
  ) async {
    window(tester, const Size(800, 700));
    tester.platformDispatcher.textScaleFactorTestValue = 1.4;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await tester.pumpWidget(buildDesktopTestApp());
    await tester.pumpAndSettle();
    for (final destination in appDestinations) {
      await tester.tap(
        find.descendant(
          of: find.byType(BottomNav),
          matching: find.text(destination.label),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: destination.label);
    }
  });

  testWidgets(
    'resizing preserves selected tab, analysis choice and loaded history',
    (tester) async {
      window(tester, const Size(1920, 1080));
      final investment = _Investment();
      final recommendations = _Recommendations();
      await tester.pumpWidget(
        buildDesktopTestApp(
          investment: investment,
          recommendations: recommendations,
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(
        find.descendant(of: find.byType(DesktopNav), matching: find.text('추천')),
      );
      await tester.pumpAndSettle();
      final checkbox = find.widgetWithText(CheckboxListTile, '분석 전에 뉴스·공시 수집');
      await tester.tap(checkbox);
      await tester.pumpAndSettle();
      final calls = recommendations.calls;
      for (final size in [
        const Size(800, 700),
        const Size(1099, 720),
        const Size(1100, 720),
        const Size(1280, 720),
      ]) {
        tester.view.physicalSize = size;
        await tester.pumpAndSettle();
        expect(tester.widget<CheckboxListTile>(checkbox).value, isFalse);
        expect(recommendations.calls, calls);
        expect(investment.calls, 1);
        if (size.width >= 1100) {
          expect(
            tester
                .widget<NavigationRail>(find.byType(NavigationRail))
                .selectedIndex,
            1,
          );
        } else {
          expect(
            tester.widget<BottomNav>(find.byType(BottomNav)).selectedIndex,
            1,
          );
        }
        expect(tester.takeException(), isNull);
      }
    },
  );

  testWidgets(
    'home setup supports watchlist-only analysis and shows lookup failure separately',
    (tester) async {
      window(tester, const Size(800, 800));
      var register = 0;
      var analyze = 0;
      Widget home({int? count, bool failed = false}) => MaterialApp(
        home: Scaffold(
          body: DashboardScreen(
            snapshot: _empty,
            watchlistCount: count,
            watchlistLoadFailed: failed,
            onCapitalSetupOpen: () {},
            onHoldingSetupOpen: () {},
            onWatchlistSetupOpen: () => register++,
            onAnalysisOpen: () => analyze++,
          ),
        ),
      );
      await tester.pumpWidget(home(failed: true));
      await tester.pumpAndSettle();
      expect(find.text('관심 목록 조회 실패'), findsOneWidget);
      expect(find.text('○ 등록 종목 없음'), findsNothing);
      await tester.tap(find.text('관심 종목 등록'));
      expect(register, 1);
      await tester.pumpWidget(home(count: 1));
      await tester.pumpAndSettle();
      expect(find.text('✓ 관심 1종목 등록됨'), findsOneWidget);
      await tester.tap(find.text('추천에서 분석하기'));
      expect(analyze, 1);
    },
  );

  testWidgets('empty alerts and paper trading expose analysis navigation', (
    tester,
  ) async {
    window(tester, const Size(800, 800));
    var analysis = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AlertsScreen(
            alerts: const [],
            onAnalysisOpen: () => analysis++,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('추천에서 분석하기'));
    expect(analysis, 1);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: PaperTradingScreen(
            repository: const fixtures.FakePaperTradingRepository(),
            recommendation: null,
            active: true,
            onAnalysisOpen: () => analysis++,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('추천 분석으로 이동'));
    await tester.tap(find.text('추천 분석으로 이동'));
    expect(analysis, 2);
  });

  testWidgets(
    'mini widget remains free of full navigation and can expand again',
    (tester) async {
      window(tester, const Size(1280, 720));
      await tester.pumpWidget(buildDesktopTestApp());
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('미니 위젯'));
      await tester.pumpAndSettle();
      expect(find.byType(MiniWidgetScreen), findsOneWidget);
      expect(find.byType(DesktopNav), findsNothing);
      expect(find.byType(BottomNav), findsNothing);
      await tester.tap(find.byTooltip('전체 화면'));
      // 미니 위젯의 두 번 클릭 인식이 단일 클릭을 확정할 시간을 진행합니다.
      await tester.pump(const Duration(milliseconds: 350));
      await tester.pumpAndSettle();
      expect(find.byType(MiniWidgetScreen), findsNothing);
      expect(find.byType(DesktopNav), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'failed recommendation history is distinguished from an empty history',
    (tester) async {
      window(tester, const Size(800, 700));
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: RecommendationScreen(
              recommendation: null,
              holdings: const [],
              recommendationRepository: _FailedHistory(),
              watchlistRepository: const fixtures.FakeWatchlistRepository(),
              onRecommendationChanged: () {},
              onCapitalSetupOpen: () {},
              onHoldingSetupOpen: () {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('추천 이력 조회 실패'), findsOneWidget);
      expect(find.text('추천 데이터 없음'), findsNothing);
      expect(find.text('추천 이력을 불러오지 못했습니다. 다시 조회하거나 등록된 종목을 분석하세요.'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}

class _Investment extends fixtures.FakeInvestmentRepository {
  int calls = 0;
  @override
  Future<InvestmentSnapshot> fetchSnapshot() {
    calls++;
    return super.fetchSnapshot();
  }
}

class _Recommendations extends fixtures.FakeRecommendationRepository {
  int calls = 0;
  @override
  Future<RecommendationPage> fetchHistory({
    String? status,
    int page = 0,
    int size = 20,
  }) {
    calls++;
    return super.fetchHistory(status: status, page: page, size: size);
  }
}

class _FailedHistory extends fixtures.FakeRecommendationRepository {
  @override
  Future<RecommendationPage> fetchHistory({
    String? status,
    int page = 0,
    int size = 20,
  }) async => throw const RecommendationRepositoryException('이력 조회 실패');
}

const _empty = InvestmentSnapshot(
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
  holdings: [],
  alerts: [],
  portfolioSummary: PortfolioSummary(
    totalProfit: 0,
    profitRate: 0,
    maxAllowedLoss: 0,
    riskUsageRate: 0,
  ),
);
