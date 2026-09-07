import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// 추천 점수를 원형 그래프로 보여주는 위젯입니다.
///
/// 기획서의 점수 시스템이 앱의 핵심이므로 숫자만 나열하지 않고,
/// 사용자가 80점 이상 강한 매수 구간을 즉시 인식하도록 링 형태로 강조합니다.
class ScoreRing extends StatelessWidget {
  /// 점수와 원형 위젯 크기를 받습니다.
  const ScoreRing({super.key, required this.score, required this.size});

  /// 0~100 사이 추천 점수입니다.
  final int score;

  /// 원형 점수 위젯의 가로/세로 크기입니다.
  final double size;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        painter: ScoreRingPainter(
          score: score,
          trackColor: palette.isDark
              ? const Color(0xff332a3c)
              : const Color(0xffeee7f3),
        ),
        child: Center(
          child: Text(
            '$score',
            style: TextStyle(
              color: palette.text,
              fontSize: size * .29,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
        ),
      ),
    );
  }
}

/// `ScoreRing`의 실제 원형 그래프를 그리는 CustomPainter입니다.
///
/// Flutter 기본 위젯만으로는 시안의 원형 점수 느낌을 정확히 만들기 어려워
/// Canvas에 배경 트랙과 점수 아크를 직접 그립니다.
class ScoreRingPainter extends CustomPainter {
  /// 점수와 배경 트랙 색상을 받아 그림을 결정합니다.
  ScoreRingPainter({required this.score, required this.trackColor});

  /// 원형 아크로 표현할 추천 점수입니다.
  final int score;

  /// 다크/라이트 테마에 따라 달라지는 배경 트랙 색상입니다.
  final Color trackColor;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 8;
    final stroke = size.width * .16;
    final rect = Rect.fromCircle(center: center, radius: radius);

    /// 먼저 전체 100점 기준의 희미한 배경 트랙을 그립니다.
    final trackPaint = Paint()
      ..color = trackColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke
      ..strokeCap = StrokeCap.butt;

    /// 그 위에 실제 점수만큼 브랜드 포인트 그라데이션 아크를 그립니다.
    final scorePaint = Paint()
      ..shader = const SweepGradient(
        colors: [AppTheme.point, AppTheme.sub, AppTheme.point],
      ).createShader(rect)
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke
      ..strokeCap = StrokeCap.butt;

    canvas.drawCircle(center, radius, trackPaint);
    canvas.drawArc(
      rect,
      -math.pi / 2,
      math.pi * 2 * (score / 100),
      false,
      scorePaint,
    );
  }

  @override
  bool shouldRepaint(covariant ScoreRingPainter oldDelegate) {
    /// 점수나 테마 트랙 색상이 바뀔 때만 다시 그리면 됩니다.
    return score != oldDelegate.score || trackColor != oldDelegate.trackColor;
  }
}
