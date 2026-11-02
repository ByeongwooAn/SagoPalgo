import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/account_observation.dart';
import '../repositories/account_observation_repository.dart';
import '../widgets/app_card.dart';
import '../widgets/responsive_layout.dart';
import 'observation_labels.dart';
import 'observation_collection_panel.dart';

class AccountObservationScreen extends StatefulWidget {
  const AccountObservationScreen({
    super.key,
    required this.repository,
    this.initialDate,
  });
  final AccountObservationRepository repository;
  final DateTime? initialDate;
  @override
  State<AccountObservationScreen> createState() =>
      _AccountObservationScreenState();
}

class _AccountObservationScreenState extends State<AccountObservationScreen> {
  late final TextEditingController _date;
  List<ObservationSummary> _items = [];
  List<ObservationRequest> _pending = [];
  int? _next;
  int _collectionRevision = 0;
  String? _before, _after, _error, _journalError;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    final date =
        widget.initialDate ??
        DateTime.now().toUtc().add(const Duration(hours: 9));
    _date = TextEditingController(
      text:
          '${date.year.toString().padLeft(4, '0')}${date.month.toString().padLeft(2, '0')}${date.day.toString().padLeft(2, '0')}',
    );
    unawaited(_run(() => _reload()));
  }

  @override
  void dispose() {
    _date.dispose();
    super.dispose();
  }

  Future<void> _run(Future<void> Function() action) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
    } catch (e) {
      if (mounted) setState(() => _error = _message(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _pendingRequests() async {
    try {
      final pending = await widget.repository.outstanding();
      if (mounted) {
        setState(() {
          _pending = pending;
          _journalError = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _journalError = _message(e));
    }
  }

  Future<void> _reload({bool more = false}) async {
    final cursor = more ? _next : null;
    if (!more && mounted) {
      setState(() {
        _collectionRevision++;
        _items = [];
        _next = null;
        _before = null;
        _after = null;
      });
    }
    try {
      final page = await widget.repository.history(beforeId: cursor);
      if (mounted) {
        setState(() {
          final unique = {for (final item in _items) item.requestId: item};
          for (final item in page.items) {
            unique[item.requestId] = item;
          }
          _items = unique.values.toList();
          _next = page.nextBeforeId;
        });
      }
    } finally {
      await _pendingRequests();
    }
  }

  Future<void> _capture() async {
    ObservationDetail? result;
    await _run(() async {
      try {
        result = await widget.repository.capture(_date.text);
      } catch (e) {
        if (mounted) setState(() => _error = _message(e));
      }
      try {
        await _reload();
      } catch (e) {
        if (mounted) setState(() => _error ??= _message(e));
      }
    });
    if (!mounted || result == null) return;
    await _openDetail(result!.summary.requestId, initial: result);
  }

  Future<void> _openDetail(
    String id, {
    ObservationDetail? initial,
    ObservationRequest? pending,
  }) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => ObservationDetailScreen(
          repository: widget.repository,
          requestId: id,
          initial: initial,
          pending: pending,
        ),
      ),
    );
    if (mounted) await _run(() => _pendingRequests());
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('계좌 관찰 이력'),
      actions: [
        IconButton(
          tooltip: '이력 새로고침',
          onPressed: _busy ? null : () => _run(() => _reload()),
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
    body: Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: AppLayout.maxContentWidth),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Text('계좌 상태를 저장해 이전 기록과 비교합니다. 저장 이력은 새로고침으로 갱신합니다.'),
            const SizedBox(height: 12),
            AppCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      SizedBox(
                        width: 240,
                        child: TextField(
                          controller: _date,
                          enabled: !_busy,
                          keyboardType: TextInputType.number,
                          inputFormatters: [
                            FilteringTextInputFormatter.digitsOnly,
                            LengthLimitingTextInputFormatter(8),
                          ],
                          decoration: const InputDecoration(
                            labelText: '주문 조회일 (한국 기준)',
                            hintText: 'YYYYMMDD',
                            helperText: '보유·잔고는 요청 시점의 상태입니다.',
                          ),
                        ),
                      ),
                      FilledButton.icon(
                        onPressed: _busy || _journalError != null
                            ? null
                            : _capture,
                        icon: const Icon(Icons.save_outlined),
                        label: const Text('새 관찰 저장'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    '새 관찰 저장은 KB 조회를 실행합니다. 이력·상세·비교·저장 상태 확인은 저장 기록만 읽습니다.',
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            ObservationCollectionPanel(
              key: const ValueKey('observation-collection'),
              repository: widget.repository,
              refreshRevision: _collectionRevision,
              enabled: !_busy,
              onDetail: (id) => _openDetail(id),
            ),
            if (_busy)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: LinearProgressIndicator(),
              ),
            if (_error != null) _Notice(_error!),
            if (_journalError != null) _Notice(_journalError!),
            if (_pending.isNotEmpty) ...[
              const SizedBox(height: 16),
              Text(
                '결과 확인이 필요한 요청 ${_pending.length}건',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const Text('응답이 없었어도 서버에 저장됐을 수 있습니다. 같은 요청의 저장 상태를 확인하세요.'),
              for (final request in _pending)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: AppCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('주문 조회일 ${request.orderDate}'),
                        SelectableText('요청 ID: ${request.requestId}'),
                        TextButton(
                          onPressed: _busy
                              ? null
                              : () => _openDetail(
                                  request.requestId,
                                  pending: request,
                                ),
                          child: const Text('저장 상태 확인'),
                        ),
                      ],
                    ),
                  ),
                ),
            ],
            const SizedBox(height: 20),
            Text('저장 이력', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            if (!_busy && _items.isEmpty && _error == null)
              const Text('현재 계좌 연결의 저장 이력이 없습니다. 새 관찰을 저장해 보세요.'),
            for (final item in _items)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: AppCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        observationTime(item.createdAt),
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      Text(
                        '${observationStatusLabel(item.storageState)} · ${observationStatusLabel(item.snapshotStatus)} · 주문 조회일 ${item.orderDate}',
                      ),
                      SelectableText('요청 ID: ${item.requestId}'),
                      if (item.failureCode != null)
                        Text(observationReasonLabel(item.failureCode!)),
                      TextButton(
                        onPressed: _busy
                            ? null
                            : () => _openDetail(item.requestId),
                        child: const Text('관찰 상세'),
                      ),
                    ],
                  ),
                ),
              ),
            if (_next != null)
              OutlinedButton(
                onPressed: _busy ? null : () => _run(() => _reload(more: true)),
                child: const Text('이전 이력 더 보기'),
              ),
            const SizedBox(height: 16),
            AppCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '두 관찰 비교',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const Text(
                    '이전 기록과 이후 기록을 순서대로 선택하세요. 비교 불가 사유는 결과에서 확인할 수 있습니다.',
                  ),
                  const SizedBox(height: 12),
                  _selector(
                    '이전 관찰',
                    _before,
                    (value) => setState(() => _before = value),
                  ),
                  const SizedBox(height: 12),
                  _selector(
                    '이후 관찰',
                    _after,
                    (value) => setState(() => _after = value),
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    children: [
                      TextButton(
                        onPressed: _busy
                            ? null
                            : () => setState(() {
                                final a = _before;
                                _before = _after;
                                _after = a;
                              }),
                        child: const Text('순서 바꾸기'),
                      ),
                      FilledButton(
                        onPressed:
                            _busy ||
                                _before == null ||
                                _after == null ||
                                _before == _after
                            ? null
                            : () => Navigator.of(context).push(
                                MaterialPageRoute<void>(
                                  builder: (_) => ObservationComparisonScreen(
                                    repository: widget.repository,
                                    before: _before!,
                                    after: _after!,
                                  ),
                                ),
                              ),
                        child: const Text('선택한 관찰 비교'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    ),
  );

  Widget _selector(
    String label,
    String? value,
    ValueChanged<String?> changed,
  ) => DropdownButtonFormField<String>(
    key: ValueKey('$label-$value-${_items.length}'),
    initialValue: value,
    isExpanded: true,
    decoration: InputDecoration(labelText: label),
    items: [
      for (final item in _items)
        DropdownMenuItem(
          value: item.requestId,
          child: Text(
            '${observationTime(item.createdAt)} · ${observationStatusLabel(item.storageState)} · ${item.requestId.substring(0, 8)}',
            overflow: TextOverflow.ellipsis,
          ),
        ),
    ],
    onChanged: _busy ? null : changed,
  );
}

String _message(Object error) => error is ObservationRepositoryException
    ? error.message
    : '관찰 기록을 확인하지 못했습니다. 연결 상태를 확인한 뒤 다시 조회하세요.';

class _Notice extends StatelessWidget {
  const _Notice(this.message);
  final String message;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 8),
    child: AppCard(soft: true, child: SelectableText(message)),
  );
}

