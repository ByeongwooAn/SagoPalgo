import '../models/order_precheck.dart';

/// 실제 주문 전송과 분리된 주문 사전검증 경계입니다.
abstract class OrderPrecheckRepository {
  const OrderPrecheckRepository();

  Future<OrderPrecheckResult> precheck(OrderPrecheckInput input);

  Future<OrderApprovalPreparation> prepareApproval(OrderPrecheckInput input) =>
      throw UnsupportedError('수동 승인 준비를 지원하지 않습니다.');

  Future<String> confirmApproval(OrderApprovalPreparation preparation) =>
      throw UnsupportedError('수동 승인을 지원하지 않습니다.');
}

class OrderPrecheckRepositoryException implements Exception {
  const OrderPrecheckRepositoryException(this.message);

  final String message;

  @override
  String toString() => message;
}
