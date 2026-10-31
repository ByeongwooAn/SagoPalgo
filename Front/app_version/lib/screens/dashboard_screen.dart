import 'package:flutter/material.dart';

import '../models/investment_snapshot.dart';
import '../models/market_summary.dart';
import '../theme/app_theme.dart';
import '../widgets/app_card.dart';
import '../widgets/app_text.dart';
import '../widgets/market_bars.dart';
import '../widgets/score_progress.dart';
import '../widgets/score_ring.dart';
import '../widgets/section_header.dart';
import '../widgets/status_chip.dart';
import '../widgets/responsive_layout.dart';

/// 홈 대시보드 화면입니다.
///
/// 자본금, 시장 흐름, 뉴스 감성, 대표 추천 후보를 한눈에 보여줘
/// 사용자가 앱을 열자마자 오늘 판단해야 할 핵심 정보를 파악하게 합니다.
class DashboardScreen extends StatelessWidget {
  /// 전체 투자 스냅샷을 받아 홈 화면에 필요한 데이터만 골라 사용합니다.
  const DashboardScreen({
    super.key,
    required this.snapshot,
    required this.onCapitalSetupOpen,
    required this.onHoldingSetupOpen,
    this.onRefresh,
    this.watchlistCount,
    this.watchlistLoadFailed = false,
    this.onWatchlistSetupOpen,
    this.onAnalysisOpen,
    this.onSettingsOpen,
  });

  /// Repository가 내려준 시장/추천/보유/알림 데이터 묶음입니다.
  final InvestmentSnapshot snapshot;

  /// 자본금 수정 화면으로 이동하는 콜백입니다.
  final VoidCallback onCapitalSetupOpen;

  /// 보유 종목 추가 화면으로 이동하는 콜백입니다.
  final VoidCallback onHoldingSetupOpen;
  final VoidCallback? onRefresh;
  final int? watchlistCount;
  final bool watchlistLoadFailed;
  final VoidCallback? onWatchlistSetupOpen;
  final VoidCallback? onAnalysisOpen;
  final VoidCallback? onSettingsOpen;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final summary = snapshot.marketSummary;
    final recommendation = snapshot.recommendation;

    return AppScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionHeader(
            eyebrow: '사고팔고',
            title: palette.isDark ? 'AI 시장 관제' : '오늘의 투자 브리핑',
            action: IconButton(
              onPressed: onRefresh,
              tooltip: '대시보드 새로고침',
              icon: const Icon(Icons.refresh),
            ),
          ),
          const SizedBox(height: 18),
          if (summary.checkedAt != null)
            TextCaption(
              '화면 데이터 조회 ${summary.checkedAt!.toLocal().toString().split('.').first}',
            ),
          CapitalCard(
            capital: summary.availableCapital,
            monthlyReturnRate: summary.monthlyReturnRate,
            recommendedPositionRange: summary.recommendedPositionRange,
          ),
          if (snapshot.holdings.any((holding) => holding.priceFallback)) ...[
            const SizedBox(height: 8),
            const Text('일부 보유 종목의 시세를 확인하지 못해 수익률에 매수가 대체 평가가 포함되어 있습니다.'),
          ],
          if (_needsSetup) ...[
            const SizedBox(height: 12),
            DashboardSetupCard(
              onCapitalTap: onCapitalSetupOpen,
              onHoldingTap: onHoldingSetupOpen,
              capitalConfigured: summary.availableCapital > 0,
              hasHoldings: snapshot.holdings.isNotEmpty,
              watchlistCount: watchlistCount,
              watchlistLoadFailed: watchlistLoadFailed,
              analysisAvailable: recommendation != null,
              onWatchlistTap: onWatchlistSetupOpen,
              onAnalysisTap: onAnalysisOpen,
            ),
          ],
          const SizedBox(height: 12),
          AdaptiveColumns(
            breakpoint: 560,
            first: MetricCard(
              label: '코스피 흐름',
              value: summary.marketTrend,
              caption: summary.index?.value == null
                  ? summary.index?.message ?? '시장 지수 미연동'
                  : '${summary.index!.value!.toStringAsFixed(2)} · 전일 대비 ${formatSignedPercent(summary.index!.changeRate!)}',
              color: AppTheme.point,
            ),
            second: MetricCard(
              label: '뉴스 키워드',
              value: summary.newsSentiment,
              caption: summary.news == null
                  ? '저장 뉴스 없음'
                  : '${summary.news!.articleCount}건 · 긍정 ${summary.news!.positiveCount} · 부정 ${summary.news!.negativeCount}',
              color: AppTheme.sub,
            ),
          ),
          if (summary.news != null)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: TextCaption(summary.news!.method),
            ),
          if (summary.news?.latestPublishedAt != null)
            TextCaption(
              '최근 기사 발행 ${summary.news!.latestPublishedAt!.toLocal().toString().split('.').first}',
            ),
          const SizedBox(height: 12),
          AdaptiveColumns(
            first: CandidateCard(
              stockName: recommendation?.stockName,
              score: recommendation?.score,
              analysisLabel: recommendation == null
                  ? null
                  : recommendation.analysisContext == 'WATCHLIST'
                  ? '관심 종목 분석'
                  : '보유 종목 분석',
              analyzedAt: recommendation?.createdAt,
              reasonLine:
                  recommendation?.reasons
                      .map((reason) => reason.label)
                      .take(3)
                      .join(' + ') ??
                  '',
            ),
            second: MarketBarsCard(
              values: summary.marketBars,
              index: summary.index,
              onSettingsOpen: onSettingsOpen,
            ),
          ),
          const SizedBox(height: 20),
        ],
      ),
    );
  }

  bool get _needsSetup {
    return snapshot.marketSummary.availableCapital == 0 ||
        (snapshot.holdings.isEmpty && watchlistCount == 0) ||
        snapshot.recommendation == null;
  }
}

