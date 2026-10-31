import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// 홈 화면의 시장 지표를 간단한 막대 그래프로 표현하는 위젯입니다.
class MarketBars extends StatelessWidget {
  /// 각 막대의 0~1 사이 높이 값을 받습니다.
  const MarketBars({super.key, required this.values, this.labels});

  /// 코스피, 나스닥, 업종, 거래량 등 시장 지표를 요약한 값들입니다.
  final List<double> values;
  final List<String>? labels;

  @override
  Widget build(BuildContext context) {
    final colors = [AppTheme.main, AppTheme.sub, AppTheme.point];

    return SizedBox(
      height: 112,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          for (var index = 0; index < values.length; index++)
            MarketBar(
              height: values[index],
              color: colors[index % colors.length],
              label: labels != null && index < labels!.length
                  ? labels![index]
                  : null,
            ),
        ],
      ),
    );
  }
}

/// `MarketBars` 안에서 실제 막대 하나를 그리는 위젯입니다.
class MarketBar extends StatelessWidget {
  /// 막대 높이 비율과 색상을 받습니다.
  const MarketBar({
    super.key,
    required this.height,
    required this.color,
    this.label,
  });

  /// 부모 높이 대비 막대가 차지하는 비율입니다.
  final double height;

  /// 막대에 적용할 브랜드 색상입니다.
  final Color color;
  final String? label;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Tooltip(
        message: label ?? '',
        child: Align(
          alignment: Alignment.bottomCenter,
          child: FractionallySizedBox(
            heightFactor: height.clamp(0, 1),
            child: Container(
              margin: const EdgeInsets.symmetric(horizontal: 5),
              decoration: BoxDecoration(
                color: color,
                borderRadius: const BorderRadius.vertical(
                  top: Radius.circular(8),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
