import '../models/auth_session.dart';

/// 인증 화면이 의존하는 인증 Repository 계약입니다.
///
/// 화면은 Google/Naver SDK나 HTTP 구현을 직접 알지 않고 이 인터페이스만 호출합니다.
/// 그래서 현재 Mock 구현에서 실제 Spring Boot API 구현으로 바꿔도 로그인 화면 코드는 거의 바뀌지 않습니다.
abstract class AuthRepository {
  /// Google 로그인으로 사고팔고 세션을 생성합니다.
  Future<AuthSession> loginWithGoogle();

  /// Naver 로그인으로 사고팔고 세션을 생성합니다.
  Future<AuthSession> loginWithNaver();

  /// refresh token으로 사고팔고 세션을 갱신합니다.
  Future<AuthSession> refresh(String refreshToken);

  /// 현재 access token 기준으로 서버 로그아웃을 요청합니다.
  Future<void> logout(String accessToken);
}
