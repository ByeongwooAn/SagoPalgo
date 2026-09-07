import 'package:flutter/material.dart';

/// 추천 화면에서 사용하는 그라데이션 액션 버튼입니다.
///
/// 아직 API 연결 전이라 실제 클릭 로직은 없지만, 버튼 자체를 위젯으로
/// 분리해 두면 관심 등록/알림 설정 API를 붙일 때 `onTap`만 추가하면 됩니다.
class GradientActionButton extends StatelessWidget {
  /// 버튼의 표시 문구, 아이콘, 배경 그라데이션을 받습니다.
  const GradientActionButton({
    super.key,
    required this.label,
    required this.icon,
    required this.gradient,
    this.darkText = false,
  });

  /// 버튼에 표시되는 명령 문구입니다.
  final String label;

  /// 버튼의 의미를 빠르게 보여주는 아이콘입니다.
  final IconData icon;

  /// 브랜드 컬러 기반 배경 그라데이션입니다.
  final Gradient gradient;

  /// 밝은 배경 버튼일 때 글자색을 어둡게 바꾸는 옵션입니다.
  final bool darkText;

  @override
  Widget build(BuildContext context) {
    final foreground = darkText ? const Color(0xff21120a) : Colors.white;

    return Container(
      height: 48,
      decoration: BoxDecoration(
        gradient: gradient,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, color: foreground, size: 18),
          const SizedBox(width: 7),
          Flexible(
            child: Text(
              label,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: foreground,
                fontSize: 15,
                fontWeight: FontWeight.w900,
                letterSpacing: 0,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
