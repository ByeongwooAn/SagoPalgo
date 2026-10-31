import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/paper_trading.dart';
import '../models/recommendation.dart';
import '../repositories/paper_trading_repository.dart';
import '../theme/app_theme.dart';
import '../widgets/app_card.dart';
import '../widgets/app_text.dart';
import '../widgets/section_header.dart';
import '../widgets/status_chip.dart';
import 'dashboard_screen.dart';

/// 실제 주문과 완전히 분리된 AI 신호 기반 모의매매 화면입니다.
class PaperTradingScreen extends StatefulWidget {
  const PaperTradingScreen({
    super.key,
    required this.repository,
    required this.recommendation,
    required this.active,
    this.onCapitalSetupOpen,
    this.availableCapital,
  });

  final PaperTradingRepository repository;
  final InvestmentRecommendation? recommendation;
  final bool active;
  final VoidCallback? onCapitalSetupOpen;
  final int? availableCapital;

  @override
  State<PaperTradingScreen> createState() => _PaperTradingScreenState();
}

class _PaperTradingScreenState extends State<PaperTradingScreen> {
  Future<PaperTradingSnapshot>? _snapshotFuture;
  bool _submitting = false;

  @override
  void initState() {
    super.initState();
    if (widget.active) {
      _load();
    }
  }

