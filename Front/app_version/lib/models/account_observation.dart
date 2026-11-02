/// 관찰 계약에서는 금액·수량을 숫자로 변환하거나 누락값을 0으로 채우지 않습니다.
typedef ObservationFields = Map<String, String?>;

const observationApis = ['SSQM1801', 'SSQM2932', 'SSQM2952', 'SSQM2341'];

Map<String, dynamic> observationObject(dynamic value) {
  if (value is! Map<String, dynamic>) throw const FormatException('관찰 객체 오류');
  return value;
}

List<dynamic> _list(dynamic value) {
  if (value is! List) throw const FormatException('관찰 목록 오류');
  return value;
}

String _string(dynamic value) {
  if (value is! String) throw const FormatException('관찰 문자열 오류');
  return value;
}

String? _optionalString(dynamic value) => value == null ? null : _string(value);

String observationRequestId(dynamic value) {
  final id = _string(value);
  if (!RegExp(
    r'^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$',
  ).hasMatch(id)) {
    throw const FormatException('관찰 요청 ID 오류');
  }
  return id.toLowerCase();
}

String observationDate(dynamic value) {
  final text = _string(value);
  if (!RegExp(r'^\d{8}$').hasMatch(text)) {
    throw const FormatException('조회 날짜 오류');
  }
  final date = DateTime.tryParse(
    '${text.substring(0, 4)}-${text.substring(4, 6)}-${text.substring(6)}',
  );
  if (date == null ||
      date.year < 1 ||
      date.year.toString().padLeft(4, '0') != text.substring(0, 4) ||
      date.month.toString().padLeft(2, '0') != text.substring(4, 6) ||
      date.day.toString().padLeft(2, '0') != text.substring(6)) {
    throw const FormatException('조회 날짜 오류');
  }
  return text;
}

String _choice(dynamic value, List<String> allowed) {
  final text = _string(value);
  if (!allowed.contains(text)) throw const FormatException('관찰 상태 오류');
  return text;
}

DateTime _time(dynamic value) {
  final text = _string(value);
  if (!RegExp(r'(Z|[+-]\d{2}:\d{2})$').hasMatch(text)) {
    throw const FormatException('관찰 시각 오류');
  }
  return DateTime.parse(text).toUtc();
}

int _count(dynamic value) {
  if (value is! int || value < 0) throw const FormatException('관찰 건수 오류');
  return value;
}

ObservationFields _fields(dynamic value) => Map.unmodifiable(
  observationObject(
    value,
  ).map((key, value) => MapEntry(key, _optionalString(value))),
);

Map<String, String> _scope(dynamic value) => Map.unmodifiable(
  observationObject(value).map((key, value) => MapEntry(key, _string(value))),
);

const _statuses = ['SUCCESS', 'PARTIAL', 'FAILED', 'DISABLED'];

/// 서버 설정과 실행 기록은 별개입니다. ACTIVE를 시간 경과로 해제하지 않습니다.
class ObservationCollection {
  ObservationCollection.fromJson(Map<String, dynamic> json)
    : enabled = _boolean(json['enabled']),
      personalModeEnabled = _boolean(json['personalModeEnabled']),
      accountEnabled = _boolean(json['accountEnabled']),
      connectionConfigured = _boolean(json['connectionConfigured']),
      intervalSeconds = _count(json['intervalSeconds']),
      state = _choice(json['state'], [
        'UNCONFIGURED',
        'NOT_STARTED',
        'IDLE',
        'ACTIVE',
        'PAUSED',
      ]),
      activeRequestId = json['activeRequestId'] == null
          ? null
          : observationRequestId(json['activeRequestId']),
      activeOrderDate = json['activeOrderDate'] == null
          ? null
          : observationDate(json['activeOrderDate']),
      lastRequestId = json['lastRequestId'] == null
          ? null
          : observationRequestId(json['lastRequestId']),
      lastStorageState = json['lastStorageState'] == null
          ? null
          : _choice(json['lastStorageState'], [
              'PENDING',
              'COMPLETED',
              'FAILED',
            ]),
      lastSnapshotStatus = json['lastSnapshotStatus'] == null
          ? null
          : _choice(json['lastSnapshotStatus'], _statuses),
      failureCode = _optionalString(json['failureCode']),
      nextDueAt = json['nextDueAt'] == null ? null : _time(json['nextDueAt']),
      startedAt = json['startedAt'] == null ? null : _time(json['startedAt']),
      completedAt = json['completedAt'] == null
          ? null
          : _time(json['completedAt']) {
    if (json['readOnly'] != true ||
        json['usableForTrading'] != false ||
        intervalSeconds < 60 ||
        intervalSeconds > 86400) {
      throw const FormatException('수집 상태 계약 오류');
    }
  }

  final bool enabled, personalModeEnabled, accountEnabled, connectionConfigured;
  final int intervalSeconds;
  final String state;
  final String? activeRequestId,
      activeOrderDate,
      lastRequestId,
      lastStorageState,
      lastSnapshotStatus,
      failureCode;
  final DateTime? nextDueAt, startedAt, completedAt;

