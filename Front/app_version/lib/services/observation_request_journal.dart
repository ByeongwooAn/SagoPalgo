import 'dart:convert';
import 'dart:io';

import '../models/account_observation.dart';

/// 응답을 확인하지 못한 요청의 ID·조회일만 저장합니다. 잔고·본문·토큰은 저장하지 않습니다.
abstract class ObservationRequestJournal {
  Future<List<ObservationRequest>> load(String context);
  Future<void> start(String context, ObservationRequest request);
  Future<void> complete(String context, String requestId);
}

class MemoryObservationRequestJournal implements ObservationRequestJournal {
  final _requests = <String, Map<String, ObservationRequest>>{};
  @override
  Future<List<ObservationRequest>> load(String context) async =>
      List.unmodifiable(_requests[context]?.values ?? []);
  @override
  Future<void> start(String context, ObservationRequest request) async {
    (_requests[context] ??= {})[request.requestId] = request;
  }

  @override
  Future<void> complete(String context, String requestId) async {
    _requests[context]?.remove(requestId);
  }
}

class FileObservationRequestJournal implements ObservationRequestJournal {
  FileObservationRequestJournal(this.file);
  final File file;
  Future<void> _writes = Future.value();

  @override
  Future<List<ObservationRequest>> load(String context) async {
    await _writes;
    if (!await file.exists()) return [];
    final requests = <String, ObservationRequest>{};
    for (final line in await file.readAsLines()) {
      if (line.isEmpty) continue;
      final event = observationObject(jsonDecode(line));
      if (event['context'] != context) continue;
      final request = ObservationRequest.fromJson(
        observationObject(event['request']),
      );
      switch (event['event']) {
        case 'START':
          requests[request.requestId] = request;
        case 'COMPLETE':
          requests.remove(request.requestId);
        default:
          throw const FormatException('요청 복구 기록 오류');
      }
    }
    return List.unmodifiable(requests.values);
  }

  @override
  Future<void> start(String context, ObservationRequest request) => _append({
    'event': 'START',
    'context': context,
    'request': request.toJson(),
  });

  @override
  Future<void> complete(String context, String requestId) async {
    final pending = await load(context);
    final matches = pending.where((e) => e.requestId == requestId);
    if (matches.isEmpty) return;
    await _append({
      'event': 'COMPLETE',
      'context': context,
      'request': matches.first.toJson(),
    });
  }

  Future<void> _append(Map<String, dynamic> event) {
    final operation = _writes.then((_) async {
      await file.parent.create(recursive: true);
      await file.writeAsString(
        '${jsonEncode(event)}\n',
        mode: FileMode.append,
        flush: true,
      );
    });
    _writes = operation.catchError((Object _) {});
    return operation;
  }
}

ObservationRequestJournal createObservationRequestJournal() {
  final directory =
      Platform.environment['LOCALAPPDATA'] ?? Platform.environment['HOME'];
  // 복구 기록을 영속 보관할 위치가 없으면 임시 저장소로 조용히 대체하지 않습니다.
  if (directory == null || directory.isEmpty) {
    return _UnavailableObservationRequestJournal();
  }
  return FileObservationRequestJournal(
    File(
      '$directory${Platform.pathSeparator}SagoPalgo${Platform.pathSeparator}account-observation-requests.jsonl',
    ),
  );
}

class _UnavailableObservationRequestJournal
    implements ObservationRequestJournal {
  @override
  Future<List<ObservationRequest>> load(String context) async =>
      throw const FileSystemException('복구 기록 위치 없음');
  @override
  Future<void> start(String context, ObservationRequest request) async =>
      throw const FileSystemException('복구 기록 위치 없음');
  @override
  Future<void> complete(String context, String requestId) async =>
      throw const FileSystemException('복구 기록 위치 없음');
}
