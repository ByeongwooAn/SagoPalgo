import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class UnknownOrderReviewScreen extends StatefulWidget {
  const UnknownOrderReviewScreen({
    super.key,
    required this.summary,
    required this.load,
    required this.prepare,
    required this.confirm,
    this.simulation = false,
    this.allowNew = true,
  });
  final String summary;
  final Future<List<Map<String, dynamic>>> Function() load;
  final Future<Map<String, dynamic>> Function(String orderNo) prepare;
  final Future<void> Function(String reviewId, String token) confirm;
  final bool simulation;
  final bool allowNew;
  @override
  State<UnknownOrderReviewScreen> createState() =>
      _UnknownOrderReviewScreenState();
}

class _UnknownOrderReviewScreenState extends State<UnknownOrderReviewScreen> {
  final _number = TextEditingController();
  bool _busy = false, _loaded = false, _checked = false;
  String? _waitingId, _message;
  Map<String, dynamic>? _preparation;
  List<Map<String, dynamic>> _history = [];
  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _number.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _busy = true);
    try {
      final history = await widget.load();
      if (mounted) {
        setState(() {
          _history = history;
          _loaded = true;
          if (history.any((r) => r['reviewId'] == _waitingId)) {
            _waitingId = null;
          }
        });
      }
    } catch (e) {
      if (mounted) setState(() => _message = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _prepare() async {
    setState(() {
      _busy = true;
      _message = null;
      _checked = false;
    });
    try {
      final value = await widget.prepare(_number.text);
      if (mounted) setState(() => _preparation = value);
    } catch (e) {
      if (mounted) setState(() => _message = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _confirm() async {
    final prepared = _preparation!;
    setState(() {
      _busy = true;
      _message = null;
      _waitingId = prepared['reviewId'] as String;
      _preparation = null;
      _checked = false;
    });
    try {
      await widget.confirm(
        prepared['reviewId'] as String,
        prepared['token'] as String,
      );
      if (mounted) {
        setState(() => _message = '대조 관찰을 저장했습니다. UNKNOWN·전송 차단은 유지됩니다.');
      }
    } catch (e) {
      if (mounted) {
        setState(() => _message = '$e\n확인 요청을 자동 반복하지 않습니다. 이력을 새로고침하세요.');
      }
    } finally {
      if (mounted) await _load();
    }
  }

  Widget _evidence(Map<String, dynamic> e) => SelectableText(
    '${e['kind']} · ${switch (e['observation']) {
      'OPEN' => '미체결 관찰',
      'PARTIAL' => '부분체결 관찰',
      _ => '변경 주문 연결 근거 · 완료 미확정',
    }}\n'
    '${e['stockCode']} · ${e['side']} · 지정가 ${e['price']} · 주문 ${e['quantity']}주\n'
    '체결 ${e['filledQuantity']}주 · 미체결 ${e['openQuantity']}주\n'
    '주문일 ${e['orderDate']} · 번호 ${e['orderNo']} · 시각 ${e['orderTime']}\n'
    '원주문 ${e['originalOrderNo'] == '' ? '없음' : e['originalOrderNo']} · 구분 원문 ${e['changeCode'] == '' ? '없음' : e['changeCode']}\n'
    '정정 수량 ${e['correctedQuantity'] ?? '미제공'} · SOR 취소 수량 ${e['sorCancelledQuantity'] ?? '미제공'}',
  );
  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !_busy,
    child: Scaffold(
      appBar: AppBar(
        title: const Text('UNKNOWN 대조 관찰'),
        actions: [
          IconButton(
            onPressed: _busy ? null : _load,
            tooltip: '대조 관찰 이력 새로고침',
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
              if (widget.simulation) const Text('SIMULATION · 실제 KB 조회·주문 없음'),
              SelectableText(widget.summary),
              const Text(
                '미체결·부분체결과 정정·취소의 조회 근거를 대조합니다. 관찰 저장은 전송 차단을 해제하지 않습니다. 신규 주문 전량 체결은 기존 전량 체결 대조를 사용하세요.',
              ),
              if (_busy) const LinearProgressIndicator(),
              if (_message != null)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  child: SelectableText(_message!),
                ),
              if (_waitingId != null)
                const Text(
                  '확인 결과를 이력에서 확인 중입니다. 자동 반복하지 않습니다. 새 대조가 필요하면 이 화면을 다시 열어 새로 준비하세요.',
                ),
              if (widget.allowNew && _preparation == null) ...[
                TextField(
                  controller: _number,
                  enabled: !_busy && _waitingId == null,
                  maxLength: 10,
                  onChanged: (_) => setState(() {}),
                  keyboardType: TextInputType.number,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  decoration: InputDecoration(
                    labelText: widget.simulation
                        ? '가상 주문번호 10자리'
                        : 'KB 앱에서 확인한 주문번호 10자리',
                  ),
                ),
                FilledButton(
                  onPressed:
                      _busy ||
                          !_loaded ||
                          _waitingId != null ||
                          !RegExp(r'^\d{10}$').hasMatch(_number.text) ||
                          RegExp(r'^0+$').hasMatch(_number.text)
                      ? null
                      : _prepare,
                  child: const Text('읽기 전용 대조 준비'),
                ),
              ],
              if (_preparation != null)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _evidence(
                          _preparation!['evidence'] as Map<String, dynamic>,
                        ),
                        Text('확인 기한 ${_preparation!['expiresAt']} · 90초 이내'),
                        const Text(
                          '저장 직전에 다시 조회합니다. 체결·잔량·변경 근거가 달라지면 다시 준비해야 합니다. 원래 UNKNOWN과 가드를 보존합니다.',
                        ),
                        CheckboxListTile(
                          value: _checked,
                          onChanged: _busy
                              ? null
                              : (v) => setState(() => _checked = v ?? false),
                          title: const Text(
                            '해당 원주문과 관찰 내용을 확인했고 전송 차단이 유지됨을 이해했습니다.',
                          ),
                        ),
                        Wrap(
                          spacing: 8,
                          children: [
                            TextButton(
                              onPressed: _busy
                                  ? null
                                  : () => setState(() {
                                      _preparation = null;
                                      _checked = false;
                                    }),
                              child: const Text('준비 취소'),
                            ),
                            FilledButton(
                              onPressed: _busy || !_checked ? null : _confirm,
                              child: const Text('대조 관찰 저장'),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              const SizedBox(height: 20),
              const Text('저장된 대조 관찰 · 당시 조회이며 현재 체결 확정 아님'),
              if (_loaded && _history.isEmpty) const Text('저장된 대조 관찰이 없습니다.'),
              for (final r in _history)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('저장 ${r['confirmedAt']} · 전송 차단 유지'),
                        _evidence(r['evidence'] as Map<String, dynamic>),
                      ],
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    ),
  );
}
