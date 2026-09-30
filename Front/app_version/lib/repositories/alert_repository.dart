import '../models/app_alert.dart';

/// 저장 알림 조회와 Windows 전달·읽음 상태 변경을 담당합니다.
abstract class AlertRepository {
  Future<List<AppAlert>> fetchAlerts({bool unreadOnly = false});

  Future<List<AppAlert>> fetchPending({int? afterAlertId});

  Future<void> markSent(int alertId);

  Future<void> markRead(int alertId);
}

class AlertRepositoryException implements Exception {
  const AlertRepositoryException(this.message);

  final String message;

  @override
  String toString() => message;
}
