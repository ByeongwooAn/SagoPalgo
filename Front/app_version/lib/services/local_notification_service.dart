import 'dart:io';

import 'package:flutter/services.dart';

import '../models/app_alert.dart';

/// 운영체제 알림 표시를 앱 흐름에서 분리한 인터페이스입니다.
abstract class LocalNotificationService {
  Future<void> show(AppAlert alert);
}

/// 위젯 테스트와 Windows 외 플랫폼에서 사용하는 빈 구현입니다.
class NoopLocalNotificationService implements LocalNotificationService {
  const NoopLocalNotificationService();

  @override
  Future<void> show(AppAlert alert) async {}
}

/// Windows 알림 센터에 투자 신호 토스트를 표시합니다.
class WindowsLocalNotificationService implements LocalNotificationService {
  static const _channel = MethodChannel('sagopalgo/windows_notification');

  @override
  Future<void> show(AppAlert alert) async {
    if (!Platform.isWindows) {
      return;
    }
    await _channel.invokeMethod<void>('show', <String, String>{
      'title': alert.title,
      'body': alert.body,
    });
  }
}
