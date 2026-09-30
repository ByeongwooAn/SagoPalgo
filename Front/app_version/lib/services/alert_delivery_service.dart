import '../repositories/alert_repository.dart';
import 'local_notification_service.dart';

/// Windows 표시 성공과 서버 확인을 분리해 알림별 재시도를 관리합니다.
class AlertDeliveryService {
  AlertDeliveryService({
    required this.repository,
    required this.notificationService,
  });

  static const _pageSize = 20;
  static const _maxPagesPerPoll = 5;

  final AlertRepository repository;
  final LocalNotificationService notificationService;
  final Set<int> _displayedButUnacknowledged = {};
  int _afterAlertId = 0;

  Future<bool> deliverPending() async {
    var foundPending = false;
    for (var page = 0; page < _maxPagesPerPoll; page++) {
      final pending = await repository.fetchPending(
        afterAlertId: _afterAlertId == 0 ? null : _afterAlertId,
      );
      if (pending.isEmpty) {
        _afterAlertId = 0;
        break;
      }
      foundPending = true;
      final lastId = pending.last.alertId;
      if (lastId == null || lastId <= _afterAlertId) {
        _afterAlertId = 0;
        break;
      }

      for (final alert in pending) {
        final alertId = alert.alertId;
        if (alertId == null) {
          continue;
        }
        try {
          if (!_displayedButUnacknowledged.contains(alertId)) {
            await notificationService.show(alert);
            _displayedButUnacknowledged.add(alertId);
          }
          await repository.markSent(alertId);
          _displayedButUnacknowledged.remove(alertId);
        } catch (_) {
          // 한 건의 표시·확인 실패가 뒤의 알림 전달을 막지 않게 합니다.
        }
      }

      _afterAlertId = lastId;
      if (pending.length < _pageSize) {
        _afterAlertId = 0;
        break;
      }
    }
    return foundPending;
  }
}
