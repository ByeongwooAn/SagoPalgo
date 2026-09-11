import 'app_environment.dart';

/// 앱이 Spring Boot 백엔드와 통신할 때 사용하는 API 기본 설정입니다.
///
/// API 주소는 코드에 직접 쓰지 않고 `.env`의 `SAGOPALGO_API_BASE_URL`에서 읽습니다.
/// 실제 기기, 에뮬레이터, 운영 배포마다 `.env` 값만 바꾸면 같은 코드로 실행할 수 있습니다.
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
}
