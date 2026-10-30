import 'package:flutter/material.dart';

import '../models/kb_portfolio_import.dart';
import '../repositories/kb_portfolio_importer.dart';

/// 미리보기에서는 저장하지 않고, 사용자가 선택한 범위만 확인 뒤 반영합니다.
class KbPortfolioImportSheet extends StatefulWidget {
  const KbPortfolioImportSheet({super.key, required this.importer});
  final KbPortfolioImporter importer;

  @override
  State<KbPortfolioImportSheet> createState() => _KbPortfolioImportSheetState();
}

class _KbPortfolioImportSheetState extends State<KbPortfolioImportSheet> {
  late Future<KbPortfolioPreview> _future;
  final _markets = <String, String>{};
  final _stopLoss = TextEditingController(text: '-5');
  final _takeProfit = TextEditingController(text: '9');
  bool _capital = false;
  bool _holdings = false;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _future = widget.importer.previewKbImport();
  }

  @override
  void dispose() {
    _stopLoss.dispose();
    _takeProfit.dispose();
    super.dispose();
  }

  void _reload() => setState(() {
    _future = widget.importer.previewKbImport();
    _markets.clear();
    _capital = false;
    _holdings = false;
    _error = null;
  });

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !_saving,
    child: Padding(
      padding: EdgeInsets.fromLTRB(
        20,
        18,
        20,
        20 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text(
                    'KB 계좌에서 불러오기',
                    style: TextStyle(fontSize: 22, fontWeight: FontWeight.w900),
                  ),
                ),
                IconButton(
                  onPressed: _saving ? null : () => Navigator.pop(context),
                  tooltip: '닫기',
                  icon: const Icon(Icons.close),
                ),
              ],
            ),
            const Text(
              '미리보기는 앱 데이터를 변경하지 않습니다. 실제 계좌 앱과 수량·평균 매수가·주문가능 현금을 대조한 뒤 반영하세요.',
            ),
            const SizedBox(height: 12),
            FutureBuilder<KbPortfolioPreview>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Padding(
                    padding: EdgeInsets.all(24),
                    child: Center(child: CircularProgressIndicator()),
                  );
                }
                if (snapshot.hasError || !snapshot.hasData) {
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(snapshot.error.toString()),
                      OutlinedButton(
                        onPressed: _reload,
                        child: const Text('KB 미리보기 다시 조회'),
                      ),
                    ],
                  );
                }
                return _content(snapshot.data!);
              },
            ),
          ],
        ),
      ),
    ),
  );

  Widget _content(KbPortfolioPreview preview) {
    const markets = ['KOSPI', 'KOSDAQ', 'KONEX'];
    final importable = preview.items.where((item) => item.canImport).toList();
    final invalid = preview.items.any((item) => item.action == 'INVALID');
    final checkedAt = preview.checkedAt.toLocal().toString().split('.').first;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('KB 조회 시각 $checkedAt · 미리보기 유효시간 5분'),
        const SizedBox(height: 12),
        CheckboxListTile(
          contentPadding: EdgeInsets.zero,
          value: _capital,
          onChanged: _saving || preview.orderAvailableCash == null
              ? null
              : (value) => setState(() => _capital = value!),
          title: const Text('KB 주문가능 현금을 앱 투자 가능 자본금으로 반영'),
          subtitle: Text(
            '현재 앱 ${preview.currentCapital}원 → KB ${preview.orderAvailableCash == null ? '미제공 (반영 불가)' : '${preview.orderAvailableCash}원'}\n예수금·순자산과 다른 기준이며, 기존 자본금은 선택한 경우에만 변경됩니다.',
          ),
        ),
        CheckboxListTile(
          contentPadding: EdgeInsets.zero,
          value: _holdings,
          onChanged: _saving || importable.isEmpty || invalid
              ? null
              : (value) => setState(() => _holdings = value!),
          title: const Text('KB 보유 종목을 앱에 추가·갱신'),
          subtitle: const Text('수동 등록분은 보존합니다. 기존 KB 보유분의 손절·익절 기준도 유지합니다.'),
        ),
        if (preview.items.isEmpty) const Text('현재 KB 응답에 보유 종목이 없습니다.'),
        for (final item in preview.items)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${item.stockName} (${item.stockCode}) · ${item.quantity}주 · 평균 ${item.averageBuyPrice}원',
                ),
                Text(item.message),
                if (item.canImport && _holdings)
                  DropdownButtonFormField<String>(
                    key: ValueKey('${preview.token}-${item.stockCode}'),
                    initialValue:
                        _markets[item.stockCode] ??
                        (markets.contains(item.market) ? item.market : null),
                    decoration: const InputDecoration(
                      labelText: '실제 상장 시장 선택 (필수)',
                    ),
                    items: markets
                        .map(
                          (market) => DropdownMenuItem(
                            value: market,
                            child: Text(market),
                          ),
                        )
                        .toList(),
                    onChanged: _saving
                        ? null
                        : (value) =>
                              setState(() => _markets[item.stockCode] = value!),
                  ),
              ],
            ),
          ),
        if (_holdings) ...[
          const SizedBox(height: 12),
          const Text('새로 추가하는 종목의 기본 기준 (%) · 실제 매수일은 미제공으로 보관'),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _stopLoss,
                  enabled: !_saving,
                  decoration: const InputDecoration(labelText: '손절 (-100~0)'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: TextField(
                  controller: _takeProfit,
                  enabled: !_saving,
                  decoration: const InputDecoration(
                    labelText: '익절 (0~999.999)',
                  ),
                ),
              ),
            ],
          ),
        ],
        const SizedBox(height: 12),
        Text(
          '현재 응답에 없는 기존 KB 보유분 ${preview.retainedImportedCount}건은 유지됩니다. 조회 누락과 매도를 구분할 수 없어 자동 삭제하지 않습니다. 매도 완료분은 보유 목록에서 직접 삭제하세요.',
        ),
        const Text(
          '불러온 보유분은 수동 스냅샷입니다. 수량·평균 매수가는 다시 불러와 갱신하며, 모의매매 기록은 변경하지 않습니다.',
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        const SizedBox(height: 16),
        Wrap(
          spacing: 12,
          runSpacing: 8,
          children: [
            OutlinedButton(
              onPressed: _saving ? null : _reload,
              child: const Text('KB 미리보기 다시 조회'),
            ),
            FilledButton(
              onPressed: _saving || (!_capital && !_holdings)
                  ? null
                  : () => _apply(preview),
              child: Text(_saving ? '반영 중…' : '선택한 데이터 반영'),
            ),
          ],
        ),
      ],
    );
  }

  Future<void> _apply(KbPortfolioPreview preview) async {
    const supported = ['KOSPI', 'KOSDAQ', 'KONEX'];
    final markets = <String, String>{};
    final stop = double.tryParse(_stopLoss.text.trim());
    final take = double.tryParse(_takeProfit.text.trim());
    if (_holdings) {
      for (final item in preview.items.where((item) => item.canImport)) {
        final market = _markets[item.stockCode] ?? item.market;
        if (!supported.contains(market)) {
          setState(() => _error = '${item.stockName}의 실제 시장을 선택하세요.');
          return;
        }
        markets[item.stockCode] = market;
      }
      if (stop == null ||
          take == null ||
          !stop.isFinite ||
          !take.isFinite ||
          stop < -100 ||
          stop > 0 ||
          take < 0 ||
          take > 999.999) {
        setState(() => _error = '손절·익절 기준을 허용 범위의 숫자로 입력하세요.');
        return;
      }
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final result = await widget.importer.applyKbImport(
        preview: preview,
        importCapital: _capital,
        importHoldings: _holdings,
        markets: markets,
        stopLossRate: _holdings ? stop! : -5,
        takeProfitRate: _holdings ? take! : 9,
      );
      if (mounted) {
        setState(() => _saving = false);
        Navigator.of(context).pop(result);
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          _saving = false;
          _error = error.toString();
        });
      }
    }
  }
}
