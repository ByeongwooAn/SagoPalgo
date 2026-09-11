import '../models/recommendation.dart';
import 'watchlist_repository.dart';

/// API 연결 없이 추천 화면의 관심 종목 액션을 확인하기 위한 Mock Repository입니다.
class MockWatchlistRepository implements WatchlistRepository {
  /// 별도 설정 없이 즉시 성공 결과를 반환합니다.
  const MockWatchlistRepository();

  @override
  Future<WatchlistActionResult> addRecommendation(
    InvestmentRecommendation recommendation,
  ) async {
    return WatchlistActionResult(
      message: '${recommendation.stockName} 관심 종목에 등록했습니다.',
    );
  }

  @override
  Future<WatchlistActionResult> enableAlert(
    InvestmentRecommendation recommendation,
  ) async {
    return WatchlistActionResult(
      message: '${recommendation.stockName} 알림을 켰습니다.',
    );
  }
}
