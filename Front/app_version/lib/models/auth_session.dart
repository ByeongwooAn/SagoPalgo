/// 로그인 성공 후 앱이 보관해야 하는 인증 세션 모델입니다.
///
/// 백엔드의 `AuthTokenResponse`와 구조를 맞췄습니다. 지금은 메모리에만 들고 있지만,
/// 실제 앱에서는 보안 저장소에 accessToken과 refreshToken을 저장하는 단계가 이어져야 합니다.
class AuthSession {
  /// 토큰과 사용자 정보를 모두 명시적으로 받습니다.
  const AuthSession({
    required this.accessToken,
    required this.refreshToken,
    required this.expiresIn,
    required this.user,
  });

  /// API 요청의 `Authorization: Bearer` 헤더에 넣을 사고팔고 JWT access token입니다.
  final String accessToken;

  /// access token 만료 시 `/auth/refresh`에 전달할 사고팔고 refresh token입니다.
  final String refreshToken;

  /// access token이 만료되기까지 남은 시간입니다. 백엔드는 초 단위로 내려줍니다.
  final int expiresIn;

  /// 현재 로그인한 사용자 프로필입니다.
  final AuthUser user;

  /// 백엔드 JSON 응답의 `data` 객체를 앱 모델로 변환합니다.
  ///
  /// 서버 응답 키 이름과 앱 모델 필드를 이곳에서 한 번만 매핑해두면,
  /// 화면 코드는 JSON 구조를 직접 몰라도 됩니다.
  factory AuthSession.fromJson(Map<String, dynamic> json) {
    return AuthSession(
      accessToken: json['accessToken'] as String,
      refreshToken: json['refreshToken'] as String,
      expiresIn: json['expiresIn'] as int,
      user: AuthUser.fromJson(json['user'] as Map<String, dynamic>),
    );
  }
}

/// 인증 세션 안에 들어가는 사용자 기본 정보입니다.
class AuthUser {
  /// 화면과 API 호출에 필요한 최소 사용자 정보를 받습니다.
  const AuthUser({
    required this.userId,
    required this.authProvider,
    required this.email,
    required this.nickname,
    required this.profileImageUrl,
  });

  /// 사고팔고 DB의 사용자 PK입니다.
  final int userId;

  /// 사용자가 로그인한 소셜 제공자입니다. 현재는 `GOOGLE` 또는 `NAVER`입니다.
  final String authProvider;

  /// 소셜 제공자에서 동의받아 내려준 이메일입니다. 제공자 정책에 따라 없을 수 있습니다.
  final String? email;

  /// 앱 화면에 표시할 사용자 이름입니다.
  final String nickname;

  /// 소셜 제공자 프로필 이미지 URL입니다. 이미지 동의가 없으면 null일 수 있습니다.
  final String? profileImageUrl;

  /// 백엔드 JSON 응답의 `user` 객체를 앱 사용자 모델로 변환합니다.
  factory AuthUser.fromJson(Map<String, dynamic> json) {
    return AuthUser(
      userId: json['userId'] as int,
      authProvider: json['authProvider'] as String,
      email: json['email'] as String?,
      nickname: json['nickname'] as String,
      profileImageUrl: json['profileImageUrl'] as String?,
    );
  }
}
