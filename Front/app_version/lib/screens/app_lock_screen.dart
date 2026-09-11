import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// 개인용 Windows 프로그램의 선택형 로컬 잠금 화면입니다.
class AppLockScreen extends StatefulWidget {
  /// 잠금 해제에 사용할 PIN과 성공 콜백을 받습니다.
  const AppLockScreen({
    super.key,
    required this.pin,
    required this.onUnlocked,
    required this.onThemeToggle,
  });

  /// 로컬 설정에서 읽은 앱 잠금 PIN입니다.
  final String pin;

  /// PIN이 맞았을 때 홈 화면 진입을 알리는 콜백입니다.
  final VoidCallback onUnlocked;

  /// 잠금 화면에서도 테마를 바꿀 수 있게 루트 콜백을 받습니다.
  final ValueChanged<Brightness> onThemeToggle;

  @override
  State<AppLockScreen> createState() => _AppLockScreenState();
}

class _AppLockScreenState extends State<AppLockScreen> {
  final TextEditingController _pinController = TextEditingController();
  String? _errorMessage;

  @override
  void dispose() {
    _pinController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final isDark = palette.isDark;

    return Scaffold(
      body: Container(
        decoration: BoxDecoration(gradient: palette.pageGradient),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              children: [
                Align(
                  alignment: Alignment.centerRight,
                  child: IconButton.filledTonal(
                    onPressed: () =>
                        widget.onThemeToggle(Theme.of(context).brightness),
                    tooltip: isDark ? '라이트모드로 전환' : '다크모드로 전환',
                    icon: Icon(isDark ? Icons.light_mode : Icons.dark_mode),
                  ),
                ),
                const Spacer(),
                Icon(
                  Icons.lock_rounded,
                  size: 48,
                  color: isDark ? AppTheme.point : AppTheme.main,
                ),
                const SizedBox(height: 18),
                Text(
                  'SagoPalgo 잠금',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: palette.text,
                    fontSize: 26,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  '개인 투자 데이터를 보려면 PIN을 입력하세요.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: palette.muted,
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 26),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 360),
                  child: TextField(
                    controller: _pinController,
                    autofocus: true,
                    obscureText: true,
                    keyboardType: TextInputType.number,
                    textInputAction: TextInputAction.done,
                    onSubmitted: (_) => _unlock(),
                    decoration: InputDecoration(
                      labelText: 'PIN',
                      errorText: _errorMessage,
                      prefixIcon: const Icon(Icons.pin_rounded),
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 360),
                  child: SizedBox(
                    width: double.infinity,
                    height: 52,
                    child: FilledButton.icon(
                      onPressed: _unlock,
                      icon: const Icon(Icons.lock_open_rounded),
                      label: const Text('잠금 해제'),
                    ),
                  ),
                ),
                const Spacer(flex: 2),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _unlock() {
    if (_pinController.text == widget.pin) {
      widget.onUnlocked();
      return;
    }

    setState(() {
      _errorMessage = 'PIN이 일치하지 않습니다.';
    });
  }
}
