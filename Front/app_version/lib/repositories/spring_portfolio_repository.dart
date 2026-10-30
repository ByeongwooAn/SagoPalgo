import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/holding.dart';
import '../models/kb_portfolio_import.dart';
import 'kb_portfolio_importer.dart';
import 'portfolio_repository.dart';

/// Spring Boot 자본금/보유 종목 API에서 포트폴리오 데이터를 불러오는 Repository입니다.
class SpringPortfolioRepository
    implements PortfolioRepository, KbPortfolioImporter {
  /// 개인용 모드의 선택 access token, API 설정, HTTP 클라이언트를 주입받습니다.
  SpringPortfolioRepository({
    required this.accessToken,
    ApiConfig? config,
    http.Client? client,
  }) : config = config ?? ApiConfig(),
       client = client ?? http.Client();

  /// 백엔드 API 요청에 선택적으로 사용하는 access token입니다.
  final String accessToken;

  /// 백엔드 기본 URL과 포트폴리오 관련 경로 설정입니다.
  final ApiConfig config;

  /// HTTP 요청을 실제로 보내는 클라이언트입니다.
  final http.Client client;

  @override
  Future<KbPortfolioPreview> previewKbImport() async {
    final response = await client.get(
      Uri.parse('${config.kbPortfolioImportUrl}/preview'),
      headers: _headers,
    );
    return KbPortfolioPreview.fromJson(
      _decodeResponse(response)['data'] as Map<String, dynamic>,
    );
  }

  @override
  Future<KbPortfolioImportResult> applyKbImport({
    required KbPortfolioPreview preview,
    required bool importCapital,
    required bool importHoldings,
    required Map<String, String> markets,
    required double stopLossRate,
    required double takeProfitRate,
  }) async {
    final response = await client.post(
      Uri.parse(config.kbPortfolioImportUrl),
      headers: {..._headers, 'Content-Type': 'application/json'},
      body: jsonEncode({
        'previewToken': preview.token,
        'expiresAt': preview.expiresAt.toUtc().toIso8601String(),
        'importCapital': importCapital,
        'importHoldings': importHoldings,
        'markets': markets,
        'stopLossRate': stopLossRate,
        'takeProfitRate': takeProfitRate,
      }),
    );
    return KbPortfolioImportResult.fromJson(
      _decodeResponse(response)['data'] as Map<String, dynamic>,
    );
  }

  @override
  Future<PortfolioSnapshot> fetchPortfolio() async {
    final capitalResponse = await client.get(
      Uri.parse(config.capitalBaseUrl),
      headers: _headers,
    );
    final holdingsResponse = await client.get(
      Uri.parse(config.holdingsBaseUrl),
      headers: _headers,
    );

    final capital = _decodeResponse(capitalResponse)['data'];
    final holdings = _decodeResponse(holdingsResponse)['data'];
    final holdingsMap = holdings as Map<String, dynamic>;

    return PortfolioSnapshot(
      capital: CapitalSettings.fromJson(capital as Map<String, dynamic>),
      summary: PortfolioSummary.fromJson(
        holdingsMap['summary'] as Map<String, dynamic>,
      ),
      holdings: (holdingsMap['items'] as List<dynamic>)
          .map((item) => Holding.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }

  @override
  Future<CapitalSettings> updateCapital(CapitalInput input) async {
    final response = await client.put(
      Uri.parse(config.capitalBaseUrl),
      headers: _jsonHeaders,
      body: jsonEncode(input.toJson()),
    );
    final data = _decodeResponse(response)['data'] as Map<String, dynamic>;
    return CapitalSettings.fromJson(data);
  }

  @override
  Future<void> createHolding(HoldingInput input) async {
    final response = await client.post(
      Uri.parse(config.holdingsBaseUrl),
      headers: _jsonHeaders,
      body: jsonEncode(input.toJson()),
    );
    _decodeResponse(response);
  }

  @override
  Future<Holding> updateHolding(int holdingId, HoldingInput input) async {
    final response = await client.put(
      Uri.parse('${config.holdingsBaseUrl}/$holdingId'),
      headers: _jsonHeaders,
      body: jsonEncode(input.toJson()),
    );
    final data = _decodeResponse(response)['data'] as Map<String, dynamic>;
    return Holding.fromJson(data);
  }

  @override
  Future<void> deleteHolding(int holdingId) async {
    final response = await client.delete(
      Uri.parse('${config.holdingsBaseUrl}/$holdingId'),
      headers: _headers,
    );
    _decodeResponse(response);
  }

  Map<String, String> get _headers => {
    'Accept': 'application/json',
    if (accessToken.trim().isNotEmpty) 'Authorization': 'Bearer $accessToken',
  };

  Map<String, String> get _jsonHeaders => {
    ..._headers,
    'Content-Type': 'application/json',
  };

  /// 공통 API 응답을 확인하고 성공이면 디코딩된 JSON 전체를 반환합니다.
  Map<String, dynamic> _decodeResponse(http.Response response) {
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    final success = decoded['success'] as bool? ?? false;
    if (response.statusCode >= 200 && response.statusCode < 300 && success) {
      return decoded;
    }

    final error = decoded['error'] as Map<String, dynamic>?;
    final message = error?['message'] as String? ?? '포트폴리오 데이터를 불러오지 못했습니다.';
    throw PortfolioRepositoryException(message);
  }
}
