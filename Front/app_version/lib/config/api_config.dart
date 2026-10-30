import 'app_environment.dart';

/// 앱이 Spring Boot 백엔드와 통신할 때 사용하는 API 기본 설정입니다.
///
/// API 주소는 코드에 직접 쓰지 않고 `.env`의 `SAGOPALGO_API_BASE_URL`에서 읽습니다.
/// Windows 로컬 실행, Docker 프록시 실행마다 `.env` 값만 바꾸면 같은 코드로 실행할 수 있습니다.
class ApiConfig {
  /// 환경 설정에서 API 주소를 읽어 설정 객체를 만듭니다.
  ApiConfig({String? baseUrl})
    : baseUrl = baseUrl ?? AppEnvironment.instance.apiBaseUrl;

  /// Spring Boot API 서버의 기본 URL입니다.
  final String baseUrl;

  /// 대시보드 API가 공통으로 사용하는 `/api/v1/dashboard` 기본 경로입니다.
  String get dashboardBaseUrl => '$baseUrl/api/v1/dashboard';

  /// 관심 종목 API가 공통으로 사용하는 `/api/v1/watchlist` 기본 경로입니다.
  String get watchlistBaseUrl => '$baseUrl/api/v1/watchlist';

  /// 자본금 API가 공통으로 사용하는 `/api/v1/capital` 기본 경로입니다.
  String get capitalBaseUrl => '$baseUrl/api/v1/capital';

  /// 보유 종목 API가 공통으로 사용하는 `/api/v1/holdings` 기본 경로입니다.
  String get holdingsBaseUrl => '$baseUrl/api/v1/holdings';

  /// 증권사 연동 설정 API가 사용하는 `/api/v1/settings/providers` 경로입니다.
  String get providerSettingsUrl => '$baseUrl/api/v1/settings/providers';

  /// 저장된 뉴스·공시 통합 피드 조회 경로입니다.
  String get researchFeedUrl => '$baseUrl/api/v1/research/feed';

  /// 외부 뉴스·공시 Provider 수동 동기화 경로입니다.
  String get researchFeedSyncUrl => '$researchFeedUrl/sync';

  /// 선택 종목의 마지막 뉴스·공시 동기화 상태 조회 경로입니다.
  String get researchSyncStatusUrl => '$baseUrl/api/v1/research/sync/status';

  /// 국내주식 일·주·월봉 조회 경로입니다.
  String get marketCandlesUrl => '$baseUrl/api/v1/market/candles';

  /// 앱 알림 이력과 Windows 전달 대기 목록의 기본 경로입니다.
  String get alertsBaseUrl => '$baseUrl/api/v1/alerts';

  /// 추천 이력, 상세, 보유 종목 수동 분석 API의 기본 경로입니다.
  String get recommendationsBaseUrl => '$baseUrl/api/v1/recommendations';

  /// 실제 주문과 분리된 모의매매 조회·체결 API 기본 경로입니다.
  String get paperTradingBaseUrl => '$baseUrl/api/v1/paper-trading';

  /// 실제 전송 없이 주문 안전 조건만 검사하는 API 기본 경로입니다.
  String get orderBaseUrl => '$baseUrl/api/v1/orders';

  /// KB증권 보유 주식 조회 API 경로입니다.
  String get kbHoldingsUrl => '$baseUrl/api/v1/kb/accounts/primary/holdings';

  String get kbPortfolioImportUrl => '$baseUrl/api/v1/kb/portfolio-import';

  /// KB증권 결제기준 잔고 현황 조회 API 경로입니다.
  String get kbSettlementBalanceUrl =>
      '$baseUrl/api/v1/kb/accounts/primary/balances/settlement';

  /// KB증권 체결기준 잔고 현황 조회 API 경로입니다.
  String get kbExecutionBalanceUrl =>
      '$baseUrl/api/v1/kb/accounts/primary/balances/execution';
}