/// 모든 주요 화면에서 같은 스크롤 여백을 사용하기 위한 래퍼입니다.
class AppScrollView extends StatelessWidget {
  /// 스크롤 영역 안에 들어갈 화면별 콘텐츠를 받습니다.
  const AppScrollView({super.key, required this.child});

  /// 실제 화면 콘텐츠입니다.
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(
          constraints.maxWidth < 600 ? 16 : 24,
          10,
          constraints.maxWidth < 600 ? 16 : 24,
          24,
        ),
        physics: const BouncingScrollPhysics(),
        child: Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: const BoxConstraints(
              maxWidth: AppLayout.maxContentWidth,
            ),
            child: SizedBox(width: double.infinity, child: child),
          ),
        ),
      ),
    );
  }
}

/// 실제 데이터가 부족할 때 다음 설정 행동을 안내하는 카드입니다.
class DashboardSetupCard extends StatelessWidget {
  /// 포트폴리오 관리 탭으로 이동할 콜백을 받습니다.
  const DashboardSetupCard({
    super.key,
    required this.onCapitalTap,
    required this.onHoldingTap,
    this.capitalConfigured = false,
    this.hasHoldings = false,
    this.watchlistCount,
    this.watchlistLoadFailed = false,
    this.analysisAvailable = false,
    this.onWatchlistTap,
    this.onAnalysisTap,
  });