  @override
  void didUpdateWidget(covariant PaperTradingScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.active &&
        (!oldWidget.active ||
            oldWidget.repository != widget.repository ||
            oldWidget.availableCapital != widget.availableCapital)) {
      _load();
    }
  }

  void _load() {
    setState(() {
      _snapshotFuture = widget.repository.fetchSnapshot();
    });
  }

  @override
  Widget build(BuildContext context) {
    final future = _snapshotFuture;
    if (!widget.active && future == null) {
      return const SizedBox.shrink();
    }

    return FutureBuilder<PaperTradingSnapshot>(
      future: future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError || !snapshot.hasData) {
          return _PaperTradingError(
            message: _errorMessage(snapshot.error),
            onRetry: _load,
            onCapitalSetupOpen: _capitalRequired(snapshot.error)
                ? widget.onCapitalSetupOpen
                : null,
          );
        }
        return _buildContent(snapshot.data!);
      },
    );
  }

  Widget _buildContent(PaperTradingSnapshot snapshot) {
    return AppScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionHeader(
            eyebrow: '가상 체결',
            title: 'AI 모의매매',
            action: const StatusChip(
              label: 'PAPER',
              icon: Icons.science_rounded,
            ),
          ),
          const SizedBox(height: 18),
          _SummaryCard(summary: snapshot.summary),
          const SizedBox(height: 8),
          const TextCaption(
            '현재 설정 자본금 기준입니다. 자본금을 변경하면 모의 현금·수익률도 재산정되며 거래 기록은 유지됩니다.',
          ),
          const SizedBox(height: 12),
          _RecommendationAction(
            recommendation: widget.recommendation,
            submitting: _submitting,
            onBuy: _buyFromRecommendation,
          ),
          const SizedBox(height: 18),
          _SubsectionTitle(
            title: '보유 포지션',
            count: snapshot.positions.length,
            onRefresh: _load,
          ),
          const SizedBox(height: 10),
          if (snapshot.positions.isEmpty)
            const _EmptyCard(
              icon: Icons.inventory_2_outlined,
              title: '보유 중인 모의 포지션이 없습니다',
              description: '최신 AI 매수 신호를 이용해 실제 주문 없이 전략을 검증할 수 있습니다.',
            )
          else
            ...snapshot.positions.map(
              (position) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: _PositionCard(
                  position: position,
                  submitting: _submitting,
                  onSell: () => _sellPosition(position),
                ),
              ),
            ),
          const SizedBox(height: 8),
          _SubsectionTitle(title: '체결 이력', count: snapshot.trades.length),
          const SizedBox(height: 10),
          if (snapshot.trades.isEmpty)
            const _EmptyCard(
              icon: Icons.receipt_long_outlined,
              title: '아직 체결 이력이 없습니다',
              description: '모의 체결 결과는 실제 증권사 주문이나 계좌 잔고에 영향을 주지 않습니다.',
            )
          else
            ...snapshot.trades.map(
              (trade) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: _TradeCard(trade: trade),
              ),
            ),
          const SizedBox(height: 20),
        ],
      ),
    );
  }

  Future<void> _buyFromRecommendation() async {
    final recommendation = widget.recommendation;
    final recommendationId = recommendation?.recommendationId;
    if (recommendation == null || recommendationId == null) {
      _showMessage('저장된 AI 매수 신호가 필요합니다.');
      return;
    }
    final quantity = await _showQuantityDialog(
      title: '${recommendation.stockName} 모의매수',
      actionLabel: '모의매수',
    );
    if (quantity == null || !mounted) return;
    await _submit(
      () => widget.repository.buyFromRecommendation(recommendationId, quantity),
      '${recommendation.stockName} 모의매수가 체결되었습니다.',
    );
  }

  Future<void> _sellPosition(PaperPosition position) async {
    final quantity = await _showQuantityDialog(
      title: '${position.stockName} 모의매도',
      actionLabel: '모의매도',
      maxQuantity: position.quantity,
    );
    if (quantity == null || !mounted) return;
    await _submit(
      () => widget.repository.sellPosition(
        stockCode: position.stockCode,
        market: position.market,
        quantity: quantity,
      ),
      '${position.stockName} 모의매도가 체결되었습니다.',
    );
  }

  Future<void> _submit(
    Future<PaperTradingSnapshot> Function() action,
    String successMessage,
  ) async {
    setState(() => _submitting = true);
    try {
      final result = await action();
      if (!mounted) return;
      setState(() {
        _snapshotFuture = Future.value(result);
      });
      _showMessage(successMessage);
    } catch (error) {
      if (mounted) _showMessage(_errorMessage(error));
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<double?> _showQuantityDialog({
    required String title,
    required String actionLabel,
    double? maxQuantity,
  }) async {
    return showDialog<double>(
      context: context,
      builder: (context) => _QuantityDialog(
        title: title,
        actionLabel: actionLabel,
        maxQuantity: maxQuantity,
      ),
    );
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }
}

class _QuantityDialog extends StatefulWidget {
  const _QuantityDialog({
    required this.title,
    required this.actionLabel,
    required this.maxQuantity,
  });

  final String title;
  final String actionLabel;
  final double? maxQuantity;

  @override
  State<_QuantityDialog> createState() => _QuantityDialogState();
}

class _QuantityDialogState extends State<_QuantityDialog> {
  final TextEditingController _controller = TextEditingController();
  String? _validationMessage;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.title),
      content: TextField(
        controller: _controller,
        autofocus: true,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        inputFormatters: [
          FilteringTextInputFormatter.allow(RegExp(r'^\d*\.?\d{0,4}')),
        ],
        decoration: InputDecoration(
          labelText: '수량',
          suffixText: '주',
          errorText: _validationMessage,
          helperText: widget.maxQuantity == null
              ? '서버가 확인한 현재가로 가상 체결됩니다.'
              : '최대 ${_formatQuantity(widget.maxQuantity!)}주',
        ),
        onSubmitted: (_) => _submit(),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('취소'),
        ),
        FilledButton(onPressed: _submit, child: Text(widget.actionLabel)),
      ],
    );
  }

  void _submit() {
    final quantity = double.tryParse(_controller.text.trim());
    if (quantity == null ||
        quantity <= 0 ||
        (widget.maxQuantity != null && quantity > widget.maxQuantity!)) {
      setState(() => _validationMessage = '가능한 수량을 입력해 주세요.');
      return;
    }
    Navigator.of(context).pop(quantity);
  }
}

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({required this.summary});

  final PaperTradingSummary summary;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final profitColor = _profitColor(summary.totalProfit, palette);
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const LabelText('모의 총자산'),
          const SizedBox(height: 6),
          Text(
            '${_formatMoney(summary.totalAsset)}원',
            style: TextStyle(
              color: palette.text,
              fontSize: 28,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            '${_formatSignedMoney(summary.totalProfit)}원  ${formatSignedPercent(summary.returnRate)}',
            style: TextStyle(
              color: profitColor,
              fontSize: 14,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
          const AppDivider(),
          LayoutBuilder(
            builder: (context, constraints) {
              final width = (constraints.maxWidth - 12) / 2;
              return Wrap(
                spacing: 12,
                runSpacing: 14,
                children: [
                  _Metric(
                    width: width,
                    label: '현금',
                    value: '${_formatMoney(summary.cashBalance)}원',
                  ),
                  _Metric(
                    width: width,
                    label: '평가액',
                    value: '${_formatMoney(summary.openPositionValue)}원',
                  ),
                  _Metric(
                    width: width,
                    label: '실현 손익',
                    value: '${_formatSignedMoney(summary.realizedProfit)}원',
                  ),
                  _Metric(
                    width: width,
                    label: '평가 손익',
                    value: '${_formatSignedMoney(summary.unrealizedProfit)}원',
                  ),
                  _Metric(
                    width: width,
                    label: '승률',
                    value:
                        '${summary.winRate.toStringAsFixed(1)}% · ${summary.completedTrades}회',
                  ),
                  _Metric(
                    width: width,
                    label: '최대 단일 손실',
                    value: '${_formatMoney(summary.maxLoss)}원',
                  ),
                  _Metric(
                    width: width,
                    label: '회전율',
                    value: '${summary.turnoverRate.toStringAsFixed(1)}%',
                  ),
                  _Metric(
                    width: width,
                    label: '설정 자본',
                    value: '${_formatMoney(summary.initialCapital)}원',
                  ),
                ],
              );
            },
          ),
        ],
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({
    required this.width,
    required this.label,
    required this.value,
  });

  final double width;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return SizedBox(
      width: width,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LabelText(label),
          const SizedBox(height: 3),
          Text(
            value,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: palette.text,
              fontSize: 14,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
        ],
      ),
    );
  }
}

