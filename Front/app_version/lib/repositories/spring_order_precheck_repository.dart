import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/order_precheck.dart';
import 'order_precheck_repository.dart';
import 'manual_order_repository.dart';

/// Spring Boot 주문 사전검증 API를 호출합니다.
class SpringOrderPrecheckRepository
    implements
        OrderPrecheckRepository,
        ManualOrderRepository,
        ManualOrderReconciliationRepository,
        ManualOrderDispatchRepository,
        ManualOrderDiagnosticRepository {
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

  @override
  Future<OrderApprovalPreparation> prepareApproval(
    OrderPrecheckInput input,
  ) async {
    final response = await client.post(
      Uri.parse('${config.orderBaseUrl}/approvals/prepare'),
      headers: _headers,
      body: jsonEncode(input.toJson()),
    );
    final data = _readData(response, '주문 승인 준비에 실패했습니다.');
    return OrderApprovalPreparation.fromJson(data);
  }

  @override
  Future<String> confirmApproval(OrderApprovalPreparation preparation) async {
    final response = await client.post(
      Uri.parse('${config.orderBaseUrl}/approvals/confirm'),
      headers: _headers,
      body: jsonEncode({
        'approvalId': preparation.approvalId,
        'token': preparation.token,
        'acknowledged': true,
      }),
    );
    final data = _readData(response, '수동 승인에 실패했습니다.');
    if (data['orderSubmitted'] != false) {
      throw const OrderPrecheckRepositoryException('주문 승인 응답을 확인할 수 없습니다.');
    }
    return data['message'] as String;
  }

  Map<String, String> get _headers => {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    if (accessToken.trim().isNotEmpty) 'Authorization': 'Bearer $accessToken',
  };

  Future<dynamic> _manual(String path, {Map<String, dynamic>? body}) async {
    final uri = Uri.parse('${config.orderBaseUrl}/$path');
    final response =
        await (body == null
                ? client.get(uri, headers: _headers)
                : client.post(uri, headers: _headers, body: jsonEncode(body)))
            .timeout(const Duration(seconds: 45));
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode >= 200 &&
        response.statusCode < 300 &&
        decoded['success'] == true) {
      return decoded['data'];
    }
    throw OrderPrecheckRepositoryException(
      (decoded['error'] as Map<String, dynamic>?)?['message'] as String? ??
          '주문 기록을 확인할 수 없습니다.',
    );
  }

  @override
  Future<bool> manualOrderReady() async =>
      (await _manual('readiness') as Map<String, dynamic>)['canSubmit'] == true;
  @override
  Future<List<ManualOrder>> manualOrderHistory() async =>
      (await _manual('manual') as List)
          .map((e) => ManualOrder(e as Map<String, dynamic>))
          .toList();
  @override
  Future<ManualOrder> submitManualOrder(int approvalId) async => ManualOrder(
    await _manual(
          'manual',
          body: {
            'approvalId': approvalId,
            'acknowledged': true,
            'confirmation': '실제 주문 전송',
          },
        )
        as Map<String, dynamic>,
  );
  @override
  Future<Map<String, dynamic>> observeManualOrder(String id) async =>
      await _manual('manual/$id/observations', body: {})
          as Map<String, dynamic>;
  @override
  Future<List<Map<String, dynamic>>> manualOrderObservations(String id) async =>
      (await _manual('manual/$id/observations') as List)
          .cast<Map<String, dynamic>>();
  @override
  Future<Map<String, dynamic>> prepareManualChange(
    String id,
    String kind,
    int? price,
  ) async =>
      await _manual(
            'manual/$id/changes/prepare',
            body: {'kind': kind, 'price': ?price},
          )
          as Map<String, dynamic>;
  @override
  Future<ManualOrder> submitManualChange(String id, String token) async =>
      ManualOrder(
        await _manual(
              'manual/$id/submit',
              body: {
                'token': token,
                'acknowledged': true,
                'confirmation': '실제 주문 전송',
              },
            )
            as Map<String, dynamic>,
      );

  @override
  Future<Map<String, dynamic>> prepareReconciliation(
    String id,
    String orderNo,
  ) async =>
      await _manual(
            'manual/$id/reconciliation/prepare',
            body: {'orderNo': orderNo},
          )
          as Map<String, dynamic>;

  @override
  Future<void> confirmReconciliation(String id, String token) async {
    await _manual(
      'manual/$id/reconciliation/confirm',
      body: {
        'token': token,
        'acknowledged': true,
        'confirmation': '전량 체결 대조 확정',
      },
    );
  }

  Map<String, dynamic> _readData(http.Response response, String fallback) {
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode >= 200 &&
        response.statusCode < 300 &&
        decoded['success'] == true) {
      return decoded['data'] as Map<String, dynamic>;
    }
    final error = decoded['error'] as Map<String, dynamic>?;
    throw OrderPrecheckRepositoryException(
      error?['message'] as String? ?? fallback,
    );
  }

  @override
  Future<Map<String, dynamic>> fetchDispatch(String id) async =>
      await _manual('manual/$id/dispatch') as Map<String, dynamic>;

  @override
  Future<List<Map<String, dynamic>>> diagnosticHistory(String id) async =>
      (await _manual('manual/$id/diagnostics') as List)
          .cast<Map<String, dynamic>>();

  @override
  Future<Map<String, dynamic>> diagnoseSending(
    String id,
    String diagnosticId,
    String orderNo,
  ) async =>
      await _manual(
            'manual/$id/diagnostics',
            body: {
              'diagnosticId': diagnosticId,
              'orderNo': orderNo,
              'acknowledged': true,
              'confirmation': '잠금 유지 진단',
            },
          )
          as Map<String, dynamic>;

  @override
  Future<Map<String, dynamic>> recoverDispatch(String id) async =>
      await _manual(
            'manual/$id/dispatch/recover',
            body: {'acknowledged': true, 'confirmation': '저장된 전송 결과 복구'},
          )
          as Map<String, dynamic>;
}
