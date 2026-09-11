import '../models/recommendation.dart';

/// 추천 화면에서 관심 종목 관련 사용자 액션을 처리하는 Repository입니다.
abstract class WatchlistRepository {
  /// 추천 종목을 관심 종목으로 등록합니다.
  Future<WatchlistActionResult> addRecommendation(
    InvestmentRecommendation recommendation,
  );

  /// 추천 종목을 관심 종목에 등록하고 알림을 켭니다.
  Future<WatchlistActionResult> enableAlert(
    InvestmentRecommendation recommendation,
  );
}

/// 관심 종목 액션 결과와 사용자 피드백 메시지입니다.
class WatchlistActionResult {
  /// 성공 여부와 화면에 보여줄 메시지를 받습니다.
  const WatchlistActionResult({required this.message, this.changed = true});

  /// 스낵바에 표시할 메시지입니다.
  final String message;

  /// 서버 상태가 실제로 변경됐는지 여부입니다.
  final bool changed;
}
