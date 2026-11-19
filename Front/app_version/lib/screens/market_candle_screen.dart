import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models/market_candle.dart';
import '../repositories/market_data_repository.dart';
import '../repositories/realtime_market_repository.dart';
import 'market_realtime_screen.dart';
import '../theme/app_theme.dart';
import '../widgets/app_card.dart';
import '../widgets/app_text.dart';
import '../widgets/daily_model_signal_card.dart';
import '../widgets/status_chip.dart';
import 'dashboard_screen.dart';

/// 보유 종목의 실제 일·주·월봉을 확인하는 상세 화면입니다.
class MarketCandleScreen extends StatefulWidget {
  const MarketCandleScreen({
    super.key,
    required this.stockCode,
    required this.stockName,
    required this.market,
    required this.repository,
    this.usLookup,
  });

  final String stockCode;
  final String stockName;
  final String market;
  final MarketDataRepository repository;
  final UsStockLookup? usLookup;

  @override
  State<MarketCandleScreen> createState() => _MarketCandleScreenState();
}

class _MarketCandleScreenState extends State<MarketCandleScreen> {
  MarketCandleInterval _interval = MarketCandleInterval.daily;
  int? _selectedIndex;
  late Future<MarketCandleSnapshot> _future;
  Future<String>? _stockName;
  Future<({String provider, double price})>? _quote;

