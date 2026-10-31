import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// 각 화면의 상단 제목 영역입니다.
///
/// 작은 eyebrow, 큰 제목, 우측 상태 칩을 같은 행에 배치해서
/// 홈/추천/보유/알림 화면이 모두 같은 정보 계층을 갖도록 합니다.
class SectionHeader extends StatelessWidget {
  /// 화면별 라벨, 제목, 우측 액션 위젯을 받습니다.
  const SectionHeader({
    super.key,
    required this.eyebrow,
    required this.title,
    required this.action,
  });

  /// 제목 위에 작게 표시되는 화면 분류 라벨입니다.
  final String eyebrow;

  /// 화면의 핵심 제목입니다.
  final String title;

  /// 상태 칩이나 카운터처럼 제목 오른쪽에 붙는 위젯입니다.
  final Widget action;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    final heading = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          eyebrow,
          style: TextStyle(
            color: palette.muted,
            fontSize: 12,
            fontWeight: FontWeight.w800,
            letterSpacing: 0,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          title,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: palette.text,
            fontSize: 27,
            height: 1.08,
            fontWeight: FontWeight.w900,
            letterSpacing: 0,
          ),
        ),
      ],
    );
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth < 520) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [heading, const SizedBox(height: 10), action],
          );
        }
        return Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(child: heading),
            const SizedBox(width: 12),
            action,
          ],
        );
      },
    );
  }
}
