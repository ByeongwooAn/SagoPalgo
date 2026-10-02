import '../repositories/alert_repository.dart';
import 'alert_display_journal.dart';
import 'local_notification_service.dart';

class AlertDeliveryStatus {
  const AlertDeliveryStatus({
    this.checkedAt,
    this.unconfirmedCount = 0,
    this.failedCount = 0,
    this.checkFailed = false,
  });

  final DateTime? checkedAt;
  final int unconfirmedCount;
  final int failedCount;
  final bool checkFailed;
}

/// Windows 표시 성공과 서버 확인을 분리해 알림별 재시도를 관리합니다.
class AlertDeliveryService {
  AlertDeliveryService({
    required this.repository,
    required this.notificationService,
    this.displayJournal = const NoopAlertDisplayJournal(),
  });

  static const _pageSize = 20;
  static const _maxPagesPerPoll = 5;

  final AlertRepository repository;
  final LocalNotificationService notificationService;
  final AlertDisplayJournal displayJournal;
  final Set<int> _displayedButUnacknowledged = {};
  int _afterAlertId = 0;
  bool _journalLoaded = false;
  AlertDeliveryStatus status = const AlertDeliveryStatus();

  Future<bool> deliverPending() async {
    var foundPending = false;
    var failedCount = 0;
    try {
      if (!_journalLoaded) {
        _displayedButUnacknowledged.addAll(await displayJournal.load());
        _journalLoaded = true;
      }
      final startedAtBeginning = _afterAlertId == 0;
      final seenPendingIds = <int>{};
      var completedScan = false;
      for (var page = 0; page < _maxPagesPerPoll; page++) {
        final pending = await repository.fetchPending(
          afterAlertId: _afterAlertId == 0 ? null : _afterAlertId,
        );
        if (pending.isEmpty) {
          _afterAlertId = 0;
          completedScan = true;
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
          seenPendingIds.add(alertId);
          try {
            if (!_displayedButUnacknowledged.contains(alertId)) {
              await notificationService.show(alert);
              _displayedButUnacknowledged.add(alertId);
              await displayJournal.recordDisplayed(alertId);
            }
            await repository.markSent(alertId);
            await displayJournal.recordAcknowledged(alertId);
            _displayedButUnacknowledged.remove(alertId);
          } catch (_) {
            failedCount++;
            // 한 건의 표시·확인 실패가 뒤의 알림 전달을 막지 않게 합니다.
          }
        }

        _afterAlertId = lastId;
        if (pending.length < _pageSize) {
          _afterAlertId = 0;
          completedScan = true;
          break;
        }
      }
      if (startedAtBeginning && completedScan) {
        for (final alertId
            in _displayedButUnacknowledged
                .difference(seenPendingIds)
                .toList()) {
          try {
            await displayJournal.recordAcknowledged(alertId);
            _displayedButUnacknowledged.remove(alertId);
          } catch (_) {
            failedCount++;
          }
        }
      }
      status = AlertDeliveryStatus(
        checkedAt: DateTime.now(),
        unconfirmedCount: _displayedButUnacknowledged.length,
        failedCount: failedCount,
      );
      return foundPending;
    } catch (_) {
      status = AlertDeliveryStatus(
        checkedAt: DateTime.now(),
        unconfirmedCount: _displayedButUnacknowledged.length,
        failedCount: failedCount,
        checkFailed: true,
      );
      rethrow;
    }
  }
}
