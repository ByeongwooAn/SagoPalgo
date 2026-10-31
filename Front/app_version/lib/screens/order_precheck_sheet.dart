import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/holding.dart';
import '../models/order_precheck.dart';
import '../repositories/order_precheck_repository.dart';
import '../theme/app_theme.dart';
import '../widgets/app_card.dart';
import '../widgets/app_text.dart';
import 'dashboard_screen.dart';

enum _OrderSide { buy, sell }

/// 보유 종목의 지정가 주문안을 실제 전송 없이 검증하는 바텀 시트입니다.
class OrderPrecheckSheet extends StatefulWidget {
  const OrderPrecheckSheet({
    super.key,
    required this.holding,
    required this.repository,
  });

  final Holding holding;
  final OrderPrecheckRepository repository;

  @override
  State<OrderPrecheckSheet> createState() => _OrderPrecheckSheetState();
}

class _OrderPrecheckSheetState extends State<OrderPrecheckSheet> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _priceController;
  late final TextEditingController _quantityController;
  _OrderSide _side = _OrderSide.sell;
  OrderPrecheckResult? _result;
  String? _errorMessage;
  String? _approvalMessage;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    final initialPrice = widget.holding.currentPrice > 0
        ? widget.holding.currentPrice
        : widget.holding.buyPrice;
    _priceController = TextEditingController(text: initialPrice.toString());
    _quantityController = TextEditingController(
      text: _formatQuantity(widget.holding.quantity),
    );
  }

  @override
  void dispose() {
    _priceController.dispose();
    _quantityController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final keyboardInset = MediaQuery.viewInsetsOf(context).bottom;
    return SafeArea(
      child: SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(20, 18, 20, 20 + keyboardInset),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const LabelText('KB 주문 안전장치'),
                        const SizedBox(height: 5),
                        CardTitle('${widget.holding.stockName} 주문 사전검토'),
                        const SizedBox(height: 4),
                        TextCaption(
                          '${widget.holding.stockCode} · ${widget.holding.market}',
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    onPressed: () => Navigator.of(context).pop(),
                    tooltip: '닫기',
                    icon: const Icon(Icons.close_rounded),
                  ),
                ],
              ),
              const SizedBox(height: 18),
              SizedBox(
                width: double.infinity,
                child: SegmentedButton<_OrderSide>(
                  segments: const [
                    ButtonSegment(
                      value: _OrderSide.buy,
                      label: Text('매수'),
                      icon: Icon(Icons.add_chart_rounded),
                    ),
                    ButtonSegment(
                      value: _OrderSide.sell,
                      label: Text('매도'),
                      icon: Icon(Icons.sell_outlined),
                    ),
                  ],
                  selected: {_side},
                  onSelectionChanged: _loading
                      ? null
                      : (selection) {
                          setState(() {
                            _side = selection.single;
                            _result = null;
                            _errorMessage = null;
                            _approvalMessage = null;
                          });
                        },
                ),
              ),
              const SizedBox(height: 14),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _priceController,
                      onChanged: (_) => _clearResult(),
                      enabled: !_loading,
                      keyboardType: const TextInputType.numberWithOptions(
                        decimal: true,
                      ),
                      inputFormatters: [_numberFormatter(2)],
                      decoration: const InputDecoration(
                        labelText: '지정가',
                        suffixText: '원',
                        border: OutlineInputBorder(),
                      ),
                      validator: _positiveNumberValidator,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: TextFormField(
                      controller: _quantityController,
                      onChanged: (_) => _clearResult(),
                      enabled: !_loading,
                      keyboardType: const TextInputType.numberWithOptions(
                        decimal: true,
                      ),
                      inputFormatters: [_numberFormatter(4)],
                      decoration: const InputDecoration(
                        labelText: '수량',
                        suffixText: '주',
                        border: OutlineInputBorder(),
                      ),
                      validator: _positiveNumberValidator,
                    ),
                  ),
                ],
              ),
              if (_errorMessage != null) ...[
                const SizedBox(height: 10),
                Text(
                  _errorMessage!,
                  style: const TextStyle(
                    color: AppTheme.sub,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0,
                  ),
                ),
              ],
              const SizedBox(height: 14),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: _loading ? null : _runPrecheck,
                  icon: _loading
                      ? const SizedBox.square(
                          dimension: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.verified_user_outlined),
                  label: Text(_loading ? '검증 중' : '안전 조건 검증'),
                ),
              ),
              if (_result != null) ...[
                const SizedBox(height: 16),
                _OrderPrecheckResultCard(result: _result!),
                if (_result!.eligible && _approvalMessage == null) ...[
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: _loading ? null : _prepareApproval,
                      icon: const Icon(Icons.fact_check_outlined),
                      label: const Text('수동 승인 기록'),
                    ),
                  ),
                ],
              ],
              if (_approvalMessage != null) ...[
                const SizedBox(height: 10),
                TextBody(_approvalMessage!),
              ],
              const SizedBox(height: 12),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    Icons.lock_outline_rounded,
                    size: 18,
                    color: palette.muted,
                  ),
                  const SizedBox(width: 7),
                  Expanded(
                    child: Text(
                      '이 창은 승인 기록만 저장합니다. 실제 전송은 보유 탭의 KB 수동 주문에서 진행하세요.',
                      style: TextStyle(
                        color: palette.muted,
                        fontSize: 12,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 0,
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _runPrecheck() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _errorMessage = null;
      _result = null;
      _approvalMessage = null;
    });
    try {
      final result = await widget.repository.precheck(_currentInput());
      if (mounted) setState(() => _result = result);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _errorMessage = switch (error) {
          OrderPrecheckRepositoryException exception => exception.message,
          _ => '주문 사전검증에 실패했습니다.',
        };
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  OrderPrecheckInput _currentInput() => OrderPrecheckInput(
    stockCode: widget.holding.stockCode,
    stockName: widget.holding.stockName,
    market: widget.holding.market,
    side: _side == _OrderSide.buy ? 'BUY' : 'SELL',
    limitPrice: double.parse(_priceController.text.trim()),
    quantity: double.parse(_quantityController.text.trim()),
  );

  void _clearResult() {
    if (_result == null && _approvalMessage == null) return;
    setState(() {
      _result = null;
      _approvalMessage = null;
    });
  }

  Future<void> _prepareApproval() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _errorMessage = null;
      _approvalMessage = null;
    });
    try {
      final preparation = await widget.repository.prepareApproval(
        _currentInput(),
      );
      if (!mounted) return;
      setState(() {
        _result = preparation.precheck;
        _loading = false;
      });
      final reviewed = preparation.precheck;
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('수동 승인 기록'),
          content: Text(
            '${reviewed.stockName} ${reviewed.side == 'BUY' ? '매수' : '매도'} '
            '${_formatQuantity(reviewed.quantity)}주\n'
            '지정가 ${formatCurrency(reviewed.limitPrice.round())}원 · '
            '예상 ${formatCurrency(reviewed.estimatedAmount.round())}원\n\n'
            '방금 안전 조건을 다시 검증했습니다. 90초 이내에 승인하면 기록만 저장됩니다. '
            'KB증권에 실제 주문은 전송되지 않습니다.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('취소'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('기록 승인'),
            ),
          ],
        ),
      );
      if (confirmed != true || !mounted) return;
      setState(() => _loading = true);
      final message = await widget.repository.confirmApproval(preparation);
      if (mounted) setState(() => _approvalMessage = message);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _errorMessage = switch (error) {
          OrderPrecheckRepositoryException exception => exception.message,
          _ => '수동 승인 기록에 실패했습니다.',
        };
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String? _positiveNumberValidator(String? value) {
    final number = double.tryParse(value?.trim() ?? '');
    return number == null || number <= 0 ? '0보다 큰 값을 입력하세요.' : null;
  }

  TextInputFormatter _numberFormatter(int fractionDigits) {
    return FilteringTextInputFormatter.allow(
      RegExp('^\\d*\\.?\\d{0,$fractionDigits}'),
    );
  }
}

