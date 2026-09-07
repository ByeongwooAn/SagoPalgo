import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// 화면 상단이나 카드 내부에서 쓰는 작은 라벨 텍스트입니다.
class LabelText extends StatelessWidget {
  /// 표시할 라벨 문자열을 받습니다.
  const LabelText(this.text, {super.key});

  /// 실제 화면에 표시되는 라벨입니다.
  final String text;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Text(
      text,
      style: TextStyle(
        color: palette.muted,
        fontSize: 12,
        fontWeight: FontWeight.w800,
        letterSpacing: 0,
      ),
    );
  }
}

/// 보조 설명이나 시간 표시처럼 한 줄로 짧게 들어가는 텍스트입니다.
class TextCaption extends StatelessWidget {
  /// 표시할 보조 텍스트를 받습니다.
  const TextCaption(this.text, {super.key});

  /// 실제 화면에 표시되는 보조 문자열입니다.
  final String text;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Text(
      text,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: TextStyle(
        color: palette.muted,
        fontSize: 12,
        fontWeight: FontWeight.w700,
        letterSpacing: 0,
      ),
    );
  }
}

/// 카드 본문 설명에 사용하는 텍스트입니다.
class TextBody extends StatelessWidget {
  /// 여러 줄 설명 문장을 받습니다.
  const TextBody(this.text, {super.key});

  /// 실제 화면에 표시되는 본문입니다.
  final String text;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Text(
      text,
      style: TextStyle(
        color: palette.text,
        fontSize: 13,
        height: 1.36,
        fontWeight: FontWeight.w700,
        letterSpacing: 0,
      ),
    );
  }
}

/// 카드 안의 주요 제목에 사용하는 텍스트입니다.
class CardTitle extends StatelessWidget {
  /// 제목 문자열과 필요 시 폰트 크기를 받습니다.
  const CardTitle(this.text, {super.key, this.fontSize = 18});

  /// 실제 화면에 표시되는 제목입니다.
  final String text;

  /// 화면 밀도에 맞춰 조절할 수 있는 제목 크기입니다.
  final double fontSize;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Text(
      text,
      maxLines: 2,
      overflow: TextOverflow.ellipsis,
      style: TextStyle(
        color: palette.text,
        fontSize: fontSize,
        height: 1.12,
        fontWeight: FontWeight.w900,
        letterSpacing: 0,
      ),
    );
  }
}

/// 카드 내부 섹션을 분리하는 얇은 구분선입니다.
class AppDivider extends StatelessWidget {
  /// 별도 설정 없이 팔레트의 border 색을 사용합니다.
  const AppDivider({super.key});

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Container(
      height: 1,
      margin: const EdgeInsets.symmetric(vertical: 16),
      color: palette.border,
    );
  }
}
