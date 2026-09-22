import 'package:app_version/services/app_security_service.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'stored Credential Manager PIN takes precedence over legacy env',
    () async {
      final store = MemoryCredentialStore({
        AppSecurityService.appLockPinTarget: '5678',
      });
      final service = AppSecurityService(store);

      final pin = await service.loadPin(legacyPin: '1234');

      expect(pin, '5678');
    },
  );

  test('legacy env PIN is migrated when secure storage is empty', () async {
    final store = MemoryCredentialStore();
    final service = AppSecurityService(store);

    final pin = await service.loadPin(legacyPin: '1234');

    expect(pin, '1234');
    expect(await store.read(AppSecurityService.appLockPinTarget), '1234');
  });

  test('PIN validation rejects non numeric or short values', () async {
    final service = AppSecurityService(MemoryCredentialStore());

    expect(
      () => service.validatePin('12a4'),
      throwsA(isA<AppSecurityException>()),
    );
    expect(
      () => service.validatePin('123'),
      throwsA(isA<AppSecurityException>()),
    );
  });

  test(
    'Windows credential store invokes read write and delete channel',
    () async {
      const channel = MethodChannel('sagopalgo/windows_credentials');
      final calls = <MethodCall>[];
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            calls.add(call);
            if (call.method == 'read') return '2468';
            return null;
          });
      addTearDown(
        () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
            .setMockMethodCallHandler(channel, null),
      );

      const store = WindowsCredentialStore();
      expect(await store.read(AppSecurityService.appLockPinTarget), '2468');
      await store.write(AppSecurityService.appLockPinTarget, '1357');
      await store.delete(AppSecurityService.appLockPinTarget);

      expect(calls.map((call) => call.method), ['read', 'write', 'delete']);
      expect(calls[1].arguments, {
        'target': AppSecurityService.appLockPinTarget,
        'value': '1357',
      });
    },
  );
}
