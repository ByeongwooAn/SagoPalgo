import '../config/app_environment.dart';

/// Google/Naver SDK에서 provider token을 가져오는 책임을 분리한 인터페이스입니다.
///
/// Google은 공식 `google_sign_in` 패키지의 ID token을, Naver는 공식 Android SDK의 access token을
/// 가져와야 합니다. 현재 파일은 앱 구조를 먼저 잡기 위한 계약이며, 실제 SDK 연결은 이 인터페이스를
/// 구현하는 클래스로 교체하면 됩니다.
abstract class SocialTokenProvider {
  /// Google 로그인 성공 후 서버에 전달할 Google ID token을 반환합니다.
  Future<String> fetchGoogleIdToken();

  /// Naver 로그인 성공 후 서버에 전달할 Naver access token을 반환합니다.
  Future<String> fetchNaverAccessToken();
}

/// 실제 SDK 연결 전까지 앱 UI와 인증 흐름을 확인하기 위한 Mock 토큰 Provider입니다.
///
/// 이 Provider는 진짜 Google/Naver 토큰을 만들지 않습니다. 실제 서버에 연결할 때는
/// `fetchGoogleIdToken`, `fetchNaverAccessToken`을 SDK 호출 코드로 교체해야 합니다.
class MockSocialTokenProvider implements SocialTokenProvider {
  /// Mock 객체는 외부 상태가 없으므로 const 생성자로 충분합니다.
  const MockSocialTokenProvider();

  @override
  Future<String> fetchGoogleIdToken() async {
    return 'mock-google-id-token';
  }

  @override
  Future<String> fetchNaverAccessToken() async {
    return 'mock-naver-access-token';
  }
}

/// 실제 Google/Naver SDK 연결 전까지 SpringAuthRepository가 사용할 자리표시자 Provider입니다.
///
/// `.env`에서 client id는 읽어두지만, 실제 토큰 발급은 플랫폼 SDK 연동이 필요합니다.
/// 따라서 `SAGOPALGO_USE_MOCK_AUTH=false`로 바꾼 상태에서 버튼을 누르면 어떤 SDK 작업이
/// 남아 있는지 명확한 오류 메시지를 반환합니다.
class PendingSdkSocialTokenProvider implements SocialTokenProvider {
  /// `.env`에서 읽은 앱 환경 설정을 주입받습니다.
  const PendingSdkSocialTokenProvider(this.environment);

  /// Google/Naver 공개 client id를 제공하는 환경 설정입니다.
  final AppEnvironment environment;

  @override
  Future<String> fetchGoogleIdToken() {
    final clientId = environment.googleServerClientId;
    if (clientId == null) {
      return Future.error(
        StateError('SAGOPALGO_GOOGLE_SERVER_CLIENT_ID가 .env에 설정되어 있지 않습니다.'),
      );
    }

    return Future.error(
      StateError(
        'Google SDK 연결이 아직 필요합니다. google_sign_in에서 받은 ID token을 반환하도록 구현해야 합니다.',
      ),
    );
  }

  @override
  Future<String> fetchNaverAccessToken() {
    final clientId = environment.naverClientId;
    if (clientId == null) {
      return Future.error(
        StateError('SAGOPALGO_NAVER_CLIENT_ID가 .env에 설정되어 있지 않습니다.'),
      );
    }

    return Future.error(
      StateError(
        'Naver Android SDK 연결이 아직 필요합니다. SDK에서 받은 access token을 반환하도록 구현해야 합니다.',
      ),
    );
  }
}
