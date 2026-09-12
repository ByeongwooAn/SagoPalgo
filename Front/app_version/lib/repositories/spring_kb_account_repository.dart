import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/kb_account_snapshot.dart';
import 'kb_account_repository.dart';

/// Spring Boot KB증권 계좌 API와 통신하는 Repository입니다.
class SpringKbAccountRepository implements KbAccountRepository {
  /// 선택 access token, API 설정, HTTP 클라이언트를 주입받습니다.
  SpringKbAccountRepository({
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
  Future<KbAccountSnapshot> fetchSnapshot() async {
    final responses = await Future.wait([
      client.get(Uri.parse(config.kbHoldingsUrl), headers: _headers),
      client.get(Uri.parse(config.kbSettlementBalanceUrl), headers: _headers),
      client.get(Uri.parse(config.kbExecutionBalanceUrl), headers: _headers),
    ]);

    final holdings = _decodeResponse(responses[0])['data'];
    final settlementBalance = _decodeResponse(responses[1])['data'];
    final executionBalance = _decodeResponse(responses[2])['data'];

    return KbAccountSnapshot(
      holdings: KbHoldingsSnapshot.fromJson(holdings as Map<String, dynamic>),
      settlementBalance: KbBalanceSnapshot.fromJson(
        settlementBalance as Map<String, dynamic>,
      ),
      executionBalance: KbBalanceSnapshot.fromJson(
        executionBalance as Map<String, dynamic>,
      ),
    );
  }

  Map<String, dynamic> _decodeResponse(http.Response response) {
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    final success = decoded['success'] as bool? ?? false;
    if (response.statusCode >= 200 && response.statusCode < 300 && success) {
      return decoded;
    }

    final error = decoded['error'] as Map<String, dynamic>?;
    final message = error?['message'] as String? ?? 'KB증권 계좌를 조회하지 못했습니다.';
    throw KbAccountRepositoryException(message);
  }

  Map<String, String> get _headers => {
    'Accept': 'application/json',
    if (accessToken.trim().isNotEmpty) 'Authorization': 'Bearer $accessToken',
  };
}
