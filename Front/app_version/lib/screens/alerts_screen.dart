import 'package:flutter/material.dart';

import '../models/app_alert.dart';
import '../theme/app_theme.dart';
import '../widgets/app_card.dart';
import '../widgets/app_text.dart';
import '../widgets/section_header.dart';
import '../widgets/status_chip.dart';
import 'dashboard_screen.dart';

/// 실시간 추천/시장 알림 목록 화면입니다.
///
/// FCM으로 받은 알림을 사용자가 나중에 다시 확인할 수 있게 하는 영역이며,
/// MVP에서는 매수 후보, 매도 검토, 시장 흐름 업데이트를 우선 표시합니다.
class AlertsScreen extends StatelessWidget {
  /// 알림 목록을 외부에서 주입받습니다.
  const AlertsScreen({super.key, required this.alerts});

  /// 최근 알림 데이터 목록입니다.
  final List<AppAlert> alerts;

  @override
  Widget build(BuildContext context) {
    return AppScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionHeader(
            eyebrow: '실시간 알림',
            title: '추천 신호',
            action: StatusChip(
              label: 'FCM',
              icon: Icons.notifications_rounded,
              gradient: AppGradients.main,
            ),
          ),
          const SizedBox(height: 18),
          for (final alert in alerts) ...[
            AlertItem(alert: alert),
            const SizedBox(height: 10),
          ],
          const SizedBox(height: 10),
        ],
      ),
    );
  }
}

/// 알림 리스트에서 한 개 알림을 카드로 표시하는 위젯입니다.
class AlertItem extends StatelessWidget {
  /// 알림 모델 하나를 받습니다.
  const AlertItem({super.key, required this.alert});

  /// 제목, 본문, 시간, 분류를 담은 알림 데이터입니다.
  final AppAlert alert;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final color = alertColor(alert.type);

    return AppCard(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: color.withValues(alpha: .14),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(alertIcon(alert.type), color: color),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(child: CardTitle(alert.title, fontSize: 17)),
                    TextCaption(alert.timeLabel),
                  ],
                ),
                const SizedBox(height: 6),
                Text(
                  alert.body,
                  style: TextStyle(
                    color: palette.text,
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    height: 1.35,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// 알림 타입에 맞는 Material 아이콘을 선택합니다.
IconData alertIcon(AppAlertType type) {
  switch (type) {
    case AppAlertType.sell:
      return Icons.sell_rounded;
    case AppAlertType.candidate:
      return Icons.add_chart_rounded;
    case AppAlertType.market:
      return Icons.public_rounded;
  }
}

/// 알림 타입에 맞는 브랜드 강조색을 선택합니다.
Color alertColor(AppAlertType type) {
  switch (type) {
    case AppAlertType.sell:
      return AppTheme.sub;
    case AppAlertType.candidate:
      return AppTheme.point;
    case AppAlertType.market:
      return AppTheme.main;
  }
}
