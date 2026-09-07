import 'package:flutter/material.dart';

import '../models/investment_snapshot.dart';
import '../theme/app_theme.dart';
import '../widgets/app_card.dart';
import '../widgets/app_text.dart';
import '../widgets/market_bars.dart';
import '../widgets/score_progress.dart';
import '../widgets/score_ring.dart';
import '../widgets/section_header.dart';
import '../widgets/status_chip.dart';

/// 홈 대시보드 화면입니다.
///
/// 자본금, 시장 흐름, 뉴스 감성, 대표 추천 후보를 한눈에 보여줘
/// 사용자가 앱을 열자마자 오늘 판단해야 할 핵심 정보를 파악하게 합니다.
class DashboardScreen extends StatelessWidget {
  /// 전체 투자 스냅샷을 받아 홈 화면에 필요한 데이터만 골라 사용합니다.
  const DashboardScreen({super.key, required this.snapshot});

  /// Repository가 내려준 시장/추천/보유/알림 데이터 묶음입니다.
  final InvestmentSnapshot snapshot;

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
            action: const StatusChip(
              label: 'AI 분석중',
              icon: Icons.auto_awesome_rounded,
              gradient: AppGradients.main,
            ),
          ),
          const SizedBox(height: 18),
          CapitalCard(
            capital: summary.availableCapital,
            monthlyReturnRate: summary.monthlyReturnRate,
            recommendedPositionRange: summary.recommendedPositionRange,
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: MetricCard(
                  label: '코스피 흐름',
                  value: summary.marketTrend,
                  caption: '시장 점수 ${summary.marketScore}',
                  color: AppTheme.point,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: MetricCard(
                  label: '뉴스 감성',
                  value: summary.newsSentiment,
                  caption: '호재 ${summary.positiveNewsCount}건',
                  color: AppTheme.sub,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          CandidateCard(
            stockName: recommendation.stockName,
            score: recommendation.score,
          ),
          const SizedBox(height: 12),
          MarketBarsCard(values: summary.marketBars),
          const SizedBox(height: 20),
        ],
      ),
    );
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
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 10, 20, 20),
      physics: const BouncingScrollPhysics(),
      child: child,
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
                  '월간 ${formatSignedPercent(monthlyReturnRate)}',
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
  });

  /// 대표 추천 후보 종목명입니다.
  final String stockName;

  /// 대표 추천 후보의 AI 점수입니다.
  final int score;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

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
                    const LabelText('실시간 후보'),
                    const SizedBox(height: 8),
                    CardTitle(stockName, fontSize: 24),
                  ],
                ),
              ),
              ScoreRing(score: score, size: 108),
            ],
          ),
          const SizedBox(height: 16),
          ScoreProgress(value: score / 100),
          const SizedBox(height: 10),
          Text(
            'RSI 과매도 탈출 + 거래량 2.1배 + 긍정 뉴스 증가',
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

/// 시장 지표 막대 그래프를 카드 안에 담아 보여주는 위젯입니다.
class MarketBarsCard extends StatelessWidget {
  /// 그래프로 표시할 시장 지표 값들을 받습니다.
  const MarketBarsCard({super.key, required this.values});

  /// 각 막대의 0~1 높이 값입니다.
  final List<double> values;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      soft: true,
      child: Column(
        children: [
          const Row(
            children: [
              Expanded(child: LabelText('시장 지표')),
              TextCaption('1분 전 업데이트'),
            ],
          ),
          const SizedBox(height: 18),
          MarketBars(values: values),
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