  /// 버튼 표시 조건일 뿐이며 최종 종료/무결성 대조는 서버가 수행합니다.
  bool get canResume =>
      connectionConfigured &&
      state == 'PAUSED' &&
      activeRequestId == null &&
      activeOrderDate == null &&
      lastRequestId != null &&
      completedAt != null &&
      ((lastStorageState == 'FAILED' && lastSnapshotStatus == null) ||
          (lastStorageState == 'COMPLETED' && lastSnapshotStatus != null)) &&
      const [
        'SNAPSHOT_PARTIAL',
        'SNAPSHOT_FAILED',
        'SNAPSHOT_DISABLED',
        'SNAPSHOT_UNUSABLE',
        'OBSERVATION_FAILED',
        'CONTEXT_CHANGED',
      ].contains(failureCode);
}

bool _boolean(dynamic value) {
  if (value is! bool) throw const FormatException('수집 설정 오류');
  return value;
}

class ObservationRequest {
  const ObservationRequest(this.requestId, this.orderDate);
  factory ObservationRequest.fromJson(Map<String, dynamic> json) =>
      ObservationRequest(
        observationRequestId(json['requestId']),
        observationDate(json['orderDate']),
      );
  final String requestId;
  final String orderDate;
  Map<String, String> toJson() => {
    'requestId': requestId,
    'orderDate': orderDate,
  };
}

class ObservationSummary {
  ObservationSummary.fromJson(Map<String, dynamic> json)
    : requestId = observationRequestId(json['requestId']),
      orderDate = observationDate(json['orderDate']),
      storageState = _choice(json['storageState'], [
        'PENDING',
        'COMPLETED',
        'FAILED',
      ]),
      snapshotStatus = json['snapshotStatus'] == null
          ? null
          : _choice(json['snapshotStatus'], _statuses),
      observationId = json['observationId'] == null
          ? null
          : observationRequestId(json['observationId']),
      createdAt = _time(json['createdAt']),
      completedAt = json['completedAt'] == null
          ? null
          : _time(json['completedAt']),
      failureCode = _optionalString(json['failureCode']) {
    if (json['readOnly'] != true ||
        (storageState == 'COMPLETED' &&
            (observationId == null || snapshotStatus == null))) {
      throw const FormatException('관찰 저장 계약 오류');
    }
  }
  final String requestId, orderDate, storageState;
  final String? snapshotStatus, observationId, failureCode;
  final DateTime createdAt;
  final DateTime? completedAt;
}

class ObservationPage {
  ObservationPage.fromJson(Map<String, dynamic> json)
    : items = List.unmodifiable(
        _list(
          json['items'],
        ).map((e) => ObservationSummary.fromJson(observationObject(e))),
      ),
      nextBeforeId = json['nextBeforeId'] == null
          ? null
          : _count(json['nextBeforeId']) {
    if (nextBeforeId == 0) throw const FormatException('관찰 커서 오류');
  }
  final List<ObservationSummary> items;
  final int? nextBeforeId;
}

class ObservationIssue {
  ObservationIssue.fromJson(Map<String, dynamic> json)
    : code = _string(json['code']),
      field = _optionalString(json['field']);
  final String code;
  final String? field;
}

class ObservationSection {
  ObservationSection.fromJson(Map<String, dynamic> json)
    : api = _choice(json['api'], observationApis),
      scope = _scope(json['scope']),
      status = _choice(json['status'], _statuses),
      completeness = _choice(json['completeness'], [
        'COMPLETE',
        'PARTIAL',
        'UNKNOWN',
        'INVALID',
      ]),
      startedAt = _time(json['startedAt']),
      completedAt = _time(json['completedAt']),
      providerProcessTime = _optionalString(json['providerProcessTime']),
      pagesRead = _count(json['pagesRead']),
      receivedRowCount = _count(json['receivedRowCount']),
      reportedTotalCount = json['reportedTotalCount'] == null
          ? null
          : _count(json['reportedTotalCount']),
      summary = _fields(json['summary']),
      rows = List.unmodifiable(
        _list(json['rows']).map((e) => _fields(observationObject(e)['fields'])),
      ),
      issues = List.unmodifiable(
        _list(
          json['issues'],
        ).map((e) => ObservationIssue.fromJson(observationObject(e))),
      );
  final String api, status, completeness;
  final Map<String, String> scope;
  final DateTime startedAt, completedAt;
  final String? providerProcessTime;
  final int pagesRead, receivedRowCount;
  final int? reportedTotalCount;
  final ObservationFields summary;
  final List<ObservationFields> rows;
  final List<ObservationIssue> issues;
}