class ObservationDetailScreen extends StatelessWidget {
  const ObservationDetailScreen({
    super.key,
    required this.repository,
    required this.requestId,
    this.initial,
    this.pending,
  });
  final AccountObservationRepository repository;
  final String requestId;
  final ObservationDetail? initial;
  final ObservationRequest? pending;
  @override
  Widget build(BuildContext context) => _ReadPage<ObservationDetail>(
    title: '관찰 상세',
    initial: initial,
    load: () => pending == null
        ? repository.detail(requestId)
        : repository.check(pending!),
    content: (result) => [
      AppCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SelectableText('요청 ID: ${result.summary.requestId}'),
            Text(
              '저장 상태: ${observationStatusLabel(result.summary.storageState)}',
            ),
            Text(
              '조회 결과: ${observationStatusLabel(result.summary.snapshotStatus)}',
            ),
            Text('주문 조회일: ${result.summary.orderDate}'),
            Text('요청 기록: ${observationTime(result.summary.createdAt)}'),
            Text('저장 완료: ${observationTime(result.summary.completedAt)}'),
            if (result.summary.failureCode != null)
              Text(observationReasonLabel(result.summary.failureCode!)),
            if (result.summary.storageState == 'PENDING')
              const Text(
                '결과 대기 상태입니다. 실행 중인지 중단됐는지는 확정하지 않습니다. 상단 새로고침으로 같은 요청의 저장 상태를 확인할 수 있습니다.',
              ),
          ],
        ),
      ),
      const Padding(
        padding: EdgeInsets.symmetric(vertical: 12),
        child: Text('조회 구간마다 수신 시각이 다릅니다. 이 기록을 거래 가능한 확정 잔고로 사용하지 않습니다.'),
      ),
      if (result.observation != null) ...[
        Text(
          '관찰 수신: ${observationTime(result.observation!.startedAt)} → ${observationTime(result.observation!.completedAt)}',
        ),
        for (final section in result.observation!.sections)
          _DetailSection(section),
      ],
    ],
  );
}

