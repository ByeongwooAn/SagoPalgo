import '../models/order_precheck.dart';

/// 실제 주문 전송과 분리된 주문 사전검증 경계입니다.
abstract class OrderPrecheckRepository {
  Future<OrderPrecheckResult> precheck(OrderPrecheckInput input);
}

class OrderPrecheckRepositoryException implements Exception {
  const OrderPrecheckRepositoryException(this.message);

  final String message;

  @override
  String toString() => message;
}
