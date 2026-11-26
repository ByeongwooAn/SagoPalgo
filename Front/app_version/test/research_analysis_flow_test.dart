import 'package:app_version/models/holding.dart';
import 'package:app_version/models/investment_snapshot.dart';
import 'package:app_version/models/market_summary.dart';
import 'package:app_version/models/paper_trading.dart';
import 'package:app_version/models/recommendation.dart';
import 'package:app_version/models/research_feed.dart';
import 'package:app_version/models/watchlist_item.dart';
import 'package:app_version/models/stock_identity.dart';
import 'package:app_version/repositories/paper_trading_repository.dart';
import 'package:app_version/repositories/recommendation_repository.dart';
import 'package:app_version/repositories/research_feed_repository.dart';
import 'package:app_version/repositories/watchlist_editor.dart';
import 'package:app_version/repositories/watchlist_repository.dart';
import 'package:app_version/screens/alerts_screen.dart';
import 'package:app_version/screens/dashboard_screen.dart';
import 'package:app_version/screens/paper_trading_screen.dart';
import 'package:app_version/screens/recommendation_screen.dart';
import 'package:app_version/screens/research_timeline_screen.dart';
import 'package:app_version/screens/watchlist_setup_sheet.dart';
import 'package:app_version/services/alert_delivery_service.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  void largeWindow(WidgetTester tester) {
    tester.view.physicalSize = const Size(1100, 1100);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  testWidgets(
    'watchlist form validates identity and sends an explicit alert preference',
    (tester) async {
      largeWindow(tester);
      final editor = _Watchlist();
      bool? saved;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () async {
                  saved = await showWatchlistSetup(context, editor);
                },
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('관심 종목 저장'));
      await tester.pumpAndSettle();
      expect(editor.saved, isNull);
      expect(find.text('국내 종목코드 6자리를 입력하세요.'), findsOneWidget);
      await tester.enterText(find.byType(TextFormField).at(0), '005930');
      await tester.pump(const Duration(milliseconds: 401));
      await tester.pumpAndSettle();
      expect(find.text('삼성전자'), findsOneWidget);
      await tester.tap(find.text('추천 신호 알림 켜기'));
      await tester.tap(find.text('관심 종목 저장'));
      await tester.pumpAndSettle();
      expect(editor.saved, {
        'code': '005930',
        'name': '삼성전자',
        'market': 'KOSPI',
        'alerts': true,
      });
      expect(saved, isTrue);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'an active research screen loads a newly supplied watchlist and clears removed selection',
    (tester) async {
      largeWindow(tester);
      final repo = _Research();
      Widget screen(List<ResearchStock> stocks) => MaterialApp(
        home: Scaffold(
          body: ResearchTimelineScreen(
            repository: repo,
            stocks: stocks,
            active: true,
            onHoldingSetupOpen: () {},
          ),
        ),
      );
      await tester.pumpWidget(screen([]));
      await tester.pumpAndSettle();
      expect(find.text('조회할 종목이 없습니다'), findsOneWidget);
      await tester.pumpWidget(screen([_stock]));
      await tester.pumpAndSettle();
      expect(repo.loaded, ['005930']);
      expect(find.text('저장된 뉴스와 공시가 없습니다'), findsOneWidget);
      await tester.pumpWidget(screen([]));
      await tester.pumpAndSettle();
      expect(find.text('조회할 종목이 없습니다'), findsOneWidget);
      await tester.pumpWidget(
        screen([const ResearchStock(stockCode: '000660', stockName: 'SK하이닉스')]),
      );
      await tester.pumpAndSettle();
      expect(repo.loaded, ['005930', '000660']);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'research distinguishes failed collection from a successful empty search',
    (tester) async {
      largeWindow(tester);
      final repo = _Research()..syncStatus = 'FAILED';
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ResearchTimelineScreen(
              repository: repo,
              stocks: const [_stock],
              active: true,
              onHoldingSetupOpen: () {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('외부 뉴스·공시 동기화'));
      await tester.pumpAndSettle();
      expect(find.text('수집 실패 · 저장된 결과 없음'), findsOneWidget);
      expect(find.textContaining('수집 완료'), findsNothing);
      repo.syncStatus = 'SUCCESS';
      await tester.tap(find.byTooltip('외부 뉴스·공시 동기화'));
      await tester.pumpAndSettle();
      expect(find.text('조회 기간에 검색 결과가 없습니다'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'watchlist analysis collects research first and displays persisted evidence',
    (tester) async {
      largeWindow(tester);
      final events = <String>[];
      final research = _Research(events: events);
      final recommendation = _Recommendations(events);
      var changed = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: RecommendationScreen(
              recommendation: null,
              holdings: const [],
              recommendationRepository: recommendation,
              watchlistRepository: _Watchlist(),
              researchFeedRepository: research,
              onRecommendationChanged: () => changed++,
              onCapitalSetupOpen: () {},
              onHoldingSetupOpen: () {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('관심 종목 분석'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('삼성전자'));
      await tester.pumpAndSettle();
      expect(events, ['research', 'analysis']);
      expect(changed, 1);
      expect(find.textContaining('WEIGHTED_SIGNAL_V1'), findsOneWidget);
      expect(find.textContaining('뉴스 2'), findsOneWidget);
      expect(find.text('분석 설명'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'alert fetch failure does not claim that there are no alerts or invalidate delivery status',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AlertsScreen(
              alerts: const [],
              fetchError: '목록 요청 실패',
              deliveryStatus: AlertDeliveryStatus(
                checkedAt: DateTime(2026, 10, 31, 10),
              ),
            ),
          ),
        ),
      );
      expect(find.text('목록 요청 실패'), findsOneWidget);
      expect(find.text('알림 목록을 확인할 수 없습니다.'), findsOneWidget);
      expect(find.text('새로운 투자 알림이 없습니다'), findsNothing);
      expect(find.text('전달 상태 정상'), findsOneWidget);
    },
  );

  testWidgets(
    'paper capital requirement opens setup and retries when capital changes',
    (tester) async {
      largeWindow(tester);
      final repo = _Paper();
      var setup = 0;
      Widget screen(int capital) => MaterialApp(
        home: Scaffold(
          body: PaperTradingScreen(
            repository: repo,
            recommendation: null,
            active: true,
            availableCapital: capital,
            onCapitalSetupOpen: () => setup++,
          ),
        ),
      );
      await tester.pumpWidget(screen(0));
      await tester.pumpAndSettle();
      await tester.tap(find.text('자본금 설정하기'));
      expect(setup, 1);
      repo.capital = 1000000;
      await tester.pumpWidget(screen(1000000));
      await tester.pumpAndSettle();
      expect(repo.fetchCount, 2);
      expect(find.text('AI 모의매매'), findsOneWidget);
      expect(find.textContaining('거래 기록은 유지됩니다'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'dashboard shows valuation return, actual index date and article scope',
    (tester) async {
      largeWindow(tester);
      final summary = MarketSummary.fromJson({
        'availableCapital': 55,
        'monthlyReturnRate': 999,
        'portfolioReturnRate': 4.25,
        'recommendedPositionRange': '5원~11원',
        'marketTrend': '상승',
        'marketScore': 0,
        'newsSentiment': '긍정 우세',
        'positiveNewsCount': 2,
        'marketBars': [0.15, 1.0],
        'checkedAt': '2026-10-31T01:00:00Z',
        'index': {
          'status': 'SUCCESS',
          'provider': 'KIS',
          'message': 'KOSPI',
          'value': 3020.5,
          'changeRate': 1.25,
          'receivedAt': '2026-10-31T01:00:00Z',
          'points': [
            {'date': '2026-10-29', 'close': 3000},
            {'date': '2026-10-30', 'close': 3020.5},
          ],
        },
        'news': {
          'status': 'SUCCESS',
          'method': '보유·관심 최근 7일 키워드 분류',
          'articleCount': 3,
          'positiveCount': 2,
          'negativeCount': 0,
          'latestPublishedAt': '2026-10-30T22:00:00Z',
        },
      });
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: DashboardScreen(
              snapshot: InvestmentSnapshot(
                marketSummary: summary,
                recommendation: null,
                portfolioSummary: const PortfolioSummary(
                  totalProfit: 0,
                  profitRate: 0,
                  maxAllowedLoss: 0,
                  riskUsageRate: 0,
                ),
                holdings: const [],
                alerts: const [],
              ),
              onCapitalSetupOpen: () {},
              onHoldingSetupOpen: () {},
            ),
          ),
        ),
      );
      expect(find.text('평가 +4.3%'), findsOneWidget);
      expect(find.textContaining('3020.50 · 전일 대비 +1.3%'), findsOneWidget);
      expect(find.text('1분 전 업데이트'), findsNothing);
      expect(find.textContaining('보유·관심 최근 7일'), findsOneWidget);
      expect(find.byTooltip('2026-10-30 · 3020.50'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}

const _stock = ResearchStock(stockCode: '005930', stockName: '삼성전자');

class _Watchlist implements WatchlistRepository, WatchlistEditor {
  @override
  Future<StockIdentity> lookupStock(String stockCode) async => StockIdentity(
    stockCode: stockCode,
    stockName: '삼성전자',
    market: 'KOSPI',
    provider: 'KIS',
  );
  @override
  Future<void> deleteStock(int watchlistId) async {}
  Map<String, Object>? saved;
  @override
  Future<void> addStock({
    required String stockCode,
    required String stockName,
    required String market,
    required bool alertEnabled,
  }) async {
    saved = {
      'code': stockCode,
      'name': stockName,
      'market': market,
      'alerts': alertEnabled,
    };
  }

  @override
  Future<List<WatchlistItem>> fetchWatchlist() async => const [
    WatchlistItem(
      watchlistId: 12,
      stockCode: '005930',
      stockName: '삼성전자',
      market: 'KOSPI',
      alertEnabled: true,
      provider: 'KB',
      currentPrice: 100,
      changeRate: 0,
    ),
  ];
  @override
  Future<WatchlistActionResult> addRecommendation(
    InvestmentRecommendation recommendation,
  ) async => const WatchlistActionResult(message: '등록');
  @override
  Future<WatchlistActionResult> enableAlert(
    InvestmentRecommendation recommendation,
  ) async => const WatchlistActionResult(message: '설정');
}

class _Research implements ResearchFeedRepository {
  _Research({this.events});
  final List<String>? events;
  final loaded = <String>[];
  String syncStatus = 'SUCCESS';
  ResearchFeed feed(ResearchStock stock, {bool cached = false}) => ResearchFeed(
    stockCode: stock.stockCode,
    stockName: stock.stockName,
    fromDate: DateTime(2026, 10, 1),
    toDate: DateTime(2026, 10, 31),
    news: const [],
    disclosures: const [],
    providers: [
      ResearchProviderStatus(
        provider: cached ? 'LOCAL_DB' : 'NAVER_NEWS',
        dataType: cached ? 'CACHE' : 'NEWS',
        status: cached ? 'SUCCESS' : syncStatus,
        message: cached ? '저장 결과' : '조회 결과',
      ),
    ],
  );
  @override
  Future<ResearchFeed> fetchFeed(ResearchStock stock) async {
    loaded.add(stock.stockCode);
    return feed(stock, cached: true);
  }

  @override
  Future<ResearchFeed> syncFeed(ResearchStock stock) async {
    events?.add('research');
    return feed(stock);
  }

  @override
  Future<ResearchSyncOverview> fetchSyncStatus(ResearchStock stock) async =>
      const ResearchSyncOverview(
        enabled: false,
        cron: '',
        zone: 'Asia/Seoul',
        item: null,
      );
}

class _Recommendations implements RecommendationRepository {
  _Recommendations(this.events);
  final List<String> events;
  InvestmentRecommendation? result;
  @override
  Future<InvestmentRecommendation> analyzeWatchlist(int watchlistId) async {
    events.add('analysis');
    return result = const InvestmentRecommendation(
      recommendationId: 21,
      stockName: '삼성전자',
      stockCode: '005930',
      market: 'KOSPI',
      status: '매수 관찰',
      recommendationType: 'BUY',
      analysisContext: 'WATCHLIST',
      score: 65,
      entryPrice: 100,
      stopLossRate: null,
      aiSummary: '수집 입력 기반 결과',
      reasons: [],
      evidence: AnalysisEvidence(
        modelVersion: 'WEIGHTED_SIGNAL_V1',
        candleCount: 20,
        newsCount: 2,
        disclosureCount: 1,
      ),
    );
  }

  @override
  Future<RecommendationPage> fetchHistory({
    String? status,
    int page = 0,
    int size = 20,
  }) async => RecommendationPage(
    items: result == null ? [] : [result!],
    page: page,
    size: size,
    total: result == null ? 0 : 1,
  );
  @override
  Future<InvestmentRecommendation> fetchDetail(int recommendationId) async =>
      result!;
  @override
  Future<InvestmentRecommendation> analyzeHolding(int holdingId) async =>
      throw UnimplementedError();
}

class _Paper implements PaperTradingRepository {
  int capital = 0;
  int fetchCount = 0;
  @override
  Future<PaperTradingSnapshot> fetchSnapshot() async {
    fetchCount++;
    if (capital == 0) {
      throw const PaperTradingRepositoryException(
        '자본금이 필요합니다.',
        code: 'PAPER_CAPITAL_REQUIRED',
      );
    }
    return PaperTradingSnapshot.fromJson({
      'summary': {
        'initialCapital': capital,
        'cashBalance': capital,
        'openPositionValue': 0,
        'totalAsset': capital,
        'realizedProfit': 0,
        'unrealizedProfit': 0,
        'totalProfit': 0,
        'returnRate': 0,
        'completedTrades': 0,
        'winRate': 0,
        'maxLoss': 0,
        'turnoverRate': 0,
      },
      'positions': [],
      'trades': [],
    });
  }

  @override
  Future<PaperTradingSnapshot> buyFromRecommendation(
    int recommendationId,
    double quantity, {
    required String requestId,
  }) async => throw UnimplementedError();
  @override
  Future<PaperTradingSnapshot> sellPosition({
    required String stockCode,
    required String market,
    required double quantity,
    required String requestId,
  }) async => throw UnimplementedError();
}
