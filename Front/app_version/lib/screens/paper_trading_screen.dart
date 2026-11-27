import 'dart:math';

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
import '../widgets/responsive_layout.dart';
import 'automated_paper_trading_screen.dart';
import 'dashboard_screen.dart';
import 'order_simulation_screen.dart';
import '../repositories/order_simulation_repository.dart';

/// 실제 주문과 완전히 분리된 AI 신호 기반 모의매매 화면입니다.
class PaperTradingScreen extends StatefulWidget {
  const PaperTradingScreen({
    super.key,
    required this.repository,
    required this.recommendation,
    required this.active,
    this.onCapitalSetupOpen,
    this.availableCapital,
    this.onAnalysisOpen,
    this.usRepository,
  });

  final PaperTradingRepository repository;
  final InvestmentRecommendation? recommendation;
  final bool active;
  final VoidCallback? onCapitalSetupOpen;
  final int? availableCapital;
  final VoidCallback? onAnalysisOpen;
  final UsPaperTradingRepository? usRepository;

  @override
  State<PaperTradingScreen> createState() => _PaperTradingScreenState();
}

class _PaperTradingScreenState extends State<PaperTradingScreen> {
  Future<PaperTradingSnapshot>? _snapshotFuture;
  bool _submitting = false;
  ({Future<PaperTradingSnapshot> Function() send, String message})?
  _pendingTrade;
  String? _tradeError;

