import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:app_version/models/provider_setting.dart';
import 'package:app_version/models/kb_account_snapshot.dart';
import 'package:app_version/repositories/kb_account_repository.dart';
import 'package:app_version/screens/settings_screen.dart';
import 'package:app_version/services/app_security_service.dart';

void main() {
  test('provider settings parse order readiness without sensitive values', () {
    final snapshot = ProviderSettingsSnapshot.fromJson({
      'orderReadiness': {
        'canSubmit': false,
        'checks': [
          {
            'code': 'SUBMISSION_TRANSPORT',
            'passed': false,
            'message': 'KB 실주문 전송 어댑터가 아직 연결되지 않았습니다.',
          },
        ],
      },
      'providers': [],
    });

    expect(snapshot.orderReadiness?.canSubmit, isFalse);
    expect(snapshot.orderReadiness?.checks.single.code, 'SUBMISSION_TRANSPORT');
  });

  testWidgets('settings show blocked live order readiness', (tester) async {
    tester.view.physicalSize = const Size(360, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final snapshot = ProviderSettingsSnapshot.fromJson({
      'orderReadiness': {
        'canSubmit': false,
        'checks': [
          {
            'code': 'LIVE_ORDER_SWITCH',
            'passed': false,
            'message': '실주문 별도 스위치가 꺼져 있습니다.',
          },
          {
            'code': 'SUBMISSION_TRANSPORT',
            'passed': false,
            'message': 'KB 실주문 전송 어댑터가 아직 연결되지 않았습니다.',
          },
        ],
      },
      'providers': [],
    });
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SettingsScreen(
            providerSettingsFuture: Future.value(snapshot),
            kbAccountRepository: _UnusedKbAccountRepository(),
            appSecurityService: const AppSecurityService(NoopCredentialStore()),
            appLockPinConfigured: false,
            onAppLockPinChanged: (_) {},
            onRetry: () {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('KB 실주문 준비 상태'), findsOneWidget);
    expect(find.text('실주문 별도 스위치'), findsOneWidget);
    expect(find.text('KB 실주문 전송 어댑터가 아직 연결되지 않았습니다.'), findsOneWidget);
    expect(find.text('잠금'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

class _UnusedKbAccountRepository implements KbAccountRepository {
  @override
  Future<KbAccountSnapshot> fetchSnapshot() => throw UnimplementedError();
}
