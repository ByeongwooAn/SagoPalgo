import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../repositories/order_simulation_repository.dart';
import 'order_diagnostics_screen.dart';
import 'unknown_order_review_screen.dart';

/// 고정 가정 시세와 가상 현금으로 주문 실패/체결 순서를 수동 시험합니다.
class OrderSimulationScreen extends StatefulWidget {
  const OrderSimulationScreen({super.key, required this.repository});
  final OrderSimulationRepository repository;
  @override
  State<OrderSimulationScreen> createState() => _OrderSimulationScreenState();
}

class _OrderSimulationScreenState extends State<OrderSimulationScreen> {
  final _code = TextEditingController(text: '005930');
  final _name = TextEditingController(text: '삼성전자');
  final _price = TextEditingController(text: '75000');
  final _quantity = TextEditingController(text: '2');
  String _market = 'KOSPI';
  String _side = 'BUY';
  String _scenario = 'WAIT';
  bool _busy = false;
  bool _uncertainRequest = false;
  String? _awaitingCommandId;
  String? _message;
  Map<String, dynamic>? _state;
  List<Map<String, dynamic>> _sessions = [];
  static const scenarios = {
    'WAIT': '미체결 대기',
    'PARTIAL_FILL': '부분체결',
    'FULL_FILL': '전량 체결',
    'REJECT': '명시적 거절',
    'TIMEOUT_BEFORE_ACCEPT': '접수 전 응답 유실',
    'TIMEOUT_AFTER_ACCEPT': '접수 후 응답 유실',
    'SAVE_FAILURE': '접수 후 결과 저장 실패',
    'STOP_BEFORE_SEND': '전송 예약 직후 중단',
    'JOURNAL_FAILURE': '접수 후 반환 기록 실패',
    'TIMEOUT_AFTER_OPEN': '미체결 접수 후 응답 유실',
    'TIMEOUT_AFTER_PARTIAL': '부분체결 후 응답 유실',
  };
  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    for (final c in [_code, _name, _price, _quantity]) {
      c.dispose();
    }
    super.dispose();
  }

  String get _id => _state!['sessionId'] as String;
  Future<void> _load() async {
    setState(() => _busy = true);
    try {
      final sessions = await widget.repository.simulationSessions();
      Map<String, dynamic>? state = _state;
      if (state != null) {
        state = await widget.repository.simulation(_id);
      } else if (sessions.isNotEmpty) {
        state = await widget.repository.simulation(
          sessions.first['sessionId'] as String,
        );
      }
      if (mounted) {
        setState(() {
          _sessions = sessions;
          _state = state;
          final resolved = (state?['commands'] as List? ?? []).any(
            (c) =>
                c['id'] == _awaitingCommandId &&
                (['ACCEPTED', 'REJECTED'].contains(c['status']) ||
                    (c['resolved'] == true &&
                        c['completion'] is Map &&
                        c['completion']['source'] == 'SIMULATION')),
          );
          if (resolved) {
            _uncertainRequest = false;
            _awaitingCommandId = null;
          }
        });
      }
    } catch (e) {
      if (mounted) setState(() => _message = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _create() async {
    var cash = '10000000';
    final value = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('새 가상 주문 세션'),
        content: TextFormField(
          initialValue: cash,
          onChanged: (value) => cash = value,
          keyboardType: TextInputType.number,
          inputFormatters: [FilteringTextInputFormatter.digitsOnly],
          decoration: const InputDecoration(labelText: '가상 시작 현금 (원)'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, cash),
            child: const Text('가상 세션 만들기'),
          ),
        ],
      ),
    );
    final amount = num.tryParse(value ?? '');
    if (amount == null || !mounted) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final state = await widget.repository.createSimulation(amount);
      if (mounted) {
        setState(() {
          _state = state;
          _uncertainRequest = false;
          _awaitingCommandId = null;
        });
      }
      await _load();
    } catch (e) {
      if (mounted) setState(() => _message = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = _state;
    final selectedId = state?['sessionId'] as String?;
    final commands = (state?['commands'] as List? ?? [])
        .cast<Map<String, dynamic>>()
        .reversed;
    final blocked = state?['blocked'] == true || _uncertainRequest;
    return PopScope(
      canPop: !_busy,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('주문 시뮬레이션'),
          actions: [
            IconButton(
              onPressed: _busy ? null : _load,
              tooltip: '모의 세션 새로고침',
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
        body: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1000),
            child: ListView(
              padding: const EdgeInsets.all(20),
              children: [
                const Text(
                  'SIMULATION · 실제 주문 전송 없음',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 20),
                ),
                const Text(
                  '가상 현금·가정 시세·수동 체결을 사용합니다. 기존 AI 모의매매와 실계좌 기록은 별도입니다. 실제 KB 모의투자 서버가 아닙니다.',
                ),
                if (_busy) const LinearProgressIndicator(),
                if (_message != null)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    child: SelectableText(_message!),
                  ),
                Wrap(
                  spacing: 12,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    FilledButton.icon(
                      onPressed: _busy ? null : _create,
                      icon: const Icon(Icons.add),
                      label: const Text('새 가상 세션'),
                    ),
                    if (_sessions.isNotEmpty)
                      SizedBox(
                        width: 280,
                        child: DropdownButton<String>(
                          isExpanded: true,
                          value:
                              _sessions.any((s) => s['sessionId'] == selectedId)
                              ? selectedId
                              : null,
                          hint: const Text('저장 세션 선택'),
                          items: _sessions
                              .map(
                                (s) => DropdownMenuItem<String>(
                                  value: s['sessionId'] as String,
                                  child: Text(
                                    '${s['createdAt']} · ${(s['sessionId'] as String).split('-').first}',
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                              )
                              .toList(),
                          onChanged: _busy
                              ? null
                              : (id) async {
                                  if (id == null) return;
                                  setState(() => _busy = true);
                                  try {
                                    final loaded = await widget.repository
                                        .simulation(id);
                                    if (mounted) {
                                      setState(() {
                                        _state = loaded;
                                        _uncertainRequest = false;
                                        _awaitingCommandId = null;
                                      });
                                    }
                                  } catch (e) {
                                    if (mounted) {
                                      setState(() => _message = '$e');
                                    }
                                  } finally {
                                    if (mounted) setState(() => _busy = false);
                                  }
                                },
                        ),
                      ),
                  ],
                ),
                if (state != null) ...[
                  const SizedBox(height: 12),
                  SelectableText(
                    '가상 현금 ${state['cash']}원 · 예약 제외 사용 가능 ${state['availableCash']}원\n가상 보유 ${state['positions']}\n가정 시세 ${state['quotes']}',
                  ),
                  if (blocked)
                    const Text(
                      '미확정 모의 전송 또는 응답 유실로 새 전송을 차단했습니다. 기록은 보존됩니다. 다른 시나리오는 새 세션에서 실행하세요.',
                    ),
                  const SizedBox(height: 16),
                  Wrap(
                    spacing: 10,
                    runSpacing: 12,
                    children: [
                      _field(_code, '종목코드', 160),
                      _field(_name, '종목명', 180, digits: false),
                      SizedBox(
                        width: 130,
                        child: DropdownButtonFormField<String>(
                          isExpanded: true,
                          initialValue: _market,
                          decoration: const InputDecoration(labelText: '시장'),
                          items: ['KOSPI', 'KOSDAQ']
                              .map(
                                (m) =>
                                    DropdownMenuItem(value: m, child: Text(m)),
                              )
                              .toList(),
                          onChanged: _busy
                              ? null
                              : (m) => setState(() => _market = m!),
                        ),
                      ),
                      SizedBox(
                        width: 100,
                        child: DropdownButtonFormField<String>(
                          isExpanded: true,
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
                      _field(_price, '지정가 / 가정 시세', 170),
                      _field(_quantity, '정수 수량', 130),
                    ],
                  ),
                  Wrap(
                    spacing: 12,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      SizedBox(
                        width: 280,
                        child: DropdownButton<String>(
                          isExpanded: true,
                          value: _scenario,
                          items: scenarios.entries
                              .map(
                                (e) => DropdownMenuItem(
                                  value: e.key,
                                  child: Text(
                                    e.value,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                              )
                              .toList(),
                          onChanged: _busy
                              ? null
                              : (s) => setState(() => _scenario = s!),
                        ),
                      ),
                      OutlinedButton(
                        onPressed: _busy ? null : _quote,
                        child: const Text('입력 가격을 가정 시세로 저장'),
                      ),
                    ],
                  ),
                  FilledButton(
                    onPressed: _busy || blocked ? null : () => _order(),
                    child: const Text('모의 주문 검증·승인'),
                  ),
                  const SizedBox(height: 20),
                  for (final c in commands)
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            SelectableText(
                              '${c['kind']} · ${c['status']}${c['expired'] == true ? ' (승인 만료)' : ''} · ${scenarios[c['scenario']]}\n${_summary(c['plan'] as Map<String, dynamic>)}\n'
                              '모의 전송 ${c['sendCount']}회 · 가상 증권사 ${c['brokerStatus']} · 번호 ${c['brokerOrderNo']}\n체결 ${c['filledQuantity']}주 / 미체결 ${c['openQuantity']}주',
                            ),
                            if (c['resolved'] == true)
                              const Text('가상 종결 확인 · UNKNOWN 원본 보존'),
                            Text(
                              '전송 단계 ${c['dispatchPhase'] ?? 'LEGACY_UNVERIFIED'} · 저장 결과 ${c['receipt'] ?? '없음'}',
                            ),
                            if (c['recoveredAt'] != null)
                              Text('기록 복구 ${c['recoveredAt']}'),
                            if (c['status'] == 'SENDING' &&
                                c['recoverable'] != true)
                              const Text(
                                '호출 종료 결과가 없어 차단을 유지합니다. 시간이 지나도 자동 해제하지 않습니다.',
                              ),
                            Wrap(
                              spacing: 8,
                              children: [
                                if (c['status'] == 'UNKNOWN' &&
                                    c['resolved'] != true)
                                  TextButton(
                                    onPressed: _busy
                                        ? null
                                        : () => _unknownReview(
                                            c,
                                            true,
                                            terminal: true,
                                          ),
                                    child: const Text('가상 주문 종결 대조'),
                                  ),
                                if (c['resolved'] == true)
                                  TextButton(
                                    onPressed: _busy
                                        ? null
                                        : () => _unknownReview(
                                            c,
                                            false,
                                            terminal: true,
                                          ),
                                    child: const Text('가상 종결 이력'),
                                  ),
                                if (c['status'] == 'UNKNOWN' &&
                                    c['resolved'] != true)
                                  TextButton(
                                    onPressed: _busy
                                        ? null
                                        : () => _unknownReview(c, true),
                                    child: const Text('미체결·변경 주문 대조'),
                                  ),
                                if ((c['reviews'] as List? ?? []).isNotEmpty)
                                  TextButton(
                                    onPressed: _busy
                                        ? null
                                        : () => _unknownReview(c, false),
                                    child: const Text('저장된 대조 관찰'),
                                  ),
                                if (c['recoverable'] == true)
                                  TextButton(
                                    onPressed: _busy ? null : () => _recover(c),
                                    child: const Text('기록으로 결과 복구'),
                                  ),
                                if (c['status'] == 'SENDING' &&
                                    c['dispatchPhase'] != 'RETURNED')
                                  TextButton(
                                    onPressed: _busy
                                        ? null
                                        : () => _diagnostics(c, true),
                                    child: const Text('가상 주문번호로 잠금 유지 진단'),
                                  ),
                                if ((c['diagnostics'] as List? ?? [])
                                    .isNotEmpty)
                                  TextButton(
                                    onPressed: _busy
                                        ? null
                                        : () => _diagnostics(c, false),
                                    child: const Text('저장된 진단 이력'),
                                  ),
                                if (num.parse('${c['openQuantity']}') > 0) ...[
                                  TextButton(
                                    onPressed: _busy ? null : () => _fill(c, 1),
                                    child: const Text('1주 가상 체결'),
                                  ),
                                  TextButton(
                                    onPressed: _busy
                                        ? null
                                        : () => _fill(
                                            c,
                                            num.parse('${c['openQuantity']}'),
                                          ),
                                    child: const Text('잔량 가상 체결'),
                                  ),
                                ],
                                if (c['status'] == 'ACCEPTED' &&
                                    c['kind'] == 'NEW' &&
                                    c['changed'] != true) ...[
                                  TextButton(
                                    onPressed: _busy || blocked
                                        ? null
                                        : () =>
                                              _order(parent: c, kind: 'AMEND'),
                                    child: const Text('지정가 변경 검토'),
                                  ),
                                  TextButton(
                                    onPressed: _busy || blocked
                                        ? null
                                        : () =>
                                              _order(parent: c, kind: 'CANCEL'),
                                    child: const Text('전부 취소 검토'),
                                  ),
                                ],
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),
                  const SizedBox(height: 16),
                  const Text('세션 이벤트 (서버에 저장 · 최근 순서)'),
                  for (final e in (state['events'] as List).reversed)
                    Text('${e['at']} · ${e['message']}'),
                ],
                if (state == null && !_busy)
                  const Padding(
                    padding: EdgeInsets.all(16),
                    child: Text('새 가상 세션을 만들어 주문 상태를 시험하세요.'),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _field(
    TextEditingController controller,
    String label,
    double width, {
    bool digits = true,
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

  Map<String, dynamic> _plan() => {
    'stockCode': _code.text.trim(),
    'stockName': _name.text.trim(),
    'market': _market,
    'side': _side,
    'limitPrice': num.parse(_price.text),
    'quantity': num.parse(_quantity.text),
  };
  String _summary(Map<String, dynamic> p) =>
      '${p['stockName']} (${p['stockCode']}) · ${p['market']} · ${p['side'] == 'BUY' ? '매수' : '매도'}\n'
      '지정가 ${p['limitPrice']}원 · ${p['quantity']}주';
  Future<void> _quote() async {
    await _mutation(
      () => widget.repository.simulationAction(_id, 'quotes', {
        'stockCode': _code.text.trim(),
        'market': _market,
        'price': num.parse(_price.text),
      }),
    );
  }

  Future<void> _fill(Map<String, dynamic> c, num quantity) async => _mutation(
    () => widget.repository.simulationAction(
      _id,
      'orders/${c['brokerOrderNo']}/fill',
      {'quantity': quantity},
    ),
  );
  Future<void> _unknownReview(
    Map<String, dynamic> c,
    bool allowNew, {
    bool terminal = false,
  }) async {
    final session = _id;
    setState(() => _busy = true);
    try {
      await Navigator.of(context).push<void>(
        MaterialPageRoute(
          builder: (_) => UnknownOrderReviewScreen(
            summary: _summary(c['plan'] as Map<String, dynamic>),
            simulation: true,
            terminal: terminal,
            allowNew: allowNew,
            load: () async {
              final state = await widget.repository.simulation(session);
              final command = (state['commands'] as List)
                  .cast<Map<String, dynamic>>()
                  .firstWhere((r) => r['id'] == c['id']);
              if (terminal) {
                final completion = command['completion'];
                if (command['resolved'] != true ||
                    completion is! Map ||
                    completion['source'] != 'SIMULATION') {
                  return <Map<String, dynamic>>[];
                }
                return [
                  {
                    ...Map<String, dynamic>.from(completion),
                    'reviewId': completion['resolutionId'],
                  },
                ];
              }
              return (command['reviews'] as List? ?? [])
                  .cast<Map<String, dynamic>>();
            },
            prepare: (number) async {
              final result = await widget.repository.simulationAction(
                session,
                'commands/${c['id']}/${terminal ? 'completion' : 'reviews'}/prepare',
                {'orderNo': number},
              );
              return terminal
                  ? {...result, 'reviewId': result['resolutionId']}
                  : result;
            },
            confirm: (id, token) async {
              await widget.repository.simulationAction(
                session,
                'commands/${c['id']}/${terminal ? 'completion' : 'reviews'}/confirm',
                {
                  if (terminal) 'resolutionId': id else 'reviewId': id,
                  'token': token,
                  'acknowledged': true,
                  'confirmation': terminal ? '가상 주문 종결 확정' : '잠금 유지 대조 저장',
                },
              );
            },
          ),
        ),
      );
    } finally {
      if (mounted) await _load();
    }
  }

  Future<void> _diagnostics(Map<String, dynamic> command, bool allowNew) async {
    final session = _id;
    setState(() => _busy = true);
    try {
      await Navigator.of(context).push<void>(
        MaterialPageRoute(
          builder: (_) => OrderDiagnosticsScreen(
            simulation: true,
            summary: _summary(command['plan'] as Map<String, dynamic>),
            allowNew: allowNew,
            load: () async {
              final snapshot = await widget.repository.simulation(session);
              final c = (snapshot['commands'] as List)
                  .cast<Map<String, dynamic>>()
                  .firstWhere((c) => c['id'] == command['id']);
              return (c['diagnostics'] as List? ?? [])
                  .cast<Map<String, dynamic>>();
            },
            diagnose: (id, number) => widget.repository.simulationAction(
              session,
              'commands/${command['id']}/diagnostics',
              {
                'diagnosticId': id,
                'orderNo': number,
                'acknowledged': true,
                'confirmation': '잠금 유지 진단',
              },
            ),
          ),
        ),
      );
    } finally {
      if (mounted) await _load();
    }
  }

  Future<void> _recover(Map<String, dynamic> command) async {
    setState(() => _busy = true);
    try {
      final confirmed = await _review(
        '모의 전송 결과 복구',
        '${_summary(command['plan'] as Map<String, dynamic>)}\n저장 결과 ${command['receipt']}\n추가 전송·가상 체결 없이 상태만 복구합니다. UNKNOWN은 계속 차단됩니다.',
        finalStep: true,
        actionLabel: '기록으로 결과 복구',
        acknowledgement: '추가 주문 전송 없이 저장 결과만 복구함을 확인했습니다.',
      );
      if (confirmed && mounted) {
        await _mutation(
          () => widget.repository.simulationAction(
            _id,
            'commands/${command['id']}/recover',
            {'acknowledged': true, 'confirmation': '저장된 전송 결과 복구'},
          ),
        );
      }
    } finally {
      if (mounted) await _load();
    }
  }

  Future<void> _mutation(Future<Map<String, dynamic>> Function() action) async {
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final state = await action();
      if (mounted) setState(() => _state = state);
    } catch (e) {
      if (mounted) {
        setState(() => _message = '$e\n요청을 자동 반복하지 않습니다. 새로고침으로 저장 상태를 확인하세요.');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<bool> _review(
    String title,
    String text, {
    bool finalStep = false,
    String? actionLabel,
    String? acknowledgement,
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
                    Text(text),
                    if (finalStep)
                      CheckboxListTile(
                        value: checked,
                        onChanged: (v) => update(() => checked = v ?? false),
                        title: Text(
                          acknowledgement ?? '가상 계좌의 모의 전송임을 확인했습니다.',
                        ),
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
                  onPressed: !finalStep || checked
                      ? () => Navigator.pop(context, true)
                      : null,
                  child: Text(
                    actionLabel ?? (finalStep ? '모의 주문 전송' : '모의 승인 기록 저장'),
                  ),
                ),
              ],
            ),
          ),
        ) ??
        false;
  }

  Future<void> _order({
    Map<String, dynamic>? parent,
    String kind = 'NEW',
  }) async {
    Map<String, dynamic> plan;
    try {
      plan = parent == null
          ? _plan()
          : Map<String, dynamic>.from(parent['plan'] as Map);
      if (kind == 'AMEND') {
        var input = '${plan['limitPrice']}';
        final value = await showDialog<String>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('모의 새 지정가'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '기존 지정가 ${plan['limitPrice']}원 · 수량 ${plan['quantity']}주 유지',
                ),
                const Text(
                  '매수 증액은 기존 예약금을 합산하지 않고 새 주문 전체 금액 이상의 가용 가상 현금이 필요합니다.',
                ),
                TextFormField(
                  initialValue: input,
                  onChanged: (v) => input = v,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('취소'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(context, input),
                child: const Text('검증'),
              ),
            ],
          ),
        );
        if (value == null || !mounted) return;
        final amended = num.parse(value);
        if (amended <= 0 || amended == plan['limitPrice']) {
          setState(() => _message = '새 지정가는 기존과 다른 양수 가격이어야 합니다.');
          return;
        }
        plan['limitPrice'] = amended;
      }
    } catch (_) {
      setState(() => _message = '종목·시장·방향·정수 지정가와 수량을 확인하세요.');
      return;
    }
    if (!mounted) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final prepared = await widget.repository.simulationAction(
        _id,
        'commands/prepare',
        {
          'plan': plan,
          'kind': kind,
          'parentId': parent?['id'],
          'scenario': _scenario,
        },
      );
      final commandId = prepared['commandId'] as String;
      if (mounted) {
        setState(() => _state = prepared['snapshot'] as Map<String, dynamic>);
      }
      final summary =
          '${_summary(plan)}\n${kind == 'AMEND' ? '지정가 ${parent!['plan']['limitPrice']}원 → ${plan['limitPrice']}원\n' : ''}$kind · ${scenarios[_scenario]}\n90초 안에 승인하세요. 실제 계좌에는 전송하지 않습니다.';
      if (!await _review('모의 주문안 승인', summary) || !mounted) return;
      final confirmed = await widget.repository.simulationAction(
        _id,
        'commands/$commandId/confirm',
        {'token': prepared['token'], 'acknowledged': true},
      );
      if (mounted) setState(() => _state = confirmed);
      if (!await _review('모의 전송 최종 확인', summary, finalStep: true) || !mounted) {
        return;
      }
      _uncertainRequest = true;
      _awaitingCommandId = commandId;
      final result = await widget.repository.simulationAction(
        _id,
        'commands/$commandId/submit',
        {'acknowledged': true, 'confirmation': '모의 주문 전송'},
      );
      if (mounted) {
        setState(() {
          _state = result;
          _uncertainRequest = false;
          _awaitingCommandId = null;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _message = '$e\n요청을 자동 반복하지 않습니다. 기록을 새로고침하세요.');
      }
    } finally {
      if (mounted) {
        await _load();
      }
    }
  }
}
