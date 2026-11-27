import 'dart:async';

import 'package:flutter/material.dart';

import '../models/paper_trading.dart';
import '../repositories/paper_trading_repository.dart';
import '../widgets/app_card.dart';
import '../widgets/app_text.dart';
import '../widgets/responsive_layout.dart';
import '../widgets/status_chip.dart';
import 'dashboard_screen.dart';

class AutomatedPaperTradingScreen extends StatefulWidget {
  const AutomatedPaperTradingScreen({super.key, required this.repository});

  final AutomatedPaperTradingRepository repository;

  @override
  State<AutomatedPaperTradingScreen> createState() =>
      _AutomatedPaperTradingScreenState();
}

class _AutomatedPaperTradingScreenState
    extends State<AutomatedPaperTradingScreen> {
  late final Timer _poll;
  AutomatedPaperSnapshot? _snapshot;
  bool _loading = false;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    _refresh();
    _poll = Timer.periodic(const Duration(seconds: 15), (_) => _refresh());
  }

  @override
  void dispose() {
    _poll.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    if (_loading) return;
    setState(() => _loading = true);
    try {
      final next = await widget.repository.fetchAutomatedSnapshot();
      if (!mounted) return;
      setState(() {
        _snapshot = next;
        _failed = false;
      });
    } catch (_) {
      if (mounted) setState(() => _failed = true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final snapshot = _snapshot;
    return Scaffold(
      appBar: AppBar(
        title: const Text('AI 자동 모의매매'),
        actions: [
          IconButton(
            onPressed: _loading ? null : _refresh,
            icon: const Icon(Icons.refresh_rounded),
            tooltip: '자동 모의매매 새로고침',
          ),
        ],
      ),
      body: snapshot == null && _loading && !_failed
          ? const Center(child: CircularProgressIndicator())
          : AppScrollView(
              child: snapshot == null
                  ? AppCard(
                      child: TextBody(
                        _failed
                            ? '자동 모의매매 현황을 불러오지 못했습니다.'
                            : '조회 가능한 자동 모의매매 실행이 없습니다.',
                      ),
                    )
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        AdaptiveColumns(
                          first: _portfolio(snapshot),
                          second: _entry(snapshot),
                          breakpoint: 740,
                        ),
                        const SizedBox(height: 12),
                        _daily(snapshot.closedDays),
                        const SizedBox(height: 12),
                        _fills(snapshot),
                      ],
                    ),
            ),
    );
  }

  Widget _portfolio(AutomatedPaperSnapshot snapshot) {
    final portfolio = snapshot.portfolio;
    final online = snapshot.online && !_failed;
    return _card('${snapshot.stockName} (${snapshot.stockCode})', [
      Wrap(
        spacing: 8,
        runSpacing: 6,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          StatusChip(label: online ? snapshot.status : '업데이트 지연'),
          const TextBody('가격 규칙 · 가상 체결'),
        ],
      ),
      TextBody('장 마감 종료 ${snapshot.endDate}'),
      TextBody(
        '순자산 ${_won(portfolio.netAsset)} · 시작 현금 ${_won(portfolio.initialCash)}',
      ),
      TextBody(
        '가상 현금 ${_won(portfolio.cash)} · 보유 ${_shares(portfolio.quantity)}주',
      ),
      TextBody(
        '실현손익 ${_won(portfolio.realizedProfit, signed: true)} · '
        '미실현손익 ${_won(portfolio.unrealizedProfit, signed: true)}',
      ),
      if (portfolio.markPrice case final mark?)
        TextBody('${portfolio.markSource ?? '평가 가격'} ${_won(mark)}'),
      TextBody('원장 갱신 ${_kst(snapshot.publishedAt)}'),
      if (snapshot.lastMarketAt case final last?)
        TextBody('최근 장중 시세 ${_kst(last)}'),
    ]);
  }

  Widget _entry(AutomatedPaperSnapshot snapshot) {
    final entry = snapshot.entry;
    return _card('최초 매수 기준', [
      TextBody(entry.rule),
      TextBody('적용 거래일 ${entry.appliesOn}'),
      if (!entry.eligible)
        const TextBody('후속 매매 조건을 적용 중입니다.')
      else if (entry.threshold case final threshold?)
        TextBody('매수 기준가 ${_won(threshold)} 이하')
      else
        const TextBody('기준가 계산 대기'),
      if (entry.averageClose case final average?)
        TextBody('5거래일 종가 평균 ${_won(average)}'),
      if (entry.previousClose case final close?)
        TextBody('전 거래일 종가 ${_won(close)}'),
    ]);
  }

  Widget _daily(List<AutomatedPaperDay> days) => _card('일별 마감', [
    if (days.isEmpty) const TextBody('마감 집계가 아직 없습니다.'),
    for (final day in days)
      TextBody(
        '${day.date} · 매수 ${day.buyCount}건 · 매도 ${day.sellCount}건 · '
        '순손익 ${_won(day.profit, signed: true)}',
      ),
  ]);

  Widget _fills(
    AutomatedPaperSnapshot snapshot,
  ) => _card('자동 체결 ${snapshot.fillCount}건', [
    if (snapshot.fills.isEmpty) const TextBody('기록된 자동 체결이 없습니다.'),
    for (final fill in snapshot.fills) ...[
      const AppDivider(),
      TextBody(
        '${fill.side == 'BUY' ? '매수' : '매도'} · 주문 ${fill.id} · ${_kst(fill.at)}',
      ),
      TextBody(
        '${_shares(fill.quantity)}주 × ${_won(fill.price)} · 비용 ${_won(fill.costs)}',
      ),
      TextBody('${fill.rule} · 조건 경계 ${_won(fill.threshold)}'),
      if (fill.side == 'SELL')
        TextBody('실현손익 ${_won(fill.realizedProfit, signed: true)}'),
    ],
  ]);

  Widget _card(String title, List<Widget> details) => AppCard(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        CardTitle(title),
        for (final detail in details) ...[const SizedBox(height: 8), detail],
      ],
    ),
  );
}

String _won(double? value, {bool signed = false}) {
  if (value == null) return '미확정';
  return '${signed && value > 0 ? '+' : ''}${formatCurrency(value.round())}원';
}

String _shares(double value) => value == value.truncateToDouble()
    ? value.truncate().toString()
    : value.toStringAsFixed(4);

String _kst(DateTime value) {
  final seoul = value.toUtc().add(const Duration(hours: 9));
  final timestamp = seoul.toIso8601String();
  return '${timestamp.substring(0, 10)} ${timestamp.substring(11, 19)} KST';
}
