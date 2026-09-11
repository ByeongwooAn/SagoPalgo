import 'package:flutter/material.dart';

import '../models/recommendation.dart';
import '../repositories/watchlist_repository.dart';
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
class RecommendationScreen extends StatefulWidget {
  /// 화면에 표시할 대표 추천 데이터를 받습니다.
  const RecommendationScreen({
    super.key,
    required this.recommendation,
    required this.watchlistRepository,
    required this.onCapitalSetupOpen,
    required this.onHoldingSetupOpen,
  });

  /// Repository에서 받은 매수 추천 모델입니다.
  final InvestmentRecommendation? recommendation;

  /// 관심 종목 등록과 알림 설정 액션을 처리하는 Repository입니다.
  final WatchlistRepository watchlistRepository;

  /// 자본금 수정 화면으로 이동하는 콜백입니다.
  final VoidCallback onCapitalSetupOpen;

  /// 보유 종목 추가 화면으로 이동하는 콜백입니다.
  final VoidCallback onHoldingSetupOpen;

  @override
  State<RecommendationScreen> createState() => _RecommendationScreenState();
}

class _RecommendationScreenState extends State<RecommendationScreen> {
  bool _addingWatchlist = false;
  bool _enablingAlert = false;

  @override
  Widget build(BuildContext context) {
    final recommendation = widget.recommendation;
    if (recommendation == null) {
      return _EmptyRecommendationState(
        onCapitalTap: widget.onCapitalSetupOpen,
        onHoldingTap: widget.onHoldingSetupOpen,
      );
    }

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
          Row(
            children: [
              Expanded(
                child: GradientActionButton(
                  label: '관심 등록',
                  icon: Icons.star_rounded,
                  gradient: AppGradients.main,
                  busy: _addingWatchlist,
                  onTap: _addingWatchlist || _enablingAlert
                      ? null
                      : _addRecommendation,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: GradientActionButton(
                  label: '알림 켜기',
                  icon: Icons.notifications_active_rounded,
                  gradient: AppGradients.point,
                  darkText: true,
                  busy: _enablingAlert,
                  onTap: _addingWatchlist || _enablingAlert
                      ? null
                      : _enableAlert,
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
        ],
      ),
    );
  }

  Future<void> _addRecommendation() async {
    await _runAction(
      setBusy: (busy) => _addingWatchlist = busy,
      action: () =>
          widget.watchlistRepository.addRecommendation(widget.recommendation!),
    );
  }

  Future<void> _enableAlert() async {
    await _runAction(
      setBusy: (busy) => _enablingAlert = busy,
      action: () =>
          widget.watchlistRepository.enableAlert(widget.recommendation!),
    );
  }

  Future<void> _runAction({
    required ValueChanged<bool> setBusy,
    required Future<WatchlistActionResult> Function() action,
  }) async {
    setState(() => setBusy(true));

    try {
      final result = await action();
      if (!mounted) {
        return;
      }
      _showMessage(result.message);
    } catch (error) {
      if (!mounted) {
        return;
      }
      _showMessage(error.toString());
    } finally {
      if (mounted) {
        setState(() => setBusy(false));
      }
    }
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }
}

class _EmptyRecommendationState extends StatelessWidget {
  const _EmptyRecommendationState({
    required this.onCapitalTap,
    required this.onHoldingTap,
  });

  final VoidCallback onCapitalTap;
  final VoidCallback onHoldingTap;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return AppScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionHeader(
            eyebrow: '매수 추천',
            title: '추천 데이터 없음',
            action: StatusChip(label: '대기', icon: Icons.hourglass_empty),
          ),
          const SizedBox(height: 18),
          AppCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(
                      Icons.info_outline_rounded,
                      color: AppTheme.main,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        '아직 서버에 추천할 실제 데이터가 없습니다. 자본금과 보유 종목을 등록하면 실제 계정 데이터 기준으로 추천 판단이 표시됩니다.',
                        style: TextStyle(
                          color: palette.text,
                          fontSize: 14,
                          height: 1.4,
                          fontWeight: FontWeight.w800,
                          letterSpacing: 0,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: onCapitalTap,
                    icon: const Icon(Icons.savings_rounded),
                    label: const Text('자본금 설정하기'),
                  ),
                ),
                const SizedBox(height: 8),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    onPressed: onHoldingTap,
                    icon: const Icon(Icons.add_rounded),
                    label: const Text('보유 종목 추가하기'),
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
