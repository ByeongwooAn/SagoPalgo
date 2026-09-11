import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/investment_snapshot.dart';
import 'investment_repository.dart';

/// Spring Boot 대시보드 API에서 투자 데이터를 불러오는 Repository입니다.
class SpringInvestmentRepository implements InvestmentRepository {
  /// 개인용 모드의 선택 access token, API 설정, HTTP 클라이언트를 주입받습니다.
  SpringInvestmentRepository({
    required this.accessToken,
    ApiConfig? config,
    http.Client? client,
  }) : config = config ?? ApiConfig(),
       client = client ?? http.Client();

  /// 백엔드 API 요청에 선택적으로 사용하는 access token입니다.
  final String accessToken;

  /// 백엔드 기본 URL과 대시보드 경로 설정입니다.
  final ApiConfig config;

  /// HTTP 요청을 실제로 보내는 클라이언트입니다.
  final http.Client client;

  @override
  Future<InvestmentSnapshot> fetchSnapshot() async {
    final response = await client.get(
      Uri.parse('${config.dashboardBaseUrl}/snapshot'),
      headers: _headers,
    );

    final decoded = _decodeResponse(response);
    return InvestmentSnapshot.fromJson(decoded['data'] as Map<String, dynamic>);
  }

  /// 공통 API 응답을 확인하고 성공이면 디코딩된 JSON 전체를 반환합니다.
  Map<String, dynamic> _decodeResponse(http.Response response) {
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    final success = decoded['success'] as bool? ?? false;
    if (response.statusCode >= 200 && response.statusCode < 300 && success) {
      return decoded;
    }

    final error = decoded['error'] as Map<String, dynamic>?;
    final message = error?['message'] as String? ?? '투자 데이터를 불러오지 못했습니다.';
    throw InvestmentRepositoryException(message);
  }

  Map<String, String> get _headers => {
    'Accept': 'application/json',
    if (accessToken.trim().isNotEmpty) 'Authorization': 'Bearer $accessToken',
  };
}

/// 투자 Repository에서 화면으로 전달하는 실패 예외입니다.
class InvestmentRepositoryException implements Exception {
  /// 사용자에게 보여줄 수 있는 오류 메시지를 받습니다.
  const InvestmentRepositoryException(this.message);

  /// 오류 화면이나 로그에서 사용할 실패 메시지입니다.
  final String message;

  @override
  String toString() => message;
}
