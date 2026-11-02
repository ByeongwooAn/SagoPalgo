import '../models/account_observation.dart';

abstract class AccountObservationRepository {
  Future<ObservationCollection> collectionStatus();

  /// 수집 설정을 켜거나 즉시 KB를 조회하지 않습니다. 자동 재시도하지 않습니다.
  Future<ObservationCollection> resumeCollection(String lastRequestId);

  Future<ObservationPage> history({int? beforeId});
  Future<ObservationDetail> detail(String requestId);
  Future<ObservationComparison> compare(
    String beforeRequestId,
    String afterRequestId,
  );
  Future<List<ObservationRequest>> outstanding();

  /// 새 UUID를 먼저 영속 기록한 뒤 POST를 한 번만 실행합니다.
  Future<ObservationDetail> capture(String orderDate);

  /// 복구는 GET만 사용하며 404/오류에서도 POST로 전환하지 않습니다.
  Future<ObservationDetail> check(ObservationRequest request);
}

class ObservationRepositoryException implements Exception {
  const ObservationRepositoryException(this.code, this.message);
  final String code, message;
  @override
  String toString() => message;
}
