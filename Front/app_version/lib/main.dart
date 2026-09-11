import 'package:flutter/material.dart';

import 'config/app_environment.dart';
import 'models/auth_session.dart';
import 'repositories/auth_repository.dart';
import 'repositories/mock_auth_repository.dart';
import 'repositories/mock_investment_repository.dart';
import 'repositories/spring_investment_repository.dart';
import 'repositories/spring_auth_repository.dart';
import 'screens/login_screen.dart';
import 'screens/sago_palgo_home.dart';
import 'services/social_token_provider.dart';
import 'theme/app_theme.dart';

/// Flutter 애플리케이션의 시작점입니다.
///
/// Android에서 앱이 실행되면 가장 먼저 이 함수가 호출되고,
/// `SagoPalgoApp`을 Flutter 위젯 트리의 루트로 올립니다.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AppEnvironment.load();
  runApp(SagoPalgoApp.fromEnvironment());
}

/// 사고팔고 앱의 최상위 위젯입니다.
///
/// 이 위젯은 MaterialApp, 다크/라이트 테마, Repository 주입을 담당합니다.
/// 실제 화면 구현은 `SagoPalgoHome` 아래로 내려서 main 파일이 앱 조립만 맡도록 했습니다.
class SagoPalgoApp extends StatefulWidget {
  /// 테스트나 실제 API 연동 단계에서 인증 Repository를 교체할 수 있게 주입받습니다.
  const SagoPalgoApp({
    super.key,
    this.authRepository = const MockAuthRepository(),
    this.useMockInvestment = true,
  });

  /// `.env`에서 읽은 앱 설정에 따라 실제 사용할 인증 Repository를 결정합니다.
  ///
  /// 현재는 `SAGOPALGO_USE_MOCK_AUTH=true`일 때 Mock 로그인을 사용합니다.
  /// false일 때는 실제 Google/Naver 로그인 흐름을 사용하는 `SpringAuthRepository`를 주입합니다.
  factory SagoPalgoApp.fromEnvironment() {
    final environment = AppEnvironment.instance;
    if (environment.useMockAuth) {
      return SagoPalgoApp(useMockInvestment: environment.useMockInvestment);
    }

    return SagoPalgoApp(
      authRepository: SpringAuthRepository(
        tokenProvider: SdkSocialTokenProvider(environment),
      ),
      useMockInvestment: environment.useMockInvestment,
    );
  }

  /// Google/Naver 로그인과 refresh/logout을 처리하는 인증 Repository입니다.
  final AuthRepository authRepository;

  /// true이면 홈 화면 투자 데이터를 Mock Repository에서 불러옵니다.
  final bool useMockInvestment;

  @override
  State<SagoPalgoApp> createState() => _SagoPalgoAppState();
}

class _SagoPalgoAppState extends State<SagoPalgoApp> {
  /// 시스템 설정을 기본으로 따르되, 사용자가 상단 버튼을 누르면 명시적으로 바뀝니다.
  ThemeMode _themeMode = ThemeMode.system;

  /// 로그인 성공 후 앱이 보관하는 현재 인증 세션입니다.
  ///
  /// null이면 아직 로그인하지 않은 상태라 로그인 화면을 보여주고,
  /// 값이 있으면 기존 투자 대시보드 화면으로 진입합니다.
  AuthSession? _session;

  /// 현재 화면 밝기를 기준으로 반대 테마를 선택합니다.
  ///
  /// 다크모드에서는 라이트모드로, 라이트모드에서는 다크모드로 전환해
  /// A/B 시안을 앱 안에서 바로 비교할 수 있게 합니다.
  void _toggleTheme(Brightness brightness) {
    setState(() {
      _themeMode = brightness == Brightness.dark
          ? ThemeMode.light
          : ThemeMode.dark;
    });
  }

  /// 로그인 화면에서 인증에 성공했을 때 세션을 저장하고 홈 화면으로 전환합니다.
  void _handleSignedIn(AuthSession session) {
    setState(() {
      _session = session;
    });
  }

  /// 홈 화면에서 로그아웃을 누르면 서버 로그아웃을 요청한 뒤 로컬 세션을 비웁니다.
  ///
  /// Mock Repository에서는 즉시 성공하고, 실제 Repository에서는 Spring Boot의
  /// `/api/v1/auth/logout` API를 호출합니다.
  Future<void> _handleLogout() async {
    final session = _session;
    if (session != null) {
      await widget.authRepository.logout(session.accessToken);
    }

    setState(() {
      _session = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: '사고팔고',
      themeMode: _themeMode,
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      home: _session == null
          ? LoginScreen(
              authRepository: widget.authRepository,
              onSignedIn: _handleSignedIn,
              onThemeToggle: _toggleTheme,
            )
          : SagoPalgoHome(
              onThemeToggle: _toggleTheme,
              onLogout: _handleLogout,
              repository: widget.useMockInvestment
                  ? const MockInvestmentRepository()
                  : SpringInvestmentRepository(
                      accessToken: _session!.accessToken,
                    ),
              session: _session!,
            ),
    );
  }
}

/// 기존 Flutter 기본 테스트나 외부 import가 `MyApp`을 찾을 가능성을 고려한 별칭입니다.
///
/// 새 코드에서는 `SagoPalgoApp`을 직접 사용하는 것을 권장합니다.
@Deprecated('Use SagoPalgoApp instead.')
typedef MyApp = SagoPalgoApp;
