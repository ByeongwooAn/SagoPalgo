import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:app_version/models/stock_identity.dart';
import 'package:app_version/models/watchlist_item.dart';
import 'package:app_version/models/recommendation.dart';
import 'package:app_version/repositories/watchlist_editor.dart';
import 'package:app_version/repositories/watchlist_repository.dart';
import 'package:app_version/repositories/recommendation_repository.dart';
import 'package:app_version/screens/watchlist_setup_sheet.dart';
import 'package:app_version/screens/watchlist_management_sheet.dart';
import 'package:app_version/screens/recommendation_screen.dart';

void main() {
  void largeWindow(WidgetTester tester) {
    tester.view.physicalSize = const Size(1100, 1100);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  Widget host(
    _Watchlist repo, {
    bool manage = false,
    ValueChanged<bool>? onClosed,
  }) => MaterialApp(
    home: Builder(
      builder: (context) => Scaffold(
        body: TextButton(
          onPressed: () async {
            final changed = await (manage
                ? showWatchlistManagement(context, repo)
                : showWatchlistSetup(context, repo));
            onClosed?.call(changed);
          },
          child: const Text('open'),
        ),
      ),
    ),
  );

  testWidgets(
    'late identity response cannot overwrite a newer code or be saved',
    (tester) async {
      largeWindow(tester);
      final first = Completer<StockIdentity>();
      final second = Completer<StockIdentity>();
      final repo = _Watchlist()
        ..lookup = (code) => code == '005930' ? first.future : second.future;
      await tester.pumpWidget(host(repo, onClosed: (_) {}));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextFormField).first, '005930');
      await tester.pump(const Duration(milliseconds: 401));
      await tester.enterText(find.byType(TextFormField).first, '000660');
      await tester.pump(const Duration(milliseconds: 401));
      second.complete(
        const StockIdentity(
          stockCode: '000660',
          stockName: 'SK하이닉스',
          market: 'KOSPI',
          provider: 'KIS',
        ),
      );
      await tester.pumpAndSettle();
      first.complete(
        const StockIdentity(
          stockCode: '005930',
          stockName: '삼성전자',
          market: 'KOSPI',
          provider: 'KIS',
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('SK하이닉스'), findsOneWidget);
      expect(find.text('삼성전자'), findsNothing);
      await tester.tap(find.text('관심 종목 저장'));
      await tester.pumpAndSettle();
      expect(repo.saved?['code'], '000660');
      expect(repo.saved?['name'], 'SK하이닉스');
    },
  );

  testWidgets(
    'lookup failure cannot save guessed identity and supports explicit manual entry',
    (tester) async {
      largeWindow(tester);
      final repo = _Watchlist()
        ..lookup = (_) async => throw Exception('종목 조회 실패');
      await tester.pumpWidget(host(repo, onClosed: (_) {}));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextFormField).first, '000660');
      await tester.pump(const Duration(milliseconds: 401));
      await tester.pumpAndSettle();
      expect(find.textContaining('종목 조회 실패'), findsOneWidget);
      await tester.tap(find.text('관심 종목 저장'));
      await tester.pumpAndSettle();
      expect(repo.saved, isNull);
      await tester.tap(find.text('종목명·시장 직접 입력'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextFormField).at(1), 'SK하이닉스');
      await tester.tap(find.byType(DropdownButtonFormField<String>));
      await tester.pumpAndSettle();
      await tester.tap(find.text('KOSPI').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('관심 종목 저장'));
      await tester.pumpAndSettle();
      expect(repo.saved, {
        'code': '000660',
        'name': 'SK하이닉스',
        'market': 'KOSPI',
        'alerts': false,
      });
    },
  );

  testWidgets('failed lookup can retry with the same code', (tester) async {
    largeWindow(tester);
    final repo = _Watchlist()..lookup = (_) async => throw Exception('일시 실패');
    await tester.pumpWidget(host(repo, onClosed: (_) {}));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField).first, '000660');
    await tester.pump(const Duration(milliseconds: 401));
    await tester.pumpAndSettle();
    repo.lookup = (_) async => const StockIdentity(
      stockCode: '000660',
      stockName: 'SK하이닉스',
      market: 'KOSPI',
      provider: 'KIS',
    );
    await tester.tap(find.text('종목 다시 조회'));
    await tester.pumpAndSettle();
    expect(find.text('SK하이닉스'), findsOneWidget);
    expect(find.textContaining('일시 실패'), findsNothing);
    expect(repo.saved, isNull);
  });

  testWidgets(
    'delete cancel sends nothing and failure retains row until a successful retry',
    (tester) async {
      largeWindow(tester);
      final repo = _Watchlist();
      bool? changed;
      await tester.pumpWidget(
        host(repo, manage: true, onClosed: (value) => changed = value),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('SK하이닉스 관심 종목 삭제'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('취소'));
      await tester.pumpAndSettle();
      expect(repo.deleted, isEmpty);
      repo.deleteFailure = true;
      await tester.tap(find.byTooltip('SK하이닉스 관심 종목 삭제'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('삭제'));
      await tester.pumpAndSettle();
      expect(find.text('SK하이닉스'), findsOneWidget);
      expect(find.textContaining('삭제 실패'), findsOneWidget);
      repo.deleteFailure = false;
      await tester.tap(find.byTooltip('SK하이닉스 관심 종목 삭제'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('삭제'));
      await tester.pumpAndSettle();
      expect(repo.deleted, [7, 7]);
      expect(find.text('등록된 관심 종목이 없습니다.'), findsOneWidget);
      await tester.tap(find.byTooltip('닫기'));
      await tester.pumpAndSettle();
      expect(changed, isTrue);
    },
  );

  testWidgets(
    'delete completion is required before closing and duplicate submission',
    (tester) async {
      largeWindow(tester);
      final pending = Completer<void>();
      final repo = _Watchlist()..pendingDelete = pending.future;
      await tester.pumpWidget(host(repo, manage: true, onClosed: (_) {}));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('SK하이닉스 관심 종목 삭제'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('삭제'));
      await tester.pump();
      expect(
        tester
            .widget<IconButton>(find.widgetWithIcon(IconButton, Icons.close))
            .onPressed,
        isNull,
      );
      expect(
        tester
            .widget<IconButton>(
              find.widgetWithIcon(IconButton, Icons.delete_outline),
            )
            .onPressed,
        isNull,
      );
      expect(repo.deleted, [7]);
      pending.complete();
      await tester.pumpAndSettle();
      expect(find.text('등록된 관심 종목이 없습니다.'), findsOneWidget);
    },
  );

  testWidgets(
    'recommendation empty state exposes management and refreshes root after deletion',
    (tester) async {
      largeWindow(tester);
      final repo = _Watchlist();
      var changed = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: RecommendationScreen(
              recommendation: null,
              holdings: const [],
              recommendationRepository: _Recommendations(),
              watchlistRepository: repo,
              onRecommendationChanged: () => changed++,
              onCapitalSetupOpen: () {},
              onHoldingSetupOpen: () {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('관심 목록 관리'));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('SK하이닉스 관심 종목 삭제'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('삭제'));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('닫기'));
      await tester.pumpAndSettle();
      expect(changed, 1);
      expect(tester.takeException(), isNull);
    },
  );
}

class _Watchlist implements WatchlistRepository, WatchlistEditor {
  Future<StockIdentity> Function(String)? lookup;
  Map<String, Object>? saved;
  final deleted = <int>[];
  bool deleteFailure = false;
  Future<void>? pendingDelete;
  final items = <WatchlistItem>[
    const WatchlistItem(
      watchlistId: 7,
      stockCode: '000660',
      stockName: 'SK하이닉스',
      market: 'KOSPI',
      alertEnabled: true,
      provider: 'KIS',
      currentPrice: 100,
      changeRate: 0,
    ),
  ];
  @override
  Future<StockIdentity> lookupStock(String stockCode) => lookup!(stockCode);
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
  Future<void> deleteStock(int watchlistId) async {
    deleted.add(watchlistId);
    if (pendingDelete != null) await pendingDelete;
    if (deleteFailure) throw Exception('삭제 실패');
    items.removeWhere((value) => value.watchlistId == watchlistId);
  }

  @override
  Future<List<WatchlistItem>> fetchWatchlist() async => List.of(items);
  @override
  Future<WatchlistActionResult> addRecommendation(
    InvestmentRecommendation recommendation,
  ) async => const WatchlistActionResult(message: '등록');
  @override
  Future<WatchlistActionResult> enableAlert(
    InvestmentRecommendation recommendation,
  ) async => const WatchlistActionResult(message: '알림');
}

class _Recommendations extends Fake implements RecommendationRepository {
  @override
  Future<RecommendationPage> fetchHistory({
    String? status,
    int page = 0,
    int size = 20,
  }) async => const RecommendationPage(items: [], page: 0, size: 20, total: 0);
}
