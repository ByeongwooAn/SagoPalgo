import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models/kb_account_snapshot.dart';
import '../theme/app_theme.dart';
import 'dashboard_screen.dart';

enum _Source { settlement, holdings }

typedef _Position = ({
  String stockCode,
  String stockName,
  double quantity,
  int valuationAmount,
  int profitAmount,
  double profitRate,
  double? weightRate,
});

/// KB 결제 잔고와 보유주식 조회를 출처별로 확인하는 읽기 전용 목록입니다.
class KbHoldingsDetailDialog extends StatefulWidget {
  const KbHoldingsDetailDialog({super.key, required this.snapshot});

  final KbAccountSnapshot snapshot;

  @override
  State<KbHoldingsDetailDialog> createState() => _KbHoldingsDetailDialogState();
}

class _KbHoldingsDetailDialogState extends State<KbHoldingsDetailDialog> {
  late _Source _source;

  @override
  void initState() {
    super.initState();
    _source = widget.snapshot.settlementBalance.items.isNotEmpty
        ? _Source.settlement
        : _Source.holdings;
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final viewport = MediaQuery.sizeOf(context);
    final isSettlement = _source == _Source.settlement;
    final positions = isSettlement
        ? widget.snapshot.settlementBalance.items
              .map(
                (item) => (
                  stockCode: item.stockCode,
                  stockName: item.stockName,
                  quantity: item.quantity,
                  valuationAmount: item.valuationAmount,
                  profitAmount: item.profitAmount,
                  profitRate: item.profitRate,
                  weightRate: item.valuationWeightRate,
                ),
              )
              .toList()
        : widget.snapshot.holdings.items
              .map(
                (item) => (
                  stockCode: item.stockCode,
                  stockName: item.stockName,
                  quantity: item.quantity,
                  valuationAmount: item.valuationAmount,
                  profitAmount: item.profitAmount,
                  profitRate: item.profitRate,
                  weightRate: item.weightRate,
                ),
              )
              .toList();
    final totalValuation = positions.fold<int>(
      0,
      (total, item) => total + item.valuationAmount,
    );
    final hasValuation = isSettlement || totalValuation > 0;
    final reportedCount =
        widget.snapshot.settlementBalance.summary.reportedItemCount;
    final countMismatch =
        reportedCount != null &&
        reportedCount != widget.snapshot.settlementBalance.items.length;

    return Dialog(
      insetPadding: const EdgeInsets.all(16),
      child: SizedBox(
        width: math.min(720, viewport.width - 32),
        height: math.min(680, viewport.height - 32),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 12, 12, 8),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      'KB 계좌 상세',
                      style: TextStyle(
                        color: palette.text,
                        fontSize: 18,
                        fontWeight: FontWeight.w800,
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
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: SegmentedButton<_Source>(
                segments: const [
                  ButtonSegment(
                    value: _Source.settlement,
                    label: Text('결제 잔고'),
                  ),
                  ButtonSegment(value: _Source.holdings, label: Text('보유 주식')),
                ],
                selected: {_source},
                onSelectionChanged: (selection) => setState(() {
                  _source = selection.single;
                }),
              ),
            ),
            const SizedBox(height: 10),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: Text(
                '상세 평가금액 ${formatCurrency(totalValuation)}원 · '
                '${positions.length}${isSettlement ? '항목' : '종목'}',
                style: TextStyle(
                  color: palette.text,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 5, 20, 12),
              child: Text(
                isSettlement
                    ? '비중: KB 결제기준 잔고 응답의 평가비중'
                    : '비중: 조회된 보유 주식 평가금액 합계 기준 (예수금·순자산 제외)',
                style: TextStyle(
                  color: palette.muted,
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            if (isSettlement)
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 12),
                child: Text(
                  reportedCount == null
                      ? 'KB 보고 건수 미제공 · 현재 응답 ${positions.length}건'
                      : 'KB 보고 $reportedCount건 · 현재 응답 ${positions.length}건'
                            '${countMismatch ? ' · 건수 확인 필요' : ' · 건수 일치'}',
                  style: TextStyle(
                    color: countMismatch ? palette.text : palette.muted,
                    fontSize: 11,
                    fontWeight: countMismatch
                        ? FontWeight.w800
                        : FontWeight.w600,
                  ),
                ),
              ),
            const Divider(height: 1),
            Expanded(
              child: positions.isEmpty
                  ? const Center(child: Text('조회된 종목이 없습니다.'))
                  : ListView.separated(
                      itemCount: positions.length,
                      separatorBuilder: (_, _) => const Divider(height: 1),
                      itemBuilder: (context, index) => _HoldingDetailRow(
                        holding: positions[index],
                        hasValuation: hasValuation,
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HoldingDetailRow extends StatelessWidget {
  const _HoldingDetailRow({required this.holding, required this.hasValuation});

  final _Position holding;
  final bool hasValuation;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final weight = hasValuation && holding.weightRate != null
        ? '${holding.weightRate!.toStringAsFixed(1)}%'
        : '산정 불가';
    final title = holding.stockName.isEmpty
        ? holding.stockCode
        : holding.stockName;
    final details =
        '${holding.stockCode} · ${holding.quantity.toStringAsFixed(0)}주';
    final valuation = '${formatCurrency(holding.valuationAmount)}원';
    final profit =
        '${formatCurrency(holding.profitAmount)}원 '
        '(${formatSignedPercent(holding.profitRate)})';

    return LayoutBuilder(
      builder: (context, constraints) {
        final narrow = constraints.maxWidth < 520;
        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          child: narrow
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(child: _name(title, details, palette)),
                        Text(weight, style: _strongStyle(palette)),
                      ],
                    ),
                    const SizedBox(height: 7),
                    Text('$valuation · $profit', style: _subtleStyle(palette)),
                  ],
                )
              : Row(
                  children: [
                    Expanded(flex: 3, child: _name(title, details, palette)),
                    Expanded(
                      flex: 3,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Text(valuation, style: _strongStyle(palette)),
                          Text(profit, style: _subtleStyle(palette)),
                        ],
                      ),
                    ),
                    SizedBox(
                      width: 84,
                      child: Text(
                        weight,
                        textAlign: TextAlign.right,
                        style: _strongStyle(palette),
                      ),
                    ),
                  ],
                ),
        );
      },
    );
  }

  Widget _name(String title, String details, AppPalette palette) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(title, style: _strongStyle(palette)),
      Text(details, style: _subtleStyle(palette)),
    ],
  );

  TextStyle _strongStyle(AppPalette palette) =>
      TextStyle(color: palette.text, fontSize: 12, fontWeight: FontWeight.w800);

  TextStyle _subtleStyle(AppPalette palette) => TextStyle(
    color: palette.muted,
    fontSize: 11,
    fontWeight: FontWeight.w600,
  );
}
