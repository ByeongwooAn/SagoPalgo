import 'package:flutter/material.dart';

import '../models/holding.dart';
import '../repositories/portfolio_repository.dart';
import '../repositories/market_data_repository.dart';
import '../repositories/order_precheck_repository.dart';
import '../theme/app_theme.dart';
import '../widgets/app_card.dart';
import '../widgets/app_text.dart';
import '../widgets/score_progress.dart';
import '../widgets/section_header.dart';
import '../widgets/status_chip.dart';
import 'dashboard_screen.dart';
import 'market_candle_screen.dart';
import 'order_precheck_sheet.dart';

/// 다른 탭의 빈 상태 CTA에서 포트폴리오 탭으로 전달하는 초기 작업입니다.
enum PortfolioSetupAction { editCapital, addHolding }

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
    required this.repository,
    required this.marketDataRepository,
    required this.orderPrecheckRepository,
    required this.portfolioFuture,
    required this.pendingSetupAction,
    required this.onRetry,
    required this.onChanged,
    required this.onPendingSetupActionConsumed,
  });

  /// 대시보드 스냅샷에서 즉시 표시할 자본금 설정입니다.
  final CapitalSettings capital;

  /// 전체 평가 손익과 위험 한도 사용률입니다.
  final PortfolioSummary summary;

  /// 사용자가 보유한 종목 목록입니다.
  final List<Holding> holdings;

  /// 자본금/보유 종목 API 요청을 처리하는 Repository입니다.
  final PortfolioRepository repository;

  /// 보유 종목 상세 차트 데이터를 조회하는 Repository입니다.
  final MarketDataRepository marketDataRepository;

  /// 실제 주문을 보내지 않고 KB 계좌 기준 안전 조건을 검증합니다.
  final OrderPrecheckRepository orderPrecheckRepository;

  /// 자본금/보유 종목 API에서 다시 불러오는 최신 포트폴리오 데이터입니다.
  final Future<PortfolioSnapshot> portfolioFuture;

  /// 다른 탭에서 요청한 자본금 수정 또는 보유 종목 추가 작업입니다.
  final PortfolioSetupAction? pendingSetupAction;

  /// 최신 포트폴리오 데이터 요청이 실패했을 때 다시 시도하는 콜백입니다.
  final VoidCallback onRetry;

  /// 자본금/보유 종목이 변경됐을 때 상위 화면에 갱신을 요청하는 콜백입니다.
  final VoidCallback onChanged;

  /// 요청된 초기 작업을 한 번 실행한 뒤 상위 상태를 비우는 콜백입니다.
  final VoidCallback onPendingSetupActionConsumed;

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
          repository: repository,
          marketDataRepository: marketDataRepository,
          orderPrecheckRepository: orderPrecheckRepository,
          pendingSetupAction: pendingSetupAction,
          onRetry: onRetry,
          onChanged: onChanged,
          onPendingSetupActionConsumed: onPendingSetupActionConsumed,
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
    required this.repository,
    required this.marketDataRepository,
    required this.orderPrecheckRepository,
    required this.pendingSetupAction,
    required this.onRetry,
    required this.onChanged,
    required this.onPendingSetupActionConsumed,
  });

  final PortfolioSnapshot portfolio;
  final bool isRefreshing;
  final bool hasRefreshError;
  final PortfolioRepository repository;
  final MarketDataRepository marketDataRepository;
  final OrderPrecheckRepository orderPrecheckRepository;
  final PortfolioSetupAction? pendingSetupAction;
  final VoidCallback onRetry;
  final VoidCallback onChanged;
  final VoidCallback onPendingSetupActionConsumed;

  @override
  Widget build(BuildContext context) {
    final holdings = portfolio.holdings;
    _schedulePendingSetupAction(context);

    return AppScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionHeader(
            eyebrow: '보유 종목',
            title: '손익과 리스크',
            action: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton.filledTonal(
                  onPressed: () => _openCapitalEditor(context),
                  tooltip: '자본금 수정',
                  icon: const Icon(Icons.savings_rounded),
                ),
                const SizedBox(width: 4),
                IconButton.filled(
                  onPressed: () => _openHoldingEditor(context),
                  tooltip: '보유 종목 추가',
                  icon: const Icon(Icons.add_rounded),
                ),
              ],
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
          CapitalRuleSummaryCard(
            capital: portfolio.capital,
            onEdit: () => _openCapitalEditor(context),
          ),
          const SizedBox(height: 12),
          ProfitCard(summary: portfolio.summary),
          const SizedBox(height: 12),
          if (holdings.isEmpty)
            EmptyHoldingsCard(onAdd: () => _openHoldingEditor(context))
          else
            for (final holding in holdings) ...[
              PortfolioRow(
                holding: holding,
                onChart: () => _openCandleChart(context, holding),
                onOrderPrecheck: () => _openOrderPrecheck(context, holding),
                onEdit: () => _openHoldingEditor(context, holding: holding),
                onDelete: () => _confirmDeleteHolding(context, holding),
              ),
              const SizedBox(height: 10),
            ],
          RiskRuleCard(riskUsageRate: portfolio.summary.riskUsageRate),
          const SizedBox(height: 20),
        ],
      ),
    );
  }

  void _schedulePendingSetupAction(BuildContext context) {
    final action = pendingSetupAction;
    if (action == null) {
      return;
    }

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!context.mounted) {
        return;
      }
      onPendingSetupActionConsumed();
      switch (action) {
        case PortfolioSetupAction.editCapital:
          _openCapitalEditor(context);
        case PortfolioSetupAction.addHolding:
          _openHoldingEditor(context);
      }
    });
  }

  Future<void> _openCapitalEditor(BuildContext context) async {
    final input = await showModalBottomSheet<CapitalInput>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (context) => CapitalFormSheet(capital: portfolio.capital),
    );
    if (input == null || !context.mounted) {
      return;
    }

    await _runAction(
      context,
      action: () async {
        await repository.updateCapital(input);
      },
      successMessage: '자본금 기준을 저장했습니다.',
    );
  }

  Future<void> _openHoldingEditor(
    BuildContext context, {
    Holding? holding,
  }) async {
    final input = await showModalBottomSheet<HoldingInput>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (context) => HoldingFormSheet(holding: holding),
    );
    if (input == null || !context.mounted) {
      return;
    }

    await _runAction(
      context,
      action: () async {
        if (holding == null) {
          await repository.createHolding(input);
        } else {
          await repository.updateHolding(holding.holdingId, input);
        }
      },
      successMessage: holding == null ? '보유 종목을 등록했습니다.' : '보유 종목을 수정했습니다.',
    );
  }

  void _openCandleChart(BuildContext context, Holding holding) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (context) => MarketCandleScreen(
          stockCode: holding.stockCode,
          stockName: holding.stockName,
          market: holding.market,
          repository: marketDataRepository,
        ),
      ),
    );
  }

  Future<void> _openOrderPrecheck(BuildContext context, Holding holding) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (context) => OrderPrecheckSheet(
        holding: holding,
        repository: orderPrecheckRepository,
      ),
    );
  }

  Future<void> _confirmDeleteHolding(
    BuildContext context,
    Holding holding,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('보유 종목 삭제'),
        content: Text('${holding.stockName} 보유 내역을 삭제할까요?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('삭제'),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) {
      return;
    }

    await _runAction(
      context,
      action: () => repository.deleteHolding(holding.holdingId),
      successMessage: '보유 종목을 삭제했습니다.',
    );
  }

  Future<void> _runAction(
    BuildContext context, {
    required Future<void> Function() action,
    required String successMessage,
  }) async {
    try {
      await action();
      if (!context.mounted) {
        return;
      }
      onChanged();
      _showMessage(context, successMessage);
    } catch (error) {
      if (!context.mounted) {
        return;
      }
      _showMessage(context, error.toString());
    }
  }

  void _showMessage(BuildContext context, String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }
}

