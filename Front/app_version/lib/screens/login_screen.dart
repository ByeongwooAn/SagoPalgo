import 'package:flutter/material.dart';

import '../models/auth_session.dart';
import '../repositories/auth_repository.dart';
import '../theme/app_theme.dart';
import '../widgets/social_login_button.dart';

/// 앱 진입 시 가장 먼저 표시되는 소셜 로그인 화면입니다.
///
/// 이메일/비밀번호 가입을 제거한 백엔드 정책에 맞춰 Google과 Naver 로그인 버튼만 제공합니다.
/// 로그인 성공 시 백엔드가 발급한 사고팔고 JWT 세션을 앱 루트로 전달합니다.
class LoginScreen extends StatefulWidget {
  /// 인증 Repository, 로그인 성공 콜백, 테마 전환 콜백을 주입받습니다.
  const LoginScreen({
    super.key,
    required this.authRepository,
    required this.onSignedIn,
    required this.onThemeToggle,
  });

  /// Google/Naver 로그인 요청을 처리하는 Repository입니다.
  final AuthRepository authRepository;

  /// 로그인 성공 후 앱 루트에 AuthSession을 전달하는 콜백입니다.
  final ValueChanged<AuthSession> onSignedIn;

  /// 로그인 화면에서도 다크/라이트 시안을 전환할 수 있게 하는 콜백입니다.
  final ValueChanged<Brightness> onThemeToggle;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  /// 현재 어떤 제공자의 로그인 요청이 진행 중인지 저장합니다.
  ///
  /// null이면 아무 요청도 진행 중이 아니고, 값이 있으면 해당 버튼만 로딩 상태로 표시합니다.
  SocialLoginProvider? _loadingProvider;

  /// 로그인 실패 시 화면 하단에 보여줄 오류 메시지입니다.
  String? _errorMessage;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final isDark = palette.isDark;

    return Scaffold(
      body: Container(
        decoration: BoxDecoration(gradient: palette.pageGradient),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 18, 24, 24),
            child: Column(
              children: [
                _LoginTopBar(
                  isDark: isDark,
                  onThemeToggle: () =>
                      widget.onThemeToggle(Theme.of(context).brightness),
                ),
                Expanded(
                  child: Center(
                    child: SingleChildScrollView(
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 420),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            const _BrandMark(),
                            const SizedBox(height: 26),
                            _LoginHeadline(isDark: isDark),
                            const SizedBox(height: 34),
                            SocialLoginButton(
                              provider: SocialLoginProvider.google,
                              isLoading:
                                  _loadingProvider ==
                                  SocialLoginProvider.google,
                              onPressed: () => _signIn(
                                SocialLoginProvider.google,
                                widget.authRepository.loginWithGoogle,
                              ),
                            ),
                            const SizedBox(height: 12),
                            SocialLoginButton(
                              provider: SocialLoginProvider.naver,
                              isLoading:
                                  _loadingProvider == SocialLoginProvider.naver,
                              onPressed: () => _signIn(
                                SocialLoginProvider.naver,
                                widget.authRepository.loginWithNaver,
                              ),
                            ),
                            const SizedBox(height: 18),
                            _AuthPolicyText(errorMessage: _errorMessage),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// 지정된 소셜 제공자 로그인 함수를 실행하고 성공 시 세션을 앱 루트로 전달합니다.
  ///
  /// @param provider 로딩 표시를 적용할 소셜 제공자입니다.
  /// @param loginAction 실제 로그인 요청을 수행하는 Repository 메서드입니다.
  Future<void> _signIn(
    SocialLoginProvider provider,
    Future<AuthSession> Function() loginAction,
  ) async {
    setState(() {
      _loadingProvider = provider;
      _errorMessage = null;
    });

    try {
      final session = await loginAction();
      if (!mounted) {
        return;
      }

      widget.onSignedIn(session);
    } catch (error) {
      if (!mounted) {
        return;
      }

      setState(() {
        _errorMessage = error.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _loadingProvider = null;
        });
      }
    }
  }
}

/// 로그인 화면 상단의 브랜드/테마 전환 바입니다.
class _LoginTopBar extends StatelessWidget {
  /// 현재 테마와 전환 콜백을 받습니다.
  const _LoginTopBar({required this.isDark, required this.onThemeToggle});

  /// true이면 현재 다크모드입니다.
  final bool isDark;

  /// 사용자가 테마 버튼을 누를 때 실행됩니다.
  final VoidCallback onThemeToggle;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Row(
      children: [
        Expanded(
          child: Text(
            '사고팔고',
            style: TextStyle(
              color: palette.text,
              fontSize: 22,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
        ),
        IconButton.filledTonal(
          onPressed: onThemeToggle,
          tooltip: isDark ? '라이트모드로 전환' : '다크모드로 전환',
          icon: Icon(isDark ? Icons.light_mode : Icons.dark_mode),
        ),
      ],
    );
  }
}

/// 로그인 화면 중앙에 표시하는 사고팔고 브랜드 심볼입니다.
class _BrandMark extends StatelessWidget {
  /// 별도 상태가 없는 장식 요소라 const 생성자를 사용합니다.
  const _BrandMark();

  @override
  Widget build(BuildContext context) {
    return Align(
      child: Container(
        width: 86,
        height: 86,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: AppGradients.point,
          boxShadow: [
            BoxShadow(
              color: AppTheme.sub.withValues(alpha: .28),
              blurRadius: 28,
              offset: const Offset(0, 16),
            ),
          ],
        ),
        child: const Icon(
          Icons.auto_graph_rounded,
          size: 42,
          color: Colors.white,
        ),
      ),
    );
  }
}

/// 로그인 화면의 제목과 보조 문구입니다.
class _LoginHeadline extends StatelessWidget {
  /// 현재 테마에 맞춰 문구 톤을 조금 다르게 보여주기 위해 다크모드 여부를 받습니다.
  const _LoginHeadline({required this.isDark});

  /// 다크모드 여부입니다.
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Column(
      children: [
        Text(
          'AI 투자 판단을\n소셜 로그인으로 빠르게 시작하세요',
          textAlign: TextAlign.center,
          style: TextStyle(
            color: palette.text,
            fontSize: 28,
            height: 1.22,
            fontWeight: FontWeight.w900,
            letterSpacing: 0,
          ),
        ),
        const SizedBox(height: 12),
        Text(
          isDark ? '다크 콘솔 모드로 시장 신호를 확인합니다' : '라이트 어시스턴트 모드로 투자 흐름을 정리합니다',
          textAlign: TextAlign.center,
          style: TextStyle(
            color: palette.muted,
            fontSize: 14,
            height: 1.45,
            fontWeight: FontWeight.w700,
            letterSpacing: 0,
          ),
        ),
      ],
    );
  }
}

/// 로그인 화면 하단의 인증 안내와 오류 메시지 영역입니다.
class _AuthPolicyText extends StatelessWidget {
  /// 오류 메시지가 있으면 안내 문구 대신 오류를 강조해서 보여줍니다.
  const _AuthPolicyText({required this.errorMessage});

  /// 로그인 실패 시 표시할 메시지입니다.
  final String? errorMessage;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final hasError = errorMessage != null;

    return Text(
      hasError ? errorMessage! : 'Google 또는 Naver 계정으로만 사고팔고를 이용할 수 있습니다.',
      textAlign: TextAlign.center,
      style: TextStyle(
        color: hasError ? AppTheme.sub : palette.muted,
        fontSize: 12,
        height: 1.4,
        fontWeight: FontWeight.w700,
        letterSpacing: 0,
      ),
    );
  }
}
