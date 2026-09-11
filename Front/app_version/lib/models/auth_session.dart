/// 개인용 프로그램에서 앱이 사용하는 로컬 프로필 세션 모델입니다.
///
/// 과거 소셜 로그인 기반 백엔드 응답과의 호환을 위해 토큰 필드는 남겨두지만,
/// 개인용 모드에서는 빈 토큰과 로컬 사용자 프로필로 바로 홈 화면에 진입합니다.
class AuthSession {
  /// 토큰과 사용자 정보를 모두 명시적으로 받습니다.
  const AuthSession({
    required this.accessToken,
    required this.refreshToken,
    required this.expiresIn,
    required this.user,
  });

  /// 로그인 없이 앱을 실행할 때 사용하는 기본 개인 프로필입니다.
  static const personal = AuthSession(
    accessToken: '',
    refreshToken: '',
    expiresIn: 0,
    user: AuthUser(
      userId: 1,
      authProvider: 'LOCAL',
      email: null,
      nickname: '개인 사용자',
      profileImageUrl: null,
    ),
  );

  /// API 요청의 `Authorization: Bearer` 헤더에 넣을 토큰입니다.
  ///
  /// 개인용 모드에서는 빈 문자열이며, Repository는 Authorization 헤더를 생략합니다.
  final String accessToken;

  /// 과거 refresh 흐름과의 호환을 위해 남겨둔 refresh token입니다.
  final String refreshToken;

  /// access token이 만료되기까지 남은 시간입니다.
  final int expiresIn;

  /// 현재 로컬 사용자 프로필입니다.
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

  /// 사용자 프로필 출처입니다. 개인용 모드에서는 `LOCAL`입니다.
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
