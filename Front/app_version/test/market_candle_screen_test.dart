import 'package:app_version/models/market_candle.dart';
import 'package:app_version/models/recommendation.dart';
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
  testWidgets('US lookup shows USD prices and the returned stock name', (
    tester,
  ) async {
    final repository = _FakeMarketDataRepository(currency: 'USD');
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: MarketCandleScreen(
          stockCode: 'AAPL',
          stockName: 'AAPL',
          market: 'NASDAQ',
          repository: repository,
          usLookup: repository,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('애플'), findsOneWidget);
    expect(find.text('AAPL · NASDAQ'), findsOneWidget);
    expect(find.text('현재가 223.125 USD · KIS'), findsOneWidget);
    expect(find.text('223.12 USD'), findsOneWidget);
    expect(repository.signalRequests, 0);
    await tester.tap(find.text('장 마감 모델'));
    await tester.pumpAndSettle();
    expect(repository.signalRequests, 1);
    expect(find.text('AAPL 장 마감 모델'), findsOneWidget);
    expect(find.text('기준 거래일 2026-11-18'), findsOneWidget);
    expect(find.text('장 마감 모델 · 신호 보류'), findsOneWidget);
  });
}

class _FakeMarketDataRepository
    implements MarketDataRepository, UsStockLookup, UsDailySignalAccess {
  _FakeMarketDataRepository({this.currency = 'KRW'});

  final List<MarketCandleInterval> requestedIntervals = [];
  final String currency;
  int signalRequests = 0;

  @override
  Future<DailyModelSignal> fetchUsDailySignal(
    String ticker,
    String market,
  ) async {
    expect(ticker, 'AAPL');
    expect(market, 'NASDAQ');
    signalRequests++;
    return const DailyModelSignal(
      decision: 'WITHHELD',
      holdReason: 'BAR_NOT_FINAL',
      basisDate: '2026-11-18',
      contributions: {},
    );
  }

  @override
  Future<({String provider, double price})> fetchUsQuote(
    String ticker,
    String market,
  ) async => (provider: 'KIS', price: 223.125);

  @override
  Future<String> fetchUsStockName(String ticker, String market) async => '애플';

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
      currency: currency,
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
          closePrice: currency == 'USD' ? 223.12 : 75200,
          volume: 1122334,
        ),
      ],
    );
  }
}
