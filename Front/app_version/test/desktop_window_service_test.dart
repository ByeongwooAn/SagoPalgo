import 'package:app_version/services/desktop_window_service.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('Windows desktop service forwards window commands', () async {
    const channel = MethodChannel('sagopalgo/window_control');
    final calls = <String>[];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call.method);
          return null;
        });
    addTearDown(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, null);
    });
    final service = WindowsDesktopWindowService(channel: channel);
    await service.initialize(
      onShowDashboard: () {},
      onEnterMiniMode: () {},
      onRefresh: () {},
      onOpenSettings: () {},
    );

    await service.enterMiniMode();
    await service.showDashboard();
    await service.hideToTray();

    expect(calls, ['enterMiniMode', 'showDashboard', 'hideToTray']);
    await service.dispose();
  });
}
