import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/paper_trading.dart';
import 'paper_trading_repository.dart';
import 'order_simulation_repository.dart';

/// Spring Boot 모의매매 API를 호출합니다.
class SpringPaperTradingRepository
    implements
        PaperTradingRepository,
        OrderSimulationRepository,
        UsPaperTradingRepository {
  SpringPaperTradingRepository({
    required this.accessToken,
    ApiConfig? config,
    http.Client? client,
  }) : config = config ?? ApiConfig(),
       client = client ?? http.Client();

  final String accessToken;
  final ApiConfig config;
  final http.Client client;

  @override
  Future<PaperTradingSnapshot> fetchUsSnapshot() => _usRequest('GET', '/us');

  @override
  Future<PaperTradingSnapshot> openUsAccount(String initialCapital) =>
      _usRequest('PUT', '/us/account', {'initialCapital': initialCapital});

  @override
  Future<PaperTradingSnapshot> tradeUs(UsPaperOrder order) =>
      _usRequest('POST', '/us/trades', {
        'stockCode': order.stockCode,
        'market': order.market,
        'side': order.side,
        'quantity': order.quantity,
        'requestId': order.requestId,
      });

  Future<PaperTradingSnapshot> _usRequest(
    String method,
    String path, [
    Map<String, String>? body,
  ]) async {
    final request = http.Request(
      method,
      Uri.parse('${config.paperTradingBaseUrl}$path'),
    )..headers.addAll(_headers(contentType: body != null));
    if (body != null) request.body = jsonEncode(body);
    final response = await client
        .send(request)
        .then(http.Response.fromStream)
        .timeout(const Duration(seconds: 30));
    final snapshot = _snapshot(response);
    if (snapshot.currency != 'USD') {
      throw const FormatException('USD 모의매매 응답을 확인할 수 없습니다.');
    }
    return snapshot;
  }

  Future<dynamic> _simulationRequest(
    String path, [
    Map<String, dynamic>? body,
  ]) async {
    final uri = Uri.parse('${config.orderBaseUrl}/simulations$path');
    final response =
        await (body == null
                ? client.get(uri, headers: _headers())
                : client.post(
                    uri,
                    headers: _headers(contentType: true),
                    body: jsonEncode(body),
                  ))
            .timeout(const Duration(seconds: 30));
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode >= 200 &&
        response.statusCode < 300 &&
        decoded['success'] == true) {
      return decoded['data'];
    }
    throw Exception(
      (decoded['error'] as Map<String, dynamic>?)?['message'] ??
          '모의 주문 요청에 실패했습니다.',
    );
  }

  @override
  Future<List<Map<String, dynamic>>> simulationSessions() async =>
      (await _simulationRequest('') as List).cast<Map<String, dynamic>>();
  @override
  Future<Map<String, dynamic>> createSimulation(num cash) async =>
      await _simulationRequest('', {'cash': cash}) as Map<String, dynamic>;
  @override
  Future<Map<String, dynamic>> simulation(String id) async =>
      await _simulationRequest('/$id') as Map<String, dynamic>;
  @override
  Future<Map<String, dynamic>> simulationAction(
    String id,
    String path,
    Map<String, dynamic> body,
  ) async =>
      await _simulationRequest('/$id/$path', body) as Map<String, dynamic>;

  @override
  Future<PaperTradingSnapshot> fetchSnapshot() async {
    final response = await client.get(
      Uri.parse(config.paperTradingBaseUrl),
      headers: _headers(),
    );
    return _snapshot(response);
  }

  @override
  Future<PaperTradingSnapshot> buyFromRecommendation(
    int recommendationId,
    double quantity, {
    required String requestId,
  }) async {
    final response = await client.post(
      Uri.parse(
        '${config.paperTradingBaseUrl}/recommendations/$recommendationId/buy',
      ),
      headers: _headers(contentType: true),
      body: jsonEncode({'quantity': quantity, 'requestId': requestId}),
    );
    return _snapshot(response);
  }

  @override
  Future<PaperTradingSnapshot> sellPosition({
    required String stockCode,
    required String market,
    required double quantity,
    required String requestId,
  }) async {
    final response = await client.post(
      Uri.parse('${config.paperTradingBaseUrl}/sell'),
      headers: _headers(contentType: true),
      body: jsonEncode({
        'stockCode': stockCode,
        'market': market,
        'quantity': quantity,
        'requestId': requestId,
      }),
    );
    return _snapshot(response);
  }

  PaperTradingSnapshot _snapshot(http.Response response) {
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    final success = decoded['success'] as bool? ?? false;
    if (response.statusCode >= 200 && response.statusCode < 300 && success) {
      return PaperTradingSnapshot.fromJson(
        decoded['data'] as Map<String, dynamic>,
      );
    }
    final error = decoded['error'] as Map<String, dynamic>?;
    throw PaperTradingRepositoryException(
      error?['message'] as String? ?? '모의매매 요청에 실패했습니다.',
      code: error?['code'] as String?,
    );
  }

  Map<String, String> _headers({bool contentType = false}) {
    return {
      'Accept': 'application/json',
      if (accessToken.trim().isNotEmpty) 'Authorization': 'Bearer $accessToken',
      if (contentType) 'Content-Type': 'application/json',
    };
  }
}
