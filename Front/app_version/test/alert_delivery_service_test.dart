import 'package:app_version/models/app_alert.dart';
import 'package:app_version/repositories/alert_repository.dart';
import 'package:app_version/services/alert_delivery_service.dart';
import 'package:app_version/services/local_notification_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('one display failure does not block later alerts', () async {
    final repository = _FakeAlertRepository([_alert(7), _alert(8)]);
    final notifications = _FakeNotificationService()..failIds.add(7);
    final delivery = AlertDeliveryService(
      repository: repository,
      notificationService: notifications,
    );

    expect(await delivery.deliverPending(), isTrue);
    expect(repository.sentIds, [8]);
    expect(notifications.shownIds, [8]);

    notifications.failIds.clear();
    expect(await delivery.deliverPending(), isTrue);
    expect(repository.sentIds, [8, 7]);
  });

  test(
    'ack retry does not display the same alert again in this app session',
    () async {
      final repository = _FakeAlertRepository([_alert(7)])..failAckIds.add(7);
      final notifications = _FakeNotificationService();
      final delivery = AlertDeliveryService(
        repository: repository,
        notificationService: notifications,
      );

      await delivery.deliverPending();
      repository.failAckIds.clear();
      await delivery.deliverPending();

      expect(notifications.shownIds, [7]);
      expect(repository.sentIds, [7]);
    },
  );

  test('failed first page does not starve later pending alerts', () async {
    final repository = _FakeAlertRepository([
      for (var id = 1; id <= 21; id++) _alert(id),
    ]);
    final notifications = _FakeNotificationService()
      ..failIds.addAll(List.generate(20, (index) => index + 1));
    final delivery = AlertDeliveryService(
      repository: repository,
      notificationService: notifications,
    );

    await delivery.deliverPending();

    expect(repository.sentIds, [21]);
    expect(repository.cursors, [null, 20]);
  });

  test(
    'bounded polling resumes beyond one hundred failures next cycle',
    () async {
      final repository = _FakeAlertRepository([
        for (var id = 1; id <= 101; id++) _alert(id),
      ]);
      final notifications = _FakeNotificationService()
        ..failIds.addAll(List.generate(100, (index) => index + 1));
      final delivery = AlertDeliveryService(
        repository: repository,
        notificationService: notifications,
      );

      await delivery.deliverPending();
      expect(repository.sentIds, isEmpty);
      await delivery.deliverPending();

      expect(repository.sentIds, [101]);
      expect(repository.cursors.last, 100);
    },
  );
}

AppAlert _alert(int id) => AppAlert(
  alertId: id,
  title: '알림 $id',
  body: '본문',
  timeLabel: '방금 전',
  type: AppAlertType.market,
);

class _FakeAlertRepository implements AlertRepository {
  _FakeAlertRepository(this.alerts);

  final List<AppAlert> alerts;
  final Set<int> failAckIds = {};
  final List<int> sentIds = [];
  final List<int?> cursors = [];

  @override
  Future<List<AppAlert>> fetchPending({int? afterAlertId}) async {
    cursors.add(afterAlertId);
    return alerts
        .where(
          (alert) =>
              alert.alertId! > (afterAlertId ?? 0) &&
              !sentIds.contains(alert.alertId),
        )
        .take(20)
        .toList();
  }

  @override
  Future<void> markSent(int alertId) async {
    if (failAckIds.contains(alertId)) {
      throw const AlertRepositoryException('확인 실패');
    }
    sentIds.add(alertId);
  }

  @override
  Future<List<AppAlert>> fetchAlerts({bool unreadOnly = false}) async => [];

  @override
  Future<void> markRead(int alertId) async {}
}

class _FakeNotificationService implements LocalNotificationService {
  final Set<int> failIds = {};
  final List<int> shownIds = [];

  @override
  Future<void> show(AppAlert alert) async {
    if (failIds.contains(alert.alertId)) {
      throw StateError('표시 실패');
    }
    shownIds.add(alert.alertId!);
  }
}