class _ExpansionCard extends StatelessWidget {
  const _ExpansionCard({required this.child});
  final Widget child;
  @override
  Widget build(BuildContext context) => AppCard(
    padding: EdgeInsets.zero,
    child: Material(type: MaterialType.transparency, child: child),
  );
}

class _DetailSection extends StatelessWidget {
  const _DetailSection(this.section);
  final ObservationSection section;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 12),
    child: _ExpansionCard(
      child: ExpansionTile(
        title: Text(observationApiLabel(section.api)),
        subtitle: Text(
          '${observationStatusLabel(section.status)} · ${observationStatusLabel(section.completeness)} · ${section.rows.length}행',
        ),
        childrenPadding: const EdgeInsets.all(16),
        expandedAlignment: Alignment.centerLeft,
        expandedCrossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('수신 시작: ${observationTime(section.startedAt)}'),
          Text('수신 완료: ${observationTime(section.completedAt)}'),
          Text(
            '조회 ${section.pagesRead}페이지 · 수신 ${section.receivedRowCount}행 · 보고된 전체 ${section.reportedTotalCount?.toString() ?? '미제공'}행',
          ),
          if (section.providerProcessTime != null)
            Text('공급자 처리 시각: ${section.providerProcessTime} (시간대 미확인)'),
          _Fields(section.scope),
          for (final issue in section.issues)
            Text(
              '${observationReasonLabel(issue.code)}${issue.field == null ? '' : ' · ${observationFieldLabel(issue.field!)}'}',
            ),
          const SizedBox(height: 8),
          const Text('요약'),
          _Fields(section.summary),
          const SizedBox(height: 8),
          if (section.rows.isEmpty)
            Text(
              section.status == 'SUCCESS' && section.completeness == 'COMPLETE'
                  ? '조회 범위에서 확인된 행이 없습니다.'
                  : '표시할 행이 없습니다. 빈 계좌로 확정하지 않습니다.',
            ),
          _Rows(
            items: section.rows,
            builder: (row) => ExpansionTile(
              title: Text(_rowTitle(row)),
              expandedAlignment: Alignment.centerLeft,
              expandedCrossAxisAlignment: CrossAxisAlignment.start,
              children: [_Fields(row)],
            ),
          ),
        ],
      ),
    ),
  );
}

String _rowTitle(Map<String, String?> row) {
  final title = [
    row['is_nm'] ?? row['hngl_shrt_nm'],
    row['is_no'] ?? row['is_cd'] ?? row['stnd_is_no'],
    if (row['ordr_no'] != null) '주문 ${row['ordr_no']}',
  ].whereType<String>().where((s) => s.isNotEmpty).join(' · ');
  return title.isEmpty ? '식별 정보 미제공' : title;
}

class _Fields extends StatelessWidget {
  const _Fields(this.fields);
  final Map<String, String?> fields;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      for (final entry in fields.entries)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 3),
          child: SelectableText(
            '${observationFieldLabel(entry.key)}: ${entry.value ?? '값 미제공'}',
          ),
        ),
    ],
  );
}

