import 'dart:io';

/// 로컬에 표시했지만 서버 전달 완료를 기록하지 못한 알림을 기억합니다.
abstract class AlertDisplayJournal {
  Future<Set<int>> load();
  Future<void> recordDisplayed(int alertId);
  Future<void> recordAcknowledged(int alertId);
}

class NoopAlertDisplayJournal implements AlertDisplayJournal {
  const NoopAlertDisplayJournal();

  @override
  Future<Set<int>> load() async => {};

  @override
  Future<void> recordDisplayed(int alertId) async {}

  @override
  Future<void> recordAcknowledged(int alertId) async {}
}

/// 추가 기록 방식으로 이전에 저장된 알림 상태를 유지합니다.
class FileAlertDisplayJournal implements AlertDisplayJournal {
  FileAlertDisplayJournal(this.file);

  final File file;

  @override
  Future<Set<int>> load() async {
    if (!await file.exists()) return {};
    final outstanding = <int>{};
    for (final line in await file.readAsLines()) {
      final parts = line.split(' ');
      if (parts.length != 2) continue;
      final id = int.tryParse(parts[1]);
      if (id == null || id <= 0) continue;
      if (parts[0] == 'D') outstanding.add(id);
      if (parts[0] == 'A') outstanding.remove(id);
    }
    return outstanding;
  }

  @override
  Future<void> recordDisplayed(int alertId) => _append('D', alertId);

  @override
  Future<void> recordAcknowledged(int alertId) => _append('A', alertId);

  Future<void> _append(String event, int alertId) async {
    await file.parent.create(recursive: true);
    await file.writeAsString(
      '$event $alertId\n',
      mode: FileMode.append,
      flush: true,
    );
  }
}

AlertDisplayJournal createDefaultAlertDisplayJournal() {
  final localAppData = Platform.environment['LOCALAPPDATA'];
  if (!Platform.isWindows || localAppData == null || localAppData.isEmpty) {
    return const NoopAlertDisplayJournal();
  }
  return FileAlertDisplayJournal(
    File(
      '$localAppData${Platform.pathSeparator}SagoPalgo'
      '${Platform.pathSeparator}alert-display.log',
    ),
  );
}
