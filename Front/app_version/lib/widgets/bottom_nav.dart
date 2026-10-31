import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

const appDestinations = [
  (label: '홈', icon: Icons.home_rounded),
  (label: '추천', icon: Icons.auto_graph_rounded),
  (label: '보유', icon: Icons.pie_chart_rounded),
  (label: '소식', icon: Icons.dynamic_feed_rounded),
  (label: '알림', icon: Icons.notifications_rounded),
  (label: '모의', icon: Icons.science_rounded),
  (label: '설정', icon: Icons.settings_rounded),
];

class DesktopNav extends StatelessWidget {
  const DesktopNav({
    super.key,
    required this.selectedIndex,
    required this.onSelected,
  });
  final int selectedIndex;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return NavigationRail(
      extended: true,
      minExtendedWidth: 184,
      scrollable: true,
      backgroundColor: palette.surface.withValues(alpha: .8),
      indicatorColor: AppTheme.main.withValues(alpha: .16),
      selectedIndex: selectedIndex,
      onDestinationSelected: onSelected,
      selectedIconTheme: const IconThemeData(color: AppTheme.main),
      selectedLabelTextStyle: Theme.of(context).textTheme.labelLarge?.copyWith(
        color: AppTheme.main,
        fontWeight: FontWeight.w900,
      ),
      unselectedLabelTextStyle: Theme.of(context).textTheme.labelLarge
          ?.copyWith(color: palette.text, fontWeight: FontWeight.w700),
      destinations: [
        for (final destination in appDestinations)
          NavigationRailDestination(
            icon: Icon(destination.icon),
            label: Text(destination.label),
          ),
      ],
    );
  }
}

/// 앱 하단의 주요 탭 네비게이션입니다.
///
/// 홈, 추천, 보유, 소식, 알림, 모의매매는 개인 투자 흐름의 핵심이므로
/// 별도 위젯으로 분리해 화면 컨테이너가 네비게이션 구현 세부사항을 몰라도 되게 합니다.
class BottomNav extends StatelessWidget {
  /// 현재 선택된 탭과 탭 선택 콜백을 받습니다.
  const BottomNav({
    super.key,
    required this.selectedIndex,
    required this.onSelected,
  });

  /// 0부터 홈, 추천, 보유, 소식, 알림, 모의, 설정 탭 순서입니다.
  final int selectedIndex;

  /// 사용자가 탭을 누를 때 부모 화면으로 선택 인덱스를 전달합니다.
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return SafeArea(
      top: false,
      child: Container(
        margin: const EdgeInsets.fromLTRB(18, 0, 18, 12),
        padding: const EdgeInsets.all(7),
        decoration: BoxDecoration(
          color: palette.isDark
              ? const Color(0xff16121e).withValues(alpha: .94)
              : Colors.white.withValues(alpha: .94),
          borderRadius: BorderRadius.circular(22),
          border: Border.all(color: palette.border),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: palette.isDark ? .28 : .1),
              blurRadius: 24,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: Row(
          children: [
            for (final (index, destination) in appDestinations.indexed)
              _NavItem(
                label: destination.label,
                icon: destination.icon,
                active: selectedIndex == index,
                onTap: () => onSelected(index),
              ),
          ],
        ),
      ),
    );
  }
}

/// 하단 네비게이션 안의 단일 탭 버튼입니다.
class _NavItem extends StatelessWidget {
  /// 탭의 라벨, 아이콘, 선택 상태, 클릭 콜백을 받습니다.
  const _NavItem({
    required this.label,
    required this.icon,
    required this.active,
    required this.onTap,
  });

  /// 탭 아래에 표시되는 짧은 이름입니다.
  final String label;

  /// 탭의 목적을 나타내는 Material 아이콘입니다.
  final IconData icon;

  /// 현재 탭이 선택됐는지 여부입니다.
  final bool active;

  /// 사용자가 탭을 누르면 실행되는 콜백입니다.
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Expanded(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          height: 44,
          decoration: BoxDecoration(
            color: active ? AppTheme.main : Colors.transparent,
            borderRadius: BorderRadius.circular(16),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 18, color: active ? Colors.white : palette.text),
              const SizedBox(height: 2),
              Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: active ? Colors.white : palette.text,
                  fontSize: 10,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
