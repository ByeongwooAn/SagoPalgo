import 'package:flutter/material.dart';

abstract final class AppLayout {
  static const maxContentWidth = 1280.0;
  static const desktopNavigationWidth = 1100.0;
}

/// 각 열의 높이를 강제하지 않고, 실제 콘텐츠 폭에 따라 나란히 또는 순서대로 표시합니다.
class AdaptiveColumns extends StatelessWidget {
  const AdaptiveColumns({
    super.key,
    required this.first,
    required this.second,
    this.breakpoint = 900,
    this.firstFlex = 1,
    this.secondFlex = 1,
  });
  final Widget first;
  final Widget second;
  final double breakpoint;
  final int firstFlex;
  final int secondFlex;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      if (constraints.maxWidth < breakpoint) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [first, const SizedBox(height: 12), second],
        );
      }
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(flex: firstFlex, child: first),
          const SizedBox(width: 16),
          Expanded(flex: secondFlex, child: second),
        ],
      );
    },
  );
}

/// 가변 높이의 카드 목록을 너비에 맞춰 배치합니다.
class AdaptiveCardGrid extends StatelessWidget {
  const AdaptiveCardGrid({
    super.key,
    required this.children,
    this.minCardWidth = 440,
  });
  final List<Widget> children;
  final double minCardWidth;
  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final columns = constraints.maxWidth >= minCardWidth * 2 + 12 ? 2 : 1;
      final width = (constraints.maxWidth - (columns - 1) * 12) / columns;
      return Wrap(
        spacing: 12,
        runSpacing: 12,
        children: [
          for (final child in children) SizedBox(width: width, child: child),
        ],
      );
    },
  );
}
