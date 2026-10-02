import 'package:app_version/screens/alerts_screen.dart';
import 'package:app_version/services/alert_delivery_service.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('shows retry details without exposing alert contents', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AlertsScreen(
            alerts: const [],
            deliveryStatus: AlertDeliveryStatus(
              checkedAt: DateTime(2026, 10, 2, 14, 32),
              unconfirmedCount: 2,
              failedCount: 1,
            ),
          ),
        ),
      ),
    );

    expect(find.textContaining('전달 재시도 중'), findsOneWidget);
    expect(find.textContaining('전달 기록 확인 대기 2건'), findsOneWidget);
    expect(find.textContaining('이번 점검 실패 1건'), findsOneWidget);
    expect(find.text('14:32'), findsOneWidget);
  });

  testWidgets('shows check failure separately from item failures', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AlertsScreen(
            alerts: const [],
            deliveryStatus: AlertDeliveryStatus(
              checkedAt: DateTime(2026, 10, 2, 14, 33),
              checkFailed: true,
            ),
          ),
        ),
      ),
    );

    expect(find.textContaining('전달 상태 확인 실패'), findsOneWidget);
    expect(find.textContaining('이번 점검 실패'), findsNothing);
  });

  testWidgets('keeps delivery status readable in a narrow window', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AlertsScreen(
            alerts: const [],
            deliveryStatus: AlertDeliveryStatus(
              checkedAt: DateTime(2026, 10, 2, 14, 32),
              unconfirmedCount: 1234,
              failedCount: 56,
            ),
          ),
        ),
      ),
    );

    expect(tester.takeException(), isNull);
    expect(find.textContaining('전달 재시도 중'), findsOneWidget);
  });
}
