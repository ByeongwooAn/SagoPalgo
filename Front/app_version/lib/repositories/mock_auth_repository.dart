import '../models/auth_session.dart';
import '../services/social_token_provider.dart';
import 'auth_repository.dart';

/// 실제 소셜 SDK와 백엔드가 연결되기 전까지 앱 로그인 UI를 동작시키는 Mock Repository입니다.
///
/// 버튼을 누르면 MockSocialTokenProvider에서 가짜 로그인 값을 받은 뒤,
/// 백엔드 응답과 같은 형태의 AuthSession을 반환합니다.
class MockAuthRepository implements AuthRepository {
  /// 소셜 토큰 Provider를 주입받아 실제 구현과 같은 호출 흐름을 유지합니다.
  const MockAuthRepository({
    this.tokenProvider = const MockSocialTokenProvider(),
  });

  /// Google/Naver 로그인 값을 가져오는 객체입니다.
  final SocialTokenProvider tokenProvider;

  @override
  Future<AuthSession> loginWithGoogle() async {
    await tokenProvider.fetchGoogleIdToken();
    return const AuthSession(
      accessToken: 'mock-sagopalgo-access-token',
      refreshToken: 'mock-sagopalgo-refresh-token',
      expiresIn: 3600,
      user: AuthUser(
        userId: 1,
        authProvider: 'GOOGLE',
        email: 'google.user@example.com',
        nickname: '구글사용자',
        profileImageUrl: null,
      ),
    );
  }

  @override
  Future<AuthSession> loginWithNaver() async {
    await tokenProvider.fetchNaverAuthorizationCode();
    return const AuthSession(
      accessToken: 'mock-sagopalgo-access-token',
      refreshToken: 'mock-sagopalgo-refresh-token',
      expiresIn: 3600,
      user: AuthUser(
        userId: 2,
        authProvider: 'NAVER',
        email: 'naver.user@example.com',
        nickname: '네이버사용자',
        profileImageUrl: null,
      ),
    );
  }

  @override
  Future<AuthSession> refresh(String refreshToken) async {
    return const AuthSession(
      accessToken: 'mock-refreshed-access-token',
      refreshToken: 'mock-refreshed-refresh-token',
      expiresIn: 3600,
      user: AuthUser(
        userId: 1,
        authProvider: 'GOOGLE',
        email: 'google.user@example.com',
        nickname: '구글사용자',
        profileImageUrl: null,
      ),
    );
  }

  @override
  Future<void> logout(String accessToken) async {
    return;
  }
}