/// 보유 종목이 없을 때 추가 행동을 바로 제공하는 카드입니다.
class EmptyHoldingsCard extends StatelessWidget {
  /// 보유 종목 추가 버튼 콜백을 받습니다.
  const EmptyHoldingsCard({super.key, required this.onAdd});

  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return AppCard(
      soft: true,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(
            Icons.account_balance_wallet_outlined,
            color: AppTheme.main,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              '등록된 보유 종목이 없습니다. 실제 매수 내역을 추가하면 손익과 추천 판단이 계산됩니다.',
              style: TextStyle(
                color: palette.text,
                fontSize: 14,
                height: 1.4,
                fontWeight: FontWeight.w800,
                letterSpacing: 0,
              ),
            ),
          ),
          const SizedBox(width: 8),
          IconButton.filled(
            onPressed: onAdd,
            tooltip: '보유 종목 추가',
            icon: const Icon(Icons.add_rounded),
          ),
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
  const CapitalRuleSummaryCard({
    super.key,
    required this.capital,
    required this.onEdit,
  });

  final CapitalSettings capital;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(child: LabelText('자본금 기준')),
              IconButton(
                onPressed: onEdit,
                tooltip: '자본금 수정',
                icon: const Icon(Icons.edit_rounded),
              ),
            ],
          ),
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
  const PortfolioRow({
    super.key,
    required this.holding,
    required this.onChart,
    required this.onOrderPrecheck,
    required this.onEdit,
    required this.onDelete,
  });

  /// 매수가, 수량, 수익률, 상태를 가진 보유 종목 모델입니다.
  final Holding holding;
  final VoidCallback onChart;
  final VoidCallback onOrderPrecheck;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

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
                  '매수가 ${formatCurrency(holding.buyPrice)} · ${_formatQuantity(holding.quantity)}주',
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
          const SizedBox(width: 2),
          IconButton(
            onPressed: onChart,
            tooltip: '${holding.stockName} 차트',
            icon: const Icon(Icons.candlestick_chart_rounded),
          ),
          PopupMenuButton<_HoldingMenuAction>(
            tooltip: '보유 종목 메뉴',
            icon: const Icon(Icons.more_vert_rounded),
            onSelected: (action) {
              switch (action) {
                case _HoldingMenuAction.edit:
                  onEdit();
                case _HoldingMenuAction.delete:
                  onDelete();
                case _HoldingMenuAction.orderPrecheck:
                  onOrderPrecheck();
              }
            },
            itemBuilder: (context) => const [
              PopupMenuItem(
                value: _HoldingMenuAction.orderPrecheck,
                child: Row(
                  children: [
                    Icon(Icons.verified_user_outlined),
                    SizedBox(width: 8),
                    Text('주문 사전검토'),
                  ],
                ),
              ),
              PopupMenuItem(
                value: _HoldingMenuAction.edit,
                child: Row(
                  children: [
                    Icon(Icons.edit_rounded),
                    SizedBox(width: 8),
                    Text('수정'),
                  ],
                ),
              ),
              PopupMenuItem(
                value: _HoldingMenuAction.delete,
                child: Row(
                  children: [
                    Icon(Icons.delete_outline_rounded),
                    SizedBox(width: 8),
                    Text('삭제'),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

enum _HoldingMenuAction { orderPrecheck, edit, delete }

/// 현재 미실현 손실이 사용하는 위험 한도를 보여주는 리스크 관리 카드입니다.
class RiskRuleCard extends StatelessWidget {
  /// 현재 미실현 손실의 위험 한도 사용률을 받습니다.
  const RiskRuleCard({super.key, required this.riskUsageRate});

  /// 현재 미실현 손실의 위험 한도 사용률입니다.
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
            '현재 손실 위험 한도 ${(riskUsageRate * 100).round()}%',
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

/// 자본금 수정 입력 시트입니다.
class CapitalFormSheet extends StatefulWidget {
  /// 기존 자본금 설정을 초기값으로 받습니다.
  const CapitalFormSheet({super.key, required this.capital});

  final CapitalSettings capital;

  @override
  State<CapitalFormSheet> createState() => _CapitalFormSheetState();
}

class _CapitalFormSheetState extends State<CapitalFormSheet> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _capitalController;
  late final TextEditingController _riskRateController;

  @override
  void initState() {
    super.initState();
    _capitalController = TextEditingController(
      text: widget.capital.availableCapital.toString(),
    );
    _riskRateController = TextEditingController(
      text: (widget.capital.riskPerTradeRate * 100).toStringAsFixed(1),
    );
  }

  @override
  void dispose() {
    _capitalController.dispose();
    _riskRateController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return _SheetScaffold(
      title: '자본금 수정',
      child: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _NumberField(
              controller: _capitalController,
              label: '투자 가능 자본금',
              suffix: '원',
              validator: (value) => _validateInt(value, min: 0),
            ),
            const SizedBox(height: 12),
            _NumberField(
              controller: _riskRateController,
              label: '1회 리스크 비율',
              suffix: '%',
              allowDecimal: true,
              validator: (value) => _validateDouble(value, min: 0.01, max: 100),
            ),
            const SizedBox(height: 18),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _submit,
                icon: const Icon(Icons.save_rounded),
                label: const Text('저장'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _submit() {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    Navigator.of(context).pop(
      CapitalInput(
        availableCapital: int.parse(_capitalController.text.trim()),
        riskPerTradeRate: double.parse(_riskRateController.text.trim()) / 100,
      ),
    );
  }
}

/// 보유 종목 등록/수정 입력 시트입니다.
class HoldingFormSheet extends StatefulWidget {
  /// 기존 보유 종목이 있으면 수정, 없으면 신규 등록으로 동작합니다.
  const HoldingFormSheet({super.key, this.holding});

  final Holding? holding;

  @override
  State<HoldingFormSheet> createState() => _HoldingFormSheetState();
}

class _HoldingFormSheetState extends State<HoldingFormSheet> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _stockCodeController;
  late final TextEditingController _stockNameController;
  late final TextEditingController _marketController;
  late final TextEditingController _buyPriceController;
  late final TextEditingController _quantityController;
  late final TextEditingController _stopLossRateController;
  late final TextEditingController _takeProfitRateController;
  late DateTime _buyDate;

  @override
  void initState() {
    super.initState();
    final holding = widget.holding;
    _stockCodeController = TextEditingController(
      text: holding?.stockCode ?? '',
    );
    _stockNameController = TextEditingController(
      text: holding?.stockName ?? '',
    );
    _marketController = TextEditingController(text: holding?.market ?? 'KOSPI');
    _buyPriceController = TextEditingController(
      text: holding?.buyPrice.toString() ?? '',
    );
    _quantityController = TextEditingController(
      text: holding?.quantity.toString() ?? '',
    );
    _stopLossRateController = TextEditingController(
      text: holding?.stopLossRate.toStringAsFixed(1) ?? '-5.0',
    );
    _takeProfitRateController = TextEditingController(
      text: holding?.takeProfitRate.toStringAsFixed(1) ?? '9.0',
    );
    _buyDate = holding?.buyDate ?? DateTime.now();
  }

  @override
  void dispose() {
    _stockCodeController.dispose();
    _stockNameController.dispose();
    _marketController.dispose();
    _buyPriceController.dispose();
    _quantityController.dispose();
    _stopLossRateController.dispose();
    _takeProfitRateController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final title = widget.holding == null ? '보유 종목 추가' : '보유 종목 수정';

    return _SheetScaffold(
      title: title,
      child: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                Expanded(
                  child: _TextField(
                    controller: _stockCodeController,
                    label: '종목 코드',
                    validator: _validateRequired,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _TextField(
                    controller: _marketController,
                    label: '시장',
                    validator: _validateRequired,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _TextField(
              controller: _stockNameController,
              label: '종목명',
              validator: _validateRequired,
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _NumberField(
                    controller: _buyPriceController,
                    label: '매수가',
                    suffix: '원',
                    validator: (value) => _validateInt(value, min: 1),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _NumberField(
                    controller: _quantityController,
                    label: '수량',
                    allowDecimal: true,
                    validator: (value) => _validateDouble(value, min: 0.0001),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _DateSelector(date: _buyDate, onTap: _pickBuyDate),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _NumberField(
                    controller: _stopLossRateController,
                    label: '손절 기준',
                    suffix: '%',
                    allowDecimal: true,
                    signed: true,
                    validator: (value) =>
                        _validateDouble(value, min: -100, max: 0),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _NumberField(
                    controller: _takeProfitRateController,
                    label: '익절 기준',
                    suffix: '%',
                    allowDecimal: true,
                    validator: (value) => _validateDouble(value, min: 0),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 18),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _submit,
                icon: const Icon(Icons.save_rounded),
                label: Text(widget.holding == null ? '등록' : '저장'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _pickBuyDate() async {
    final selected = await showDatePicker(
      context: context,
      initialDate: _buyDate,
      firstDate: DateTime(1990),
      lastDate: DateTime.now().add(const Duration(days: 1)),
    );
    if (selected == null) {
      return;
    }

    setState(() => _buyDate = selected);
  }

  void _submit() {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    Navigator.of(context).pop(
      HoldingInput(
        stockCode: _stockCodeController.text.trim(),
        stockName: _stockNameController.text.trim(),
        market: _marketController.text.trim().toUpperCase(),
        buyPrice: int.parse(_buyPriceController.text.trim()),
        quantity: double.parse(_quantityController.text.trim()),
        buyDate: _buyDate,
        stopLossRate: double.parse(_stopLossRateController.text.trim()),
        takeProfitRate: double.parse(_takeProfitRateController.text.trim()),
      ),
    );
  }
}

class _SheetScaffold extends StatelessWidget {
  const _SheetScaffold({required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final bottom = MediaQuery.viewInsetsOf(context).bottom;

    return Padding(
      padding: EdgeInsets.fromLTRB(20, 18, 20, 20 + bottom),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    title,
                    style: TextStyle(
                      color: palette.text,
                      fontSize: 22,
                      fontWeight: FontWeight.w900,
                      letterSpacing: 0,
                    ),
                  ),
                ),
                IconButton(
                  onPressed: () => Navigator.of(context).pop(),
                  tooltip: '닫기',
                  icon: const Icon(Icons.close_rounded),
                ),
              ],
            ),
            const SizedBox(height: 16),
            child,
          ],
        ),
      ),
    );
  }
}

class _TextField extends StatelessWidget {
  const _TextField({
    required this.controller,
    required this.label,
    required this.validator,
  });

  final TextEditingController controller;
  final String label;
  final FormFieldValidator<String> validator;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: controller,
      decoration: InputDecoration(labelText: label),
      textInputAction: TextInputAction.next,
      validator: validator,
    );
  }
}

class _NumberField extends StatelessWidget {
  const _NumberField({
    required this.controller,
    required this.label,
    required this.validator,
    this.suffix,
    this.allowDecimal = false,
    this.signed = false,
  });

  final TextEditingController controller;
  final String label;
  final String? suffix;
  final bool allowDecimal;
  final bool signed;
  final FormFieldValidator<String> validator;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: controller,
      decoration: InputDecoration(labelText: label, suffixText: suffix),
      keyboardType: TextInputType.numberWithOptions(
        decimal: allowDecimal,
        signed: signed,
      ),
      textInputAction: TextInputAction.next,
      validator: validator,
    );
  }
}

class _DateSelector extends StatelessWidget {
  const _DateSelector({required this.date, required this.onTap});

  final DateTime date;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: InputDecorator(
        decoration: const InputDecoration(
          labelText: '매수일',
          suffixIcon: Icon(Icons.calendar_today_rounded),
        ),
        child: Text(_formatDate(date)),
      ),
    );
  }
}

/// 금액을 천 단위 쉼표와 부호가 포함된 문자열로 바꿉니다.
String formatSignedCurrency(int value) {
  final sign = value > 0 ? '+' : '';
  return '$sign${formatCurrency(value)}';
}

String? _validateRequired(String? value) {
  if (value == null || value.trim().isEmpty) {
    return '필수 입력값입니다.';
  }
  return null;
}

String? _validateInt(String? value, {required int min}) {
  final number = int.tryParse(value?.trim() ?? '');
  if (number == null) {
    return '숫자로 입력해 주세요.';
  }
  if (number < min) {
    return '$min 이상 입력해 주세요.';
  }
  return null;
}

String? _validateDouble(String? value, {required double min, double? max}) {
  final number = double.tryParse(value?.trim() ?? '');
  if (number == null) {
    return '숫자로 입력해 주세요.';
  }
  if (number < min) {
    return '$min 이상 입력해 주세요.';
  }
  if (max != null && number > max) {
    return '$max 이하 입력해 주세요.';
  }
  return null;
}

String _formatDate(DateTime value) {
  final year = value.year.toString().padLeft(4, '0');
  final month = value.month.toString().padLeft(2, '0');
  final day = value.day.toString().padLeft(2, '0');
  return '$year-$month-$day';
}

String _formatQuantity(double value) {
  final asInt = value.truncateToDouble();
  if (value == asInt) {
    return asInt.toInt().toString();
  }

  return value.toStringAsFixed(4).replaceFirst(RegExp(r'\.?0+$'), '');
}
