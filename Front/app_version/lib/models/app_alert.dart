/// 앱 알림 탭에서 보여줄 단일 알림 데이터입니다.
///
/// Flutter의 Material `AlertDialog`와 이름이 겹치지 않도록
/// 도메인 모델 이름을 `AppAlert`로 명확히 둡니다.
class AppAlert {
  /// 알림 카드에 필요한 제목, 본문, 시간, 분류를 모두 받습니다.
  const AppAlert({
    required this.title,
    required this.body,
    required this.timeLabel,
    required this.type,
  });

  /// 알림의 핵심 제목입니다.
  final String title;

  /// 사용자가 행동을 판단할 수 있게 해주는 상세 설명입니다.
  final String body;

  /// "방금 전", "3분 전"처럼 앱에서 바로 보여줄 시간 문자열입니다.
  final String timeLabel;

  /// 아이콘과 강조색을 결정하는 알림 분류입니다.
  final AppAlertType type;

  /// 백엔드 대시보드 스냅샷의 알림 JSON을 앱 모델로 변환합니다.
  factory AppAlert.fromJson(Map<String, dynamic> json) {
    return AppAlert(
      title: json['title'] as String,
      body: json['body'] as String,
      timeLabel: json['timeLabel'] as String,
      type: _appAlertTypeFromApiValue(json['type'] as String?),
    );
  }
}

/// 알림의 의미를 화면 스타일과 연결하기 위한 분류값입니다.
enum AppAlertType {
  /// 매도 또는 리스크 관련 알림입니다.
  sell,

  /// 신규 관심 종목 또는 매수 후보 알림입니다.
  candidate,

  /// 시장 흐름 변화 알림입니다.
  market,
}

/// 백엔드 alert type 문자열을 화면 분류로 변환합니다.
AppAlertType _appAlertTypeFromApiValue(String? value) {
  return switch (value) {
    'SELL' || 'RISK' => AppAlertType.sell,
    'CANDIDATE' || 'BUY' => AppAlertType.candidate,
    _ => AppAlertType.market,
  };
}
