import '../models/kb_account_snapshot.dart';

/// KB증권 계좌 조회 데이터를 제공하는 Repository입니다.
abstract class KbAccountRepository {
  /// 보유 주식, 결제기준 잔고, 체결기준 잔고를 한 번에 조회합니다.
  Future<KbAccountSnapshot> fetchSnapshot();
}

/// KB증권 계좌 조회 실패 예외입니다.
class KbAccountRepositoryException implements Exception {
  /// 화면에 표시할 오류 메시지를 받습니다.
  const KbAccountRepositoryException(this.message);

  /// 사용자에게 보여줄 수 있는 오류 메시지입니다.
  final String message;

  @override
  String toString() => message;
}