class ObservationPayload {
  ObservationPayload.fromJson(Map<String, dynamic> json)
    : observationId = observationRequestId(json['observationId']),
      status = _choice(json['status'], _statuses),
      startedAt = _time(json['startedAt']),
      completedAt = _time(json['completedAt']),
      sections = List.unmodifiable(
        _list(
          json['sections'],
        ).map((e) => ObservationSection.fromJson(observationObject(e))),
      ) {
    if (json['contractVersion'] != 'KB_ACCOUNT_OBSERVATION_V1' ||
        json['provider'] != 'KB' ||
        json['accountAlias'] != 'primary' ||
        json['atomic'] != false ||
        json['usableForTrading'] != false ||
        startedAt.isAfter(completedAt) ||
        sections.length != 4) {
      throw const FormatException('관찰 계약 오류');
    }
    for (var i = 0; i < 4; i++) {
      if (sections[i].api != observationApis[i]) {
        throw const FormatException('관찰 구간 오류');
      }
    }
  }
  final String observationId, status;
  final DateTime startedAt, completedAt;
  final List<ObservationSection> sections;
}

class ObservationDetail {
  ObservationDetail.fromJson(Map<String, dynamic> json)
    : summary = ObservationSummary.fromJson(json),
      observation = json['observation'] == null
          ? null
          : ObservationPayload.fromJson(
              observationObject(json['observation']),
            ) {
    if ((summary.storageState == 'COMPLETED') != (observation != null) ||
        (observation != null &&
            (observation!.observationId != summary.observationId ||
                observation!.status != summary.snapshotStatus ||
                observation!.sections.last.scope['orderDate'] !=
                    summary.orderDate))) {
      throw const FormatException('관찰 상세 계약 오류');
    }
  }
  final ObservationSummary summary;
  final ObservationPayload? observation;
}

class ObservationFieldChange {
  ObservationFieldChange.fromJson(Map<String, dynamic> json)
    : field = _string(json['field']),
      beforeValue = _optionalString(json['beforeValue']),
      afterValue = _optionalString(json['afterValue']),
      numericDelta = _optionalString(json['numericDelta']),
      beforePresent = json['beforePresent'] as bool,
      afterPresent = json['afterPresent'] as bool;
  final String field;
  final String? beforeValue, afterValue, numericDelta;
  final bool beforePresent, afterPresent;
}

class ObservationRowChange {
  ObservationRowChange.fromJson(Map<String, dynamic> json)
    : kind = _choice(json['kind'], [
        'CHANGED',
        'OBSERVED_ONLY_BEFORE',
        'OBSERVED_ONLY_AFTER',
      ]),
      identity = _scope(json['identity']),
      fields = List.unmodifiable(
        _list(
          json['fields'],
        ).map((e) => ObservationFieldChange.fromJson(observationObject(e))),
      );
  final String kind;
  final Map<String, String> identity;
  final List<ObservationFieldChange> fields;
}

class ObservationComparisonSection {
  ObservationComparisonSection.fromJson(Map<String, dynamic> json)
    : api = _choice(json['api'], observationApis),
      status = _choice(json['status'], ['COMPARED', 'BLOCKED']),
      beforeScope = _scope(json['beforeScope']),
      afterScope = _scope(json['afterScope']),
      reasons = List.unmodifiable(_list(json['reasons']).map(_string)),
      summaryChanges = List.unmodifiable(
        _list(
          json['summaryChanges'],
        ).map((e) => ObservationFieldChange.fromJson(observationObject(e))),
      ),
      rowChanges = List.unmodifiable(
        _list(
          json['rowChanges'],
        ).map((e) => ObservationRowChange.fromJson(observationObject(e))),
      ) {
    if (status == 'BLOCKED' &&
        (reasons.isEmpty ||
            summaryChanges.isNotEmpty ||
            rowChanges.isNotEmpty)) {
      throw const FormatException('비교 차단 계약 오류');
    }
  }
  final String api, status;
  final Map<String, String> beforeScope, afterScope;
  final List<String> reasons;
  final List<ObservationFieldChange> summaryChanges;
  final List<ObservationRowChange> rowChanges;
}

class ObservationComparison {
  ObservationComparison.fromJson(Map<String, dynamic> json)
    : beforeRequestId = observationRequestId(
        observationObject(json['before'])['requestId'],
      ),
      afterRequestId = observationRequestId(
        observationObject(json['after'])['requestId'],
      ),
      status = _choice(json['status'], ['COMPARED', 'PARTIAL', 'BLOCKED']),
      sections = List.unmodifiable(
        _list(json['sections']).map(
          (e) => ObservationComparisonSection.fromJson(observationObject(e)),
        ),
      ) {
    if (json['contractVersion'] != 'KB_ACCOUNT_COMPARISON_V1' ||
        json['readOnly'] != true ||
        json['usableForTrading'] != false ||
        beforeRequestId == afterRequestId ||
        sections.length != 4) {
      throw const FormatException('관찰 비교 계약 오류');
    }
    for (var i = 0; i < 4; i++) {
      if (sections[i].api != observationApis[i]) {
        throw const FormatException('비교 구간 오류');
      }
    }
  }
  final String beforeRequestId, afterRequestId, status;
  final List<ObservationComparisonSection> sections;
}
