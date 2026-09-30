import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:app_version/models/provider_setting.dart';
import 'package:app_version/models/kb_account_snapshot.dart';
import 'package:app_version/repositories/kb_account_repository.dart';
import 'package:app_version/repositories/provider_settings_repository.dart';
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
            providerSettingsRepository: _ProbeProviderSettingsRepository(
              snapshot,
            ),
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
    expect(find.text('조회 권한 점검'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('read-only probe result does not unlock order submission', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(360, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final snapshot = ProviderSettingsSnapshot.fromJson({
      'orderReadiness': {
        'canSubmit': false,
        'checks': [
          {
            'code': 'SUBMISSION_TRANSPORT',
            'passed': false,
            'message': '전송 미연결',
          },
        ],
      },
      'providers': [],
    });
    final repository = _ProbeProviderSettingsRepository(snapshot);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SettingsScreen(
            providerSettingsFuture: Future.value(snapshot),
            providerSettingsRepository: repository,
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
    await tester.ensureVisible(find.text('조회 권한 점검'));
    await tester.tap(find.text('조회 권한 점검'));
    await tester.pumpAndSettle();

    expect(repository.calls, 1);
    expect(find.text('읽기 전용 조회를 확인했습니다. 주문 권한은 별도 확인이 필요합니다.'), findsOneWidget);
    expect(find.text('잠금'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

class _UnusedKbAccountRepository implements KbAccountRepository {
  @override
  Future<KbAccountSnapshot> fetchSnapshot() => throw UnimplementedError();
}

class _ProbeProviderSettingsRepository extends ProviderSettingsRepository {
  _ProbeProviderSettingsRepository(this.snapshot);

  final ProviderSettingsSnapshot snapshot;
  int calls = 0;

  @override
  Future<ProviderSettingsSnapshot> fetchProviderSettings() async => snapshot;

  @override
  Future<OrderReadOnlyProbe> probeReadOnlyOrderHistory() async {
    calls++;
    return OrderReadOnlyProbe.fromJson({
      'status': 'VERIFIED',
      'orderDate': '20260930',
      'checkedAt': '2026-09-30T10:00:00',
      'readOnly': true,
      'message': '읽기 전용 조회를 확인했습니다. 주문 권한은 별도 확인이 필요합니다.',
    });
  }
}
