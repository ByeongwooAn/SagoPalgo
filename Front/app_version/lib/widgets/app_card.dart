import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// 앱 전체에서 반복되는 8px 반경 카드 컨테이너입니다.
///
/// 사고팔고의 화면은 정보 밀도가 높은 투자 앱이므로 카드 스타일을
/// 여기서 통일해 각 화면이 같은 여백, 테두리, 배경 규칙을 공유하게 합니다.
class AppCard extends StatelessWidget {
  /// 카드 내부 위젯과 선택적인 여백/강조 배경 여부를 받습니다.
  const AppCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.soft = false,
  });

  /// 카드 안에 렌더링할 실제 콘텐츠입니다.
  final Widget child;

  /// 카드 내부 여백입니다. 리스트 행처럼 낮은 높이가 필요할 때만 바꿉니다.
  final EdgeInsetsGeometry padding;

  /// true이면 추천 사유나 알림처럼 살짝 강조된 배경색을 사용합니다.
  final bool soft;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Container(
      width: double.infinity,
      padding: padding,
      decoration: BoxDecoration(
        color: soft ? palette.softSurface : palette.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: palette.border),
      ),
      child: child,
    );
  }
}
