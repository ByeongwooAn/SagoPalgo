import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/stock_identity.dart';
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
  String? _market;
  StockIdentity? _identity;
  bool _manual = false;
  bool _alerts = false;
  bool _saving = false;
  bool _lookingUp = false;
  String? _error;
  Timer? _debounce;
  int _lookupVersion = 0;

  @override
  void dispose() {
    _debounce?.cancel();
    _code.dispose();
    _name.dispose();
    super.dispose();
  }

  void _codeChanged(String value) {
    _debounce?.cancel();
    _lookupVersion++;
    setState(() {
      _identity = null;
      _error = null;
      _lookingUp = false;
      // 코드가 바뀌면 이전 종목명과 시장을 새 코드에 재사용하지 않습니다.
      _name.clear();
      _market = null;
    });
    if (!_manual && RegExp(r'^\d{6}$').hasMatch(value.trim())) {
      setState(() => _lookingUp = true);
      _debounce = Timer(const Duration(milliseconds: 400), _lookup);
    }
  }

  Future<void> _lookup() async {
    _debounce?.cancel();
    final code = _code.text.trim();
    if (_manual || !RegExp(r'^\d{6}$').hasMatch(code)) return;
    final version = ++_lookupVersion;
    setState(() {
      _lookingUp = true;
      _error = null;
    });
    try {
      final result = await widget.editor.lookupStock(code);
      if (!mounted ||
          version != _lookupVersion ||
          _manual ||
          _code.text.trim() != code) {
        return;
      }
      if (result.stockCode != code) {
        throw const FormatException('조회한 종목코드가 일치하지 않습니다.');
      }
      setState(() {
        _identity = result;
        _name.text = result.stockName;
        _market = result.market;
      });
    } catch (error) {
      if (mounted && version == _lookupVersion) {
        setState(() {
          _identity = null;
          _name.clear();
          _market = null;
          _error = error.toString();
        });
      }
    } finally {
      if (mounted && version == _lookupVersion) {
        setState(() => _lookingUp = false);
      }
    }
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
              const Text('국내 종목코드 6자리를 입력하면 종목명과 상장 시장을 자동으로 가져옵니다.'),
              TextFormField(
                controller: _code,
                enabled: !_saving,
                decoration: const InputDecoration(labelText: '종목 코드 (6자리)'),
                keyboardType: TextInputType.number,
                inputFormatters: [
                  FilteringTextInputFormatter.digitsOnly,
                  LengthLimitingTextInputFormatter(6),
                ],
                onChanged: _codeChanged,
                validator: (value) =>
                    RegExp(r'^\d{6}$').hasMatch(value?.trim() ?? '')
                    ? null
                    : '국내 종목코드 6자리를 입력하세요.',
              ),
              if (_lookingUp)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 8),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                      SizedBox(width: 8),
                      Text('종목정보 조회 중…'),
                    ],
                  ),
                ),
              TextFormField(
                controller: _name,
                enabled: !_saving,
                readOnly: !_manual,
                decoration: const InputDecoration(labelText: '종목명'),
                maxLength: 100,
                validator: (value) => (value?.trim().isEmpty ?? true)
                    ? '종목명을 조회하거나 직접 입력하세요.'
                    : null,
              ),
              DropdownButtonFormField<String>(
                key: ValueKey('market:$_market:$_manual'),
                initialValue: _market,
                decoration: const InputDecoration(labelText: '상장 시장'),
                items: ['KOSPI', 'KOSDAQ', 'KONEX']
                    .map(
                      (value) =>
                          DropdownMenuItem(value: value, child: Text(value)),
                    )
                    .toList(),
                onChanged: !_manual || _saving
                    ? null
                    : (value) => setState(() => _market = value),
                validator: (value) =>
                    value == null ? '상장 시장을 조회하거나 선택하세요.' : null,
              ),
              if (_identity != null && !_manual)
                Text('종목정보 조회 · ${_identity!.provider}'),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('종목명·시장 직접 입력'),
                subtitle: const Text(
                  '자동 조회를 사용할 수 없을 때 실제 종목명과 상장 시장을 직접 입력할 수 있습니다.',
                ),
                value: _manual,
                onChanged: _saving
                    ? null
                    : (value) {
                        _debounce?.cancel();
                        _lookupVersion++;
                        setState(() {
                          _manual = value!;
                          _lookingUp = false;
                          _error = null;
                        });
                        if (!_manual) _codeChanged(_code.text);
                      },
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
              if (_error != null && !_manual)
                TextButton.icon(
                  onPressed: _lookingUp || _saving ? null : _lookup,
                  icon: const Icon(Icons.refresh),
                  label: const Text('종목 다시 조회'),
                ),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: _saving || _lookingUp ? null : _save,
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
    if (!_manual &&
        (_identity == null || _identity!.stockCode != _code.text.trim())) {
      setState(() => _error = '종목정보를 먼저 조회하거나 직접 입력을 선택하세요.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.editor.addStock(
        stockCode: _code.text.trim(),
        stockName: _name.text.trim(),
        market: _market!,
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
