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
  String get message => data['message'] as String;
  String get summary =>
      '$stockName ($stockCode) · ${side == 'BUY' ? '매수' : '매도'}\n'
      '지정가 $price원 · $quantity주 · 예상 ${price * quantity}원';
}
