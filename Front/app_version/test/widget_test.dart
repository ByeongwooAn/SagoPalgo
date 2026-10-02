import 'package:app_version/main.dart';
import 'package:app_version/models/app_alert.dart';
import 'package:app_version/models/holding.dart';
import 'package:app_version/models/investment_snapshot.dart';
import 'package:app_version/models/kb_account_snapshot.dart';
import 'package:app_version/models/market_candle.dart';
import 'package:app_version/models/market_summary.dart';
import 'package:app_version/models/order_precheck.dart';
import 'package:app_version/models/paper_trading.dart';
import 'package:app_version/models/provider_setting.dart';
import 'package:app_version/models/recommendation.dart';
import 'package:app_version/models/research_feed.dart';
import 'package:app_version/models/watchlist_item.dart';
import 'package:app_version/repositories/investment_repository.dart';
import 'package:app_version/repositories/kb_account_repository.dart';
import 'package:app_version/repositories/market_data_repository.dart';
import 'package:app_version/repositories/order_precheck_repository.dart';
import 'package:app_version/repositories/paper_trading_repository.dart';
import 'package:app_version/repositories/portfolio_repository.dart';
import 'package:app_version/repositories/provider_settings_repository.dart';
import 'package:app_version/repositories/recommendation_repository.dart';
import 'package:app_version/repositories/research_feed_repository.dart';
import 'package:app_version/repositories/watchlist_repository.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// 사고팔고 앱의 기본 위젯 스모크 테스트입니다.
///
/// 이 테스트는 세부 디자인 픽셀을 검증하기보다, 앱이 정상 렌더링되고
/// 핵심 사용자 흐름인 탭 이동과 테마 전환이 깨지지 않는지 확인합니다.
void main() {
  testWidgets('SagoPalgo UI renders and navigates', (tester) async {
    /// 앱 루트를 테스트 환경에 올려 실제 Android 앱과 같은 위젯 트리를 만듭니다.
    await tester.pumpWidget(
      SagoPalgoApp(
        investmentRepositoryBuilder: (_) => const FakeInvestmentRepository(),
        watchlistRepositoryBuilder: (_) => const FakeWatchlistRepository(),
        portfolioRepositoryBuilder: (_) => const FakePortfolioRepository(),
        providerSettingsRepositoryBuilder: (_) =>
            const FakeProviderSettingsRepository(),
        recommendationRepositoryBuilder: (_) =>
            const FakeRecommendationRepository(),
        researchFeedRepositoryBuilder: (_) =>
            const FakeResearchFeedRepository(),
        kbAccountRepositoryBuilder: (_) => const FakeKbAccountRepository(),
        marketDataRepositoryBuilder: (_) => const FakeMarketDataRepository(),
        orderPrecheckRepositoryBuilder: (_) =>
            const FakeOrderPrecheckRepository(),
        paperTradingRepositoryBuilder: (_) =>
            const FakePaperTradingRepository(),
      ),
    );

    /// 개인용 프로그램은 로그인 없이 바로 홈 화면으로 진입합니다.
    await tester.pumpAndSettle();

    /// 홈 화면에는 앱 브랜드명, 로컬 사용자명, 자본금 카드가 보여야 합니다.
    expect(find.text('사고팔고'), findsAtLeastNWidgets(1));
    expect(find.text('개인 사용자 · 개인 모드'), findsOneWidget);
    expect(find.text('3,000,000원'), findsOneWidget);

    /// 포트폴리오 보유 종목에서 실제 캔들 상세 화면으로 진입할 수 있어야 합니다.
    await tester.tap(find.text('보유'));
    await tester.pumpAndSettle();
    final chartButton = find.byTooltip('삼성전자 차트');
    await tester.ensureVisible(chartButton);
    await tester.tap(chartButton);
    await tester.pumpAndSettle();
    expect(find.text('005930 · KOSPI'), findsOneWidget);
    expect(find.text('KB 데이터'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();

    /// 하단 네비게이션의 추천 탭을 눌러 추천 상세 화면으로 이동합니다.
    await tester.tap(find.text('추천'));
    await tester.pumpAndSettle();

    /// 추천 상세 화면에는 매수 추천 제목과 강한 매수 상태가 보여야 합니다.
    expect(find.text('추천 분석'), findsOneWidget);
    expect(find.text('강한 매수'), findsOneWidget);

    /// 소식 탭에서는 보유 종목의 저장된 뉴스와 공시를 함께 확인합니다.
    await tester.tap(find.text('소식'));
    await tester.pumpAndSettle();
    expect(find.text('뉴스 · 공시'), findsOneWidget);
    expect(find.text('반도체 투자 확대'), findsOneWidget);
    expect(find.text('주요사항보고서'), findsOneWidget);
    expect(find.text('자동 수집'), findsOneWidget);
    expect(find.text('부분 성공'), findsOneWidget);

    /// 모의 탭은 실제 주문과 분리된 성과와 포지션을 표시합니다.
    await tester.tap(find.text('모의'));
    await tester.pumpAndSettle();
    expect(find.text('AI 모의매매'), findsOneWidget);
    expect(find.text('모의 총자산'), findsOneWidget);

    /// 추천 액션 검증을 위해 추천 탭으로 돌아갑니다.
    await tester.tap(find.text('추천'));
    await tester.pumpAndSettle();

    /// 관심 등록 버튼은 테스트 Repository를 통해 성공 피드백을 보여줍니다.
    await tester.ensureVisible(find.text('관심 등록'));
    await tester.tap(find.text('관심 등록'));
    await tester.pumpAndSettle();
    expect(find.text('삼성전자 관심 종목에 등록했습니다.'), findsOneWidget);

    /// 라이트모드에서 다크모드로 전환되는지 상단 테마 버튼을 눌러 확인합니다.
    await tester.tap(find.byIcon(Icons.dark_mode));
    await tester.pumpAndSettle();

    /// 다크모드가 되면 버튼 아이콘이 다시 라이트모드 전환 아이콘으로 바뀝니다.
    expect(find.byIcon(Icons.light_mode), findsOneWidget);

    /// 설정 탭에서는 개인용 증권사 연동 상태를 확인할 수 있어야 합니다.
    await tester.tap(find.text('설정'));
    await tester.pumpAndSettle();
    expect(find.text('증권사 연동'), findsOneWidget);
    expect(find.text('KB증권'), findsOneWidget);
    expect(find.text('한국투자증권'), findsOneWidget);
    expect(find.text('토스증권'), findsOneWidget);
    expect(find.text('네이버 뉴스'), findsOneWidget);
    expect(find.text('OpenDART'), findsOneWidget);
    expect(find.text('시세 fallback'), findsOneWidget);
    expect(find.text('KB증권 → 한국투자증권 → 토스증권 → 등록 매수가'), findsOneWidget);
    expect(
      find.text('누락: Base URL · 현재가 API 경로 · App Key · App Secret'),
      findsOneWidget,
    );
    expect(find.text('KB 계좌 조회'), findsOneWidget);
    expect(find.textContaining('건수 확인 필요'), findsOneWidget);
    expect(find.text('1종목'), findsOneWidget);
    expect(find.text('5,200,000원'), findsAtLeastNWidgets(1));
    await tester.ensureVisible(find.text('전체 보유 종목 (1)'));
    await tester.tap(find.text('전체 보유 종목 (1)'));
    await tester.pumpAndSettle();
    expect(find.text('KB 계좌 상세'), findsOneWidget);
    expect(find.text('14.6%'), findsAtLeastNWidgets(1));
    await tester.tap(find.byTooltip('닫기'));
    await tester.pumpAndSettle();
    expect(find.text('Windows 앱 잠금'), findsOneWidget);
    expect(find.text('설정 안 됨'), findsOneWidget);

    await tester.ensureVisible(find.text('PIN 설정'));
    await tester.tap(find.text('PIN 설정'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, '새 PIN'), '2468');
    await tester.enterText(find.widgetWithText(TextField, 'PIN 확인'), '2468');
    await tester.tap(find.text('저장'));
    await tester.pumpAndSettle();
    expect(find.text('보호됨'), findsOneWidget);
  });

  testWidgets('app lock requires configured local PIN', (tester) async {
    await tester.pumpWidget(
      SagoPalgoApp(
        appLockPin: '1234',
        investmentRepositoryBuilder: (_) => const FakeInvestmentRepository(),
        watchlistRepositoryBuilder: (_) => const FakeWatchlistRepository(),
        portfolioRepositoryBuilder: (_) => const FakePortfolioRepository(),
        providerSettingsRepositoryBuilder: (_) =>
            const FakeProviderSettingsRepository(),
        recommendationRepositoryBuilder: (_) =>
            const FakeRecommendationRepository(),
        researchFeedRepositoryBuilder: (_) =>
            const FakeResearchFeedRepository(),
        kbAccountRepositoryBuilder: (_) => const FakeKbAccountRepository(),
        marketDataRepositoryBuilder: (_) => const FakeMarketDataRepository(),
        orderPrecheckRepositoryBuilder: (_) =>
            const FakeOrderPrecheckRepository(),
        paperTradingRepositoryBuilder: (_) =>
            const FakePaperTradingRepository(),
      ),
    );

    await tester.pumpAndSettle();
    expect(find.text('SagoPalgo 잠금'), findsOneWidget);
    expect(find.text('개인 사용자 · 개인 모드'), findsNothing);

    await tester.enterText(find.byType(TextField), '0000');
    await tester.tap(find.text('잠금 해제'));
    await tester.pumpAndSettle();
    expect(find.text('PIN이 일치하지 않습니다.'), findsOneWidget);

    await tester.enterText(find.byType(TextField), '1234');
    await tester.tap(find.text('잠금 해제'));
    await tester.pumpAndSettle();
    expect(find.text('개인 사용자 · 개인 모드'), findsOneWidget);
  });
}

class FakeInvestmentRepository implements InvestmentRepository {
  const FakeInvestmentRepository();

  @override
  Future<InvestmentSnapshot> fetchSnapshot() async {
    return _testSnapshot;
  }
}

class FakePaperTradingRepository implements PaperTradingRepository {
  const FakePaperTradingRepository();

  @override
  Future<PaperTradingSnapshot> fetchSnapshot() async => _testPaperTrading;

  @override
  Future<PaperTradingSnapshot> buyFromRecommendation(
    int recommendationId,
    double quantity,
  ) async => _testPaperTrading;

  @override
  Future<PaperTradingSnapshot> sellPosition({
    required String stockCode,
    required String market,
    required double quantity,
  }) async => _testPaperTrading;
}

class FakeOrderPrecheckRepository extends OrderPrecheckRepository {
  const FakeOrderPrecheckRepository();

  @override
  Future<OrderPrecheckResult> precheck(OrderPrecheckInput input) {
    throw UnimplementedError('주문 사전검토는 전용 위젯 테스트에서 검증합니다.');
  }
}

class FakeRecommendationRepository implements RecommendationRepository {
  const FakeRecommendationRepository();

  @override
  Future<InvestmentRecommendation> analyzeHolding(int holdingId) async {
    return _testSnapshot.recommendation!;
  }

  @override
  Future<InvestmentRecommendation> analyzeWatchlist(int watchlistId) async {
    throw UnimplementedError();
  }

  @override
  Future<InvestmentRecommendation> fetchDetail(int recommendationId) async {
    return _testSnapshot.recommendation!;
  }

  @override
  Future<RecommendationPage> fetchHistory({
    String? status,
    int page = 0,
    int size = 20,
  }) async {
    return RecommendationPage(
      items: [_testSnapshot.recommendation!],
      page: page,
      size: size,
      total: 1,
    );
  }
}

class FakeMarketDataRepository implements MarketDataRepository {
  const FakeMarketDataRepository();

  @override
  Future<MarketCandleSnapshot> fetchCandles({
    required String stockCode,
    required String market,
    required MarketCandleInterval interval,
    int count = 60,
  }) async {
    return MarketCandleSnapshot(
      provider: 'KB',
      stockCode: stockCode,
      market: market,
      interval: interval,
      candles: [
        MarketCandle(
          provider: 'KB',
          stockCode: stockCode,
          market: market,
          dateTime: DateTime(2026, 9, 21),
          interval: interval,
          openPrice: 74800,
          highPrice: 75300,
          lowPrice: 74700,
          closePrice: 75200,
          volume: 1122334,
        ),
      ],
    );
  }
}

class FakePortfolioRepository implements PortfolioRepository {
  const FakePortfolioRepository();

  @override
  Future<PortfolioSnapshot> fetchPortfolio() async {
    return PortfolioSnapshot(
      capital: _testCapital,
      summary: _testPortfolioSummary,
      holdings: _testHoldings,
    );
  }

  @override
  Future<CapitalSettings> updateCapital(CapitalInput input) async {
    return CapitalSettings(
      availableCapital: input.availableCapital,
      recommendedMinPosition: (input.availableCapital * 0.1).round(),
      recommendedMaxPosition: (input.availableCapital * 0.2).round(),
      riskPerTradeRate: input.riskPerTradeRate,
    );
  }

  @override
  Future<void> createHolding(HoldingInput input) async {}

  @override
  Future<Holding> updateHolding(int holdingId, HoldingInput input) async {
    return Holding(
      holdingId: holdingId,
      stockName: input.stockName,
      stockCode: input.stockCode,
      market: input.market,
      buyPrice: input.buyPrice,
      quantity: input.quantity,
      buyDate: input.buyDate,
      currentPrice: input.buyPrice,
      profitRate: 0,
      stopLossRate: input.stopLossRate,
      takeProfitRate: input.takeProfitRate,
      status: '보유',
    );
  }

  @override
  Future<void> deleteHolding(int holdingId) async {}
}

class FakeWatchlistRepository implements WatchlistRepository {
  const FakeWatchlistRepository();

  @override
  Future<List<WatchlistItem>> fetchWatchlist() async => const [];

  @override
  Future<WatchlistActionResult> addRecommendation(
    InvestmentRecommendation recommendation,
  ) async {
    return WatchlistActionResult(
      message: '${recommendation.stockName} 관심 종목에 등록했습니다.',
    );
  }

  @override
  Future<WatchlistActionResult> enableAlert(
    InvestmentRecommendation recommendation,
  ) async {
    return WatchlistActionResult(
      message: '${recommendation.stockName} 알림을 켰습니다.',
    );
  }
}

class FakeProviderSettingsRepository implements ProviderSettingsRepository {
  const FakeProviderSettingsRepository();

  @override
  Future<OrderReadOnlyProbe?> fetchLatestReadOnlyOrderHistoryProbe() async =>
      null;

  @override
  Future<List<OrderReadOnlyProbe>> fetchReadOnlyOrderProbeHistory() async =>
      const [];

  @override
  Future<OrderReadOnlyProbe> probeReadOnlyOrderHistory() =>
      throw UnsupportedError('테스트에서 조회 권한 점검을 사용하지 않습니다.');

  @override
  Future<ProviderSettingsSnapshot> fetchProviderSettings() async {
    return const ProviderSettingsSnapshot(
      secretStorageType: 'ENV_FILE',
      secretStorageDescription: '.env 파일로 민감정보를 관리합니다.',
      orderSafetyMode: '주문 기능 OFF · 사전검증만 지원',
      marketDataFallbackOrder: ['KB', 'KIS', 'TOSS'],
      marketDataFallbackDescription: '앞 Provider가 실패하면 다음 Provider를 시도합니다.',
      providers: [
        ProviderSetting(
          code: 'KB',
          displayName: 'KB증권',
          marketDataEnabled: false,
          accountEnabled: true,
          orderEnabled: false,
          newsEnabled: false,
          disclosureEnabled: false,
          configured: true,
          missingRequiredSettings: [],
          roleDescription: '계좌 조회와 추후 주문 기능의 기준 증권사',
        ),
        ProviderSetting(
          code: 'KIS',
          displayName: '한국투자증권',
          marketDataEnabled: true,
          accountEnabled: false,
          orderEnabled: false,
          newsEnabled: false,
          disclosureEnabled: false,
          configured: true,
          missingRequiredSettings: [],
          roleDescription: '국내 주식 시세 조회용 데이터 소스',
        ),
        ProviderSetting(
          code: 'TOSS',
          displayName: '토스증권',
          marketDataEnabled: true,
          accountEnabled: false,
          orderEnabled: false,
          newsEnabled: false,
          disclosureEnabled: false,
          configured: false,
          missingRequiredSettings: [
            'Base URL',
            '현재가 API 경로',
            'App Key',
            'App Secret',
          ],
          roleDescription: '분석용 시세/종목 정보 보조 데이터 소스',
        ),
        ProviderSetting(
          code: 'NAVER_NEWS',
          displayName: '네이버 뉴스',
          marketDataEnabled: false,
          accountEnabled: false,
          orderEnabled: false,
          newsEnabled: true,
          disclosureEnabled: false,
          configured: true,
          missingRequiredSettings: [],
          roleDescription: '종목명 기준 최신 뉴스 검색 데이터 소스',
        ),
        ProviderSetting(
          code: 'OPEN_DART',
          displayName: 'OpenDART',
          marketDataEnabled: false,
          accountEnabled: false,
          orderEnabled: false,
          newsEnabled: false,
          disclosureEnabled: true,
          configured: false,
          missingRequiredSettings: ['API Key'],
          roleDescription: '종목코드와 DART 고유번호를 연결하는 전자공시 데이터 소스',
        ),
      ],
    );
  }
}

class FakeKbAccountRepository implements KbAccountRepository {
  const FakeKbAccountRepository();

  @override
  Future<KbAccountSnapshot> fetchSnapshot() async {
    return _testKbAccountSnapshot;
  }
}

class FakeResearchFeedRepository implements ResearchFeedRepository {
  const FakeResearchFeedRepository();

  @override
  Future<ResearchFeed> fetchFeed(ResearchStock stock) async {
    return _testResearchFeed;
  }

  @override
  Future<ResearchFeed> syncFeed(ResearchStock stock) async {
    return _testResearchFeed;
  }

  @override
  Future<ResearchSyncOverview> fetchSyncStatus(ResearchStock stock) async {
    return _testResearchSyncOverview;
  }
}

const _testCapital = CapitalSettings(
  availableCapital: 3000000,
  recommendedMinPosition: 300000,
  recommendedMaxPosition: 600000,
  riskPerTradeRate: 0.02,
);

const _testPortfolioSummary = PortfolioSummary(
  totalProfit: 128400,
  profitRate: 4.2,
  maxAllowedLoss: 60000,
  riskUsageRate: .42,
);

final _testHoldings = [
  Holding(
    holdingId: 21,
    stockName: '삼성전자',
    stockCode: '005930',
    market: 'KOSPI',
    buyPrice: 69100,
    quantity: 12,
    buyDate: _testBuyDate,
    currentPrice: 75300,
    profitRate: 9.0,
    stopLossRate: -5.0,
    takeProfitRate: 9.0,
    status: '부분 익절',
  ),
];

final _testBuyDate = DateTime.parse('2026-09-12');

final _testSnapshot = InvestmentSnapshot(
  marketSummary: const MarketSummary(
    availableCapital: 3000000,
    monthlyReturnRate: 3.8,
    recommendedPositionRange: '30~60만원',
    marketTrend: '강세',
    marketScore: 76,
    newsSentiment: '긍정',
    positiveNewsCount: 12,
    marketBars: [.42, .68, .54],
  ),
  recommendation: const InvestmentRecommendation(
    stockName: '삼성전자',
    stockCode: '005930',
    market: 'KOSPI',
    status: '강한 매수',
    score: 87,
    entryPrice: 72000,
    stopLossRate: -5,
    aiSummary: '테스트 추천 설명입니다.',
    reasons: [
      RecommendationReason(
        label: '수익률',
        description: '테스트 추천 사유입니다.',
        type: RecommendationReasonType.trend,
      ),
    ],
  ),
  portfolioSummary: _testPortfolioSummary,
  holdings: _testHoldings,
  alerts: const [
    AppAlert(
      title: '테스트 알림',
      body: '테스트 알림 본문입니다.',
      timeLabel: '방금 전',
      type: AppAlertType.candidate,
    ),
  ],
);

const _testPaperTrading = PaperTradingSnapshot(
  summary: PaperTradingSummary(
    initialCapital: 3000000,
    cashBalance: 3000000,
    openPositionValue: 0,
    totalAsset: 3000000,
    realizedProfit: 0,
    unrealizedProfit: 0,
    totalProfit: 0,
    returnRate: 0,
    completedTrades: 0,
    winRate: 0,
    maxLoss: 0,
    turnoverRate: 0,
  ),
  positions: [],
  trades: [],
);

const _testKbAccountSnapshot = KbAccountSnapshot(
  holdings: KbHoldingsSnapshot(
    summary: KbPortfolioSummary(
      totalPurchaseAmount: 4800000,
      totalValuationAmount: 5200000,
      totalProfitAmount: 400000,
      profitRate: 8.3,
    ),
    items: [
      KbHoldingItem(
        stockCode: '005930',
        stockName: '삼성전자',
        market: 'KRX',
        quantity: 10,
        currentPrice: 76000,
        valuationAmount: 760000,
        profitAmount: 69000,
        profitRate: 10,
        weightRate: 14.62,
      ),
    ],
  ),
  settlementBalance: KbBalanceSnapshot(
    summary: KbBalanceSummary(
      basis: 'SETTLEMENT',
      cashDeposit: 1200000,
      withdrawalAvailableAmount: 1100000,
      orderAvailableCash: 1000000,
      netAssetValuationAmount: 0,
      securitiesNetValuationAmount: 0,
      totalPurchaseAmount: 4800000,
      totalValuationAmount: 5200000,
      totalProfitAmount: 400000,
      totalYieldRate: 8.3,
      totalDataCount: '2',
    ),
    items: [],
  ),
  executionBalance: KbBalanceSnapshot(
    summary: KbBalanceSummary(
      basis: 'EXECUTION',
      cashDeposit: 0,
      withdrawalAvailableAmount: 0,
      orderAvailableCash: 0,
      netAssetValuationAmount: 5200000,
      securitiesNetValuationAmount: 5200000,
      totalPurchaseAmount: 4800000,
      totalValuationAmount: 5200000,
      totalProfitAmount: 400000,
      totalYieldRate: 8.3,
    ),
    items: [],
  ),
);

final _testResearchFeed = ResearchFeed(
  stockCode: '005930',
  stockName: '삼성전자',
  fromDate: DateTime.parse('2026-08-22'),
  toDate: DateTime.parse('2026-09-21'),
  news: [
    ResearchNewsArticle(
      provider: 'NAVER_NEWS',
      stockCode: '005930',
      title: '반도체 투자 확대',
      link: 'https://news.test/article',
      summary: '기사 요약',
      publishedAt: DateTime.parse('2026-09-21T01:00:00Z'),
    ),
  ],
  disclosures: [
    ResearchDisclosure(
      provider: 'OPEN_DART',
      stockCode: '005930',
      corpCode: '00126380',
      corpName: '삼성전자',
      reportName: '주요사항보고서',
      receiptNumber: '20260921000123',
      submitterName: '삼성전자',
      receiptDate: DateTime.parse('2026-09-21'),
      link: 'https://dart.test/report',
    ),
  ],
  providers: const [
    ResearchProviderStatus(
      provider: 'LOCAL_DB',
      dataType: 'CACHE',
      status: 'SUCCESS',
      message: '뉴스 1건 · 공시 1건',
    ),
  ],
);

final _testResearchSyncOverview = ResearchSyncOverview(
  enabled: true,
  cron: '0 0/30 * * * *',
  zone: 'Asia/Seoul',
  item: ResearchSyncStatusItem(
    stockCode: '005930',
    stockName: '삼성전자',
    triggerType: 'SCHEDULED',
    status: 'PARTIAL',
    newsCount: 1,
    disclosureCount: 1,
    providerSuccessCount: 1,
    providerFailureCount: 1,
    providerDisabledCount: 0,
    message: 'Provider 성공 1 · 실패 1 · 비활성 0',
    lastAttemptedAt: DateTime.parse('2026-09-22T00:00:00Z'),
    lastSucceededAt: DateTime.parse('2026-09-22T00:00:00Z'),
  ),
);
