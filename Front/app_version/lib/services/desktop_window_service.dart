import 'package:flutter/services.dart';

/// Windows 창 모드와 시스템 트레이 동작을 Flutter 화면에 연결합니다.
abstract class DesktopWindowService {
  const DesktopWindowService();

  Future<void> initialize({
    required VoidCallback onShowDashboard,
    required VoidCallback onEnterMiniMode,
    required VoidCallback onRefresh,
    required VoidCallback onOpenSettings,
  });

  Future<void> showDashboard();

  Future<void> enterMiniMode();

  Future<void> hideToTray();

  Future<void> dispose();
}

/// 위젯 테스트와 Windows 이외 플랫폼에서 사용하는 창 제어 구현입니다.
class NoopDesktopWindowService extends DesktopWindowService {
  const NoopDesktopWindowService();

  @override
  Future<void> initialize({
    required VoidCallback onShowDashboard,
    required VoidCallback onEnterMiniMode,
    required VoidCallback onRefresh,
    required VoidCallback onOpenSettings,
  }) async {}

  @override
  Future<void> showDashboard() async {}

  @override
  Future<void> enterMiniMode() async {}

  @override
  Future<void> hideToTray() async {}

  @override
  Future<void> dispose() async {}
}

/// Flutter Windows Runner의 네이티브 창과 트레이 메뉴를 제어합니다.
class WindowsDesktopWindowService extends DesktopWindowService {
  WindowsDesktopWindowService({MethodChannel? channel})
    : _channel = channel ?? const MethodChannel(_channelName);

  static const _channelName = 'sagopalgo/window_control';
  final MethodChannel _channel;

  VoidCallback? _onShowDashboard;
  VoidCallback? _onEnterMiniMode;
  VoidCallback? _onRefresh;
  VoidCallback? _onOpenSettings;

  @override
  Future<void> initialize({
    required VoidCallback onShowDashboard,
    required VoidCallback onEnterMiniMode,
    required VoidCallback onRefresh,
    required VoidCallback onOpenSettings,
  }) async {
    _onShowDashboard = onShowDashboard;
    _onEnterMiniMode = onEnterMiniMode;
    _onRefresh = onRefresh;
    _onOpenSettings = onOpenSettings;
    _channel.setMethodCallHandler(_handleNativeCall);
  }

  Future<Object?> _handleNativeCall(MethodCall call) async {
    if (call.method != 'trayAction') {
      return null;
    }
    switch (call.arguments) {
      case 'showDashboard':
        _onShowDashboard?.call();
      case 'miniMode':
        _onEnterMiniMode?.call();
      case 'refresh':
        _onRefresh?.call();
      case 'settings':
        _onOpenSettings?.call();
    }
    return null;
  }

  @override
  Future<void> showDashboard() => _channel.invokeMethod('showDashboard');

  @override
  Future<void> enterMiniMode() => _channel.invokeMethod('enterMiniMode');

  @override
  Future<void> hideToTray() => _channel.invokeMethod('hideToTray');

  @override
  Future<void> dispose() async {
    _channel.setMethodCallHandler(null);
  }
}
