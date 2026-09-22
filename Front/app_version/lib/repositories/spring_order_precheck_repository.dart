import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/order_precheck.dart';
import 'order_precheck_repository.dart';

/// Spring Boot 주문 사전검증 API를 호출합니다.
class SpringOrderPrecheckRepository implements OrderPrecheckRepository {
  SpringOrderPrecheckRepository({
    required this.accessToken,
    ApiConfig? config,
    http.Client? client,
  }) : config = config ?? ApiConfig(),
       client = client ?? http.Client();

  final String accessToken;
  final ApiConfig config;
  final http.Client client;

  @override
  Future<OrderPrecheckResult> precheck(OrderPrecheckInput input) async {
    final response = await client.post(
      Uri.parse('${config.orderBaseUrl}/precheck'),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        if (accessToken.trim().isNotEmpty)
          'Authorization': 'Bearer $accessToken',
      },
      body: jsonEncode(input.toJson()),
    );
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    final success = decoded['success'] as bool? ?? false;
    if (response.statusCode >= 200 && response.statusCode < 300 && success) {
      return OrderPrecheckResult.fromJson(
        decoded['data'] as Map<String, dynamic>,
      );
    }
    final error = decoded['error'] as Map<String, dynamic>?;
    throw OrderPrecheckRepositoryException(
      error?['message'] as String? ?? '주문 사전검증에 실패했습니다.',
    );
  }
}
