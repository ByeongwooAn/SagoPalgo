import 'package:app_version/models/holding.dart';
import 'package:app_version/models/recommendation.dart';
import 'package:app_version/repositories/recommendation_repository.dart';
import 'package:app_version/repositories/watchlist_repository.dart';
import 'package:app_version/screens/recommendation_screen.dart';
import 'package:app_version/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('opens history detail and manually analyzes its holding', (
    tester,
  ) async {
    final repository = _FakeRecommendationRepository();
    var changed = 0;
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: Scaffold(
          body: RecommendationScreen(
            recommendation: _recommendation,
            holdings: [_holding],
            recommendationRepository: repository,
            watchlistRepository: const _NoopWatchlistRepository(),
            onRecommendationChanged: () => changed += 1,
            onCapitalSetupOpen: () {},
            onHoldingSetupOpen: () {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('추천 이력'), findsOneWidget);
    expect(find.text('총 1건'), findsOneWidget);

    final historyItem = find.text('005930 · KOSPI · 2026.09.22 11:30');
    await tester.ensureVisible(historyItem);
    await tester.tap(historyItem);
    await tester.pumpAndSettle();

    expect(find.text('추천 상세'), findsOneWidget);
    expect(find.text('익절 기준'), findsOneWidget);
    expect(find.text('분석 시각 2026.09.22 11:30'), findsOneWidget);

    await tester.ensureVisible(find.text('이 종목 다시 분석'));
    await tester.tap(find.text('이 종목 다시 분석'));
    await tester.pumpAndSettle();

    expect(repository.analyzedHoldingId, 7);
    expect(changed, 1);
    expect(find.text('91점'), findsOneWidget);
    expect(find.text('재분석 결과입니다.'), findsOneWidget);
  });
}

class _FakeRecommendationRepository implements RecommendationRepository {
  int? analyzedHoldingId;

  @override
  Future<InvestmentRecommendation> analyzeHolding(int holdingId) async {
    analyzedHoldingId = holdingId;
    return _reanalyzedRecommendation;
  }

  @override
  Future<InvestmentRecommendation> fetchDetail(int recommendationId) async {
    return _recommendation;
  }

  @override
  Future<RecommendationPage> fetchHistory({
    String? status,
    int page = 0,
    int size = 20,
  }) async {
    return RecommendationPage(
      items: [
        analyzedHoldingId == null ? _recommendation : _reanalyzedRecommendation,
      ],
      page: page,
      size: size,
      total: 1,
    );
  }
}

class _NoopWatchlistRepository implements WatchlistRepository {
  const _NoopWatchlistRepository();

  @override
  Future<WatchlistActionResult> addRecommendation(
    InvestmentRecommendation recommendation,
  ) async => const WatchlistActionResult(message: '등록');

  @override
  Future<WatchlistActionResult> enableAlert(
    InvestmentRecommendation recommendation,
  ) async => const WatchlistActionResult(message: '알림');
}

final _holding = Holding(
  holdingId: 7,
  stockName: '삼성전자',
  stockCode: '005930',
  market: 'KOSPI',
  buyPrice: 69000,
  quantity: 10,
  buyDate: _createdAt,
  currentPrice: 75200,
  profitRate: 8.99,
  stopLossRate: -5,
  takeProfitRate: 9.5,
  status: '보유',
);

final _recommendation = InvestmentRecommendation(
  recommendationId: 41,
  stockName: '삼성전자',
  stockCode: '005930',
  market: 'KOSPI',
  status: '강한 매수',
  machineStatus: 'BUY_STRONG',
  recommendationType: 'BUY',
  score: 86,
  entryPrice: 75200,
  stopLossRate: -5,
  takeProfitRate: 9.5,
  aiSummary: '가격 추세와 뉴스 흐름이 긍정적입니다.',
  reasons: [
    RecommendationReason(
      label: '추세',
      description: '최근 종가가 상승했습니다.',
      type: RecommendationReasonType.trend,
    ),
  ],
  createdAt: _createdAt,
);

final _reanalyzedRecommendation = InvestmentRecommendation(
  recommendationId: 42,
  stockName: '삼성전자',
  stockCode: '005930',
  market: 'KOSPI',
  status: '강한 매수',
  machineStatus: 'BUY_STRONG',
  recommendationType: 'BUY',
  score: 91,
  entryPrice: 75600,
  stopLossRate: -5,
  takeProfitRate: 9.5,
  aiSummary: '재분석 결과입니다.',
  reasons: [],
  createdAt: _createdAt,
);

final _createdAt = DateTime(2026, 9, 22, 11, 30);