class _OrderPrecheckResultCard extends StatelessWidget {
  const _OrderPrecheckResultCard({required this.result});

  final OrderPrecheckResult result;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final resultColor = result.eligible
        ? const Color(0xff278b55)
        : AppTheme.sub;
    return AppCard(
      soft: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                result.eligible
                    ? Icons.check_circle_rounded
                    : Icons.block_rounded,
                color: resultColor,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: CardTitle(
                  result.eligible ? '사전검증 통과' : '주문안 차단',
                  fontSize: 18,
                ),
              ),
              Text(
                '#${result.orderPrecheckId}',
                style: TextStyle(
                  color: palette.muted,
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          TextBody(
            '${result.side == 'BUY' ? '매수' : '매도'} ${_formatQuantity(result.quantity)}주 · '
            '${formatCurrency(result.limitPrice.round())}원 · 예상 ${formatCurrency(result.estimatedAmount.round())}원',
          ),
          const SizedBox(height: 4),
          TextCaption(
            '${result.quoteProvider} 현재가 ${formatCurrency(result.currentPrice.round())}원 · '
            '이탈 ${result.priceDeviationRate.toStringAsFixed(1)}%',
          ),
          const AppDivider(),
          for (final check in result.checks) ...[
            _SafetyCheckRow(check: check),
            if (check != result.checks.last) const SizedBox(height: 10),
          ],
          const AppDivider(),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.lock_rounded, color: AppTheme.main, size: 18),
              const SizedBox(width: 7),
              Expanded(child: TextBody(result.submissionMessage)),
            ],
          ),
        ],
      ),
    );
  }
}

class _SafetyCheckRow extends StatelessWidget {
  const _SafetyCheckRow({required this.check});

  final OrderSafetyCheck check;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final color = check.passed ? const Color(0xff278b55) : AppTheme.sub;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(
          check.passed
              ? Icons.check_circle_outline_rounded
              : Icons.error_outline_rounded,
          color: color,
          size: 19,
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                check.label,
                style: TextStyle(
                  color: palette.text,
                  fontSize: 13,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                check.message,
                style: TextStyle(
                  color: palette.muted,
                  fontSize: 12,
                  height: 1.3,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

String _formatQuantity(double value) {
  if (value == value.roundToDouble()) return value.toInt().toString();
  return value
      .toStringAsFixed(4)
      .replaceFirst(RegExp(r'0+$'), '')
      .replaceFirst(RegExp(r'\.$'), '');
}
