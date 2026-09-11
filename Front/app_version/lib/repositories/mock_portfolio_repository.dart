import '../data/mock_investment_data.dart';
import '../models/holding.dart';
import 'portfolio_repository.dart';

/// API 연결 없이 포트폴리오 화면의 자본금/보유 종목 흐름을 확인하기 위한 Mock Repository입니다.
class MockPortfolioRepository implements PortfolioRepository {
  /// Mock 객체는 외부 상태가 없으므로 const 생성자로 충분합니다.
  const MockPortfolioRepository();

  @override
  Future<PortfolioSnapshot> fetchPortfolio() async {
    await Future<void>.delayed(const Duration(milliseconds: 250));
    return PortfolioSnapshot(
      capital: const CapitalSettings(
        availableCapital: 3000000,
        recommendedMinPosition: 300000,
        recommendedMaxPosition: 600000,
        riskPerTradeRate: 0.02,
      ),
      summary: mockInvestmentSnapshot.portfolioSummary,
      holdings: mockInvestmentSnapshot.holdings,
    );
  }
}
