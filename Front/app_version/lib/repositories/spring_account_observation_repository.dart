import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/account_observation.dart';
import '../services/observation_request_journal.dart';
import 'account_observation_repository.dart';

class SpringAccountObservationRepository
    implements AccountObservationRepository {
  SpringAccountObservationRepository({
    required this.accessToken,
    required this.localUserId,
    ApiConfig? config,
    http.Client? client,
    ObservationRequestJournal? journal,
    this.timeout = const Duration(seconds: 60),
  }) : config = config ?? ApiConfig(),
       client = client ?? http.Client(),
       journal = journal ?? createObservationRequestJournal();

  final String accessToken;
  final int localUserId;
  final ApiConfig config;
  final http.Client client;
  final ObservationRequestJournal journal;
  final Duration timeout;
  bool _capturing = false;

  String get _context => jsonEncode([
    Uri.parse(
      config.baseUrl,
    ).replace(userInfo: '', query: '', fragment: '').toString(),
    localUserId,
  ]);
  Uri _uri([String path = '']) =>
      Uri.parse('${config.accountObservationsUrl}$path');
  Map<String, String> get _headers => {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    if (accessToken.trim().isNotEmpty) 'Authorization': 'Bearer $accessToken',
  };

  @override
  Future<List<ObservationRequest>> outstanding() async {
    try {
      return await journal.load(_context);
    } catch (_) {
      throw const ObservationRepositoryException(
        'LOCAL_RECORD_ERROR',
        '요청 복구 기록을 읽을 수 없습니다. 로컬 기록 상태를 확인한 뒤 저장 상태를 조회하세요.',
      );
    }
  }

  @override
  Future<ObservationDetail> capture(String orderDate) async {
    if (_capturing) {
      throw const ObservationRepositoryException('BUSY', '관찰 저장 요청을 처리 중입니다.');
    }
    try {
      observationDate(orderDate);
    } catch (_) {
      throw const ObservationRepositoryException(
        'VALIDATION_ERROR',
        '조회일을 YYYYMMDD의 실제 날짜로 입력하세요.',
      );
    }
    _capturing = true;
    try {
      await outstanding();
      final request = ObservationRequest(_uuid(), orderDate);
      try {
        await journal.start(_context, request);
      } catch (_) {
        throw const ObservationRepositoryException(
          'LOCAL_RECORD_ERROR',
          '요청 ID를 보관할 수 없어 저장 요청을 보내지 않았습니다.',
        );
      }
      final json = await _call(
        () => client.post(
          _uri(),
          headers: _headers,
          body: jsonEncode(request.toJson()),
        ),
      );
      return await _confirm(json, request.requestId, orderDate);
    } finally {
      _capturing = false;
    }
  }

  @override
  Future<ObservationPage> history({int? beforeId}) async {
    if (beforeId != null && beforeId <= 0) {
      throw const ObservationRepositoryException(
        'VALIDATION_ERROR',
        '이력 페이지를 다시 조회하세요.',
      );
    }
    final data = await _call(
      () => client.get(
        _uri().replace(
          queryParameters: {
            'limit': '20',
            if (beforeId != null) 'beforeId': '$beforeId',
          },
        ),
        headers: _headers,
      ),
    );
    return _parse(() {
      final page = ObservationPage.fromJson(data);
      if (page.items.length > 20 ||
          (beforeId != null &&
              page.nextBeforeId != null &&
              page.nextBeforeId! >= beforeId)) {
        throw const FormatException('이력 페이지 오류');
      }
      return page;
    });
  }

  @override
  Future<ObservationDetail> detail(String requestId) async {
    final id = _id(requestId);
    return _confirm(
      await _call(() => client.get(_uri('/$id'), headers: _headers)),
      id,
      null,
    );
  }

  @override
  Future<ObservationDetail> check(ObservationRequest request) async {
    final id = _id(request.requestId);
    return _confirm(
      await _call(() => client.get(_uri('/$id'), headers: _headers)),
      id,
      request.orderDate,
    );
  }

  @override
  Future<ObservationComparison> compare(
    String beforeRequestId,
    String afterRequestId,
  ) async {
    final before = _id(beforeRequestId), after = _id(afterRequestId);
    if (before == after) {
      throw const ObservationRepositoryException(
        'VALIDATION_ERROR',
        '서로 다른 두 관찰을 선택하세요.',
      );
    }
    final data = await _call(
      () => client.get(
        _uri('/comparison').replace(
          queryParameters: {'beforeRequestId': before, 'afterRequestId': after},
        ),
        headers: _headers,
      ),
    );
    return _parse(() {
      final result = ObservationComparison.fromJson(data);
      if (result.beforeRequestId != before || result.afterRequestId != after) {
        throw const FormatException('비교 요청 불일치');
      }
      return result;
    });
  }

  Future<ObservationDetail> _confirm(
    Map<String, dynamic> data,
    String id,
    String? date,
  ) async {
    final result = _parse(() {
      final value = ObservationDetail.fromJson(data);
      if (value.summary.requestId != id ||
          (date != null && value.summary.orderDate != date)) {
        throw const FormatException('저장 요청 불일치');
      }
      return value;
    });
    if (result.summary.storageState != 'PENDING') {
      final pending = await outstanding();
      if (pending.any(
        (r) => r.requestId == id && r.orderDate != result.summary.orderDate,
      )) {
        throw const ObservationRepositoryException(
          'INVALID_RESPONSE',
          '요청 날짜가 일치하지 않습니다. 저장 이력을 확인하세요.',
        );
      }
      try {
        await journal.complete(_context, id);
      } catch (_) {
        throw const ObservationRepositoryException(
          'LOCAL_RECORD_ERROR',
          '서버 결과를 받았지만 로컬 확인 기록을 갱신하지 못했습니다. 같은 요청의 저장 상태를 확인하세요.',
        );
      }
    }
    return result;
  }

  String _id(String value) {
    try {
      return observationRequestId(value);
    } catch (_) {
      throw const ObservationRepositoryException(
        'VALIDATION_ERROR',
        '올바른 관찰 요청을 선택하세요.',
      );
    }
  }

  T _parse<T>(T Function() read) {
    try {
      return read();
    } catch (_) {
      throw const ObservationRepositoryException(
        'INVALID_RESPONSE',
        '서버 관찰 응답을 확인할 수 없습니다. 저장 상태를 다시 확인하세요.',
      );
    }
  }

  Future<Map<String, dynamic>> _call(
    Future<http.Response> Function() send,
  ) async {
    http.Response response;
    try {
      response = await send().timeout(timeout);
    } catch (_) {
      throw const ObservationRepositoryException(
        'CONNECTION_ERROR',
        '서버 응답을 확인하지 못했습니다. 저장을 요청했다면 아래 요청 ID로 저장 상태를 확인하세요.',
      );
    }
    dynamic decoded;
    try {
      decoded = jsonDecode(utf8.decode(response.bodyBytes));
    } catch (_) {
      throw const ObservationRepositoryException(
        'INVALID_RESPONSE',
        '서버 응답 형식을 확인할 수 없습니다. 배포 상태와 저장 이력을 확인하세요.',
      );
    }
    if (response.statusCode >= 200 &&
        response.statusCode < 300 &&
        decoded is Map &&
        decoded['success'] == true) {
      return _parse(() => observationObject(decoded['data']));
    }
    // 외부 응답 전문/예외 문자열을 화면에 복사하지 않습니다.
    final code = decoded is Map && decoded['error'] is Map
        ? decoded['error']['code']
        : null;
    if (code == 'OBSERVATION_STORAGE_UNAVAILABLE') {
      throw const ObservationRepositoryException(
        'OBSERVATION_STORAGE_UNAVAILABLE',
        '관찰 저장소를 확인할 수 없습니다. 서버의 DB 023 적용 상태를 확인한 뒤 같은 요청의 저장 상태를 확인하세요.',
      );
    }
    final message = switch (response.statusCode) {
      400 => '요청 날짜와 서버 KB 연결 설정을 확인하세요.',
      401 || 403 => '서버 접근 권한을 확인하세요.',
      404 =>
        '현재 연결에서 관찰 기록을 찾지 못했습니다. 서버 배포·계좌 연결·요청 ID를 확인하세요. 자동으로 새 요청을 보내지 않습니다.',
      409 => '계좌 연결 또는 요청 범위가 변경되었습니다. 이력을 새로 조회하세요.',
      _ => '관찰 요청을 처리하지 못했습니다. 서버 상태와 저장 이력을 확인하세요.',
    };
    throw ObservationRepositoryException(
      'HTTP_${response.statusCode}',
      message,
    );
  }

  String _uuid() {
    final random = Random.secure();
    final bytes = List.generate(16, (_) => random.nextInt(256));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    final hex = bytes.map((e) => e.toRadixString(16).padLeft(2, '0')).join();
    return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
  }
}
