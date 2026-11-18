import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';

import '../models/learning_evaluation.dart';
import '../widgets/app_card.dart';
import '../widgets/app_text.dart';
import '../widgets/responsive_layout.dart';
import 'dashboard_screen.dart';

class LearningEvaluationButton extends StatelessWidget {
  const LearningEvaluationButton({super.key});

  @override
  Widget build(BuildContext context) => OutlinedButton.icon(
    onPressed: () => Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => const LearningEvaluationScreen()),
    ),
    icon: const Icon(Icons.analytics_outlined),
    label: const Text('로컬 모델 평가'),
  );
}

class LearningEvaluationScreen extends StatefulWidget {
  const LearningEvaluationScreen({super.key});

  @override
  State<LearningEvaluationScreen> createState() =>
      _LearningEvaluationScreenState();
}

class _LearningEvaluationScreenState extends State<LearningEvaluationScreen> {
  final _path = TextEditingController();
  LearningEvaluation? _evaluation;
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _path.dispose();
    super.dispose();
  }

  Future<void> _open() async {
    if (_loading) return;
    final path = _path.text.trim().replaceAll(RegExp(r'^"|"$'), '');
    if (path.isEmpty) {
      setState(() => _error = 'app-summary.json의 로컬 경로를 입력하세요.');
      return;
    }
    setState(() {
      _loading = true;
      _evaluation = null;
      _error = null;
    });
    LearningEvaluation? evaluation;
    String? error;
    try {
      final file = await File(path).open();
      try {
        const maxBytes = 64 * 1024;
        final bytes = await file.read(maxBytes + 1);
        if (bytes.length > maxBytes) {
          throw const FormatException('Evaluation summary too large');
        }
        evaluation = LearningEvaluation.parse(utf8.decode(bytes));
      } finally {
        await file.close();
      }
    } on FileSystemException {
      error = '요약 파일을 열 수 없습니다. 로컬 경로를 확인하세요.';
    } on FormatException {
      error = '학습 도구에서 생성한 app-summary.json을 선택하세요.';
    } on TypeError {
      error = '평가 요약에 필요한 항목이 없습니다.';
    }
    if (!mounted) return;
    setState(() {
      _evaluation = evaluation;
      _error = error;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final evaluation = _evaluation;
    return Scaffold(
      appBar: AppBar(title: const Text('로컬 모델 평가')),
      body: AppScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextField(
              controller: _path,
              enabled: !_loading,
              decoration: InputDecoration(
                labelText: '평가 요약 파일 경로',
                hintText: 'app-summary.json',
                errorText: _error,
              ),
              onSubmitted: (_) => _open(),
            ),
            const SizedBox(height: 8),
            FilledButton(
              onPressed: _loading ? null : _open,
              child: const Text('결과 열기'),
            ),
            if (_loading) const LinearProgressIndicator(),
            if (evaluation != null) ...[
              const SizedBox(height: 20),
              CardTitle('공통 최종 평가 · ${evaluation.samples}일'),
              TextBody(
                '정답일 ${evaluation.firstTargetDate} ~ ${evaluation.lastTargetDate}'
                ' · 다음 거래일 시가 진입, 종가 청산 가정',
              ),
              for (final scenario in LearningEvaluation.scenarios)
                _costLine(scenario, evaluation.costs[scenario]!),
              const SizedBox(height: 12),
              AdaptiveColumns(
                first: _StockResult(stock: evaluation.stocks[0]),
                second: _StockResult(stock: evaluation.stocks[1]),
                breakpoint: 1040,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

String _scenario(String name) => name == 'base' ? '기본 비용' : '높은 비용';

Widget _costLine(String name, TradingCosts costs) => TextBody(
  '${_scenario(name)} · 편도 수수료 ${costs.fee}bps · 편도 체결 불리분 '
  '${costs.slippage}bps · 매도 제세금 ${costs.sellTax}bps',
);

String _percent(double value) => '${(100 * value).toStringAsFixed(2)}%';

class _StockResult extends StatelessWidget {
  const _StockResult({required this.stock});

  static const labels = {
    'model': '로지스틱 모델',
    'daily': '매일 진입',
    'trend5': '5일 상승 추세',
    'cash': '거래 없음',
  };
  final StockLearningEvaluation stock;

  @override
  Widget build(BuildContext context) {
    final threshold = stock.threshold;
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          CardTitle(
            '${LearningEvaluation.stockNames[stock.code]} (${stock.code})',
          ),
          TextBody(
            '${stock.version} · 매수 관찰 임곗값 '
            '${threshold == null ? '진입 안 함' : _percent(threshold)}',
          ),
          const SizedBox(height: 8),
          const CardTitle('예측 품질'),
          _predictionLine('로지스틱 모델', stock.model),
          _predictionLine('학습 상승 빈도', stock.frequency),
          for (final scenario in LearningEvaluation.scenarios) ...[
            const SizedBox(height: 12),
            CardTitle(_scenario(scenario)),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: DataTable(
                horizontalMargin: 0,
                columnSpacing: 16,
                columns: const [
                  DataColumn(label: Text('전략')),
                  DataColumn(label: Text('순수익률'), numeric: true),
                  DataColumn(label: Text('최대 낙폭'), numeric: true),
                  DataColumn(label: Text('거래'), numeric: true),
                ],
                rows: [
                  for (final name in LearningEvaluation.strategies)
                    _strategyRow(name, stock.strategies[scenario]![name]!),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _predictionLine(String label, PredictionQuality result) => TextBody(
    '$label · 적중률 ${_percent(result.accuracy)} · 로그 손실 '
    '${result.logLoss.toStringAsFixed(4)}',
  );

  DataRow _strategyRow(String strategy, TradingResult result) => DataRow(
    cells: [
      DataCell(Text(labels[strategy]!)),
      DataCell(Text(_percent(result.netReturn))),
      DataCell(Text(_percent(result.maxDrawdown))),
      DataCell(Text('${result.trades}회')),
    ],
  );
}
