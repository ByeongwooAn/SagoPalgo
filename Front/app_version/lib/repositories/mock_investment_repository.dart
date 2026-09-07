import '../data/mock_investment_data.dart';
import '../models/investment_snapshot.dart';
import 'investment_repository.dart';

/// 실제 백엔드가 준비되기 전까지 앱 UI를 구동하는 Mock Repository입니다.
///
/// 일부러 `Future`를 반환해 실제 네트워크 Repository와 같은 사용 경험을 제공합니다.
/// 화면 입장에서는 Mock인지 API인지 구분하지 않고 로딩/성공 상태를 다룰 수 있습니다.
class MockInvestmentRepository implements InvestmentRepository {
  /// Mock 데이터라도 짧은 지연을 둬서 로딩 UI와 비동기 흐름을 검증할 수 있게 합니다.
  const MockInvestmentRepository({
    this.delay = const Duration(milliseconds: 250),
  });

  /// 네트워크 대기 시간을 흉내내기 위한 지연 시간입니다.
  final Duration delay;

  @override
  Future<InvestmentSnapshot> fetchSnapshot() async {
    /// 실제 API 교체 시 이 위치에서 HTTP 호출과 JSON 파싱이 들어갑니다.
    await Future<void>.delayed(delay);
    return mockInvestmentSnapshot;
  }
}
