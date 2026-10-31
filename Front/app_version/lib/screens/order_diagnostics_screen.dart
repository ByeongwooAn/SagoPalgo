import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// 실주문/시뮬레이터 공통 읽기 전용 진단 화면. 상태 변경·전송·재시도 액션은 제공하지 않습니다.
class OrderDiagnosticsScreen extends StatefulWidget {
  const OrderDiagnosticsScreen({
    super.key,
    required this.summary,
    required this.load,
    required this.diagnose,
    this.simulation = false,
    this.allowNew = true,
  });
  final String summary;
  final Future<List<Map<String, dynamic>>> Function() load;
  final Future<Map<String, dynamic>> Function(String id, String orderNo)
  diagnose;
  final bool simulation;
  final bool allowNew;
  @override
  State<OrderDiagnosticsScreen> createState() => _OrderDiagnosticsScreenState();
}

class _OrderDiagnosticsScreenState extends State<OrderDiagnosticsScreen> {
  final _number = TextEditingController();
  bool _busy = false;
  bool _checked = false;
  bool _loaded = false;
  String? _attempt;
  String? _message;
  List<Map<String, dynamic>> _history = [];
  static const labels = {
    'FIELDS_MATCH': '주문 항목 일치 · 전송 종료 확정 아님',
    'NOT_FOUND': '조회 결과 없음 · 미접수 확정 아님',
    'INCOMPLETE': '전체 조회 미완료',
    'AMBIGUOUS': '중복·불명확한 조회 결과',
    'MISMATCH': '주문 항목 불일치',
    'LOOKUP_FAILED': '조회 실패',
    'ACCOUNT_CHANGED': '조회 도중 계좌 설정 변경',
    'CHANGE_REQUIRES_REVIEW': '정정·취소는 별도 대조 필요',
  };
  static const checkLabels = {
    'REQUEST_SCOPE': '주문일·조회 번호',
    'COMPLETE_SCAN': '전체 페이지 조회',
    'SINGLE_ROW': '단일 조회 행',
    'NEW_ORDER': '신규 주문 범위',
    'ORDER_NUMBER': '주문번호',
    'STOCK_CODE': '종목코드',
    'SIDE': '매수·매도 방향',
    'PRICE': '지정가',
    'QUANTITY': '주문 수량',
    'TIME_WINDOW': '주문 시각 범위',
    'QUANTITY_CONSISTENCY': '체결·미체결 수량 합계',
    'NO_REJECTION': '거절 사유 없음',
  };
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

  String _newId() {
    final random = Random.secure();
    final bytes = List.generate(16, (_) => random.nextInt(256));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    final hex = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
  }

  void _accept(List<Map<String, dynamic>> history) {
    _history = history;
    _loaded = true;
    if (history.any(
      (r) => r['diagnosticId'] == _attempt && r['state'] == 'COMPLETED',
    )) {
      _attempt = null;
    }
  }

  Future<void> _load() async {
    setState(() => _busy = true);
    try {
      final records = await widget.load();
      if (mounted) setState(() => _accept(records));
    } catch (e) {
      if (mounted) setState(() => _message = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _diagnose() async {
    final id = _newId();
    setState(() {
      _busy = true;
      _message = null;
      _attempt = id;
    });
    try {
      final record = await widget.diagnose(id, _number.text.trim());
      if (mounted) {
        setState(
          () => _accept([
            record,
            ..._history.where((r) => r['diagnosticId'] != id),
          ]),
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() => _message = '$e\n진단 요청을 자동 반복하지 않습니다. 저장 이력을 새로고침하세요.');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !_busy,
    child: Scaffold(
      appBar: AppBar(
        title: const Text('SENDING 잠금 유지 진단'),
        actions: [
          IconButton(
            onPressed: _busy ? null : _load,
            tooltip: '진단 이력 새로고침',
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
              const SizedBox(height: 12),
              Text(
                widget.simulation
                    ? '가상 증권사에 표시된 주문번호로 관찰을 기록합니다. 실제 KB 조회는 없습니다. 항목 일치·빈 결과로 주문 상태와 잠금을 변경하지 않습니다.'
                    : 'KB 앱에서 확인한 주문번호로 읽기 전용 조회를 합니다. 항목 일치·빈 결과는 전송 종료의 증거가 아닙니다. 주문 상태와 잠금은 변경하지 않습니다.',
              ),
              if (_busy) const LinearProgressIndicator(),
              if (_message != null)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  child: SelectableText(_message!),
                ),
              if (_attempt != null)
                const Text('요청 결과 확인 중입니다. 이력 조회만 가능하며 같은 요청을 자동 반복하지 않습니다.'),
              if (widget.allowNew) ...[
                TextField(
                  controller: _number,
                  enabled: !_busy && _attempt == null,
                  maxLength: 10,
                  keyboardType: TextInputType.number,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  decoration: const InputDecoration(
                    labelText: '확인한 주문번호 (숫자 10자리)',
                  ),
                  onChanged: (_) => setState(() {}),
                ),
                CheckboxListTile(
                  value: _checked,
                  onChanged: _busy
                      ? null
                      : (v) => setState(() => _checked = v ?? false),
                  title: const Text('이 진단은 추가 주문 전송과 잠금 해제를 하지 않음을 확인했습니다.'),
                ),
                FilledButton(
                  onPressed:
                      _busy ||
                          !_loaded ||
                          _attempt != null ||
                          !_checked ||
                          !RegExp(r'^\d{10}$').hasMatch(_number.text) ||
                          RegExp(r'^0+$').hasMatch(_number.text)
                      ? null
                      : _diagnose,
                  child: const Text('조회·진단 기록'),
                ),
              ],
              const SizedBox(height: 20),
              const Text('저장된 진단 이력 · 당시 관찰이며 현재 상태 확정 아님'),
              if (_loaded && _history.isEmpty) const Text('저장된 진단이 없습니다.'),
              for (final r in _history) _card(r),
            ],
          ),
        ),
      ),
    ),
  );
  Widget _card(Map<String, dynamic> record) {
    final report = record['report'] as Map<String, dynamic>?;
    final observation = report?['observation'] as Map<String, dynamic>?;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SelectableText(
              '진단 ${record['diagnosticId']}\n주문번호 ${record['orderNo']} · ${record['state']}\n'
              '시작 ${record['createdAt']} · 완료 ${record['completedAt'] ?? '기록 없음'}\n'
              '전송 단계 ${record['phaseBefore']} → ${report?['phaseAfter'] ?? '미확인'}',
            ),
            if (report == null)
              const Text('조회 진행·중단 또는 결과 저장 실패를 구분할 수 없습니다. 잠금을 유지합니다.'),
            if (report != null) ...[
              Text(
                labels[report['assessment']] ?? '${report['assessment']}',
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
              Text(
                '관찰 종료 시 주문 상태 ${report['commandStatusAfter']} · 조회 ${report['pagesScanned']}페이지',
              ),
              for (final c in (report['checks'] as List? ?? []))
                Text(
                  '${c['passed'] == true ? '✓' : '·'} ${checkLabels[c['code']] ?? c['code']}',
                ),
              if (observation != null)
                SelectableText(
                  '조회 관찰: ${observation['stockCode']} · ${observation['status']} · ${observation['orderTime']}\n'
                  '지정가 ${observation['price']} · 주문 ${observation['quantity']}주 · 체결 ${observation['filledQuantity']}주 · 미체결 ${observation['openQuantity']}주',
                ),
              Text('${report['message']}'),
            ],
          ],
        ),
      ),
    );
  }
}