  @override
  void initState() {
    super.initState();
    _future = _fetchCandles();
    _fetchUsDetails();
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final lookup = widget.usLookup;
    return Scaffold(
      appBar: AppBar(
        backgroundColor: palette.surface,
        foregroundColor: palette.text,
        surfaceTintColor: Colors.transparent,
        titleSpacing: 8,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            FutureBuilder<String>(
              future: _stockName,
              builder: (context, snapshot) => Text(
                snapshot.data ?? widget.stockName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0,
                ),
              ),
            ),
            Text(
              '${widget.stockCode} · ${widget.market}',
              style: TextStyle(
                color: palette.muted,
                fontSize: 11,
                fontWeight: FontWeight.w700,
                letterSpacing: 0,
              ),
            ),
          ],
        ),
        actions: [
          if (lookup is UsDailySignalAccess &&
              widget.market == 'NASDAQ' &&
              const {'AAPL', 'NVDA'}.contains(widget.stockCode))
            TextButton(
              onPressed: () => _showDailySignal(lookup as UsDailySignalAccess),
              child: const Text('장 마감 모델'),
            ),
          if (widget.usLookup == null &&
              widget.repository is RealtimeMarketAccess)
            IconButton(
              tooltip: '실시간 체결·호가',
              icon: const Icon(Icons.sensors),
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => MarketRealtimeScreen(
                      stockCode: widget.stockCode,
                      stockName: widget.stockName,
                      repository:
                          (widget.repository as RealtimeMarketAccess).realtime,
                    ),
                  ),
                );
              },
            ),
          IconButton(
            onPressed: _reload,
            tooltip: '새로고침',
            icon: const Icon(Icons.refresh_rounded),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: Container(
        width: double.infinity,
        decoration: BoxDecoration(gradient: palette.pageGradient),
        child: SafeArea(
          top: false,
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1120),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (_quote != null) ...[
                      FutureBuilder<({String provider, double price})>(
                        future: _quote,
                        builder: (context, snapshot) {
                          if (snapshot.connectionState !=
                              ConnectionState.done) {
                            return const Text('현재가 조회 중');
                          }
                          final quote = snapshot.data;
                          if (quote == null) {
                            return const Text('현재가를 불러오지 못했습니다.');
                          }
                          return Text(
                            '현재가 ${_formatPrice(quote.price, 'USD')} · ${quote.provider}',
                          );
                        },
                      ),
                      const SizedBox(height: 12),
                    ],
                    _IntervalSelector(
                      selected: _interval,
                      onSelected: _selectInterval,
                    ),
                    const SizedBox(height: 16),
                    Expanded(
                      child: FutureBuilder<MarketCandleSnapshot>(
                        future: _future,
                        builder: (context, snapshot) {
                          if (snapshot.connectionState !=
                              ConnectionState.done) {
                            return const _CandleLoadingState();
                          }
                          if (snapshot.hasError || !snapshot.hasData) {
                            return _CandleErrorState(
                              message:
                                  snapshot.error?.toString() ??
                                  '캔들 시세를 불러오지 못했습니다.',
                              onRetry: _reload,
                            );
                          }
                          final data = snapshot.data!;
                          if (data.candles.isEmpty) {
                            return const _CandleEmptyState();
                          }
                          final selectedIndex =
                              (_selectedIndex ?? data.candles.length - 1)
                                  .clamp(0, data.candles.length - 1)
                                  .toInt();
                          return _CandleContent(
                            snapshot: data,
                            selectedIndex: selectedIndex,
                            onSelected: (index) {
                              if (_selectedIndex == index) {
                                return;
                              }
                              setState(() => _selectedIndex = index);
                            },
                          );
                        },
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Future<MarketCandleSnapshot> _fetchCandles() async {
    final data = await widget.repository.fetchCandles(
      stockCode: widget.stockCode,
      market: widget.market,
      interval: _interval,
    );
    if (widget.usLookup != null && data.currency != 'USD') {
      throw const MarketDataRepositoryException('미국주식 캔들 통화가 올바르지 않습니다.');
    }
    return data;
  }

  void _showDailySignal(UsDailySignalAccess access) {
    final signal = access.fetchUsDailySignal(widget.stockCode, widget.market);
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('${widget.stockCode} 장 마감 모델'),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: FutureBuilder(
              future: signal,
              builder: (context, snapshot) {
                if (snapshot.hasError) {
                  return const Text('장 마감 모델 신호를 불러오지 못했습니다.');
                }
                if (snapshot.data case final value?) {
                  return DailyModelSignalCard(
                    signal: value,
                    inputLabel: 'KIS NASDAQ USD 원주가 일봉',
                  );
                }
                return const Center(child: CircularProgressIndicator());
              },
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('닫기'),
          ),
        ],
      ),
    );
  }

  void _fetchUsDetails() {
    _stockName = widget.usLookup?.fetchUsStockName(
      widget.stockCode,
      widget.market,
    );
    _quote = widget.usLookup?.fetchUsQuote(widget.stockCode, widget.market);
  }

  void _selectInterval(MarketCandleInterval interval) {
    if (_interval == interval) {
      return;
    }
    setState(() {
      _interval = interval;
      _selectedIndex = null;
      _future = _fetchCandles();
    });
  }

  void _reload() {
    setState(() {
      _selectedIndex = null;
      _future = _fetchCandles();
      _fetchUsDetails();
    });
  }
}

class _IntervalSelector extends StatelessWidget {
  const _IntervalSelector({required this.selected, required this.onSelected});

  final MarketCandleInterval selected;
  final ValueChanged<MarketCandleInterval> onSelected;

  @override
  Widget build(BuildContext context) {
    return SegmentedButton<MarketCandleInterval>(
      showSelectedIcon: false,
      segments: [
        for (final interval in MarketCandleInterval.values)
          ButtonSegment(value: interval, label: Text('${interval.label}봉')),
      ],
      selected: {selected},
      onSelectionChanged: (values) => onSelected(values.first),
    );
  }
}

class _CandleContent extends StatelessWidget {
  const _CandleContent({
    required this.snapshot,
    required this.selectedIndex,
    required this.onSelected,
  });

  final MarketCandleSnapshot snapshot;
  final int selectedIndex;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    final selected = snapshot.candles[selectedIndex];
    final change = selected.closePrice - selected.openPrice;
    final changeRate = selected.openPrice == 0
        ? 0.0
        : change / selected.openPrice * 100;
    final changeColor = change < 0 ? AppTheme.sub : AppTheme.main;