  bool get _usd => widget.usRepository != null;

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
      _snapshotFuture =
          widget.usRepository?.fetchUsSnapshot() ??
          widget.repository.fetchSnapshot();
    });
  }

  @override
  Widget build(BuildContext context) {
    final future = _snapshotFuture;
    if (!widget.active && future == null) {
      return const SizedBox.shrink();
    }

    final content = FutureBuilder<PaperTradingSnapshot>(
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
    final repository = widget.repository;
    if (_usd ||
        (repository is! OrderSimulationRepository &&
            repository is! UsPaperTradingRepository &&
            repository is! AutomatedPaperTradingRepository)) {
      return content;
    }
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 4),
          child: Wrap(
            spacing: 8,
            runSpacing: 8,
            alignment: WrapAlignment.center,
            children: [
              if (repository is AutomatedPaperTradingRepository)
                OutlinedButton.icon(
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => AutomatedPaperTradingScreen(
                        repository:
                            repository as AutomatedPaperTradingRepository,
                      ),
                    ),
                  ),
                  icon: const Icon(Icons.insights_outlined),
                  label: const Text('AI 자동 모의매매'),
                ),
              if (repository is UsPaperTradingRepository)
                OutlinedButton.icon(
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => Scaffold(
                        appBar: AppBar(title: const Text('미국주식 모의매매')),
                        body: PaperTradingScreen(
                          repository: repository,
                          recommendation: null,
                          active: true,
                          usRepository: repository as UsPaperTradingRepository,
                        ),
                      ),
                    ),
                  ),
                  icon: const Icon(Icons.public),
                  label: const Text('미국주식 모의매매 (USD)'),
                ),
              if (repository is OrderSimulationRepository)
                OutlinedButton.icon(
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => OrderSimulationScreen(
                        repository: repository as OrderSimulationRepository,
                      ),
                    ),
                  ),
                  icon: const Icon(Icons.bug_report_outlined),
                  label: const Text('주문 시뮬레이션 · 실패/체결 시나리오 시험'),
                ),
            ],
          ),
        ),
        Expanded(child: content),
      ],
    );
  }

  Widget _buildContent(PaperTradingSnapshot snapshot) {
    final summary = _SummaryCard(summary: snapshot.summary, usd: _usd);
    final actions = _usd
        ? _usActions(snapshot)
        : _RecommendationAction(
            recommendation: widget.recommendation,
            submitting: _submitting || _pendingTrade != null,
            onBuy: _buyFromRecommendation,
            onAnalysisOpen: widget.onAnalysisOpen,
          );
    return AppScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionHeader(
            eyebrow: '가상 체결',
            title: _usd ? '미국주식 가상 계좌' : 'AI 모의매매',
            action: StatusChip(
              label: _usd ? 'USD' : 'PAPER',
              icon: Icons.science_rounded,
            ),
          ),
          const SizedBox(height: 18),
          if (_tradeError != null) TextBody(_tradeError!),
          if (_pendingTrade case final pending? when !_submitting)
            TextButton(
              onPressed: () => _sendTrade(pending.send, pending.message),
              child: const Text('같은 주문으로 결과 확인'),
            ),
          AdaptiveColumns(
            first: _usd ? actions : summary,
            second: _usd ? summary : actions,
          ),
          const SizedBox(height: 8),
          if (!_usd)
            const TextCaption(
              '현재 설정 자본금 기준입니다. 자본금을 변경하면 모의 현금·수익률도 재산정되며 거래 기록은 유지됩니다.',
            ),
          const SizedBox(height: 12),
          const SizedBox(height: 18),
          _SubsectionTitle(
            title: '보유 포지션',
            count: snapshot.positions.length,
            onRefresh: _load,
          ),
          const SizedBox(height: 10),
          if (snapshot.positions.isEmpty)
            _EmptyCard(
              icon: Icons.inventory_2_outlined,
              title: '보유 중인 모의 포지션이 없습니다',
              description: _usd
                  ? '거래소와 티커를 입력해 모의매수할 수 있습니다.'
                  : '최신 AI 매수 신호를 이용해 실제 주문 없이 전략을 검증할 수 있습니다.',
            )
          else
            ...snapshot.positions.map(
              (position) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: _PositionCard(
                  position: position,
                  usd: _usd,
                  submitting: _submitting || _pendingTrade != null,
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
                child: _TradeCard(trade: trade, usd: _usd),
              ),
            ),
          const SizedBox(height: 20),
        ],
      ),
    );
  }

  Widget _usActions(PaperTradingSnapshot snapshot) {
    final hasAccount = snapshot.summary.initialCapital > 0;
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          CardTitle(hasAccount ? '미국주식 모의 주문' : 'USD 모의계좌 개설'),
          const SizedBox(height: 8),
          TextCaption(
            hasAccount
                ? '애플·엔비디아 매수는 서버가 매수 관찰 신호와 정규장 체결 시세를 확인합니다.'
                : '원화 모의계좌와 별도로 사용할 달러 시작 자금을 입력하세요.',
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: _submitting || _pendingTrade != null
                ? null
                : (hasAccount ? _buyUs : _openUsAccount),
            icon: const Icon(Icons.add),
            label: Text(hasAccount ? '미국주식 모의매수' : 'USD 시작 자금 설정'),
          ),
        ],
      ),
    );
  }

  Future<void> _openUsAccount() async {
    final amount = await showDialog<String>(
      context: context,
      builder: (_) => const _QuantityDialog(
        title: 'USD 모의계좌 개설',
        actionLabel: '개설',
        maxQuantity: null,
        capital: true,
      ),
    );
    if (amount == null || !mounted) return;
    await _submit(
      () => widget.usRepository!.openUsAccount(amount),
      'USD 모의계좌가 개설되었습니다.',
    );
  }

  Future<void> _buyUs() async {
    final order =
        await showDialog<({String stockCode, String market, String quantity})>(
          context: context,
          builder: (_) => const _UsPaperBuyDialog(),
        );
    if (order == null || !mounted) return;
    await _sendUsTrade((
      stockCode: order.stockCode,
      market: order.market,
      side: 'BUY',
      quantity: order.quantity,
      requestId: _newRequestId(),
    ));
  }

  Future<void> _sendUsTrade(UsPaperOrder order) => _sendTrade(
    () => widget.usRepository!.tradeUs(order),
    '${order.stockCode} 모의 주문 결과를 확인했습니다.',
  );

  Future<void> _sendTrade(
    Future<PaperTradingSnapshot> Function() send,
    String message,
  ) async {
    if (_submitting) return;
    setState(() {
      _pendingTrade = (send: send, message: message);
      _tradeError = null;
    });
    await _submit(
      () async {
        final result = await send();
        if (mounted) setState(() => _pendingTrade = null);
        return result;
      },
      message,
      onError: (error) {
        setState(() {
          if (error is PaperTradingRepositoryException &&
              const {
                'VALIDATION_ERROR',
                'PAPER_CAPITAL_REQUIRED',
                'DUPLICATE_RESOURCE',
                'RESOURCE_NOT_FOUND',
                'EXTERNAL_DATA_ERROR',
              }.contains(error.code)) {
            _pendingTrade = null;
            _tradeError = error.message;
          } else {
            _tradeError = '체결 결과를 확인하지 못했습니다. 같은 주문으로 다시 확인할 수 있습니다.';
          }
        });
      },
    );
  }

  String _newRequestId() {
    final random = Random.secure();
    return List.generate(
      16,
      (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'),
    ).join();
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
    final requestId = _newRequestId();
    await _sendTrade(
      () => widget.repository.buyFromRecommendation(
        recommendationId,
        double.parse(quantity),
        requestId: requestId,
      ),
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
    if (_usd) {
      await _sendUsTrade((
        stockCode: position.stockCode,
        market: position.market,
        side: 'SELL',
        quantity: quantity,
        requestId: _newRequestId(),
      ));
      return;
    }
    final requestId = _newRequestId();
    await _sendTrade(
      () => widget.repository.sellPosition(
        stockCode: position.stockCode,
        market: position.market,
        quantity: double.parse(quantity),
        requestId: requestId,
      ),
      '${position.stockName} 모의매도가 체결되었습니다.',
    );
  }

  Future<void> _submit(
    Future<PaperTradingSnapshot> Function() action,
    String successMessage, {
    void Function(Object)? onError,
  }) async {
    if (_submitting) return;
    setState(() => _submitting = true);
    try {
      final result = await action();
      if (!mounted) return;
      setState(() {
        _snapshotFuture = Future.value(result);
      });
      _showMessage(successMessage);
    } catch (error) {
      if (mounted) {
        if (onError == null) {
          _showMessage(_errorMessage(error));
        } else {
          onError(error);
        }
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<String?> _showQuantityDialog({
    required String title,
    required String actionLabel,
    double? maxQuantity,
  }) async {
    return showDialog<String>(
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
    this.capital = false,
  });

  final String title;
  final String actionLabel;
  final double? maxQuantity;
  final bool capital;

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
          FilteringTextInputFormatter.allow(
            widget.capital
                ? RegExp(r'^\d*\.?\d{0,2}')
                : RegExp(r'^\d*\.?\d{0,4}'),
          ),
        ],
        decoration: InputDecoration(
          labelText: widget.capital ? '시작 자금' : '수량',
          suffixText: widget.capital ? 'USD' : '주',
          errorText: _validationMessage,
          helperText: widget.capital
              ? '최소 0.01 USD · 소수점 둘째 자리까지'
              : widget.maxQuantity == null
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
    final text = _controller.text.trim();
    final quantity = double.tryParse(text);
    if (quantity == null ||
        !quantity.isFinite ||
        (widget.capital && text.split('.').first.length > 16) ||
        quantity < (widget.capital ? 0.01 : 0.0001) ||
        (widget.maxQuantity != null && quantity > widget.maxQuantity!)) {
      setState(() => _validationMessage = '가능한 수량을 입력해 주세요.');
      return;
    }
    Navigator.of(context).pop(text);
  }
}

class _UsPaperBuyDialog extends StatefulWidget {
  const _UsPaperBuyDialog();

  @override
  State<_UsPaperBuyDialog> createState() => _UsPaperBuyDialogState();
}

class _UsPaperBuyDialogState extends State<_UsPaperBuyDialog> {
  final _form = GlobalKey<FormState>();
  String _market = 'NASDAQ';
  String _ticker = '';
  String _quantity = '';

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('미국주식 모의매수'),
    content: SizedBox(
      width: 340,
      child: Form(
        key: _form,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            DropdownButtonFormField<String>(
              initialValue: _market,
              decoration: const InputDecoration(labelText: '거래소'),
              items: const [
                DropdownMenuItem(value: 'NASDAQ', child: Text('나스닥')),
                DropdownMenuItem(value: 'NYSE', child: Text('뉴욕증권거래소')),
                DropdownMenuItem(value: 'AMEX', child: Text('NYSE American')),
              ],
              onChanged: (value) => _market = value ?? _market,
            ),
            TextFormField(
              autofocus: true,
              decoration: const InputDecoration(
                labelText: '티커',
                hintText: 'AAPL',
              ),
              onChanged: (value) => _ticker = value.trim().toUpperCase(),
              validator: (_) =>
                  _ticker.length <= 16 &&
                      RegExp(
                        r'^[A-Z][A-Z0-9]{0,14}(?:[.-][A-Z0-9]{1,4})?$',
                      ).hasMatch(_ticker)
                  ? null
                  : '미국주식 티커를 입력하세요.',
            ),
            TextFormField(
              decoration: const InputDecoration(
                labelText: '수량',
                suffixText: '주',
              ),
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              onChanged: (value) => _quantity = value.trim(),
              validator: (_) =>
                  RegExp(
                        r'^(?:\d{1,14}(?:\.\d{1,4})?|\.\d{1,4})$',
                      ).hasMatch(_quantity) &&
                      (double.tryParse(_quantity) ?? 0) >= 0.0001
                  ? null
                  : '0.0001주 이상, 소수점 넷째 자리까지 입력하세요.',
              onFieldSubmitted: (_) => _confirm(),
            ),
          ],
        ),
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.of(context).pop(),
        child: const Text('취소'),
      ),
      FilledButton(onPressed: _confirm, child: const Text('현재가로 모의매수')),
    ],
  );

  void _confirm() {
    if (_form.currentState!.validate()) {
      Navigator.of(
        context,
      ).pop((stockCode: _ticker, market: _market, quantity: _quantity));
    }
  }
}

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({required this.summary, required this.usd});

  final PaperTradingSummary summary;
  final bool usd;

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
            _formatMoney(summary.totalAsset, usd),
            style: TextStyle(
              color: palette.text,
              fontSize: 28,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            '${_formatSignedMoney(summary.totalProfit, usd)}  ${formatSignedPercent(summary.returnRate)}',
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
                    value: _formatMoney(summary.cashBalance, usd),
                  ),
                  _Metric(
                    width: width,
                    label: '평가액',
                    value: _formatMoney(summary.openPositionValue, usd),
                  ),
                  _Metric(
                    width: width,
                    label: '실현 손익',
                    value: _formatSignedMoney(summary.realizedProfit, usd),
                  ),
                  _Metric(
                    width: width,
                    label: '평가 손익',
                    value: _formatSignedMoney(summary.unrealizedProfit, usd),
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
                    value: _formatMoney(summary.maxLoss, usd),
                  ),
                  _Metric(
                    width: width,
                    label: '회전율',
                    value: '${summary.turnoverRate.toStringAsFixed(1)}%',
                  ),
                  _Metric(
                    width: width,
                    label: '설정 자본',
                    value: _formatMoney(summary.initialCapital, usd),
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
    this.onAnalysisOpen,
  });

  final InvestmentRecommendation? recommendation;
  final bool submitting;
  final VoidCallback onBuy;
  final VoidCallback? onAnalysisOpen;

  @override
  Widget build(BuildContext context) {
    final item = recommendation;
    final usesDailyModel =
        item?.market == 'KOSPI' &&
        (item?.stockCode == '005930' || item?.stockCode == '000660');
    final signal = item?.evidence?.dailySignal;
    final expires = signal?.expiresAt;
    final canBuy =
        item?.recommendationId != null &&
        (usesDailyModel
            ? signal?.decision == 'BUY_WATCH' &&
                  expires != null &&
                  DateTime.now().isBefore(expires)
            : item?.recommendationType.toUpperCase() == 'BUY');
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
                      : '${item.stockName} · ${canBuy && usesDailyModel ? '매수 관찰' : item.status}',
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          TextBody(
            usesDailyModel
                ? (canBuy
                      ? '${signal?.basisDate ?? ''} 기준 장 마감 모델 매수 관찰 · 정규장에만 체결'
                      : '유효한 장 마감 모델 매수 관찰 신호가 필요합니다.')
                : canBuy
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
          if (!canBuy && onAnalysisOpen != null)
            TextButton.icon(
              onPressed: onAnalysisOpen,
              icon: const Icon(Icons.auto_graph),
              label: const Text('추천 분석으로 이동'),
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
    required this.usd,
  });

  final PaperPosition position;
  final bool submitting;
  final VoidCallback onSell;
  final bool usd;

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
            '${position.stockCode} · ${position.market} · '
            '${usd && position.provider == 'FALLBACK' ? '현재가 미확인 · 매입 원가 평가' : '${position.provider} 현재가'}',
          ),
          const AppDivider(),
          TextBody(
            '수량 ${_formatQuantity(position.quantity)}주 · 평균 ${_formatMoney(position.averagePrice, usd, unitPrice: true)}',
          ),
          const SizedBox(height: 4),
          TextBody(
            '${usd && position.provider == 'FALLBACK' ? '평가 기준가' : '현재가'} '
            '${_formatMoney(position.currentPrice, usd, unitPrice: true)} · 평가 ${_formatMoney(position.valuationAmount, usd)}',
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
  const _TradeCard({required this.trade, required this.usd});

  final PaperTrade trade;
  final bool usd;

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
                  '${_formatQuantity(trade.quantity)}주 · ${_formatMoney(trade.tradePrice, usd, unitPrice: true)} · ${_formatDateTime(trade.tradeDate)}',
                ),
                if (trade.quoteMarketAt case final marketAt?)
                  TextCaption(
                    '${trade.quoteProvider ?? ''} 거래소 체결 시각 ${_formatDateTime(marketAt.toLocal())}',
                  ),
                if (trade.signalBasisDate case final date?)
                  TextCaption('장 마감 신호 기준일 $date'),
                if (!isBuy) ...[
                  const SizedBox(height: 4),
                  Text(
                    '실현 ${_formatSignedMoney(trade.realizedProfit, usd)}',
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
            _formatMoney(trade.tradeAmount, usd),
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

String _formatMoney(double value, bool usd, {bool unitPrice = false}) {
  if (!usd) return '${formatCurrency(value.round())}원';
  return '${value.toStringAsFixed(unitPrice ? 4 : 2)} USD';
}

String _formatSignedMoney(double value, bool usd) {
  final sign = value > 0 ? '+' : '';
  return '$sign${_formatMoney(value, usd)}';
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
  return '${value.year}.${two(value.month)}.${two(value.day)} ${two(value.hour)}:${two(value.minute)}:${two(value.second)}';
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
