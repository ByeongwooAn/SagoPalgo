import 'package:flutter/material.dart';
import '../models/research_changes.dart';
import '../repositories/research_changes_repository.dart';
import '../widgets/app_card.dart';

class ResearchChangesScreen extends StatefulWidget {
  const ResearchChangesScreen({
    super.key,
    required this.stockCode,
    required this.stockName,
    required this.repository,
  });
  final String stockCode, stockName;
  final ResearchChangesAccess repository;
  @override
  State<ResearchChangesScreen> createState() => _ResearchChangesScreenState();
}

class _ResearchChangesScreenState extends State<ResearchChangesScreen> {
  final List<ResearchChange> _items = [];
  int _cursor = 0;
  bool _busy = false, _enabled = true, _more = false;
  String? _error;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load({bool reset = false}) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final page = await widget.repository.changes(
        widget.stockCode,
        afterId: reset ? 0 : _cursor,
      );
      if (!mounted) return;
      setState(() {
        if (reset) _items.clear();
        _items.addAll(page.items);
        _cursor = page.nextAfterId;
        _enabled = page.enabled;
        _more = page.items.length == 100;
      });
    } catch (_) {
      if (mounted) setState(() => _error = '변경 이력을 확인하지 못했습니다. 기존 기록은 유지합니다.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text('${widget.stockName} · 뉴스·공시 변경'),
      actions: [
        IconButton(
          tooltip: '변경 이력 새로고침',
          onPressed: _busy ? null : () => _load(reset: true),
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
    body: Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 1120),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Text(
              '서버가 처음 기록한 순서부터 표시합니다. 같은 자료의 내용 변경은 버전으로 보존합니다. 별도 접수번호의 정정 공시는 별도 자료이며 원공시 연결을 추정하지 않습니다.',
            ),
            if (_busy) const LinearProgressIndicator(),
            if (_error != null) Text(_error!),
            if (!_enabled)
              const Text(
                '서버의 증분·변경 이력 수집이 OFF입니다. 기존 뉴스·공시 목록은 계속 사용할 수 있습니다.',
              ),
            if (_enabled && !_busy && _items.isEmpty && _error == null)
              const Text('아직 저장된 변경 이력이 없습니다.'),
            for (final item in _items)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: AppCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '${item.kind == 'NEWS' ? '뉴스' : '공시'} · ${item.provider} · 버전 ${item.revision}',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      Text(
                        '${item.content['title'] ?? item.content['reportName'] ?? '제목 미제공'}',
                      ),
                      if (item.content['summary'] is String)
                        Text(item.content['summary'] as String),
                      Text(
                        '서버 기록: ${item.observedAt.add(const Duration(hours: 9)).toIso8601String().replaceFirst('T', ' ').replaceFirst('Z', '')} (한국)',
                      ),
                      Text(
                        item.origin == 'LEGACY_BASELINE'
                            ? '기존 저장 자료를 기준 버전으로 보관'
                            : '공급자 조회에서 관측',
                      ),
                      if (item.kind == 'DISCLOSURE')
                        Text(
                          '접수일: ${item.content['receiptDate'] ?? '미제공'} · 접수번호: ${item.content['receiptNumber'] ?? '미제공'}',
                        ),
                      if (item.kind == 'NEWS')
                        Text(
                          '제공된 발행 시각: ${item.content['publishedAt'] ?? '미제공'}',
                        ),
                      if (item.content['link'] is String)
                        SelectableText(item.content['link'] as String),
                    ],
                  ),
                ),
              ),
            if (_more)
              OutlinedButton(
                onPressed: _busy ? null : () => _load(),
                child: const Text('다음 변경 이력'),
              ),
          ],
        ),
      ),
    ),
  );
}
