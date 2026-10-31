import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/order_precheck.dart';
import '../repositories/order_precheck_repository.dart';
import '../repositories/manual_order_repository.dart';

/// 수동 주문 입력·명시적 전송 확인·접수 기록 및 체결 조회 화면입니다.
class ManualOrdersScreen extends StatefulWidget {
  const ManualOrdersScreen({
    super.key,
    required this.repository,
    required this.manual,
  });
  final OrderPrecheckRepository repository;
  final ManualOrderRepository manual;
  @override
  State<ManualOrdersScreen> createState() => _ManualOrdersScreenState();
}

class _ManualOrdersScreenState extends State<ManualOrdersScreen> {
  final _code = TextEditingController();
  final _name = TextEditingController();
  final _price = TextEditingController();
  final _quantity = TextEditingController(text: '1');
  String _market = 'KOSPI';
  String _side = 'BUY';
  bool _busy = false;
  bool _ready = false;
  bool _loaded = false;
  int? _awaitingApproval;
  String? _awaitingCommand;
  String? _message;
  List<ManualOrder> _orders = [];

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  @override
  void dispose() {
    for (final c in [_code, _name, _price, _quantity]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _refresh() async {
    setState(() {
      _busy = true;
      _loaded = false;
    });
    try {
      final orders = await widget.manual.manualOrderHistory();
      final ready = await widget.manual.manualOrderReady();
      if (mounted) {
        setState(() {
          _orders = orders;
          final resolved = orders.any(
            (c) =>
                ((_awaitingApproval != null &&
                        '${c.data['approvalId']}' == '$_awaitingApproval') ||
                    (_awaitingCommand != null && c.id == _awaitingCommand)) &&
                (c.status == 'ACCEPTED' || c.status == 'REJECTED'),
          );
          if (resolved) {
            _awaitingApproval = null;
            _awaitingCommand = null;
          }
          _ready = ready;
          _loaded = true;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _message = _safeError(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _safeError(Object e) => e is OrderPrecheckRepositoryException
      ? e.message
      : '처리 결과를 확인할 수 없습니다. 주문 기록과 KB 앱을 확인하세요.';

  bool get _pending =>
      _awaitingApproval != null ||
      _awaitingCommand != null ||
      _orders.any((c) => c.status == 'SENDING' || c.status == 'UNKNOWN');
  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !_busy,
    child: Scaffold(
      appBar: AppBar(
        title: const Text('KB 수동 주문'),
        actions: [
          IconButton(
            onPressed: _busy ? null : _refresh,
            tooltip: '주문 기록 새로고침',
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 900),
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              const Text('실제 계좌 주문입니다. 정규장 KRX 지정가만 지원합니다. 접수와 체결은 별도로 확인하세요.'),
              const SizedBox(height: 8),
              Text(
                _ready
                    ? '서버 설정 확인됨 · 전송 직전에 다시 검증합니다.'
                    : '전송 차단됨 · 설정 탭에서 실주문 준비 상태를 확인하세요.',
              ),
              if (_pending)
                const Text('확인되지 않은 전송이 있습니다. 새 주문을 중단하고 KB 앱에서 접수 여부를 확인하세요.'),
              if (_message != null)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  child: SelectableText(_message!),
                ),
              if (_busy) const LinearProgressIndicator(),
              const SizedBox(height: 16),
              Wrap(
                spacing: 12,
                runSpacing: 12,
                children: [
                  _field(_code, '종목코드 6자리', digits: true, width: 180),
                  _field(_name, '종목명', width: 220),
                  SizedBox(
                    width: 140,
                    child: DropdownButtonFormField<String>(
                      initialValue: _market,
                      decoration: const InputDecoration(labelText: '시장'),
                      items: ['KOSPI', 'KOSDAQ']
                          .map(
                            (s) => DropdownMenuItem(value: s, child: Text(s)),
                          )
                          .toList(),
                      onChanged: _busy
                          ? null
                          : (s) => setState(() => _market = s!),
                    ),
                  ),
                  SizedBox(
                    width: 120,
                    child: DropdownButtonFormField<String>(
                      initialValue: _side,
                      decoration: const InputDecoration(labelText: '방향'),
                      items: const [
                        DropdownMenuItem(value: 'BUY', child: Text('매수')),
                        DropdownMenuItem(value: 'SELL', child: Text('매도')),
                      ],
                      onChanged: _busy
                          ? null
                          : (s) => setState(() => _side = s!),
                    ),
                  ),
                  _field(_price, '지정가 (정수 원)', digits: true),
                  _field(_quantity, '수량 (정수 주)', digits: true),
                ],
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _busy || !_loaded || !_ready || _pending
                    ? null
                    : _newOrder,
                child: const Text('안전 조건 검증 및 주문안 확인'),
              ),
              const SizedBox(height: 24),
              const Text(
                '최근 전송·승인 기록 (최대 100건)',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
              ),
              if (_loaded && _orders.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(20),
                  child: Text('수동 주문 기록이 없습니다.'),
                ),
              for (final c in _orders)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SelectableText(
                          '${c.kind} · ${c.status}\n${c.summary}\n주문번호 ${c.orderNo.isEmpty ? '미확인' : c.orderNo}\n${c.data['orderDate']} · ${c.message}',
                        ),
                        Wrap(
                          spacing: 8,
                          children: [
                            TextButton(
                              onPressed: _busy
                                  ? null
                                  : () => _observations(c, false),
                              child: const Text('저장된 체결 조회 이력'),
                            ),
                            if (c.status == 'ACCEPTED')
                              TextButton(
                                onPressed: _busy
                                    ? null
                                    : () => _observations(c, true),
                                child: const Text('KB 체결 조회'),
                              ),
                            if (c.status == 'ACCEPTED' &&
                                c.kind == 'NEW' &&
                                !c.changeUsed) ...[
                              TextButton(
                                onPressed: _busy || !_ready || _pending
                                    ? null
                                    : () => _change(c, 'AMEND'),
                                child: const Text('지정가 인하'),
                              ),
                              TextButton(
                                onPressed: _busy || !_ready || _pending
                                    ? null
                                    : () => _change(c, 'CANCEL'),
                                child: const Text('전부 취소'),
                              ),
                            ],
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              const Text(
                '정정·취소는 당일 신규 접수 주문의 전량 미체결을 확인한 뒤 한 차례 지원합니다. '
                '가격 증액·부분체결·추가 정정은 KB 앱에서 처리하세요. 체결 조회는 앱 보유 목록·자본금을 자동 변경하지 않습니다.',
              ),
            ],
          ),
        ),
      ),
    ),
  );

  Widget _field(
    TextEditingController controller,
    String label, {
    bool digits = false,
    double width = 180,
  }) => SizedBox(
    width: width,
    child: TextField(
      controller: controller,
      enabled: !_busy,
      keyboardType: digits ? TextInputType.number : TextInputType.text,
      inputFormatters: digits ? [FilteringTextInputFormatter.digitsOnly] : null,
      decoration: InputDecoration(
        labelText: label,
        border: const OutlineInputBorder(),
      ),
    ),
  );

  Future<bool> _review(
    String title,
    String summary, {
    bool actual = false,
  }) async {
    if (!mounted) return false;
    bool checked = false;
    return await showDialog<bool>(
          context: context,
          barrierDismissible: false,
          builder: (context) => StatefulBuilder(
            builder: (context, update) => AlertDialog(
              title: Text(title),
              content: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      '$summary\n\n${actual ? '확인하면 실제 KB 계좌에 한 번 전송합니다. 네트워크 오류가 나도 다시 전송하지 마세요.' : '승인 기록만 저장합니다. 실제 전송은 다음 확인 단계에서 진행합니다.'}',
                    ),
                    if (actual)
                      CheckboxListTile(
                        value: checked,
                        onChanged: (v) => update(() => checked = v ?? false),
                        title: const Text('실제 계좌 주문임을 확인했습니다.'),
                      ),
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context, false),
                  child: const Text('취소'),
                ),
                FilledButton(
                  onPressed: !actual || checked
                      ? () => Navigator.pop(context, true)
                      : null,
                  child: Text(actual ? '실제 주문 전송' : '승인 기록 저장'),
                ),
              ],
            ),
          ),
        ) ??
        false;
  }

  Future<void> _newOrder() async {
    final price = int.tryParse(_price.text);
    final quantity = int.tryParse(_quantity.text);
    if (!RegExp(r'^\d{6}$').hasMatch(_code.text) ||
        _name.text.trim().isEmpty ||
        price == null ||
        price <= 0 ||
        quantity == null ||
        quantity <= 0) {
      setState(() => _message = '6자리 종목코드·종목명·양수 정수 지정가와 수량을 입력하세요.');
      return;
    }
    setState(() {
      _busy = true;
      _message = null;
    });
    bool attempted = false;
    try {
      final prepared = await widget.repository.prepareApproval(
        OrderPrecheckInput(
          stockCode: _code.text,
          stockName: _name.text.trim(),
          market: _market,
          side: _side,
          limitPrice: price.toDouble(),
          quantity: quantity.toDouble(),
        ),
      );
      final r = prepared.precheck;
      final summary =
          '${r.stockName} (${r.stockCode}) · ${r.market} · ${r.side == 'BUY' ? '매수' : '매도'}\n'
          '지정가 ${r.limitPrice}원 · ${r.quantity}주 · 예상 ${r.estimatedAmount}원';
      if (!await _review('주문안 승인', summary) || !mounted) return;
      await widget.repository.confirmApproval(prepared);
      if (!await _review('실제 주문 최종 확인', summary, actual: true) || !mounted) {
        return;
      }
      attempted = true;
      _awaitingApproval = prepared.approvalId;
      final result = await widget.manual.submitManualOrder(prepared.approvalId);
      if (result.status == 'ACCEPTED' || result.status == 'REJECTED') {
        _awaitingApproval = null;
      }
      if (mounted) {
        setState(() => _message = '${result.status} · ${result.message}');
      }
    } catch (e) {
      if (mounted) {
        setState(
          () => _message = attempted
              ? '전송 결과를 확인하지 못했습니다. 재전송하지 말고 주문 기록을 새로고침하고 KB 앱에서 확인하세요.\n승인 기록은 서버에 보존됩니다.'
              : _safeError(e),
        );
      }
    } finally {
      if (mounted) await _refresh();
    }
  }

  Future<void> _observations(ManualOrder c, bool fresh) async {
    setState(() => _busy = true);
    try {
      if (fresh) await widget.manual.observeManualOrder(c.id);
      final items = await widget.manual.manualOrderObservations(c.id);
      if (mounted) {
        setState(
          () => _message = items.isEmpty
              ? '저장된 체결 조회가 없습니다.'
              : items
                    .map(
                      (o) =>
                          '${o['checkedAt']} · ${o['status']} · 전체 조회 ${o['completeScan']} · 체결 ${o['filledQuantity'] ?? '미확인'} / 미체결 ${o['openQuantity'] ?? '미확인'}',
                    )
                    .join('\n'),
        );
      }
    } catch (e) {
      if (mounted) setState(() => _message = _safeError(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _change(ManualOrder c, String kind) async {
    int? price;
    if (kind == 'AMEND') {
      var input = c.price.toInt().toString();
      final text = await showDialog<String>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('새 지정가 (인하만 지원)'),
          content: TextFormField(
            initialValue: input,
            onChanged: (v) => input = v,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly],
            keyboardType: TextInputType.number,
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('취소'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, input),
              child: const Text('주문안 조회'),
            ),
          ],
        ),
      );
      if (text == null || !mounted) return;
      price = int.tryParse(text);
      if (price == null || price <= 0) return;
    }
    if (!mounted) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    bool attempted = false;
    try {
      final preparation = await widget.manual.prepareManualChange(
        c.id,
        kind,
        price,
      );
      final child = ManualOrder(preparation['command'] as Map<String, dynamic>);
      if (!await _review(
            kind == 'AMEND' ? '실제 지정가 인하' : '실제 전부 취소',
            '원주문 ${c.orderNo}\n${child.summary}\n90초 이내 확인 · 전량 미체결을 다시 조회합니다.',
            actual: true,
          ) ||
          !mounted) {
        return;
      }
      attempted = true;
      _awaitingCommand = child.id;
      final result = await widget.manual.submitManualChange(
        child.id,
        preparation['token'] as String,
      );
      if (result.status == 'ACCEPTED' || result.status == 'REJECTED') {
        _awaitingCommand = null;
      }
      if (mounted) {
        setState(() => _message = '${result.status} · ${result.message}');
      }
    } catch (e) {
      if (mounted) {
        setState(
          () => _message = attempted
              ? '전송 결과를 확인하지 못했습니다. 같은 정정·취소를 반복하지 말고 주문 기록과 KB 앱에서 확인하세요.'
              : _safeError(e),
        );
      }
    } finally {
      if (mounted) await _refresh();
    }
  }
}
