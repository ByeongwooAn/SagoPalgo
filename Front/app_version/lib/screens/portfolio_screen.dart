import 'package:flutter/material.dart';

import '../models/holding.dart';
import '../theme/app_theme.dart';
import '../widgets/app_card.dart';
import '../widgets/app_text.dart';
import '../widgets/score_progress.dart';
import '../widgets/section_header.dart';
import '../widgets/status_chip.dart';
import 'dashboard_screen.dart';

/// 보유 종목과 리스크 상태를 보여주는 화면입니다.
///
/// 기획서에서 "수익보다 생존이 우선"이라고 정의했기 때문에,
/// 단순 수익률뿐 아니라 손절 감시, 부분 익절, 위험 한도 사용률을 함께 보여줍니다.
class PortfolioScreen extends StatelessWidget {
  /// 포트폴리오 요약과 보유 종목 리스트를 받습니다.
  const PortfolioScreen({
    super.key,
    required this.capital,
    required this.summary,
    required this.holdings,
    required this.portfolioFuture,
    required this.onRetry,
  });

  /// 대시보드 스냅샷에서 즉시 표시할 자본금 설정입니다.
  final CapitalSettings capital;

  /// 전체 평가 손익과 위험 한도 사용률입니다.
  final PortfolioSummary summary;

  /// 사용자가 보유한 종목 목록입니다.
  final List<Holding> holdings;

  /// 자본금/보유 종목 API에서 다시 불러오는 최신 포트폴리오 데이터입니다.
  final Future<PortfolioSnapshot> portfolioFuture;

  /// 최신 포트폴리오 데이터 요청이 실패했을 때 다시 시도하는 콜백입니다.
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<PortfolioSnapshot>(
      future: portfolioFuture,
      builder: (context, snapshot) {
        final portfolio =
            snapshot.data ??
            PortfolioSnapshot(
              capital: capital,
              summary: summary,
              holdings: holdings,
            );

        return _PortfolioContent(
          portfolio: portfolio,
          isRefreshing: snapshot.connectionState != ConnectionState.done,
          hasRefreshError: snapshot.hasError,
          onRetry: onRetry,
        );
      },
    );
  }
}

class _PortfolioContent extends StatelessWidget {
  const _PortfolioContent({
    required this.portfolio,
    required this.isRefreshing,
    required this.hasRefreshError,
    required this.onRetry,
  });

  final PortfolioSnapshot portfolio;
  final bool isRefreshing;
  final bool hasRefreshError;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final holdings = portfolio.holdings;

    return AppScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionHeader(
            eyebrow: '보유 종목',
            title: '손익과 리스크',
            action: StatusChip(
              label: '${holdings.length}종목',
              icon: Icons.account_balance_wallet_rounded,
            ),
          ),
          const SizedBox(height: 18),
          if (isRefreshing || hasRefreshError) ...[
            PortfolioSyncBanner(
              isRefreshing: isRefreshing,
              hasRefreshError: hasRefreshError,
              onRetry: onRetry,
            ),
            const SizedBox(height: 12),
          ],
          CapitalRuleSummaryCard(capital: portfolio.capital),
          const SizedBox(height: 12),
          ProfitCard(summary: portfolio.summary),
          const SizedBox(height: 12),
          for (final holding in holdings) ...[
            PortfolioRow(holding: holding),
            const SizedBox(height: 10),
          ],
          const SellAlertCard(),
          const SizedBox(height: 12),
          RiskRuleCard(riskUsageRate: portfolio.summary.riskUsageRate),
          const SizedBox(height: 20),
        ],
      ),
    );
  }
}

/// 포트폴리오 최신화 상태를 짧게 알려주는 배너입니다.
class PortfolioSyncBanner extends StatelessWidget {
  /// 로딩/오류 상태와 재시도 콜백을 받습니다.
  const PortfolioSyncBanner({
    super.key,
    required this.isRefreshing,
    required this.hasRefreshError,
    required this.onRetry,
  });

  final bool isRefreshing;
  final bool hasRefreshError;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return AppCard(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      soft: true,
      child: Row(
        children: [
          if (isRefreshing)
            const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          else
            const Icon(Icons.cloud_off_rounded, color: AppTheme.sub, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              isRefreshing ? '최신 포트폴리오를 동기화하는 중입니다' : '최신 포트폴리오 동기화에 실패했습니다',
              style: TextStyle(
                color: palette.text,
                fontSize: 13,
                fontWeight: FontWeight.w800,
                letterSpacing: 0,
              ),
            ),
          ),
          if (hasRefreshError)
            TextButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh_rounded, size: 18),
              label: const Text('재시도'),
            ),
        ],
      ),
    );
  }
}

/// 자본금과 종목당 권장 투자 범위를 보여주는 카드입니다.
class CapitalRuleSummaryCard extends StatelessWidget {
  /// 사용자의 자본금 설정을 받습니다.
  const CapitalRuleSummaryCard({super.key, required this.capital});

