import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// 추천 상태, AI 분석중, 종목 수처럼 짧은 상태를 보여주는 칩입니다.
class StatusChip extends StatelessWidget {
  /// 라벨, 아이콘, 그라데이션 여부를 받아 다양한 상태 표현에 재사용합니다.
  const StatusChip({
    super.key,
    required this.label,
    this.icon,
    this.gradient,
    this.darkText = false,
  });

  /// 칩 안에 표시되는 짧은 상태 문구입니다.
  final String label;

  /// 상태를 더 빠르게 인지하도록 돕는 선택 아이콘입니다.
  final IconData? icon;

  /// 브랜드 강조가 필요한 칩에 적용할 그라데이션입니다.
  final Gradient? gradient;

  /// 포인트 그라데이션처럼 밝은 배경 위에 어두운 글자를 써야 할 때 사용합니다.
  final bool darkText;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final foreground = gradient == null
        ? palette.text
        : darkText
        ? const Color(0xff21120a)
        : Colors.white;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 8),
      decoration: BoxDecoration(
        color: gradient == null
            ? (palette.isDark
                  ? Colors.white.withValues(alpha: .08)
                  : AppTheme.point.withValues(alpha: .14))
            : null,
        gradient: gradient,
        borderRadius: BorderRadius.circular(999),
        border: gradient == null ? Border.all(color: palette.border) : null,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 14, color: foreground),
            const SizedBox(width: 5),
          ],
          Text(
            label,
            style: TextStyle(
              color: foreground,
              fontSize: 12,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
        ],
      ),
    );
  }
}
