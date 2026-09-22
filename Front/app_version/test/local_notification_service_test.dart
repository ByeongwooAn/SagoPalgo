import 'package:app_version/models/app_alert.dart';
import 'package:app_version/services/local_notification_service.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'Windows notification service sends title and body to native runner',
    () async {
      const channel = MethodChannel('sagopalgo/windows_notification');
      MethodCall? capturedCall;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            capturedCall = call;
            return null;
          });
      addTearDown(() {
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
            .setMockMethodCallHandler(channel, null);
      });

      await WindowsLocalNotificationService().show(
        const AppAlert(
          alertId: 7,
          recommendationId: 99,
          title: '삼성전자 위험 신호',
          body: '손절 기준에 도달했습니다.',
          timeLabel: '방금 전',
          type: AppAlertType.sell,
        ),
      );

      expect(capturedCall?.method, 'show');
      expect(capturedCall?.arguments, {
        'title': '삼성전자 위험 신호',
        'body': '손절 기준에 도달했습니다.',
      });
    },
  );
}
