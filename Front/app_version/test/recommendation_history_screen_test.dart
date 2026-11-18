import 'dart:convert';
import 'dart:io';

import 'package:app_version/models/holding.dart';
import 'package:app_version/models/recommendation.dart';
import 'package:app_version/models/watchlist_item.dart';
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

  testWidgets('analyzes a selected watchlist item without holding metrics', (
    tester,
  ) async {
    final repository = _FakeRecommendationRepository();
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: Scaffold(
          body: RecommendationScreen(
            recommendation: _recommendation,
            holdings: const [],
            recommendationRepository: repository,
            watchlistRepository: const _AnalysisWatchlistRepository(),
            onRecommendationChanged: () {},
            onCapitalSetupOpen: () {},
            onHoldingSetupOpen: () {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text('관심 종목 분석'));
    await tester.tap(find.widgetWithText(FilledButton, '분석').last);
    await tester.pumpAndSettle();
    final pickerItem = find.widgetWithText(ListTile, '삼성전자');
    await tester.ensureVisible(pickerItem);
    await tester.tap(pickerItem);
    await tester.pumpAndSettle();

    expect(repository.analyzedWatchlistId, 12);
    expect(find.textContaining('관심 종목'), findsWidgets);
    expect(find.text('손절 기준'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'opens both stocks from a local summary without saved recommendations',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(1280, 900));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final folder = Directory.systemTemp.createTempSync(
        'sagopalgo-evaluation-',
      );
      addTearDown(() => folder.deleteSync(recursive: true));
      final file = File('${folder.path}/app-summary.json');
      file.writeAsStringSync('{"schemaVersion":"invalid"}');
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light,
          home: Scaffold(
            body: RecommendationScreen(
              recommendation: null,
              holdings: const [],
              recommendationRepository: _FakeRecommendationRepository(
                hasHistory: false,
              ),
              watchlistRepository: const _NoopWatchlistRepository(),
              onRecommendationChanged: () {},
              onCapitalSetupOpen: () {},
              onHoldingSetupOpen: () {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('로컬 모델 평가'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), '"${file.path}"');
      await _loadEvaluation(tester);
      expect(find.textContaining('학습 도구에서 생성한'), findsOneWidget);

      file.writeAsStringSync(jsonEncode(_evaluationFixture()));
      await _loadEvaluation(tester);
      expect(find.text('공통 최종 평가 · 142일'), findsOneWidget);
      expect(find.text('삼성전자 (005930)'), findsOneWidget);
      expect(find.text('SK하이닉스 (000660)'), findsOneWidget);
      expect(find.textContaining('매수 관찰 임곗값 52.50%'), findsOneWidget);
      expect(find.textContaining('매수 관찰 임곗값 진입 안 함'), findsOneWidget);
      expect(find.text('70회'), findsNWidgets(2));
      expect(find.text('-12.34%'), findsNWidgets(2));
      expect(tester.takeException(), isNull);
    },
  );
}

Future<void> _loadEvaluation(WidgetTester tester) async {
  await tester.runAsync(() async {
    await tester.tap(find.text('결과 열기'));
    await tester.pump();
    final loading = find.byType(LinearProgressIndicator);
    final timer = Stopwatch()..start();
    while (loading.evaluate().isNotEmpty &&
        timer.elapsed < const Duration(seconds: 3)) {
      await Future<void>.delayed(const Duration(milliseconds: 10));
      await tester.pump();
    }
    expect(loading, findsNothing);
  });
  await tester.pumpAndSettle();
}

Map<String, Object> _evaluationFixture() {
  const period = {
    'firstTargetDate': '2026-04-03',
    'lastTargetDate': '2026-11-02',
    'samples': 142,
  };
  Map<String, Object?> stock(double? threshold) => {
    'period': period,
    'version': 'daily-l2-logistic-v1',
    'threshold': threshold,
    'prediction': {
      'model': {'accuracy': 0.5, 'logLoss': 0.7},
      'trainingFrequency': {'accuracy': 0.45, 'logLoss': 0.69},
    },
    'strategies': {
      for (final scenario in ['base', 'stress'])
        scenario: {
          'model': {
            'netReturn': threshold == null ? 0 : -0.1234,
            'maxDrawdown': threshold == null ? 0 : 0.2,
            'trades': threshold == null ? 0 : 70,
          },
          for (final name in ['daily', 'trend5', 'cash'])
            name: {'netReturn': 0, 'maxDrawdown': 0, 'trades': 0},
        },
    },
  };
  return {
    'schemaVersion': 'SAGOPALGO_DAILY_LEARNING_SUMMARY_V1',
    'purpose': 'PERSONAL_LOCAL_RESEARCH',
    'commonFinalPeriod': period,
    'costs': {
      'base': {'feeBpsPerSide': 5, 'slippageBpsPerSide': 5, 'sellTaxBps': 20},
      'stress': {
        'feeBpsPerSide': 10,
        'slippageBpsPerSide': 15,
        'sellTaxBps': 20,
      },
    },
    'stocks': {'005930': stock(0.525), '000660': stock(null)},
  };
}

class _FakeRecommendationRepository implements RecommendationRepository {
  _FakeRecommendationRepository({this.hasHistory = true});

  final bool hasHistory;
  int? analyzedHoldingId;
  int? analyzedWatchlistId;

  @override
  Future<InvestmentRecommendation> analyzeHolding(int holdingId) async {
    analyzedHoldingId = holdingId;
    return _reanalyzedRecommendation;
  }

  @override
  Future<InvestmentRecommendation> analyzeWatchlist(int watchlistId) async {
    analyzedWatchlistId = watchlistId;
    return _watchlistRecommendation;
  }

  @override
  Future<InvestmentRecommendation> fetchDetail(int recommendationId) async {
    return analyzedWatchlistId == null
        ? _recommendation
        : _watchlistRecommendation;
  }

  @override
  Future<RecommendationPage> fetchHistory({
    String? status,
    int page = 0,
    int size = 20,
  }) async {
    return RecommendationPage(
      items: [
        if (hasHistory)
          analyzedWatchlistId != null
              ? _watchlistRecommendation
              : analyzedHoldingId == null
              ? _recommendation
              : _reanalyzedRecommendation,
      ],
      page: page,
      size: size,
      total: hasHistory ? 1 : 0,
    );
  }
}

class _NoopWatchlistRepository implements WatchlistRepository {
  const _NoopWatchlistRepository();

  @override
  Future<List<WatchlistItem>> fetchWatchlist() async => const [];

  @override
  Future<WatchlistActionResult> addRecommendation(
    InvestmentRecommendation recommendation,
  ) async => const WatchlistActionResult(message: '등록');

  @override
  Future<WatchlistActionResult> enableAlert(
    InvestmentRecommendation recommendation,
  ) async => const WatchlistActionResult(message: '알림');
}

class _AnalysisWatchlistRepository implements WatchlistRepository {
  const _AnalysisWatchlistRepository();

  @override
  Future<List<WatchlistItem>> fetchWatchlist() async => const [
    WatchlistItem(
      watchlistId: 12,
      stockCode: '005930',
      stockName: '삼성전자',
      market: 'KOSPI',
      alertEnabled: false,
      provider: 'KB',
      currentPrice: 75200,
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

final _watchlistRecommendation = InvestmentRecommendation(
  recommendationId: 43,
  stockName: '삼성전자',
  stockCode: '005930',
  market: 'KOSPI',
  status: '매수 관찰',
  machineStatus: 'BUY_WATCH',
  recommendationType: 'BUY',
  analysisContext: 'WATCHLIST',
  score: 65,
  entryPrice: 75200,
  stopLossRate: null,
  aiSummary: '관심 종목 분석 결과입니다.',
  reasons: [],
  createdAt: _createdAt,
);

final _createdAt = DateTime(2026, 9, 22, 11, 30);