  final VoidCallback onCapitalTap;
  final VoidCallback onHoldingTap;
  final bool capitalConfigured;
  final bool hasHoldings;
  final int? watchlistCount;
  final bool watchlistLoadFailed;
  final bool analysisAvailable;
  final VoidCallback? onWatchlistTap;
  final VoidCallback? onAnalysisTap;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return AppCard(
      soft: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.playlist_add_check_rounded, color: AppTheme.main),
              SizedBox(width: 8),
              Expanded(child: CardTitle('실제 데이터 시작하기', fontSize: 20)),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '보유 주식 없이도 관심 종목으로 소식 수집과 분석을 시작할 수 있습니다. 자본금은 포트폴리오와 모의매매에 사용합니다.',
            style: TextStyle(
              color: palette.text,
              fontSize: 13,
              height: 1.4,
              fontWeight: FontWeight.w800,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 16,
            runSpacing: 6,
            children: [
              Text(capitalConfigured ? '✓ 자본금 설정됨' : '○ 자본금 미설정'),
              Text(
                hasHoldings
                    ? '✓ 보유 종목 등록됨'
                    : watchlistLoadFailed
                    ? '관심 목록 조회 실패'
                    : watchlistCount == null
                    ? '관심 목록 확인 중'
                    : watchlistCount! > 0
                    ? '✓ 관심 $watchlistCount종목 등록됨'
                    : '○ 등록 종목 없음',
              ),
              Text(analysisAvailable ? '✓ 저장 분석 있음' : '○ 분석 결과 없음'),
            ],
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              FilledButton.icon(
                onPressed: onCapitalTap,
                icon: const Icon(Icons.savings_rounded),
                label: Text(capitalConfigured ? '자본금 수정하기' : '자본금 설정하기'),
              ),
              OutlinedButton.icon(
                onPressed: onHoldingTap,
                icon: const Icon(Icons.add_rounded),
                label: const Text('보유 종목 추가하기'),
              ),
              if (onWatchlistTap != null)
                OutlinedButton.icon(
                  onPressed: onWatchlistTap,
                  icon: const Icon(Icons.star_border),
                  label: const Text('관심 종목 등록'),
                ),
              if (onAnalysisTap != null)
                OutlinedButton.icon(
                  onPressed: hasHoldings || (watchlistCount ?? 0) > 0
                      ? onAnalysisTap
                      : null,
                  icon: const Icon(Icons.auto_graph),
                  label: const Text('추천에서 분석하기'),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

/// 사용자 자본금과 종목당 권장 투자 범위를 보여주는 메인 카드입니다.
class CapitalCard extends StatelessWidget {
  /// 자본금, 월 수익률, 권장 투자 범위를 외부 데이터로 받습니다.
  const CapitalCard({
    super.key,
    required this.capital,
    required this.monthlyReturnRate,
    required this.recommendedPositionRange,
  });

  /// 사용자가 투자 가능하다고 설정한 자본금입니다.
  final int capital;

  /// 월간 포트폴리오 수익률입니다.
  final double monthlyReturnRate;

  /// 기획서의 리스크 관리 기준에 따른 종목당 투자 범위입니다.
  final String recommendedPositionRange;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(8),
        gradient: AppGradients.main,
        boxShadow: [
          BoxShadow(
            color: AppTheme.main.withValues(alpha: .18),
            blurRadius: 24,
            offset: const Offset(0, 16),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text(
                  '투자 가능 자본금',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0,
                  ),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: .18),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  '평가 ${formatSignedPercent(monthlyReturnRate)}',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 12,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              '${formatCurrency(capital)}원',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 34,
                fontWeight: FontWeight.w900,
                letterSpacing: 0,
              ),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '종목당 권장 투자금 $recommendedPositionRange',
            style: const TextStyle(
              color: Colors.white,
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

/// 시장 흐름이나 뉴스 감성처럼 짧은 지표를 보여주는 카드입니다.
class MetricCard extends StatelessWidget {
  /// 라벨, 값, 설명, 강조색을 받아 같은 카드 구조로 표시합니다.
  const MetricCard({
    super.key,
    required this.label,
    required this.value,
    required this.caption,
    required this.color,
  });

  /// 카드 상단의 작은 라벨입니다.
  final String label;

  /// 카드의 핵심 값입니다.
  final String value;

  /// 값 아래의 보조 설명입니다.
  final String caption;

  /// 핵심 값에 적용할 강조색입니다.
  final Color color;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return AppCard(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LabelText(label),
          const SizedBox(height: 8),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 24,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 3),
          Text(
            caption,
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

/// 홈 화면에서 대표 매수 후보를 압축해서 보여주는 카드입니다.
class CandidateCard extends StatelessWidget {
  /// 후보 종목명과 AI 점수를 받습니다.
  const CandidateCard({
    super.key,
    required this.stockName,
    required this.score,
    required this.reasonLine,
    this.analysisLabel,
    this.analyzedAt,
  });

  /// 대표 추천 후보 종목명입니다.
  final String? stockName;

  /// 대표 추천 후보의 AI 점수입니다.
  final int? score;

  /// 대표 추천 후보를 만든 핵심 근거 요약입니다.
  final String reasonLine;
  final String? analysisLabel;
  final DateTime? analyzedAt;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final candidateScore = score;

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const LabelText('최근 저장 분석'),
                    const SizedBox(height: 8),
                    CardTitle(stockName ?? '추천 데이터 없음', fontSize: 24),
                  ],
                ),
              ),
              if (candidateScore == null)
                const StatusChip(label: '대기', icon: Icons.hourglass_empty)
              else
                ScoreRing(score: candidateScore, size: 108),
            ],
          ),
          const SizedBox(height: 16),
          ScoreProgress(value: (candidateScore ?? 0) / 100),
          const SizedBox(height: 10),
          Text(
            reasonLine.isEmpty ? '보유 종목이나 추천 분석 결과가 아직 없습니다' : reasonLine,
            style: TextStyle(
              color: palette.text,
              fontSize: 13,
              fontWeight: FontWeight.w800,
              letterSpacing: 0,
            ),
          ),
          if (analysisLabel != null) ...[
            const SizedBox(height: 8),
            TextCaption(
              '$analysisLabel · ${analyzedAt == null ? '저장 시각 미제공' : analyzedAt!.toLocal().toString().split('.').first}',
            ),
          ],
        ],
      ),
    );
  }
}

