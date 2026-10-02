import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/provider_setting.dart';
import 'provider_settings_repository.dart';

/// Spring Boot 증권사 설정 API와 통신하는 Repository입니다.
class SpringProviderSettingsRepository implements ProviderSettingsRepository {
  /// API 설정, HTTP 클라이언트, 선택 access token을 주입받습니다.
  SpringProviderSettingsRepository({
    required this.accessToken,
    ApiConfig? config,
    http.Client? client,
  }) : config = config ?? ApiConfig(),
       client = client ?? http.Client();

  /// 개인용 모드에서는 빈 문자열이며, 비어 있으면 Authorization 헤더를 보내지 않습니다.
  final String accessToken;

  /// 백엔드 기본 URL 설정입니다.
  final ApiConfig config;

  /// HTTP 요청 클라이언트입니다.
  final http.Client client;

  @override
  Future<ProviderSettingsSnapshot> fetchProviderSettings() async {
    final response = await client.get(
      Uri.parse(config.providerSettingsUrl),
      headers: _headers,
    );

    final decoded = _decodeResponse(response);
    return ProviderSettingsSnapshot.fromJson(
      decoded['data'] as Map<String, dynamic>,
    );
  }

  @override
  Future<OrderReadOnlyProbe> probeReadOnlyOrderHistory() async {
    final response = await client.post(
      Uri.parse('${config.orderBaseUrl}/readiness/probe'),
      headers: _headers,
    );
    final decoded = _decodeResponse(response);
    return OrderReadOnlyProbe.fromJson(decoded['data'] as Map<String, dynamic>);
  }

  @override
  Future<OrderReadOnlyProbe?> fetchLatestReadOnlyOrderHistoryProbe() async {
    final response = await client.get(
      Uri.parse('${config.orderBaseUrl}/readiness/probe/latest'),
      headers: _headers,
    );
    final data = _decodeResponse(response)['data'];
    return data == null
        ? null
        : OrderReadOnlyProbe.fromJson(data as Map<String, dynamic>);
  }

  @override
  Future<List<OrderReadOnlyProbe>> fetchReadOnlyOrderProbeHistory() async {
    final response = await client.get(
      Uri.parse('${config.orderBaseUrl}/readiness/probe/history'),
      headers: _headers,
    );
    final data = _decodeResponse(response)['data'] as List<dynamic>;
    return data
        .map(
          (item) => OrderReadOnlyProbe.fromJson(item as Map<String, dynamic>),
        )
        .toList();
  }

  Map<String, dynamic> _decodeResponse(http.Response response) {
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    final success = decoded['success'] as bool? ?? false;
    if (response.statusCode >= 200 && response.statusCode < 300 && success) {
      return decoded;
    }

    final error = decoded['error'] as Map<String, dynamic>?;
    final message = error?['message'] as String? ?? '증권사 설정을 불러오지 못했습니다.';
    throw ProviderSettingsRepositoryException(message);
  }

  Map<String, String> get _headers => {
    'Accept': 'application/json',
    if (accessToken.trim().isNotEmpty) 'Authorization': 'Bearer $accessToken',
  };
}
