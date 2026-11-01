/// 실제 전송은 승인 기록 후 별도의 확인을 통해서만 요청합니다.
abstract interface class ManualOrderRepository {
  Future<bool> manualOrderReady();
  Future<List<ManualOrder>> manualOrderHistory();
  Future<ManualOrder> submitManualOrder(int approvalId);
  Future<Map<String, dynamic>> observeManualOrder(String id);
  Future<List<Map<String, dynamic>>> manualOrderObservations(String id);
  Future<Map<String, dynamic>> prepareManualChange(
    String id,
    String kind,
    int? price,
  );
  Future<ManualOrder> submitManualChange(String id, String token);
}

/// 미확정 전송 대조는 실제 주문 전송 기능과 분리합니다.
abstract interface class ManualOrderReconciliationRepository {
  Future<Map<String, dynamic>> prepareReconciliation(String id, String orderNo);
  Future<void> confirmReconciliation(String id, String token);
}

/// 저장된 호출 종료 결과만 적용합니다. 주문을 전송하지 않습니다.
abstract interface class ManualOrderDispatchRepository {
  Future<Map<String, dynamic>> fetchDispatch(String id);
  Future<Map<String, dynamic>> recoverDispatch(String id);
}

abstract interface class ManualOrderReservationAbortRepository {
  Future<Map<String, dynamic>> abortReservation(String id);
}

abstract interface class ManualOrderDiagnosticRepository {
  Future<List<Map<String, dynamic>>> diagnosticHistory(String id);
  Future<Map<String, dynamic>> diagnoseSending(
    String id,
    String diagnosticId,
    String orderNo,
  );
}

abstract interface class UnknownOrderReviewRepository {
  Future<Map<String, dynamic>> prepareUnknownReview(String id, String orderNo);
  Future<void> confirmUnknownReview(String id, String reviewId, String token);
  Future<List<Map<String, dynamic>>> unknownReviewHistory(String id);
}

class ManualOrder {
  ManualOrder(this.data);
  final Map<String, dynamic> data;
  String get id => data['commandId'] as String;
  String get status => data['status'] as String;
  String get kind => data['kind'] as String;
  String get stockName => data['stockName'] as String;
  String get stockCode => data['stockCode'] as String;
  String get side => data['side'] as String;
  String get orderNo => data['orderNo'] as String? ?? '';
  num get price => num.parse('${data['price']}');
  num get quantity => num.parse('${data['quantity']}');
  bool get changeUsed => data['changeUsed'] == true;
  Map<String, dynamic>? get reconciliation =>
      data['reconciliation'] as Map<String, dynamic>?;
  bool get reconciled => reconciliation != null;
  bool get abortedBeforeDispatch =>
      status == 'SENDING' &&
      orderNo.isEmpty &&
      data['reservationAbort'] is Map &&
      data['reservationAbort']['source'] == 'LOCAL_BEFORE_DISPATCH' &&
      data['reservationAbort']['abortedAt'] is String;
  bool get unresolved =>
      (status == 'SENDING' && !abortedBeforeDispatch) ||
      (status == 'UNKNOWN' && !reconciled);
  String get message => data['message'] as String;
  String get summary =>
      '$stockName ($stockCode) · ${side == 'BUY' ? '매수' : '매도'}\n'
      '지정가 $price원 · $quantity주 · 예상 ${price * quantity}원';
}