/// 시장 지표 막대 그래프를 카드 안에 담아 보여주는 위젯입니다.
class MarketBarsCard extends StatelessWidget {
  /// 그래프로 표시할 시장 지표 값들을 받습니다.
  const MarketBarsCard({
    super.key,
    required this.values,
    this.index,
    this.onSettingsOpen,
  });

  /// 각 막대의 0~1 높이 값입니다.
  final List<double> values;
  final MarketIndexSummary? index;
  final VoidCallback? onSettingsOpen;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return AppCard(
      soft: true,
      child: Column(
        children: [
          Wrap(
            spacing: 12,
            runSpacing: 6,
            children: [
              const LabelText('코스피 · 최근 최대 20거래일 일봉'),
              TextCaption(
                index?.receivedAt == null
                    ? '시세 미확인'
                    : '${index!.provider} 조회 ${index!.receivedAt!.toLocal().toString().split('.').first}',
              ),
            ],
          ),
          const SizedBox(height: 18),
          if (values.isEmpty)
            SizedBox(
              height: 112,
              child: Center(
                child: Text(
                  index?.message ?? '연동된 시장 지표가 없습니다',
                  style: TextStyle(
                    color: palette.muted,
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0,
                  ),
                ),
              ),
            )
          else
            MarketBars(
              values: values,
              labels: index?.points
                  .map(
                    (point) =>
                        '${point.date.toString().split(' ').first} · ${point.close.toStringAsFixed(2)}',
                  )
                  .toList(),
            ),
          if (index != null && index!.points.isNotEmpty) ...[
            const SizedBox(height: 10),
            TextCaption(
              '${index!.points.first.date.toString().split(' ').first} ~ ${index!.points.last.date.toString().split(' ').first} · 구간 내 상대 높이(절대 지수 축 아님) · 당일은 진행값',
            ),
          ],
          if (values.isEmpty && onSettingsOpen != null)
            TextButton.icon(
              onPressed: onSettingsOpen,
              icon: const Icon(Icons.settings_outlined),
              label: const Text('연동 설정 확인'),
            ),
        ],
      ),
    );
  }
}

/// 정수 금액을 천 단위 쉼표가 있는 문자열로 바꿉니다.
String formatCurrency(int value) {
  return value.toString().replaceAllMapped(
    RegExp(r'\B(?=(\d{3})+(?!\d))'),
    (match) => ',',
  );
}

/// 수익률처럼 부호가 필요한 퍼센트 값을 `+3.8%` 형식으로 바꿉니다.
String formatSignedPercent(double value) {
  final sign = value > 0 ? '+' : '';
  return '$sign${value.toStringAsFixed(1)}%';
}
