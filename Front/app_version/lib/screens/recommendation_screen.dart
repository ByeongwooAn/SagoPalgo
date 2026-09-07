import 'package:flutter/material.dart';

import '../models/recommendation.dart';
import '../theme/app_theme.dart';
import '../widgets/app_card.dart';
import '../widgets/app_text.dart';
import '../widgets/gradient_action_button.dart';
import '../widgets/score_ring.dart';
import '../widgets/section_header.dart';
import '../widgets/status_chip.dart';
import 'dashboard_screen.dart';

/// 매수 추천 상세 화면입니다.
///
/// 사용자가 AI 추천을 맹목적으로 따르지 않도록 점수, 진입 가격,
/// 손절 기준, 추천 사유, AI 설명을 한 화면에 함께 배치합니다.
class RecommendationScreen extends StatelessWidget {
  /// 화면에 표시할 대표 추천 데이터를 받습니다.
  const RecommendationScreen({super.key, required this.recommendation});

  /// Repository에서 받은 매수 추천 모델입니다.
  final InvestmentRecommendation recommendation;

  @override
  Widget build(BuildContext context) {
    return AppScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionHeader(
            eyebrow: '매수 추천',
            title: recommendation.stockName,
            action: StatusChip(
              label: recommendation.status,
              icon: Icons.bolt_rounded,
              gradient: AppGradients.point,
              darkText: true,
            ),
          ),
          const SizedBox(height: 18),
          ScoreDetailCard(recommendation: recommendation),
          const SizedBox(height: 12),
          RecommendationReasonCard(reasons: recommendation.reasons),
          const SizedBox(height: 12),
          AppCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const CardTitle('AI 설명'),
                const SizedBox(height: 8),
                TextBody(recommendation.aiSummary),
              ],
            ),
          ),
          const SizedBox(height: 12),
          const Row(
            children: [
              Expanded(
                child: GradientActionButton(
                  label: '관심 등록',
                  icon: Icons.star_rounded,
                  gradient: AppGradients.main,
                ),
              ),
              SizedBox(width: 10),
              Expanded(
                child: GradientActionButton(
                  label: '알림 켜기',
                  icon: Icons.notifications_active_rounded,
                  gradient: AppGradients.point,
                  darkText: true,
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
        ],
      ),
    );
  }
}

/// 추천 점수, 진입 가격, 손절 기준을 묶어서 보여주는 카드입니다.
class ScoreDetailCard extends StatelessWidget {
  /// 추천 모델을 받아 세부 지표를 표시합니다.
  const ScoreDetailCard({super.key, required this.recommendation});

  /// 추천 점수와 가격 정보를 담은 모델입니다.
  final InvestmentRecommendation recommendation;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      child: Column(
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const LabelText('AI 확률 점수'),
                    const SizedBox(height: 8),
                    Text(
                      '${recommendation.score}점',
                      style: const TextStyle(
                        color: AppTheme.point,
                        fontSize: 33,
                        fontWeight: FontWeight.w900,
                        letterSpacing: 0,
                      ),
                    ),
                  ],
                ),
              ),
              ScoreRing(score: recommendation.score, size: 110),
            ],
          ),
          const AppDivider(),
          Row(
            children: [
              Expanded(
                child: DetailMetric(
                  label: '진입 가격대',
                  value: '${formatCurrency(recommendation.entryPrice)}원',
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: DetailMetric(
                  label: '손절 기준',
                  value: formatSignedPercent(recommendation.stopLossRate),
                  color: AppTheme.sub,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// 라벨과 큰 수치를 세로로 배치하는 작은 지표 위젯입니다.
class DetailMetric extends StatelessWidget {
  /// 라벨, 값, 선택 강조색을 받습니다.
  const DetailMetric({
    super.key,
    required this.label,
    required this.value,
    this.color,
  });

  /// 지표 이름입니다.
  final String label;

  /// 사용자가 보는 지표 값입니다.
  final String value;

  /// 값에 적용할 선택 강조색입니다.
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        LabelText(label),
        const SizedBox(height: 6),
        FittedBox(
          fit: BoxFit.scaleDown,
          alignment: Alignment.centerLeft,
          child: Text(
            value,
            style: TextStyle(
              color: color ?? palette.text,
              fontSize: 24,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
        ),
      ],
    );
  }
}

/// RSI, MACD, 뉴스 등 추천 근거 목록을 표시하는 카드입니다.
class RecommendationReasonCard extends StatelessWidget {
  /// 추천 근거 리스트를 받습니다.
  const RecommendationReasonCard({super.key, required this.reasons});

  /// 점수에 반영된 추천 근거 목록입니다.
  final List<RecommendationReason> reasons;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      soft: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const CardTitle('추천 사유'),
          const SizedBox(height: 8),
          for (final reason in reasons)
            ReasonRow(
              label: reason.label,
              text: reason.description,
              color: reasonColor(reason.type),
            ),
        ],
      ),
    );
  }
}

/// 추천 근거 타입을 브랜드 색상에 매핑합니다.
Color reasonColor(RecommendationReasonType type) {
  switch (type) {
    case RecommendationReasonType.technical:
      return AppTheme.main;
    case RecommendationReasonType.trend:
      return AppTheme.sub;
    case RecommendationReasonType.news:
      return AppTheme.point;
  }
}

/// 추천 사유 한 줄을 라벨과 설명으로 보여주는 위젯입니다.
class ReasonRow extends StatelessWidget {
  /// 라벨, 설명, 강조색을 받습니다.
  const ReasonRow({
    super.key,
    required this.label,
    required this.text,
    required this.color,
  });

  /// 예: RSI, MACD, 뉴스.
  final String label;

  /// 추천 근거 설명 문장입니다.
  final String text;

  /// 라벨에 적용할 강조색입니다.
  final Color color;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: palette.border)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 52,
            child: Text(
              label,
              style: TextStyle(
                color: color,
                fontSize: 13,
                fontWeight: FontWeight.w900,
                letterSpacing: 0,
              ),
            ),
          ),
          Expanded(
            child: Text(
              text,
              style: TextStyle(
                color: palette.muted,
                fontSize: 13,
                height: 1.35,
                fontWeight: FontWeight.w700,
                letterSpacing: 0,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
