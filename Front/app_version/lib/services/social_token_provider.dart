import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../config/app_environment.dart';

/// Naver callback으로 받은 authorization code 로그인 값입니다.
class NaverAuthorizationCode {
  /// code, state, redirectUri를 보관합니다.
  const NaverAuthorizationCode({
    required this.authorizationCode,
    required this.state,
    required this.redirectUri,
  });

  /// Naver callback query의 code 값입니다.
  final String authorizationCode;

  /// Naver authorization 요청과 callback을 매칭하는 CSRF 방지 값입니다.
  final String state;

  /// Naver Developers에 등록된 callback URL입니다.
  final String redirectUri;
}

/// Google/Naver SDK에서 provider token을 가져오는 책임을 분리한 인터페이스입니다.
///
/// Google은 공식 `google_sign_in` 패키지의 ID token을 가져오고, Naver는 브라우저 OAuth callback으로
/// 받은 authorization code를 가져와 백엔드 소셜 로그인 API에 전달합니다.
abstract class SocialTokenProvider {
  /// Google 로그인 성공 후 서버에 전달할 Google ID token을 반환합니다.
  Future<String> fetchGoogleIdToken();

  /// Naver 로그인 성공 후 서버에 전달할 authorization code 정보를 반환합니다.
  Future<NaverAuthorizationCode> fetchNaverAuthorizationCode();
}

/// Google/Naver SDK에서 실제 provider token을 가져오는 Provider입니다.
///
/// Google은 `google_sign_in`으로 ID token을 받고, Naver는 백엔드가 생성한 authorization URL을
/// Android 브라우저에 열어 callback code를 받습니다.
class SdkSocialTokenProvider implements SocialTokenProvider {
  /// `.env`에서 읽은 앱 환경 설정과 네이티브 채널을 주입받습니다.
  SdkSocialTokenProvider(
    this.environment, {
    ApiConfig? config,
    http.Client? client,
    this.naverChannel = _defaultNaverChannel,
    GoogleSignIn? googleSignIn,
  }) : config = config ?? ApiConfig(),
       client = client ?? http.Client(),
       googleSignIn = googleSignIn ?? GoogleSignIn.instance;

  static const MethodChannel _defaultNaverChannel = MethodChannel(
    'com.sagopalgo.app/naver_login',
  );

  /// Google/Naver 공개 client id를 제공하는 환경 설정입니다.
  final AppEnvironment environment;

  /// 백엔드 인증 API 주소입니다.
  final ApiConfig config;

  /// 백엔드에서 Naver authorization URL을 가져오는 HTTP 클라이언트입니다.
  final http.Client client;

  final MethodChannel naverChannel;
  final GoogleSignIn googleSignIn;
  Future<void>? _googleInitializeFuture;

  @override
  Future<String> fetchGoogleIdToken() async {
    final clientId = environment.googleServerClientId;
    if (clientId == null) {
      throw StateError(
        'SAGOPALGO_GOOGLE_SERVER_CLIENT_ID 또는 SAGOPALGO_GOOGLE_CLIENT_ID가 .env에 설정되어 있지 않습니다.',
      );
    }

    await _ensureGoogleInitialized(clientId);
    if (!googleSignIn.supportsAuthenticate()) {
      throw StateError('현재 플랫폼은 앱 버튼에서 Google 로그인을 시작할 수 없습니다.');
    }

    final account = await googleSignIn.authenticate();
    final idToken = account.authentication.idToken;
    if (idToken == null || idToken.trim().isEmpty) {
      throw StateError('Google ID token을 가져오지 못했습니다.');
    }

    return idToken;
  }

  @override
  Future<NaverAuthorizationCode> fetchNaverAuthorizationCode() async {
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) {
      throw StateError('Naver 로그인은 현재 Android 앱에서만 지원됩니다.');
    }

    final state = _secureState();
    final authorization = await _fetchNaverAuthorizationUrl(state: state);

    final callback = await naverChannel
        .invokeMapMethod<String, String>('authorize', <String, String>{
          'authorizationUrl': authorization.authorizationUrl,
          'redirectUri': authorization.redirectUri,
        });

    final authorizationCode = callback?['code'];
    final returnedState = callback?['state'];
    if (authorizationCode == null || authorizationCode.trim().isEmpty) {
      throw StateError('Naver authorization code를 가져오지 못했습니다.');
    }
    if (returnedState != state) {
      throw StateError('Naver 로그인 state가 일치하지 않습니다.');
    }

    return NaverAuthorizationCode(
      authorizationCode: authorizationCode,
      state: returnedState!,
      redirectUri: authorization.redirectUri,
    );
  }

  Future<void> _ensureGoogleInitialized(String clientId) {
    return _googleInitializeFuture ??= googleSignIn.initialize(
      serverClientId: clientId,
    );
  }

  Future<_NaverAuthorizationUrl> _fetchNaverAuthorizationUrl({
    required String state,
  }) async {
    final uri = Uri.parse(
      '${config.authBaseUrl}/naver/authorization-url',
    ).replace(queryParameters: <String, String>{'state': state});
    final response = await client.get(uri);
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    final success = decoded['success'] as bool? ?? false;
    if (response.statusCode < 200 || response.statusCode >= 300 || !success) {
      final error = decoded['error'] as Map<String, dynamic>?;
      throw StateError(
        error?['message'] as String? ?? 'Naver 로그인 URL 생성에 실패했습니다.',
      );
    }

    final data = decoded['data'] as Map<String, dynamic>;
    final authorizationUrl = data['authorizationUrl'] as String?;
    final redirectUri = data['redirectUri'] as String?;
    if (authorizationUrl == null || authorizationUrl.trim().isEmpty) {
      throw StateError('Naver 로그인 URL을 가져오지 못했습니다.');
    }
    if (redirectUri == null || redirectUri.trim().isEmpty) {
      throw StateError('Naver redirect URI를 가져오지 못했습니다.');
    }

    return _NaverAuthorizationUrl(
      authorizationUrl: authorizationUrl,
      redirectUri: redirectUri,
    );
  }

  String _secureState() {
    final random = Random.secure();
    final bytes = List<int>.generate(24, (_) => random.nextInt(256));
    return base64UrlEncode(bytes).replaceAll('=', '');
  }
}

class _NaverAuthorizationUrl {
  const _NaverAuthorizationUrl({
    required this.authorizationUrl,
    required this.redirectUri,
  });

  final String authorizationUrl;
  final String redirectUri;
}
