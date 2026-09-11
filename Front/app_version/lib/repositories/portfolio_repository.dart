import '../models/holding.dart';

/// 포트폴리오 화면에 필요한 자본금, 손익 요약, 보유 종목을 제공하는 Repository입니다.
abstract class PortfolioRepository {
  /// 최신 포트폴리오 데이터를 불러옵니다.
  Future<PortfolioSnapshot> fetchPortfolio();

  /// 투자 가능 자본금과 1회 거래 리스크 비율을 수정합니다.
  Future<CapitalSettings> updateCapital(CapitalInput input);

  /// 보유 종목을 새로 등록합니다.
  Future<void> createHolding(HoldingInput input);

  /// 기존 보유 종목을 수정합니다.
  Future<Holding> updateHolding(int holdingId, HoldingInput input);

  /// 보유 종목을 삭제합니다.
  Future<void> deleteHolding(int holdingId);
}

/// 포트폴리오 Repository에서 화면으로 전달하는 실패 예외입니다.
class PortfolioRepositoryException implements Exception {
  /// 사용자에게 보여줄 수 있는 오류 메시지를 받습니다.
  const PortfolioRepositoryException(this.message);

  /// 오류 화면이나 로그에서 사용할 실패 메시지입니다.
  final String message;

  @override
  String toString() => message;
}
