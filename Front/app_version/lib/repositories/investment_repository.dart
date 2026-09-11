import '../models/investment_snapshot.dart';

/// 투자 관련 데이터를 화면 계층에 제공하는 추상 Repository입니다.
///
/// 화면은 이 인터페이스만 알고 있으면 되므로, Spring Boot API 호출 방식이 바뀌어도
/// 화면 코드는 거의 그대로 유지됩니다.
abstract class InvestmentRepository {
  /// 앱의 홈/추천/보유/알림 화면에 필요한 초기 스냅샷을 불러옵니다.
  ///
  /// 백엔드의 대시보드용 통합 API에서 한 번에 받아옵니다.
  Future<InvestmentSnapshot> fetchSnapshot();
}