class _RecommendationAction extends StatelessWidget {
  const _RecommendationAction({
    required this.recommendation,
    required this.submitting,
    required this.onBuy,
  });

  final InvestmentRecommendation? recommendation;
  final bool submitting;
  final VoidCallback onBuy;

  @override
  Widget build(BuildContext context) {
    final item = recommendation;
    final canBuy =
        item?.recommendationId != null &&
        item?.recommendationType.toUpperCase() == 'BUY';
    return AppCard(
      soft: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.auto_graph_rounded, color: AppTheme.main),
              const SizedBox(width: 8),
              Expanded(
                child: CardTitle(
                  item == null
                      ? 'AI 매수 신호 없음'
                      : '${item.stockName} · ${item.status}',
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          TextBody(
            canBuy
                ? '${item!.stockCode} · ${item.market} · 점수 ${item.score}점의 저장된 신호입니다.'
                : '저장된 BUY 추천이 생성되면 현재가 기준 모의매수를 시작할 수 있습니다.',
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: canBuy && !submitting ? onBuy : null,
              icon: const Icon(Icons.add_chart_rounded),
              label: const Text('AI 신호로 모의매수'),
            ),
          ),
        ],
      ),
    );
  }
}

class _SubsectionTitle extends StatelessWidget {
  const _SubsectionTitle({
    required this.title,
    required this.count,
    this.onRefresh,
  });

  final String title;
  final int count;
  final VoidCallback? onRefresh;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Row(
      children: [
        Expanded(
          child: Text(
            '$title $count',
            style: TextStyle(
              color: palette.text,
              fontSize: 17,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
        ),
        if (onRefresh != null)
          IconButton(
            onPressed: onRefresh,
            tooltip: '모의매매 새로고침',
            icon: const Icon(Icons.refresh_rounded),
          ),
      ],
    );
  }
}

class _PositionCard extends StatelessWidget {
  const _PositionCard({
    required this.position,
    required this.submitting,
    required this.onSell,
  });

  final PaperPosition position;
  final bool submitting;
  final VoidCallback onSell;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final profitColor = _profitColor(position.unrealizedProfit, palette);
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: CardTitle(position.stockName)),
              Text(
                formatSignedPercent(position.profitRate),
                style: TextStyle(
                  color: profitColor,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          TextCaption(
            '${position.stockCode} · ${position.market} · ${position.provider} 현재가',
          ),
          const AppDivider(),
          TextBody(
            '수량 ${_formatQuantity(position.quantity)}주 · 평균 ${_formatMoney(position.averagePrice)}원',
          ),
          const SizedBox(height: 4),
          TextBody(
            '현재가 ${_formatMoney(position.currentPrice)}원 · 평가 ${_formatMoney(position.valuationAmount)}원',
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: submitting ? null : onSell,
              icon: const Icon(Icons.sell_outlined),
              label: const Text('모의매도'),
            ),
          ),
        ],
      ),
    );
  }
}