  final CapitalSettings capital;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const LabelText('자본금 기준'),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: _CapitalMetric(
                  label: '투자 가능',
                  value: '${formatCurrency(capital.availableCapital)}원',
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _CapitalMetric(
                  label: '1회 손실 한도',
                  value:
                      '${(capital.riskPerTradeRate * 100).toStringAsFixed(1)}%',
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            '종목당 권장 투자금 ${_positionRange(capital)}',
            style: TextStyle(
              color: palette.text,
              fontSize: 13,
              fontWeight: FontWeight.w800,
              letterSpacing: 0,
            ),
          ),
        ],
      ),
    );
  }

  String _positionRange(CapitalSettings capital) {
    if (capital.recommendedMinPosition == 0 &&
        capital.recommendedMaxPosition == 0) {
      return '동기화 후 표시';
    }

    return '${formatCurrency(capital.recommendedMinPosition)}~${formatCurrency(capital.recommendedMaxPosition)}원';
  }
}

class _CapitalMetric extends StatelessWidget {
  const _CapitalMetric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextCaption(label),
        const SizedBox(height: 4),
        FittedBox(
          fit: BoxFit.scaleDown,
          alignment: Alignment.centerLeft,
          child: Text(
            value,
            style: TextStyle(
              color: palette.text,
              fontSize: 20,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
        ),
      ],
    );
  }
}

/// 보유 종목 전체 평가 손익을 보여주는 카드입니다.
class ProfitCard extends StatelessWidget {
  /// 포트폴리오 전체 요약 데이터를 받습니다.
  const ProfitCard({super.key, required this.summary});

  /// 평가 손익, 수익률, 최대 허용 손실을 담은 모델입니다.
  final PortfolioSummary summary;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Expanded(child: LabelText('총 평가 손익')),
              StatusChip(label: '목표 5%', darkText: true),
            ],
          ),
          const SizedBox(height: 12),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              '${formatSignedCurrency(summary.totalProfit)}원',
              style: const TextStyle(
                color: AppTheme.point,
                fontSize: 34,
                fontWeight: FontWeight.w900,
                letterSpacing: 0,
              ),
            ),
          ),
          const SizedBox(height: 6),
          Text(
            '수익률 ${formatSignedPercent(summary.profitRate)} · 최대 허용 손실 ${formatCurrency(summary.maxAllowedLoss)}원',
            style: TextStyle(
              color: palette.text,
              fontSize: 13,
              fontWeight: FontWeight.w700,
              letterSpacing: 0,
            ),
          ),
        ],
      ),
    );
  }
}

/// 보유 종목 리스트의 단일 행입니다.
class PortfolioRow extends StatelessWidget {
  /// 한 종목의 보유 정보를 받습니다.
  const PortfolioRow({super.key, required this.holding});

  /// 매수가, 수량, 수익률, 상태를 가진 보유 종목 모델입니다.
  final Holding holding;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final changeColor = holding.profitRate < 0
        ? AppTheme.sub
        : holding.profitRate >= 5
        ? AppTheme.point
        : AppTheme.main;

    return AppCard(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  holding.stockName,
                  style: TextStyle(
                    color: palette.text,
                    fontSize: 18,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 4),
                TextCaption(
                  '매수가 ${formatCurrency(holding.buyPrice)} · ${holding.quantity}주',
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                formatSignedPercent(holding.profitRate),
                style: TextStyle(
                  color: changeColor,
                  fontSize: 16,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0,
                ),
              ),
              const SizedBox(height: 4),
              TextCaption(holding.status),
            ],
          ),
        ],
      ),
    );
  }
}

/// 매도 검토 알림을 보유 화면 안에서 강조하는 카드입니다.
class SellAlertCard extends StatelessWidget {
  /// 현재는 대표 예시 메시지를 보여주고, 이후 매도 추천 API 응답으로 교체합니다.
  const SellAlertCard({super.key});

  @override
  Widget build(BuildContext context) {
    return AppCard(
      soft: true,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                LabelText('실시간 알림'),
                SizedBox(height: 6),
                CardTitle('매도 검토', fontSize: 24),
                SizedBox(height: 8),
                TextBody('삼성전자 현재 수익률 +9%. 목표 수익 도달로 부분 익절을 추천합니다.'),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: AppTheme.sub,
              borderRadius: BorderRadius.circular(999),
            ),
            child: const Text(
              'FCM',
              style: TextStyle(
                color: Colors.white,
                fontSize: 12,
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

/// 오늘 사용한 위험 한도를 보여주는 리스크 관리 카드입니다.
class RiskRuleCard extends StatelessWidget {
  /// 0~1 사이 위험 한도 사용률을 받습니다.
  const RiskRuleCard({super.key, required this.riskUsageRate});

  /// 오늘 사용한 위험 한도 비율입니다.
  final double riskUsageRate;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const LabelText('리스크 규칙'),
          const SizedBox(height: 12),
          ScoreProgress(
            value: riskUsageRate,
            colors: const [AppTheme.sub, AppTheme.point],
          ),
          const SizedBox(height: 8),
          Text(
            '오늘 사용한 위험 한도 ${(riskUsageRate * 100).round()}%',
            style: TextStyle(
              color: palette.text,
              fontSize: 13,
              fontWeight: FontWeight.w800,
              letterSpacing: 0,
            ),
          ),
        ],
      ),
    );
  }
}

/// 금액을 천 단위 쉼표와 부호가 포함된 문자열로 바꿉니다.
String formatSignedCurrency(int value) {
  final sign = value > 0 ? '+' : '';
  return '$sign${formatCurrency(value)}';
}
