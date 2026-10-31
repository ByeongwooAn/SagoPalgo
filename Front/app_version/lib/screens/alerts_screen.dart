import 'package:flutter/material.dart';

import '../models/app_alert.dart';
import '../services/alert_delivery_service.dart';
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
  const AlertsScreen({
    super.key,
    required this.alerts,
    this.deliveryStatus,
    this.onRefresh,
    this.onAlertTap,
    this.fetchError,
    this.checkedAt,
  });

  /// 최근 알림 데이터 목록입니다.
  final List<AppAlert> alerts;

  final AlertDeliveryStatus? deliveryStatus;

  final Future<void> Function()? onRefresh;

  final ValueChanged<AppAlert>? onAlertTap;
  final String? fetchError;
  final DateTime? checkedAt;

  @override
  Widget build(BuildContext context) {
    return AppScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionHeader(
            eyebrow: '실시간 알림',
            title: '추천 신호',
            action: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const StatusChip(
                  label: 'Windows',
                  icon: Icons.notifications_active_rounded,
                  gradient: AppGradients.main,
                ),
                const SizedBox(width: 4),
                IconButton(
                  onPressed: onRefresh,
                  tooltip: '알림 새로고침',
                  icon: const Icon(Icons.refresh_rounded),
                ),
              ],
            ),
          ),
          if (deliveryStatus != null) ...[
            const SizedBox(height: 12),
            _DeliveryStatusLine(status: deliveryStatus!),
          ],
          const SizedBox(height: 18),
          if (fetchError != null) ...[
            Text(
              fetchError!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
            const SizedBox(height: 12),
          ],
          if (checkedAt != null)
            TextCaption(
              '알림 목록 조회 ${checkedAt!.toLocal().toString().split('.').first}',
            ),
          const TextCaption(
            '추천 알림은 관심 종목의 알림 설정과 분석 결과 조건을 따릅니다. 전달 상태는 알림 목록 조회 상태와 별도입니다.',
          ),
          const SizedBox(height: 12),
          if (alerts.isEmpty && fetchError == null)
            const _EmptyAlerts()
          else if (alerts.isEmpty)
            const Text('알림 목록을 확인할 수 없습니다.')
          else
            for (final alert in alerts) ...[
              AlertItem(alert: alert, onTap: () => onAlertTap?.call(alert)),
              const SizedBox(height: 10),
            ],
          const SizedBox(height: 10),
        ],
      ),
    );
  }
}

class _DeliveryStatusLine extends StatelessWidget {
  const _DeliveryStatusLine({required this.status});

  final AlertDeliveryStatus status;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final hasIssue =
        status.checkFailed ||
        status.failedCount > 0 ||
        status.unconfirmedCount > 0;
    final label = status.checkedAt == null
        ? '전달 상태 확인 전'
        : status.checkFailed
        ? '전달 상태 확인 실패'
        : hasIssue
        ? '전달 재시도 중'
        : '전달 상태 정상';
    final details = <String>[
      if (status.unconfirmedCount > 0)
        '전달 기록 확인 대기 ${status.unconfirmedCount}건',
      if (status.failedCount > 0) '이번 점검 실패 ${status.failedCount}건',
    ];
    final checkedAt = status.checkedAt;
    final timeLabel = checkedAt == null
        ? null
        : '${checkedAt.hour.toString().padLeft(2, '0')}:${checkedAt.minute.toString().padLeft(2, '0')}';

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(
          status.checkedAt == null
              ? Icons.schedule_rounded
              : hasIssue
              ? Icons.sync_problem_rounded
              : Icons.check_circle_outline_rounded,
          size: 18,
          color: hasIssue ? Theme.of(context).colorScheme.error : palette.muted,
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            [label, ...details].join(' · '),
            style: TextStyle(
              color: hasIssue ? palette.text : palette.muted,
              fontSize: 12,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        if (timeLabel != null) ...[
          const SizedBox(width: 8),
          Text(timeLabel, style: TextStyle(color: palette.muted, fontSize: 12)),
        ],
      ],
    );
  }
}

/// 알림 리스트에서 한 개 알림을 카드로 표시하는 위젯입니다.
class AlertItem extends StatelessWidget {
  /// 알림 모델 하나를 받습니다.
  const AlertItem({super.key, required this.alert, this.onTap});

  /// 제목, 본문, 시간, 분류를 담은 알림 데이터입니다.
  final AppAlert alert;

  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final color = alertColor(alert.type);

    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: AppCard(
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
                      if (!alert.isRead) ...[
                        Container(
                          width: 7,
                          height: 7,
                          decoration: BoxDecoration(
                            color: color,
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 7),
                      ],
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
      ),
    );
  }
}

class _EmptyAlerts extends StatelessWidget {
  const _EmptyAlerts();

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 48),
      child: Center(
        child: Column(
          children: [
            Icon(
              Icons.notifications_none_rounded,
              color: palette.muted,
              size: 36,
            ),
            const SizedBox(height: 12),
            Text(
              '새로운 투자 알림이 없습니다',
              style: TextStyle(
                color: palette.text,
                fontSize: 16,
                fontWeight: FontWeight.w800,
                letterSpacing: 0,
              ),
            ),
          ],
        ),
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
    case AppAlertType.price:
      return Icons.price_change_rounded;
    case AppAlertType.news:
      return Icons.newspaper_rounded;
    case AppAlertType.disclosure:
      return Icons.description_rounded;
    case AppAlertType.portfolio:
      return Icons.account_balance_wallet_rounded;
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
    case AppAlertType.price:
      return AppTheme.point;
    case AppAlertType.news:
      return Colors.teal;
    case AppAlertType.disclosure:
      return Colors.indigo;
    case AppAlertType.portfolio:
      return AppTheme.sub;
  }
}
