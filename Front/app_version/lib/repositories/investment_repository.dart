import '../models/investment_snapshot.dart';

/// 투자 관련 데이터를 화면 계층에 제공하는 추상 Repository입니다.
///
/// 화면은 이 인터페이스만 알고 있으면 되므로, 현재는 Mock 데이터를 쓰다가
/// 나중에 Spring Boot API 호출 구현체로 바꿔도 화면 코드는 거의 그대로 유지됩니다.
abstract class InvestmentRepository {
  /// 앱의 홈/추천/보유/알림 화면에 필요한 초기 스냅샷을 불러옵니다.
  ///
  /// 실제 API 연동 시에는 여러 엔드포인트 호출을 이 메서드 안에서 조합하거나,
  /// 백엔드에 대시보드용 통합 API를 만들어 한 번에 받아오면 됩니다.
  Future<InvestmentSnapshot> fetchSnapshot();
}
