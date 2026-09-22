import 'package:flutter/material.dart';

import '../models/investment_snapshot.dart';
import '../models/watchlist_item.dart';
import '../theme/app_theme.dart';
import 'dashboard_screen.dart';

/// 화면 위에 고정해 핵심 투자 지표만 빠르게 확인하는 소형 창입니다.
class MiniWidgetScreen extends StatelessWidget {
  const MiniWidgetScreen({
    super.key,
    required this.snapshot,
    required this.watchlist,
    required this.onExpand,
    required this.onRefresh,
    required this.onHide,
  });

  final InvestmentSnapshot snapshot;
  final List<WatchlistItem> watchlist;
  final VoidCallback onExpand;
  final VoidCallback onRefresh;
  final VoidCallback onHide;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final portfolio = snapshot.portfolioSummary;
    final recommendation = snapshot.recommendation;

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onDoubleTap: onExpand,
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(
                    Icons.trending_up_rounded,
                    color: AppTheme.main,
                    size: 24,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      '사고팔고',
                      style: TextStyle(
                        color: palette.text,
                        fontSize: 18,
                        fontWeight: FontWeight.w900,
                        letterSpacing: 0,
                      ),
                    ),
                  ),
                  IconButton(
                    onPressed: onRefresh,
                    tooltip: '새로고침',
                    icon: const Icon(Icons.refresh_rounded),
                  ),
                  IconButton(
                    onPressed: onExpand,
                    tooltip: '전체 화면',
                    icon: const Icon(Icons.open_in_full_rounded),
                  ),
                  IconButton(
                    onPressed: onHide,
                    tooltip: '트레이로 숨기기',
                    icon: const Icon(Icons.keyboard_arrow_down_rounded),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: palette.surface,
                  border: Border.all(color: palette.border),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: _Metric(
                        label: '총 손익',
                        value: '${_signedMoney(portfolio.totalProfit)}원',
                        color: _changeColor(portfolio.totalProfit.toDouble()),
                      ),
                    ),
                    Container(width: 1, height: 38, color: palette.border),
                    const SizedBox(width: 14),
                    Expanded(
                      child: _Metric(
                        label: '수익률',
                        value: formatSignedPercent(portfolio.profitRate),
                        color: _changeColor(portfolio.profitRate),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              _SectionLabel(label: '관심 종목', count: watchlist.length),
              const SizedBox(height: 6),
              if (watchlist.isEmpty)
                _EmptyLine(label: '등록된 관심 종목 없음')
              else
                ...watchlist.take(3).map((item) => _WatchlistRow(item: item)),
              const SizedBox(height: 14),
              const _SectionLabel(label: 'AI 신호'),
              const SizedBox(height: 6),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: palette.softSurface,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: recommendation == null
                    ? Text(
                        '분석된 신호 없음',
                        style: TextStyle(
                          color: palette.muted,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 0,
                        ),
                      )
                    : Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  recommendation.stockName,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: TextStyle(
                                    color: palette.text,
                                    fontSize: 14,
                                    fontWeight: FontWeight.w900,
                                    letterSpacing: 0,
                                  ),
                                ),
                                const SizedBox(height: 3),
                                Text(
                                  recommendation.status,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                    color: AppTheme.main,
                                    fontSize: 12,
                                    fontWeight: FontWeight.w800,
                                    letterSpacing: 0,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Text(
                            '${recommendation.score}점',
                            style: const TextStyle(
                              color: AppTheme.point,
                              fontSize: 18,
                              fontWeight: FontWeight.w900,
                              letterSpacing: 0,
                            ),
                          ),
                        ],
                      ),
              ),
              const Spacer(),
              Row(
                children: [
                  Icon(Icons.circle, size: 7, color: Colors.green.shade500),
                  const SizedBox(width: 6),
                  Text(
                    '실시간 연결',
                    style: TextStyle(
                      color: palette.muted,
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0,
                    ),
                  ),
                  const Spacer(),
                  Text(
                    '더블클릭하여 대시보드 열기',
                    style: TextStyle(
                      color: palette.muted,
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _WatchlistRow extends StatelessWidget {
  const _WatchlistRow({required this.item});

  final WatchlistItem item;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return SizedBox(
      height: 48,
      child: Row(
        children: [
          Expanded(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.stockName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: palette.text,
                    fontSize: 13,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
                Text(
                  '${item.market} · ${item.provider}',
                  style: TextStyle(
                    color: palette.muted,
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
          ),
          Text(
            '${formatCurrency(item.currentPrice)}원',
            style: TextStyle(
              color: palette.text,
              fontSize: 13,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(width: 10),
          SizedBox(
            width: 58,
            child: Text(
              formatSignedPercent(item.changeRate),
              textAlign: TextAlign.right,
              style: TextStyle(
                color: _changeColor(item.changeRate),
                fontSize: 12,
                fontWeight: FontWeight.w900,
                letterSpacing: 0,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            color: palette.muted,
            fontSize: 11,
            fontWeight: FontWeight.w700,
            letterSpacing: 0,
          ),
        ),
        const SizedBox(height: 3),
        Text(
          value,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: color,
            fontSize: 16,
            fontWeight: FontWeight.w900,
            letterSpacing: 0,
          ),
        ),
      ],
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel({required this.label, this.count});

  final String label;
  final int? count;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Row(
      children: [
        Text(
          label,
          style: TextStyle(
            color: palette.text,
            fontSize: 12,
            fontWeight: FontWeight.w900,
            letterSpacing: 0,
          ),
        ),
        if (count != null) ...[
          const SizedBox(width: 6),
          Text(
            '$count',
            style: const TextStyle(
              color: AppTheme.main,
              fontSize: 11,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
        ],
      ],
    );
  }
}

class _EmptyLine extends StatelessWidget {
  const _EmptyLine({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return SizedBox(
      height: 48,
      child: Align(
        alignment: Alignment.centerLeft,
        child: Text(
          label,
          style: TextStyle(
            color: palette.muted,
            fontSize: 12,
            fontWeight: FontWeight.w700,
            letterSpacing: 0,
          ),
        ),
      ),
    );
  }
}

Color _changeColor(double value) {
  if (value > 0) return AppTheme.sub;
  if (value < 0) return const Color(0xff3578e5);
  return AppTheme.main;
}

String _signedMoney(int value) {
  final sign = value > 0 ? '+' : '';
  return '$sign${formatCurrency(value)}';
}
