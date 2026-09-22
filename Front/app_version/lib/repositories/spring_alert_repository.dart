import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/app_alert.dart';
import 'alert_repository.dart';

/// Spring Boot 알림 API를 Windows 앱 모델로 연결합니다.
class SpringAlertRepository implements AlertRepository {
  SpringAlertRepository({
    required this.accessToken,
    ApiConfig? config,
    http.Client? client,
  }) : config = config ?? ApiConfig(),
       client = client ?? http.Client();

  final String accessToken;
  final ApiConfig config;
  final http.Client client;

  @override
  Future<List<AppAlert>> fetchAlerts({bool unreadOnly = false}) async {
    final uri = Uri.parse(config.alertsBaseUrl).replace(
      queryParameters: {
        'unreadOnly': unreadOnly.toString(),
        'page': '0',
        'size': '100',
      },
    );
    final decoded = await _get(uri);
    final data = decoded['data'];
    if (data is! Map<String, dynamic> || data['items'] is! List<dynamic>) {
      throw const AlertRepositoryException('알림 목록 응답 형식이 올바르지 않습니다.');
    }
    return (data['items'] as List<dynamic>)
        .map((item) => AppAlert.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  @override
  Future<List<AppAlert>> fetchPending() async {
    final uri = Uri.parse(
      '${config.alertsBaseUrl}/pending',
    ).replace(queryParameters: {'limit': '20'});
    final decoded = await _get(uri);
    final data = decoded['data'];
    if (data is! List<dynamic>) {
      throw const AlertRepositoryException('전달 대기 알림 응답 형식이 올바르지 않습니다.');
    }
    return data
        .map((item) => AppAlert.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  @override
  Future<void> markRead(int alertId) {
    return _patch('$alertId/read');
  }

  @override
  Future<void> markSent(int alertId) {
    return _patch('$alertId/sent');
  }

  Future<Map<String, dynamic>> _get(Uri uri) async {
    final response = await client.get(uri, headers: _headers);
    return _decode(response);
  }

  Future<void> _patch(String path) async {
    final response = await client.patch(
      Uri.parse('${config.alertsBaseUrl}/$path'),
      headers: _headers,
    );
    _decode(response);
  }

  Map<String, dynamic> _decode(http.Response response) {
    try {
      final decoded = jsonDecode(response.body) as Map<String, dynamic>;
      if (response.statusCode >= 200 &&
          response.statusCode < 300 &&
          (decoded['success'] as bool? ?? false)) {
        return decoded;
      }
      final error = decoded['error'] as Map<String, dynamic>?;
      throw AlertRepositoryException(
        error?['message'] as String? ?? '알림 요청에 실패했습니다.',
      );
    } on AlertRepositoryException {
      rethrow;
    } on FormatException {
      throw const AlertRepositoryException('알림 서버 응답을 해석하지 못했습니다.');
    }
  }

  Map<String, String> get _headers => {
    'Accept': 'application/json',
    if (accessToken.trim().isNotEmpty) 'Authorization': 'Bearer $accessToken',
  };
}
