import 'dart:async';

import 'package:flutter/material.dart';

import '../models/account_observation.dart';
import '../repositories/account_observation_repository.dart';
import '../widgets/app_card.dart';
import 'observation_labels.dart';

/// 상태 확인은 GET만 실행합니다. 화면 진입이나 재조회로 재개하지 않습니다.
class ObservationCollectionPanel extends StatefulWidget {
  const ObservationCollectionPanel({
    super.key,
    required this.repository,
    required this.refreshRevision,
    this.enabled = true,
    this.onDetail,
  });

  final AccountObservationRepository repository;
  final int refreshRevision;
  final bool enabled;
  final ValueChanged<String>? onDetail;

  @override
  State<ObservationCollectionPanel> createState() =>
      _ObservationCollectionPanelState();
}

class _ObservationCollectionPanelState
    extends State<ObservationCollectionPanel> {
  ObservationCollection? _status;
  DateTime? _checkedAt;
  String? _error, _notice;
  bool _busy = false, _confirmResume = false, _refreshQueued = false;
  int _generation = 0;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void didUpdateWidget(ObservationCollectionPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.repository != widget.repository ||
        oldWidget.refreshRevision != widget.refreshRevision) {
      if (oldWidget.repository != widget.repository) {
        _generation++;
        _status = null;
        _checkedAt = null;
        _notice = null;
        _confirmResume = false;
      }
      if (_busy) {
        _refreshQueued = true;
      } else {
        unawaited(_load());
      }
    }
  }

  Future<void> _load() async {
    if (_busy) return;
    final generation = ++_generation;
    setState(() {
      _busy = true;
      _status = null; // 실패 시 이전 PAUSED를 재개 대상으로 남기지 않습니다.
      _checkedAt = null;
      _error = null;
      _notice = null;
    });
    try {
      final result = await widget.repository.collectionStatus();
      if (!mounted || generation != _generation) return;
      setState(() {
        _status = result;
        _checkedAt = DateTime.now().toUtc();
        if (_confirmResume) {
          _notice = result.state == 'IDLE'
              ? '현재 다음 주기 대기 상태입니다. 수집 설정은 별도로 적용됩니다.'
              : '현재 서버 상태를 확인했습니다. 재개 요청은 자동으로 반복하지 않습니다.';
        }
        _confirmResume = false;
      });
    } catch (e) {
      if (mounted && generation == _generation) {
        setState(() => _error = _message(e));
      }
    } finally {
      _finish();
    }
  }

  Future<void> _resume() async {
    final current = _status;
    if (_busy || !widget.enabled || current == null || !current.canResume) {
      return;
    }
    final generation = ++_generation;
    setState(() {
      _busy = true;
      _status = null;
      _checkedAt = null;
      _error = null;
      _notice = null;
    });
    try {
      final result = await widget.repository.resumeCollection(
        current.lastRequestId!,
      );
      if (!mounted || generation != _generation) return;
      setState(() {
        _status = result;
        _checkedAt = DateTime.now().toUtc();
        _notice = '재개 처리 완료. 다음 주기를 기다립니다. 즉시 KB를 조회하지 않습니다.';
      });
    } catch (e) {
      if (!mounted || generation != _generation) return;
      setState(() {
        _confirmResume = true;
        _error = _message(e);
        _notice = '재개 결과를 확정하지 못했습니다. 수집 상태 확인을 눌러 현재 결과를 조회하세요.';
      });
    } finally {
      _finish();
    }
  }

  void _finish() {
    if (!mounted) return;
    setState(() => _busy = false);
    if (_refreshQueued) {
      _refreshQueued = false;
      unawaited(_load());
    }
  }

  String _message(Object error) => error is ObservationRepositoryException
      ? error.message
      : '수집 상태를 확인하지 못했습니다. 서버 상태를 확인하세요.';

  @override
  Widget build(BuildContext context) {
    final value = _status;
    final available = widget.enabled && !_busy;
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 12,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text('자동 관찰 수집', style: Theme.of(context).textTheme.titleLarge),
              TextButton.icon(
                onPressed: available ? _load : null,
                icon: const Icon(Icons.refresh),
                label: const Text('수집 상태 확인'),
              ),
            ],
          ),
          if (_busy) const LinearProgressIndicator(),
          if (_error != null)
            Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          if (_notice != null) Text(_notice!),
          if (value != null) ...[
            Text('상태 확인 시각: ${observationTime(_checkedAt)}'),
            Text('서버 수집 설정: ${value.enabled ? 'ON' : 'OFF'}'),
            Text('실행 상태: ${_stateLabel(value.state)}'),
            Text(
              '개인용 모드: ${value.personalModeEnabled ? 'ON' : 'OFF'} · 계좌 조회: ${value.accountEnabled ? 'ON' : 'OFF'} · 연결 설정: ${value.connectionConfigured ? '구성됨' : '미구성'}',
            ),
            Text('수집 간격: ${value.intervalSeconds}초'),
            if (!value.enabled ||
                !value.personalModeEnabled ||
                !value.accountEnabled ||
                !value.connectionConfigured)
              const Text('자동 수집의 실행 조건이 충족되지 않았습니다. 재개해도 서버 설정을 켜지 않습니다.'),
            Text('다음 실행 가능 시각: ${observationTime(value.nextDueAt)}'),
            Text('최근 시작: ${observationTime(value.startedAt)}'),
            Text('최근 종료: ${observationTime(value.completedAt)}'),
            if (value.state == 'ACTIVE')
              const Text(
                '실행 중이거나 종료 결과가 미확정입니다. 시간이 지나도 자동 해제하거나 강제로 재개하지 않습니다.',
              ),
            if (value.activeRequestId != null) ...[
              SelectableText('진행 요청 ID: ${value.activeRequestId}'),
              Text('진행 요청 조회일: ${value.activeOrderDate ?? '미제공'}'),
              TextButton(
                onPressed: available && widget.onDetail != null
                    ? () => widget.onDetail!(value.activeRequestId!)
                    : null,
                child: const Text('진행 관찰 상세'),
              ),
            ],
            Text(
              '마지막 저장 결과: ${observationStatusLabel(value.lastStorageState)} · ${observationStatusLabel(value.lastSnapshotStatus)}',
            ),
            if (value.lastRequestId != null) ...[
              SelectableText('마지막 요청 ID: ${value.lastRequestId}'),
              TextButton(
                onPressed: available && widget.onDetail != null
                    ? () => widget.onDetail!(value.lastRequestId!)
                    : null,
                child: const Text('마지막 관찰 상세'),
              ),
            ],
            if (value.state == 'PAUSED') ...[
              Text('중단 사유: ${_pauseReason(value.failureCode)}'),
              if (!value.canResume)
                const Text('종료 기록과 중단 사유를 확인할 수 없어 앱에서 재개할 수 없습니다.'),
              FilledButton.icon(
                onPressed: available && value.canResume ? _resume : null,
                icon: const Icon(Icons.play_arrow),
                label: const Text('수집 재개'),
              ),
            ],
          ],
          const SizedBox(height: 8),
          const Text(
            '상태는 확인 시점 기준입니다. 시각은 서버 실행 기록이며 KB 자료의 기준 시각과 다릅니다. 다음 실행에는 지연이 있을 수 있습니다.',
          ),
          const Text(
            '재개는 종료된 중단 기록을 서버에서 대조한 뒤 다음 주기를 허용합니다. 수집 설정 변경·즉시 조회·주문은 수행하지 않습니다.',
          ),
        ],
      ),
    );
  }
}

String _stateLabel(String state) => switch (state) {
  'NOT_STARTED' => '시작 기록 없음',
  'IDLE' => '다음 주기 대기',
  'ACTIVE' => '실행 중 또는 결과 미확정',
  'PAUSED' => '중단',
  'UNCONFIGURED' => '연결 설정 필요',
  _ => '확인 불가',
};

String _pauseReason(String? code) => switch (code) {
  'SNAPSHOT_PARTIAL' => '일부 자료만 확인됐습니다.',
  'SNAPSHOT_FAILED' => 'KB 관찰 조회에 실패했습니다.',
  'SNAPSHOT_DISABLED' => '계좌 관찰 조회가 비활성 상태입니다.',
  'SNAPSHOT_UNUSABLE' => '자료의 완전성 또는 문제 항목을 확인해야 합니다.',
  'OBSERVATION_FAILED' || 'CONTEXT_CHANGED' => observationReasonLabel(code!),
  _ => '확인할 수 없는 중단 사유입니다. 서버 기록을 확인하세요.',
};
