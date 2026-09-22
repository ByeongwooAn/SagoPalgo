import 'package:flutter/services.dart';

/// 운영체제 보안 저장소의 문자열 자격 증명을 다루는 경계입니다.
abstract class SecureCredentialStore {
  Future<String?> read(String target);

  Future<void> write(String target, String value);

  Future<void> delete(String target);
}

/// Windows Credential Manager를 네이티브 Runner 채널로 호출합니다.
class WindowsCredentialStore implements SecureCredentialStore {
  const WindowsCredentialStore();

  static const MethodChannel _channel = MethodChannel(
    'sagopalgo/windows_credentials',
  );

  @override
  Future<String?> read(String target) {
    return _channel.invokeMethod<String>('read', {'target': target});
  }

  @override
  Future<void> write(String target, String value) {
    return _channel.invokeMethod<void>('write', {
      'target': target,
      'value': value,
    });
  }

  @override
  Future<void> delete(String target) {
    return _channel.invokeMethod<void>('delete', {'target': target});
  }
}

/// 테스트와 MethodChannel 미지원 플랫폼에서 사용하는 비영속 저장소입니다.
class MemoryCredentialStore implements SecureCredentialStore {
  MemoryCredentialStore([Map<String, String>? initialValues])
    : _values = {...?initialValues};

  final Map<String, String> _values;

  @override
  Future<String?> read(String target) async => _values[target];

  @override
  Future<void> write(String target, String value) async {
    _values[target] = value;
  }

  @override
  Future<void> delete(String target) async {
    _values.remove(target);
  }
}

/// 저장 기능이 필요 없는 테스트에서 사용하는 빈 구현입니다.
class NoopCredentialStore implements SecureCredentialStore {
  const NoopCredentialStore();

  @override
  Future<String?> read(String target) async => null;

  @override
  Future<void> write(String target, String value) async {}

  @override
  Future<void> delete(String target) async {}
}

/// 앱 잠금 PIN의 검증, 이전, 저장과 삭제 정책을 한곳에서 관리합니다.
class AppSecurityService {
  const AppSecurityService(this.credentialStore);

  static const appLockPinTarget = 'SagoPalgo/AppLockPin';

  final SecureCredentialStore credentialStore;

  /// Credential Manager 값을 우선하고, 없을 때만 기존 `.env` PIN을 이전합니다.
  Future<String?> loadPin({String? legacyPin}) async {
    final stored = await credentialStore.read(appLockPinTarget);
    if (stored != null && stored.isNotEmpty) {
      return stored;
    }

    final fallback = legacyPin?.trim();
    if (fallback == null || fallback.isEmpty) {
      return null;
    }
    validatePin(fallback);
    await credentialStore.write(appLockPinTarget, fallback);
    return fallback;
  }

  Future<void> savePin(String pin) async {
    final normalized = pin.trim();
    validatePin(normalized);
    await credentialStore.write(appLockPinTarget, normalized);
  }

  Future<void> deletePin() {
    return credentialStore.delete(appLockPinTarget);
  }

  /// 단순 추측을 어렵게 하면서 숫자 키패드 입력이 가능한 4~12자리만 허용합니다.
  void validatePin(String pin) {
    if (!RegExp(r'^\d{4,12}$').hasMatch(pin)) {
      throw const AppSecurityException('PIN은 숫자 4~12자리로 입력해 주세요.');
    }
  }
}

class AppSecurityException implements Exception {
  const AppSecurityException(this.message);

  final String message;

  @override
  String toString() => message;
}
