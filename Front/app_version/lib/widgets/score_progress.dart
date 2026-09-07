import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// 점수, 위험 한도, 분석 진행률처럼 선형 비율을 보여주는 공용 바입니다.
class ScoreProgress extends StatelessWidget {
  /// 0~1 사이 값과 선택적인 그라데이션 색상을 받습니다.
  const ScoreProgress({
    super.key,
    required this.value,
    this.colors = const [AppTheme.main, AppTheme.point],
  });

  /// 채워질 비율입니다. 예를 들어 `.87`이면 87%를 의미합니다.
  final double value;

  /// 채워지는 영역에 적용할 그라데이션 색상입니다.
  final List<Color> colors;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return ClipRRect(
      borderRadius: BorderRadius.circular(999),
      child: Container(
        height: 9,
        color: palette.isDark
            ? Colors.white.withValues(alpha: .09)
            : Colors.black.withValues(alpha: .08),
        child: FractionallySizedBox(
          alignment: Alignment.centerLeft,
          widthFactor: value.clamp(0, 1),
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(colors: colors),
              borderRadius: BorderRadius.circular(999),
            ),
          ),
        ),
      ),
    );
  }
}
