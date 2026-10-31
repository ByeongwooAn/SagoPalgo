import 'package:flutter/material.dart';
import '../repositories/watchlist_repository.dart';
import '../repositories/watchlist_editor.dart';

Future<bool> showWatchlistSetup(
  BuildContext context,
  WatchlistRepository repository,
) async {
  if (repository is! WatchlistEditor) return false;
  return await showModalBottomSheet<bool>(
        context: context,
        isScrollControlled: true,
        useSafeArea: true,
        isDismissible: false,
        enableDrag: false,
        builder: (_) =>
            WatchlistSetupSheet(editor: repository as WatchlistEditor),
      ) ??
      false;
}

class WatchlistSetupSheet extends StatefulWidget {
  const WatchlistSetupSheet({super.key, required this.editor});
  final WatchlistEditor editor;
  @override
  State<WatchlistSetupSheet> createState() => _WatchlistSetupSheetState();
}

class _WatchlistSetupSheetState extends State<WatchlistSetupSheet> {
  final _form = GlobalKey<FormState>();
  final _code = TextEditingController();
  final _name = TextEditingController();
  String _market = 'KOSPI';
  bool _alerts = false;
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _code.dispose();
    _name.dispose();
    super.dispose();
  }

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
        child: Form(
          key: _form,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Expanded(
                    child: Text(
                      '관심 종목 등록',
                      style: TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ),
                  IconButton(
                    onPressed: _saving
                        ? null
                        : () => Navigator.pop(context, false),
                    icon: const Icon(Icons.close),
                    tooltip: '닫기',
                  ),
                ],
              ),
              const Text(
                '보유 주식 없이도 뉴스·공시를 수집하고 분석할 수 있습니다. 국내 종목코드와 실제 상장 시장을 입력하세요.',
              ),
              TextFormField(
                controller: _code,
                enabled: !_saving,
                decoration: const InputDecoration(labelText: '종목 코드 (6자리)'),
                validator: (value) =>
                    RegExp(r'^\d{6}$').hasMatch(value?.trim() ?? '')
                    ? null
                    : '국내 종목코드 6자리를 입력하세요.',
              ),
              TextFormField(
                controller: _name,
                enabled: !_saving,
                decoration: const InputDecoration(labelText: '종목명'),
                maxLength: 100,
                validator: (value) =>
                    (value?.trim().isEmpty ?? true) ? '종목명을 입력하세요.' : null,
              ),
              DropdownButtonFormField<String>(
                initialValue: _market,
                decoration: const InputDecoration(labelText: '실제 상장 시장'),
                items: ['KOSPI', 'KOSDAQ', 'KONEX']
                    .map(
                      (value) =>
                          DropdownMenuItem(value: value, child: Text(value)),
                    )
                    .toList(),
                onChanged: _saving
                    ? null
                    : (value) => setState(() => _market = value!),
              ),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('추천 신호 알림 켜기'),
                subtitle: const Text(
                  '분석 결과가 알림 조건을 만족할 때 생성됩니다. 주기 분석은 서버 설정을 따릅니다.',
                ),
                value: _alerts,
                onChanged: _saving
                    ? null
                    : (value) => setState(() => _alerts = value!),
              ),
              if (_error != null)
                Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: _saving ? null : _save,
                child: Text(_saving ? '등록 중…' : '관심 종목 저장'),
              ),
            ],
          ),
        ),
      ),
    ),
  );

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.editor.addStock(
        stockCode: _code.text.trim(),
        stockName: _name.text.trim(),
        market: _market,
        alertEnabled: _alerts,
      );
      if (mounted) {
        setState(() => _saving = false);
        Navigator.pop(context, true);
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
