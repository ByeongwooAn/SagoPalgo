import 'package:app_version/models/recommendation.dart';
import 'package:app_version/widgets/daily_model_signal_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('displays saved prediction with KST expiry and reasons', (
    tester,
  ) async {
    final evidence = AnalysisEvidence.fromJson({
      'modelVersion': 'WEIGHTED_SIGNAL_V1',
      'dailySignal': {
        'decision': 'BUY_WATCH',
        'basisDate': '2026-10-30',
        'modelVersion': 'daily-l2-logistic-v1',
        'probability': 0.56789123456789,
        'threshold': 0.50,
        'evaluatedAt': '2026-10-30T20:30:00+09:00',
        'expiresAt': '2026-11-02T06:30:00Z',
        'contributions': {'closeReturn20': 0.30, 'volumeRatio20': -0.25},
      },
    });
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: DailyModelSignalCard(signal: evidence.dailySignal!),
        ),
      ),
    );

    final expected = DateTime.now().isBefore(evidence.dailySignal!.expiresAt!)
        ? '매수 관찰'
        : '만료';
    expect(find.text('장 마감 모델 · $expected'), findsOneWidget);
    expect(find.text('기준 거래일 2026-10-30'), findsOneWidget);
    expect(find.textContaining('상승 확률 56.79%'), findsOneWidget);
    expect(find.text('매수 관찰 기준 50.00%'), findsOneWidget);
    expect(find.text('만료 2026-11-02 15:30 KST'), findsOneWidget);
    expect(find.textContaining('최근 20거래일 수익률(상승 확률 높임)'), findsOneWidget);
    expect(find.textContaining('거래량(상승 확률 낮춤)'), findsOneWidget);
  });

  testWidgets('withheld candle shows the reason without a probability', (
    tester,
  ) async {
    final withheld = DailyModelSignal.fromJson({
      'decision': 'WITHHELD',
      'holdReason': 'BAR_NOT_FINAL',
    });
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: DailyModelSignalCard(signal: withheld)),
      ),
    );

    expect(find.text('장 마감 모델 · 신호 보류'), findsOneWidget);
    expect(find.text('기준 거래일의 일봉 확정을 기다리고 있습니다.'), findsOneWidget);
    expect(find.textContaining('상승 확률'), findsNothing);
    expect(
      AnalysisEvidence.fromJson({
        'modelVersion': 'WEIGHTED_SIGNAL_V1',
      }).dailySignal,
      isNull,
    );
  });
}