class _TradeCard extends StatelessWidget {
  const _TradeCard({required this.trade});

  final PaperTrade trade;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final isBuy = trade.tradeType.toUpperCase() == 'BUY';
    return AppCard(
      padding: const EdgeInsets.all(14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            isBuy
                ? Icons.add_circle_outline_rounded
                : Icons.remove_circle_outline_rounded,
            color: isBuy ? AppTheme.main : AppTheme.sub,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${trade.stockName} ${isBuy ? '매수' : '매도'}',
                  style: TextStyle(
                    color: palette.text,
                    fontSize: 15,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 4),
                TextCaption(
                  '${_formatQuantity(trade.quantity)}주 · ${_formatMoney(trade.tradePrice)}원 · ${_formatDateTime(trade.tradeDate)}',
                ),
                if (!isBuy) ...[
                  const SizedBox(height: 4),
                  Text(
                    '실현 ${_formatSignedMoney(trade.realizedProfit)}원',
                    style: TextStyle(
                      color: _profitColor(trade.realizedProfit, palette),
                      fontSize: 12,
                      fontWeight: FontWeight.w900,
                      letterSpacing: 0,
                    ),
                  ),
                ],
              ],
            ),
          ),
          Text(
            '${_formatMoney(trade.tradeAmount)}원',
            style: TextStyle(
              color: palette.text,
              fontSize: 13,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
        ],
      ),
    );
  }
}

class _EmptyCard extends StatelessWidget {
  const _EmptyCard({
    required this.icon,
    required this.title,
    required this.description,
  });

  final IconData icon;
  final String title;
  final String description;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      child: Column(
        children: [
          Icon(icon, color: AppPalette.of(context).muted, size: 30),
          const SizedBox(height: 8),
          CardTitle(title, fontSize: 16),
          const SizedBox(height: 6),
          TextBody(description),
        ],
      ),
    );
  }
}

class _PaperTradingError extends StatelessWidget {
  const _PaperTradingError({
    required this.message,
    required this.onRetry,
    this.onCapitalSetupOpen,
  });

  final String message;
  final VoidCallback onRetry;
  final VoidCallback? onCapitalSetupOpen;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.error_outline_rounded,
              size: 38,
              color: AppTheme.sub,
            ),
            const SizedBox(height: 10),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 14),
            if (onCapitalSetupOpen != null) ...[
              FilledButton.icon(
                onPressed: onCapitalSetupOpen,
                icon: const Icon(Icons.savings),
                label: const Text('자본금 설정하기'),
              ),
              const SizedBox(height: 8),
            ],
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh_rounded),
              label: const Text('다시 시도'),
            ),
          ],
        ),
      ),
    );
  }
}

String _formatMoney(double value) => formatCurrency(value.round());

String _formatSignedMoney(double value) {
  final sign = value > 0 ? '+' : '';
  return '$sign${formatCurrency(value.round())}';
}

String _formatQuantity(double value) {
  if (value == value.roundToDouble()) return value.toInt().toString();
  return value
      .toStringAsFixed(4)
      .replaceFirst(RegExp(r'0+$'), '')
      .replaceFirst(RegExp(r'\.$'), '');
}

String _formatDateTime(DateTime value) {
  String two(int number) => number.toString().padLeft(2, '0');
  return '${value.year}.${two(value.month)}.${two(value.day)} ${two(value.hour)}:${two(value.minute)}';
}

Color _profitColor(double value, AppPalette palette) {
  if (value > 0) return AppTheme.sub;
  if (value < 0) return const Color(0xff3478c7);
  return palette.muted;
}

String _errorMessage(Object? error) {
  return switch (error) {
    PaperTradingRepositoryException exception => exception.message,
    _ => '모의매매 정보를 불러오지 못했습니다.',
  };
}

bool _capitalRequired(Object? error) =>
    error is PaperTradingRepositoryException &&
    (error.code == 'PAPER_CAPITAL_REQUIRED' ||
        error.message.contains('투자 가능 자본금을 먼저 설정'));
