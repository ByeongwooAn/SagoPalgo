import 'package:app_version/main.dart';
import 'package:app_version/models/app_alert.dart';
import 'package:app_version/models/holding.dart';
import 'package:app_version/models/investment_snapshot.dart';
import 'package:app_version/models/market_summary.dart';
import 'package:app_version/models/provider_setting.dart';
import 'package:app_version/models/recommendation.dart';
import 'package:app_version/repositories/investment_repository.dart';
import 'package:app_version/repositories/portfolio_repository.dart';
import 'package:app_version/repositories/provider_settings_repository.dart';
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
      ),
    );

    /// 개인용 프로그램은 로그인 없이 바로 홈 화면으로 진입합니다.
    await tester.pumpAndSettle();

    /// 홈 화면에는 앱 브랜드명, 로컬 사용자명, 자본금 카드가 보여야 합니다.
    expect(find.text('사고팔고'), findsAtLeastNWidgets(1));
    expect(find.text('개인 사용자 · 개인 모드'), findsOneWidget);
    expect(find.text('3,000,000원'), findsOneWidget);

    /// 하단 네비게이션의 추천 탭을 눌러 추천 상세 화면으로 이동합니다.
    await tester.tap(find.text('추천'));
    await tester.pumpAndSettle();

    /// 추천 상세 화면에는 매수 추천 제목과 강한 매수 상태가 보여야 합니다.
    expect(find.text('매수 추천'), findsOneWidget);
    expect(find.text('강한 매수'), findsOneWidget);

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
  Future<ProviderSettingsSnapshot> fetchProviderSettings() async {
    return const ProviderSettingsSnapshot(
      providers: [
        ProviderSetting(
          code: 'KB',
          displayName: 'KB증권',
          marketDataEnabled: false,
          accountEnabled: true,
          orderEnabled: false,
          configured: false,
          roleDescription: '계좌 조회와 추후 주문 기능의 기준 증권사',
        ),
        ProviderSetting(
          code: 'KIS',
          displayName: '한국투자증권',
          marketDataEnabled: true,
          accountEnabled: false,
          orderEnabled: false,
          configured: true,
          roleDescription: '국내 주식 시세 조회용 데이터 소스',
        ),
        ProviderSetting(
          code: 'TOSS',
          displayName: '토스증권',
          marketDataEnabled: true,
          accountEnabled: false,
          orderEnabled: false,
          configured: false,
          roleDescription: '분석용 시세/종목 정보 보조 데이터 소스',
        ),
      ],
    );
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