class ObservationComparisonScreen extends StatelessWidget {
  const ObservationComparisonScreen({
    super.key,
    required this.repository,
    required this.before,
    required this.after,
  });
  final AccountObservationRepository repository;
  final String before, after;
  @override
  Widget build(BuildContext context) => _ReadPage<ObservationComparison>(
    title: '관찰 비교',
    load: () => repository.compare(before, after),
    content: (result) => [
      Text(
        observationStatusLabel(result.status),
        style: Theme.of(context).textTheme.titleLarge,
      ),
      SelectableText(
        '이전 요청: ${result.beforeRequestId}\n이후 요청: ${result.afterRequestId}',
      ),
      const Padding(
        padding: EdgeInsets.symmetric(vertical: 12),
        child: Text(
          '관찰된 필드의 차이입니다. 종목·주문의 누락은 매도·주문 완료를 뜻하지 않으며 변화량은 수익이 아닙니다.',
        ),
      ),
      for (final section in result.sections)
        Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: _ExpansionCard(
            child: ExpansionTile(
              initiallyExpanded: section.status == 'BLOCKED',
              title: Text(observationApiLabel(section.api)),
              subtitle: Text(
                '${observationStatusLabel(section.status)} · 요약 변화 ${section.summaryChanges.length}개 · 행 변화 ${section.rowChanges.length}개',
              ),
              expandedCrossAxisAlignment: CrossAxisAlignment.start,
              childrenPadding: const EdgeInsets.all(16),
              expandedAlignment: Alignment.centerLeft,
              children: [
                for (final reason in section.reasons)
                  Text(observationReasonLabel(reason)),
                const Text('이전 조회 범위'),
                _Fields(section.beforeScope),
                const Text('이후 조회 범위'),
                _Fields(section.afterScope),
                if (section.status == 'COMPARED' &&
                    section.summaryChanges.isEmpty &&
                    section.rowChanges.isEmpty)
                  const Text('지원 필드의 관찰 차이가 없습니다.'),
                for (final change in section.summaryChanges) _Change(change),
                _Rows(
                  items: section.rowChanges,
                  builder: (row) => ExpansionTile(
                    title: Text(switch (row.kind) {
                      'OBSERVED_ONLY_BEFORE' => '이전 관찰에서만 확인',
                      'OBSERVED_ONLY_AFTER' => '이후 관찰에서만 확인',
                      _ => '같은 행의 필드 변화',
                    }),
                    subtitle: Text(row.identity.values.join(' · ')),
                    expandedAlignment: Alignment.centerLeft,
                    expandedCrossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _Fields(row.identity),
                      for (final change in row.fields) _Change(change),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
    ],
  );
}

class _Change extends StatelessWidget {
  const _Change(this.change);
  final ObservationFieldChange change;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          observationFieldLabel(change.field),
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
        SelectableText(
          '이전: ${!change.beforePresent ? '필드 없음' : change.beforeValue ?? '값 미제공'} → 이후: ${!change.afterPresent ? '필드 없음' : change.afterValue ?? '값 미제공'}',
        ),
        SelectableText('변화량: ${change.numericDelta ?? '산정하지 않음'}'),
      ],
    ),
  );
}

class _Rows<T> extends StatefulWidget {
  const _Rows({required this.items, required this.builder});
  final List<T> items;
  final Widget Function(T) builder;
  @override
  State<_Rows<T>> createState() => _RowsState<T>();
}

class _RowsState<T> extends State<_Rows<T>> {
  int _visible = 25;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      for (final item in widget.items.take(_visible)) widget.builder(item),
      if (widget.items.length > _visible)
        TextButton(
          onPressed: () => setState(() => _visible += 25),
          child: const Text('저장된 행 더 보기'),
        ),
    ],
  );
}

class _ReadPage<T> extends StatefulWidget {
  const _ReadPage({
    required this.title,
    required this.load,
    required this.content,
    this.initial,
  });
  final String title;
  final Future<T> Function() load;
  final List<Widget> Function(T) content;
  final T? initial;
  @override
  State<_ReadPage<T>> createState() => _ReadPageState<T>();
}

class _ReadPageState<T> extends State<_ReadPage<T>> {
  late Future<T> _future;
  @override
  void initState() {
    super.initState();
    _future = widget.initial == null ? _load() : Future.value(widget.initial);
  }

  Future<T> _load() {
    final future = widget.load();
    // 다음 프레임의 FutureBuilder 구독 전에 완료된 오류도 처리합니다.
    future.ignore();
    return future;
  }

  void _reload() => setState(() {
    _future = _load();
  });
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(widget.title),
      actions: [
        IconButton(
          tooltip: '저장 상태 다시 확인',
          onPressed: _reload,
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
    body: FutureBuilder<T>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        return Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: const BoxConstraints(
              maxWidth: AppLayout.maxContentWidth,
            ),
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: snapshot.hasError
                  ? [
                      _Notice(_message(snapshot.error!)),
                      FilledButton(
                        onPressed: _reload,
                        child: const Text('저장 상태 다시 확인'),
                      ),
                    ]
                  : widget.content(snapshot.requireData),
            ),
          ),
        );
      },
    ),
  );
}
