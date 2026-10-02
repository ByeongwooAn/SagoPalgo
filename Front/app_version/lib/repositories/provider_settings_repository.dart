import '../models/provider_setting.dart';

/// 증권사 연동 설정 상태를 제공하는 Repository입니다.
abstract class ProviderSettingsRepository {
  /// KB/KIS/Toss 연동 역할과 설정 여부를 조회합니다.
  Future<ProviderSettingsSnapshot> fetchProviderSettings();

  /// 명시적 사용자 요청 때만 KB 주문 이력의 첫 페이지를 읽기 전용으로 점검합니다.
  Future<OrderReadOnlyProbe> probeReadOnlyOrderHistory() =>
      throw UnsupportedError('KB 주문 이력 조회 점검을 지원하지 않습니다.');

  /// 저장된 마지막 점검 결과만 조회합니다. 새로운 KB 요청은 보내지 않습니다.
  Future<OrderReadOnlyProbe?> fetchLatestReadOnlyOrderHistoryProbe() async =>
      null;

  /// 사용자 요청 시 저장된 최근 점검 10건만 조회합니다.
  Future<List<OrderReadOnlyProbe>> fetchReadOnlyOrderProbeHistory() async =>
      const [];
}

/// 증권사 설정 Repository 실패 예외입니다.
class ProviderSettingsRepositoryException implements Exception {
  /// 사용자에게 보여줄 수 있는 오류 메시지를 받습니다.
  const ProviderSettingsRepositoryException(this.message);

  /// 오류 화면이나 로그에서 사용할 실패 메시지입니다.
  final String message;

  @override
  String toString() => message;
}