    return LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxWidth < 680;
        return SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const LabelText('선택 종가'),
                        const SizedBox(height: 4),
                        Text(
                          _formatPrice(selected.closePrice, snapshot.currency),
                          style: TextStyle(
                            color: AppPalette.of(context).text,
                            fontSize: compact ? 26 : 32,
                            fontWeight: FontWeight.w900,
                            letterSpacing: 0,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          '${change >= 0 ? '+' : ''}${_formatPrice(change, snapshot.currency)}  ${changeRate >= 0 ? '+' : ''}${changeRate.toStringAsFixed(2)}%',
                          style: TextStyle(
                            color: changeColor,
                            fontSize: 13,
                            fontWeight: FontWeight.w900,
                            letterSpacing: 0,
                          ),
                        ),
                      ],
                    ),
                  ),
                  StatusChip(
                    label: '${snapshot.provider} 데이터',
                    icon: Icons.cloud_done_outlined,
                  ),
                ],
              ),
              const SizedBox(height: 16),
              AppCard(
                padding: const EdgeInsets.fromLTRB(14, 14, 10, 10),
                child: Column(
                  children: [
                    _CandleMetrics(
                      candle: selected,
                      compact: compact,
                      currency: snapshot.currency,
                    ),
                    const SizedBox(height: 12),
                    SizedBox(
                      height: compact ? 320 : 410,
                      child: _InteractiveCandleChart(
                        candles: snapshot.candles,
                        currency: snapshot.currency,
                        selectedIndex: selectedIndex,
                        onSelected: onSelected,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _CandleMetrics extends StatelessWidget {
  const _CandleMetrics({
    required this.candle,
    required this.compact,
    required this.currency,
  });

  final MarketCandle candle;
  final bool compact;
  final String currency;

  @override
  Widget build(BuildContext context) {
    final metrics = [
      ('날짜', _formatCandleDate(candle.dateTime)),
      ('시가', _formatPrice(candle.openPrice, currency)),
      ('고가', _formatPrice(candle.highPrice, currency)),
      ('저가', _formatPrice(candle.lowPrice, currency)),
      ('거래량', _compactNumber(candle.volume)),
    ];
    return Wrap(
      spacing: compact ? 16 : 28,
      runSpacing: 10,
      children: [
        for (final metric in metrics)
          SizedBox(
            width: compact ? 92 : 130,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                LabelText(metric.$1),
                const SizedBox(height: 3),
                Text(
                  metric.$2,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: AppPalette.of(context).text,
                    fontSize: 13,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _InteractiveCandleChart extends StatelessWidget {
  const _InteractiveCandleChart({
    required this.candles,
    required this.currency,
    required this.selectedIndex,
    required this.onSelected,
  });

  final List<MarketCandle> candles;
  final String currency;
  final int selectedIndex;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return LayoutBuilder(
      builder: (context, constraints) {
        void selectAt(Offset position) {
          const plotLeft = 8.0;
          const labelWidth = 68.0;
          final plotWidth = math.max(
            1.0,
            constraints.maxWidth - plotLeft - labelWidth,
          );
          final ratio = ((position.dx - plotLeft) / plotWidth).clamp(
            0.0,
            0.9999,
          );
          onSelected((ratio * candles.length).floor());
        }

        return MouseRegion(
          cursor: SystemMouseCursors.precise,
          onHover: (event) => selectAt(event.localPosition),
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTapDown: (details) => selectAt(details.localPosition),
            child: CustomPaint(
              painter: _CandleChartPainter(
                candles: candles,
                currency: currency,
                selectedIndex: selectedIndex,
                risingColor: AppTheme.main,
                fallingColor: AppTheme.sub,
                gridColor: palette.border,
                textColor: palette.muted,
                selectionColor: AppTheme.point,
              ),
              child: const SizedBox.expand(),
            ),
          ),
        );
      },
    );
  }
}

String _formatPrice(double value, String currency) {
  if (currency != 'USD') return '${formatCurrency(value.round())}원';
  final decimals = value
      .toStringAsFixed(4)
      .replaceFirstMapped(
        RegExp(r'(\.\d{2,3}?)0+$'),
        (match) => match.group(1)!,
      );
  return '$decimals USD';
}

class _CandleChartPainter extends CustomPainter {
  const _CandleChartPainter({
    required this.candles,
    required this.currency,
    required this.selectedIndex,
    required this.risingColor,
    required this.fallingColor,
    required this.gridColor,
    required this.textColor,
    required this.selectionColor,
  });

  final List<MarketCandle> candles;
  final String currency;
  final int selectedIndex;
  final Color risingColor;
  final Color fallingColor;
  final Color gridColor;
  final Color textColor;
  final Color selectionColor;

  @override
  void paint(Canvas canvas, Size size) {
    if (candles.isEmpty || size.width <= 90 || size.height <= 120) {
      return;
    }

    const left = 8.0;
    const rightLabels = 68.0;
    const top = 8.0;
    const bottomLabels = 24.0;
    const volumeHeight = 58.0;
    const volumeGap = 14.0;
    final plotWidth = size.width - left - rightLabels;
    final priceBottom = size.height - bottomLabels - volumeHeight - volumeGap;
    final volumeTop = priceBottom + volumeGap;
    final priceHeight = priceBottom - top;
    final maxPrice = candles.map((item) => item.highPrice).reduce(math.max);
    final minPrice = candles.map((item) => item.lowPrice).reduce(math.min);
    final rawRange = maxPrice - minPrice;
    final padding = rawRange == 0
        ? math.max(maxPrice * .01, 1.0)
        : rawRange * .06;
    final chartMax = maxPrice + padding;
    final chartMin = minPrice - padding;
    final priceRange = chartMax - chartMin;
    final maxVolume = candles.map((item) => item.volume).reduce(math.max);
    final slotWidth = plotWidth / candles.length;
    final bodyWidth = (slotWidth * .58).clamp(2.0, 12.0).toDouble();

    double xFor(int index) => left + slotWidth * (index + .5);
    double yFor(double value) =>
        top + (chartMax - value) / priceRange * priceHeight;

    final gridPaint = Paint()
      ..color = gridColor
      ..strokeWidth = 1;
    for (var i = 0; i <= 4; i++) {
      final ratio = i / 4;
      final y = top + priceHeight * ratio;
      canvas.drawLine(Offset(left, y), Offset(left + plotWidth, y), gridPaint);
      _paintText(
        canvas,
        currency == 'USD'
            ? (chartMax - priceRange * ratio).toStringAsFixed(2)
            : formatCurrency((chartMax - priceRange * ratio).round()),
        Offset(left + plotWidth + 7, y - 7),
        textColor,
        maxWidth: rightLabels - 7,
      );
    }

    final selectedX = xFor(selectedIndex);
    canvas.drawRect(
      Rect.fromLTWH(selectedX - slotWidth / 2, top, slotWidth, priceHeight),
      Paint()..color = selectionColor.withValues(alpha: .10),
    );
    canvas.drawLine(
      Offset(selectedX, top),
      Offset(selectedX, size.height - bottomLabels),
      Paint()
        ..color = selectionColor.withValues(alpha: .72)
        ..strokeWidth = 1,
    );

    for (var index = 0; index < candles.length; index++) {
      final candle = candles[index];
      final x = xFor(index);
      final color = candle.isRising ? risingColor : fallingColor;
      final candlePaint = Paint()
        ..color = color
        ..strokeWidth = index == selectedIndex ? 2 : 1;
      canvas.drawLine(
        Offset(x, yFor(candle.highPrice)),
        Offset(x, yFor(candle.lowPrice)),
        candlePaint,
      );
      final openY = yFor(candle.openPrice);
      final closeY = yFor(candle.closePrice);
      final bodyTop = math.min(openY, closeY);
      final bodyHeight = math.max((openY - closeY).abs(), 1.5);
      canvas.drawRect(
        Rect.fromLTWH(x - bodyWidth / 2, bodyTop, bodyWidth, bodyHeight),
        candlePaint,
      );

      final volumeRatio = maxVolume <= 0 ? 0.0 : candle.volume / maxVolume;
      final barHeight = volumeHeight * volumeRatio;
      canvas.drawRect(
        Rect.fromLTWH(
          x - bodyWidth / 2,
          volumeTop + volumeHeight - barHeight,
          bodyWidth,
          barHeight,
        ),
        Paint()..color = color.withValues(alpha: .42),
      );
    }

    for (final index in {0, candles.length ~/ 2, candles.length - 1}) {
      final text = _shortDate(candles[index].dateTime);
      final painter = TextPainter(
        text: TextSpan(
          text: text,
          style: TextStyle(
            color: textColor,
            fontSize: 10,
            fontWeight: FontWeight.w700,
            letterSpacing: 0,
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      final x = (xFor(index) - painter.width / 2)
          .clamp(left, left + plotWidth - painter.width)
          .toDouble();
      painter.paint(canvas, Offset(x, size.height - bottomLabels + 5));
    }
  }

  void _paintText(
    Canvas canvas,
    String text,
    Offset offset,
    Color color, {
    required double maxWidth,
  }) {
    final painter = TextPainter(
      text: TextSpan(
        text: text,
        style: TextStyle(
          color: color,
          fontSize: 10,
          fontWeight: FontWeight.w700,
          letterSpacing: 0,
        ),
      ),
      maxLines: 1,
      ellipsis: '…',
      textDirection: TextDirection.ltr,
    )..layout(maxWidth: maxWidth);
    painter.paint(canvas, offset);
  }

  @override
  bool shouldRepaint(covariant _CandleChartPainter oldDelegate) {
    return oldDelegate.candles != candles ||
        oldDelegate.selectedIndex != selectedIndex ||
        oldDelegate.gridColor != gridColor ||
        oldDelegate.textColor != textColor;
  }
}

class _CandleLoadingState extends StatelessWidget {
  const _CandleLoadingState();

  @override
  Widget build(BuildContext context) {
    return const Center(child: CircularProgressIndicator());
  }
}

class _CandleErrorState extends StatelessWidget {
  const _CandleErrorState({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 440),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.show_chart_rounded, color: AppTheme.sub, size: 42),
            const SizedBox(height: 12),
            Text(
              '차트를 불러오지 못했습니다',
              style: TextStyle(
                color: palette.text,
                fontSize: 18,
                fontWeight: FontWeight.w900,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              message,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: palette.muted,
                fontSize: 13,
                height: 1.4,
                fontWeight: FontWeight.w700,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh_rounded),
              label: const Text('다시 시도'),
            ),
          ],
        ),
      ),
    );
  }
}

class _CandleEmptyState extends StatelessWidget {
  const _CandleEmptyState();

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Center(
      child: Text(
        '조회된 캔들 시세가 없습니다.',
        style: TextStyle(
          color: palette.muted,
          fontSize: 14,
          fontWeight: FontWeight.w800,
          letterSpacing: 0,
        ),
      ),
    );
  }
}

String _formatCandleDate(DateTime value) {
  final month = value.month.toString().padLeft(2, '0');
  final day = value.day.toString().padLeft(2, '0');
  return '${value.year}.$month.$day';
}

String _shortDate(DateTime value) {
  return '${value.month.toString().padLeft(2, '0')}.${value.day.toString().padLeft(2, '0')}';
}

String _compactNumber(double value) {
  if (value >= 100000000) {
    return '${(value / 100000000).toStringAsFixed(1)}억';
  }
  if (value >= 10000) {
    return '${(value / 10000).toStringAsFixed(1)}만';
  }
  return formatCurrency(value.round());
}
