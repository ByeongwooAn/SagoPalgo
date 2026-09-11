import 'package:flutter/material.dart';

/// Google/Naver 소셜 로그인 버튼에서 사용하는 제공자 타입입니다.
enum SocialLoginProvider {
  /// Google ID token 기반 로그인을 의미합니다.
  google,

  /// Naver authorization code 기반 로그인을 의미합니다.
  naver,
}

/// 소셜 로그인 화면에서 반복 사용하는 로그인 버튼입니다.
///
/// 각 제공자별 색상과 라벨을 이 위젯 안에서 관리해서, 로그인 화면은 배치와 상태 처리에만 집중합니다.
class SocialLoginButton extends StatelessWidget {
  /// 버튼에 필요한 제공자, 로딩 상태, 클릭 콜백을 받습니다.
  const SocialLoginButton({
    super.key,
    required this.provider,
    required this.isLoading,
    required this.onPressed,
  });

  /// 어떤 소셜 로그인 버튼인지 나타냅니다.
  final SocialLoginProvider provider;

  /// 로그인 요청 중이면 버튼을 비활성화하고 진행 표시기를 보여줍니다.
  final bool isLoading;

  /// 사용자가 버튼을 눌렀을 때 실행할 로그인 콜백입니다.
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final isGoogle = provider == SocialLoginProvider.google;
    final backgroundColor = isGoogle ? Colors.white : const Color(0xff03c75a);
    final foregroundColor = isGoogle ? const Color(0xff1f1f1f) : Colors.white;
    final borderColor = isGoogle
        ? const Color(0xffd6d6d6)
        : const Color(0xff03c75a);

    return SizedBox(
      width: double.infinity,
      height: 56,
      child: FilledButton(
        onPressed: isLoading ? null : onPressed,
        style: FilledButton.styleFrom(
          backgroundColor: backgroundColor,
          foregroundColor: foregroundColor,
          disabledBackgroundColor: backgroundColor.withValues(alpha: .68),
          disabledForegroundColor: foregroundColor.withValues(alpha: .74),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
            side: BorderSide(color: borderColor),
          ),
          elevation: 0,
          textStyle: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w900,
            letterSpacing: 0,
          ),
        ),
        child: AnimatedSwitcher(
          duration: const Duration(milliseconds: 180),
          child: isLoading
              ? SizedBox(
                  key: const ValueKey('loading'),
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(
                    strokeWidth: 2.4,
                    color: foregroundColor,
                  ),
                )
              : Row(
                  key: const ValueKey('label'),
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    _ProviderMark(provider: provider),
                    const SizedBox(width: 10),
                    Text(isGoogle ? 'Google로 계속하기' : 'Naver로 계속하기'),
                  ],
                ),
        ),
      ),
    );
  }
}

/// 제공자 버튼 왼쪽에 표시하는 짧은 브랜드 마크입니다.
///
/// 실제 Google/Naver 가이드 이미지 자산을 추가하기 전까지 텍스트 마크를 사용합니다.
/// 다음 SDK/브랜드 리소스 적용 단계에서 이 위젯만 공식 이미지로 교체하면 됩니다.
class _ProviderMark extends StatelessWidget {
  /// 표시할 소셜 제공자를 받습니다.
  const _ProviderMark({required this.provider});

  /// Google 또는 Naver 제공자 타입입니다.
  final SocialLoginProvider provider;

  @override
  Widget build(BuildContext context) {
    final isGoogle = provider == SocialLoginProvider.google;

    return Container(
      width: 28,
      height: 28,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: isGoogle ? Colors.white : const Color(0xff03c75a),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(
          color: isGoogle ? const Color(0xffdadce0) : Colors.white,
        ),
      ),
      child: Text(
        isGoogle ? 'G' : 'N',
        style: TextStyle(
          color: isGoogle ? const Color(0xff4285f4) : Colors.white,
          fontSize: 15,
          fontWeight: FontWeight.w900,
          letterSpacing: 0,
        ),
      ),
    );
  }
}
