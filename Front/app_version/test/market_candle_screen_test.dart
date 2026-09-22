import 'package:app_version/models/market_candle.dart';
import 'package:app_version/repositories/market_data_repository.dart';
import 'package:app_version/screens/market_candle_screen.dart';
import 'package:app_version/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('candle screen shows provider and changes the interval', (
    tester,
  ) async {
    final repository = _FakeMarketDataRepository();
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: MarketCandleScreen(
          stockCode: '005930',
          stockName: '삼성전자',
          market: 'KOSPI',
          repository: repository,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(repository.requestedIntervals, [MarketCandleInterval.daily]);
    expect(find.text('삼성전자'), findsOneWidget);
    expect(find.text('005930 · KOSPI'), findsOneWidget);
    expect(find.text('KB 데이터'), findsOneWidget);
    expect(find.text('75,200원'), findsAtLeastNWidgets(1));
    expect(find.text('일봉'), findsOneWidget);
    expect(find.text('주봉'), findsOneWidget);
    expect(find.text('월봉'), findsOneWidget);

    await tester.tap(find.text('주봉'));
    await tester.pumpAndSettle();

    expect(repository.requestedIntervals, [
      MarketCandleInterval.daily,
      MarketCandleInterval.weekly,
    ]);
  });
}

class _FakeMarketDataRepository implements MarketDataRepository {
  final List<MarketCandleInterval> requestedIntervals = [];

  @override
  Future<MarketCandleSnapshot> fetchCandles({
    required String stockCode,
    required String market,
    required MarketCandleInterval interval,
    int count = 60,
  }) async {
    requestedIntervals.add(interval);
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
          dateTime: DateTime(2026, 9, 18),
          interval: interval,
          openPrice: 74000,
          highPrice: 75100,
          lowPrice: 73800,
          closePrice: 74800,
          volume: 980000,
        ),
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
