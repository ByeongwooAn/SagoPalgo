import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/auth_session.dart';
import '../services/social_token_provider.dart';
import 'auth_repository.dart';

/// Spring Boot 백엔드 인증 API와 실제로 통신하는 Repository입니다.
///
/// 이 클래스는 Google/Naver SDK에서 받은 provider token을 `/api/v1/auth/google`,
/// `/api/v1/auth/naver`로 전달하고, 백엔드가 발급한 사고팔고 JWT 세션을 앱 모델로 변환합니다.
class SpringAuthRepository implements AuthRepository {
  /// API 설정, HTTP 클라이언트, 소셜 토큰 Provider를 외부에서 주입받습니다.
  SpringAuthRepository({
    required this.tokenProvider,
    ApiConfig? config,
    http.Client? client,
  }) : config = config ?? ApiConfig(),
       client = client ?? http.Client();

  /// 백엔드 기본 URL과 인증 경로 설정입니다.
  final ApiConfig config;

  /// HTTP 요청을 실제로 보내는 클라이언트입니다.
  final http.Client client;

  /// Google/Naver SDK에서 provider token을 가져오는 객체입니다.
  final SocialTokenProvider tokenProvider;

  @override
  Future<AuthSession> loginWithGoogle() async {
    final providerToken = await tokenProvider.fetchGoogleIdToken();
    return _postAuthSession('/google', {'providerToken': providerToken});
  }

  @override
  Future<AuthSession> loginWithNaver() async {
    final providerToken = await tokenProvider.fetchNaverAccessToken();
    return _postAuthSession('/naver', {'providerToken': providerToken});
  }

  @override
  Future<AuthSession> refresh(String refreshToken) {
    return _postAuthSession('/refresh', {'refreshToken': refreshToken});
  }

  @override
  Future<void> logout(String accessToken) async {
    final response = await client.post(
      Uri.parse('${config.authBaseUrl}/logout'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $accessToken',
      },
    );

    _ensureSuccess(response);
  }

  /// 인증 API에 POST 요청을 보내고 성공 응답의 data를 AuthSession으로 변환합니다.
  ///
  /// @param path `/google`, `/naver`, `/refresh` 중 하나의 인증 하위 경로입니다.
  /// @param body 백엔드에 JSON으로 보낼 요청 본문입니다.
  /// @return 백엔드가 내려준 사고팔고 인증 세션입니다.
  Future<AuthSession> _postAuthSession(
    String path,
    Map<String, String> body,
  ) async {
    final response = await client.post(
      Uri.parse('${config.authBaseUrl}$path'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );

    _ensureSuccess(response);

    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    return AuthSession.fromJson(decoded['data'] as Map<String, dynamic>);
  }

  /// 공통 API 응답의 성공 여부를 확인하고 실패하면 예외를 던집니다.
  ///
  /// 백엔드는 실패 시 `{ success: false, error: { code, message } }` 형태를 내려주므로,
  /// 앱에서는 여기서 메시지를 추출해 로그인 화면 오류 문구로 사용할 수 있습니다.
  void _ensureSuccess(http.Response response) {
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    final success = decoded['success'] as bool? ?? false;
    if (response.statusCode >= 200 && response.statusCode < 300 && success) {
      return;
    }

    final error = decoded['error'] as Map<String, dynamic>?;
    final message = error?['message'] as String? ?? '인증 요청에 실패했습니다.';
    throw AuthRepositoryException(message);
  }
}

/// 인증 Repository에서 화면으로 전달하는 실패 예외입니다.
class AuthRepositoryException implements Exception {
  /// 사용자에게 보여줄 수 있는 오류 메시지를 받습니다.
  const AuthRepositoryException(this.message);

  /// 로그인 화면에 표시할 오류 메시지입니다.
  final String message;

  @override
  String toString() => message;
}
