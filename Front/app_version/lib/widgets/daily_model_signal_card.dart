import 'dart:async';

import 'package:flutter/material.dart';

import '../models/recommendation.dart';
import 'app_card.dart';
import 'app_text.dart';

class DailyModelSignalCard extends StatefulWidget {
  const DailyModelSignalCard({
    super.key,
    required this.signal,
    this.inputLabel = 'KIS KRX 원주가 일봉',
  });

  final DailyModelSignal signal;
  final String inputLabel;

  @override
  State<DailyModelSignalCard> createState() => _DailyModelSignalCardState();
}

class _DailyModelSignalCardState extends State<DailyModelSignalCard> {
  Timer? _expiryTimer;

  @override
  void initState() {
    super.initState();
    _scheduleExpiry();
  }

  @override
  void didUpdateWidget(DailyModelSignalCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.signal.expiresAt != widget.signal.expiresAt) {
      _scheduleExpiry();
    }
  }

  @override
  void dispose() {
    _expiryTimer?.cancel();
    super.dispose();
  }

  void _scheduleExpiry() {
    _expiryTimer?.cancel();
    final remaining = widget.signal.expiresAt?.difference(DateTime.now());
    if (remaining != null && remaining > Duration.zero) {
      _expiryTimer = Timer(remaining, () => setState(() {}));
    }
  }

  @override
  Widget build(BuildContext context) {
    final signal = widget.signal;
    final expiresAt = signal.expiresAt;
    final hasPrediction = signal.probability != null && expiresAt != null;
    final expired = expiresAt != null && !DateTime.now().isBefore(expiresAt);
    final label = switch ((hasPrediction, expired, signal.decision)) {
      (true, true, _) => '만료',
      (true, false, 'BUY_WATCH') => '매수 관찰',
      (true, false, 'WAIT') => '관망',
      _ => '신호 보류',
    };
    final factors = signal.contributions.entries.where((factor) {
      return factor.value != 0 && _featureLabels.containsKey(factor.key);
    }).toList()..sort((a, b) => b.value.abs().compareTo(a.value.abs()));

    return AppCard(
      soft: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '장 마감 모델 · $label',
            style: const TextStyle(fontWeight: FontWeight.w800),
          ),
          if (signal.basisDate != null) Text('기준 거래일 ${signal.basisDate}'),
          if (hasPrediction) ...[
            Text('다음 거래일 시가 대비 종가 상승 확률 ${_percent(signal.probability!)}'),
            if (signal.threshold != null)
              Text('매수 관찰 기준 ${_percent(signal.threshold!)}'),
            Text('만료 ${_koreaTime(expiresAt)} KST'),
            if (signal.modelVersion != null)
              TextCaption('모델 ${signal.modelVersion} · ${widget.inputLabel}'),
            if (factors.isNotEmpty)
              Text(
                '주요 판단 근거 · ${factors.take(2).map((factor) => '${_featureLabels[factor.key]}(${factor.value > 0 ? '상승 확률 높임' : '상승 확률 낮춤'})').join(' · ')}',
              ),
          ] else
            Text(_holdDescription(signal.holdReason)),
          if (signal.evaluatedAt != null)
            TextCaption('평가 ${_koreaTime(signal.evaluatedAt!)} KST'),
        ],
      ),
    );
  }
}

const _featureLabels = {
  'openToClose': '당일 시가 대비 종가 변화',
  'closeReturn1': '최근 1거래일 수익률',
  'closeReturn5': '최근 5거래일 수익률',
  'closeReturn20': '최근 20거래일 수익률',
  'rangeOverOpen': '당일 고저폭',
  'closeVolatility20': '20거래일 변동성',
  'volumeRatio20': '직전 20거래일 대비 거래량',
};

String _holdDescription(String? reason) => switch (reason) {
  'BAR_NOT_FINAL' => '기준 거래일의 일봉 확정을 기다리고 있습니다.',
  'BAR_MISSING_OR_INVALID' => '필요한 거래일의 KIS 원주가 일봉을 확인할 수 없습니다.',
  'CALENDAR_UNAVAILABLE' => '입력과 만료에 필요한 거래일 일정이 없습니다.',
  'SIGNAL_EXPIRED' => '평가 도중 다음 거래일의 정규장이 종료되었습니다.',
  _ => '이 종목의 장 마감 모델을 사용할 수 없습니다.',
};

String _percent(double value) => '${(value * 100).toStringAsFixed(2)}%';

String _koreaTime(DateTime value) {
  final korea = value.toUtc().add(const Duration(hours: 9));
  return korea.toIso8601String().substring(0, 16).replaceFirst('T', ' ');
}
