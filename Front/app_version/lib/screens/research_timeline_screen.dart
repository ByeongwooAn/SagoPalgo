import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/research_feed.dart';
import '../repositories/research_feed_repository.dart';
import '../theme/app_theme.dart';
import '../widgets/app_card.dart';
import '../widgets/section_header.dart';
import '../widgets/status_chip.dart';
import 'dashboard_screen.dart';

enum ResearchTimelineFilter { all, news, disclosures }

/// 보유·추천 종목의 뉴스와 공시를 시간순으로 조회하는 화면입니다.
class ResearchTimelineScreen extends StatefulWidget {
  const ResearchTimelineScreen({
    super.key,
    required this.repository,
    required this.stocks,
    required this.active,
    required this.onHoldingSetupOpen,
  });

  final ResearchFeedRepository repository;
  final List<ResearchStock> stocks;
  final bool active;
  final VoidCallback onHoldingSetupOpen;

  @override
  State<ResearchTimelineScreen> createState() => _ResearchTimelineScreenState();
}

class _ResearchTimelineScreenState extends State<ResearchTimelineScreen> {
  ResearchStock? _selectedStock;
  Future<ResearchFeed>? _feedFuture;
  ResearchTimelineFilter _filter = ResearchTimelineFilter.all;
  bool _syncing = false;

  @override
  void initState() {
    super.initState();
    _selectedStock = widget.stocks.isEmpty ? null : widget.stocks.first;
    if (widget.active && _selectedStock != null) {
      _feedFuture = widget.repository.fetchFeed(_selectedStock!);
    }
  }

  @override
  void didUpdateWidget(covariant ResearchTimelineScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    final selected = _selectedStock;
    final matched = selected == null
        ? null
        : _findStock(widget.stocks, selected.stockCode);
    if (matched == null && widget.stocks.isNotEmpty) {
      _selectedStock = widget.stocks.first;
      _feedFuture = null;
    } else if (matched != null) {
      _selectedStock = matched;
    }

    if (widget.active && !oldWidget.active && _selectedStock != null) {
      _feedFuture = widget.repository.fetchFeed(_selectedStock!);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionHeader(
            eyebrow: '리서치 피드',
            title: '뉴스 · 공시',
            action: StatusChip(
              label: '로컬 저장',
              icon: Icons.storage_rounded,
              gradient: AppGradients.main,
            ),
          ),
          const SizedBox(height: 16),
          if (widget.stocks.isEmpty)
            _NoStockState(onHoldingSetupOpen: widget.onHoldingSetupOpen)
          else ...[
            _StockControls(
              stocks: widget.stocks,
              selectedStock: _selectedStock!,
              syncing: _syncing,
              onChanged: _selectStock,
              onSync: _syncFeed,
            ),
            const SizedBox(height: 12),
            _FilterControl(
              selected: _filter,
              onChanged: (filter) => setState(() => _filter = filter),
            ),
            const SizedBox(height: 12),
            _buildFeed(),
          ],
          const SizedBox(height: 12),
        ],
      ),
    );
  }

  Widget _buildFeed() {
    final future = _feedFuture;
    if (future == null) {
      return widget.active
          ? const _TimelineLoadingState()
          : const SizedBox.shrink();
    }

    return FutureBuilder<ResearchFeed>(
      future: future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const _TimelineLoadingState();
        }
        if (snapshot.hasError || !snapshot.hasData) {
          return _TimelineErrorState(
            message: _errorMessage(snapshot.error),
            onRetry: _loadStoredFeed,
          );
        }

        final feed = snapshot.data!;
        final entries = _entries(feed, _filter);
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _ProviderStatusStrip(statuses: feed.providers),
            const SizedBox(height: 12),
            if (entries.isEmpty)
              _EmptyFeedState(filter: _filter)
            else
              for (var index = 0; index < entries.length; index++) ...[
                _TimelineCard(entry: entries[index]),
                if (index < entries.length - 1) const SizedBox(height: 10),
              ],
          ],
        );
      },
    );
  }

  void _selectStock(ResearchStock stock) {
    setState(() {
      _selectedStock = stock;
      _filter = ResearchTimelineFilter.all;
      _feedFuture = widget.repository.fetchFeed(stock);
    });
  }

  void _loadStoredFeed() {
    final stock = _selectedStock;
    if (stock == null) {
      return;
    }
    setState(() {
      _feedFuture = widget.repository.fetchFeed(stock);
    });
  }

  Future<void> _syncFeed() async {
    final stock = _selectedStock;
    if (stock == null || _syncing) {
      return;
    }

    final future = widget.repository.syncFeed(stock);
    setState(() {
      _syncing = true;
      _feedFuture = future;
    });

    try {
      final feed = await future;
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            '${stock.stockName} 뉴스 ${feed.news.length}건, 공시 ${feed.disclosures.length}건을 동기화했습니다.',
          ),
        ),
      );
    } catch (_) {
      // FutureBuilder의 오류 상태에서 재시도 동작과 상세 메시지를 제공합니다.
    } finally {
      if (mounted) {
        setState(() => _syncing = false);
      }
    }
  }
}

class _StockControls extends StatelessWidget {
  const _StockControls({
    required this.stocks,
    required this.selectedStock,
    required this.syncing,
    required this.onChanged,
    required this.onSync,
  });

  final List<ResearchStock> stocks;
  final ResearchStock selectedStock;
  final bool syncing;
  final ValueChanged<ResearchStock> onChanged;
  final VoidCallback onSync;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      child: Row(
        children: [
          Expanded(
            child: DropdownButtonFormField<ResearchStock>(
              initialValue: selectedStock,
              isExpanded: true,
              decoration: const InputDecoration(
                labelText: '조회 종목',
                prefixIcon: Icon(Icons.show_chart_rounded),
                border: OutlineInputBorder(),
                isDense: true,
              ),
              items: stocks
                  .map(
                    (stock) => DropdownMenuItem(
                      value: stock,
                      child: Text(
                        '${stock.stockName} · ${stock.stockCode}',
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  )
                  .toList(),
              onChanged: syncing
                  ? null
                  : (stock) {
                      if (stock != null) onChanged(stock);
                    },
            ),
          ),
          const SizedBox(width: 10),
          IconButton.filled(
            onPressed: syncing ? null : onSync,
            tooltip: '외부 뉴스·공시 동기화',
            icon: syncing
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  )
                : const Icon(Icons.sync_rounded),
          ),
        ],
      ),
    );
  }
}

class _FilterControl extends StatelessWidget {
  const _FilterControl({required this.selected, required this.onChanged});

  final ResearchTimelineFilter selected;
  final ValueChanged<ResearchTimelineFilter> onChanged;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: SegmentedButton<ResearchTimelineFilter>(
        segments: const [
          ButtonSegment(
            value: ResearchTimelineFilter.all,
            label: Text('전체'),
            icon: Icon(Icons.view_timeline_rounded),
          ),
          ButtonSegment(
            value: ResearchTimelineFilter.news,
            label: Text('뉴스'),
            icon: Icon(Icons.newspaper_rounded),
          ),
          ButtonSegment(
            value: ResearchTimelineFilter.disclosures,
            label: Text('공시'),
            icon: Icon(Icons.description_rounded),
          ),
        ],
        selected: {selected},
        showSelectedIcon: false,
        onSelectionChanged: (values) => onChanged(values.first),
      ),
    );
  }
}

class _ProviderStatusStrip extends StatelessWidget {
  const _ProviderStatusStrip({required this.statuses});

  final List<ResearchProviderStatus> statuses;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    if (statuses.isEmpty) {
      return const SizedBox.shrink();
    }

    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: statuses.map((status) {
        final failed = status.status == 'FAILED';
        final disabled = status.status == 'DISABLED';
        final statusColor = failed
            ? AppTheme.sub
            : disabled
            ? palette.muted
            : AppTheme.main;
        return Tooltip(
          message: status.message,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
            decoration: BoxDecoration(
              color: failed
                  ? AppTheme.sub.withValues(alpha: .12)
                  : palette.softSurface,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: failed ? AppTheme.sub : palette.border),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  failed
                      ? Icons.error_outline_rounded
                      : disabled
                      ? Icons.pause_circle_outline_rounded
                      : Icons.check_rounded,
                  size: 15,
                  color: statusColor,
                ),
                const SizedBox(width: 5),
                Text(
                  _providerLabel(status.provider),
                  style: TextStyle(
                    color: palette.text,
                    fontSize: 11,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }
}

class _TimelineCard extends StatelessWidget {
  const _TimelineCard({required this.entry});

  final _TimelineEntry entry;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final color = entry.isNews ? AppTheme.main : AppTheme.point;

    return AppCard(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: color.withValues(alpha: .13),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              entry.isNews
                  ? Icons.newspaper_rounded
                  : Icons.description_rounded,
              color: color,
              size: 21,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      entry.isNews ? '뉴스' : '공시',
                      style: TextStyle(
                        color: color,
                        fontSize: 11,
                        fontWeight: FontWeight.w900,
                        letterSpacing: 0,
                      ),
                    ),
                    const SizedBox(width: 7),
                    Expanded(
                      child: Text(
                        '${_providerLabel(entry.provider)} · ${_formatDate(entry.occurredAt)}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: palette.muted,
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 0,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                Text(
                  entry.title,
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: palette.text,
                    fontSize: 15,
                    height: 1.25,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
                if (entry.description.isNotEmpty) ...[
                  const SizedBox(height: 7),
                  Text(
                    entry.description,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: palette.muted,
                      fontSize: 12,
                      height: 1.4,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0,
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (entry.link.isNotEmpty) ...[
            const SizedBox(width: 6),
            IconButton(
              onPressed: () => _openLink(context, entry.link),
              tooltip: '원문 열기',
              icon: const Icon(Icons.open_in_new_rounded),
            ),
          ],
        ],
      ),
    );
  }
}

class _TimelineLoadingState extends StatelessWidget {
  const _TimelineLoadingState();

  @override
  Widget build(BuildContext context) {
    return const SizedBox(
      height: 180,
      child: Center(child: CircularProgressIndicator()),
    );
  }
}

class _TimelineErrorState extends StatelessWidget {
  const _TimelineErrorState({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return AppCard(
      soft: true,
      child: Column(
        children: [
          const Icon(Icons.cloud_off_rounded, color: AppTheme.sub, size: 32),
          const SizedBox(height: 10),
          Text(
            message,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: palette.text,
              fontSize: 13,
              fontWeight: FontWeight.w800,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('다시 시도'),
          ),
        ],
      ),
    );
  }
}

class _EmptyFeedState extends StatelessWidget {
  const _EmptyFeedState({required this.filter});

  final ResearchTimelineFilter filter;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final label = switch (filter) {
      ResearchTimelineFilter.news => '저장된 뉴스가 없습니다',
      ResearchTimelineFilter.disclosures => '저장된 공시가 없습니다',
      ResearchTimelineFilter.all => '저장된 뉴스와 공시가 없습니다',
    };
    return AppCard(
      soft: true,
      child: Column(
        children: [
          Icon(Icons.inbox_rounded, color: palette.muted, size: 34),
          const SizedBox(height: 9),
          Text(
            label,
            style: TextStyle(
              color: palette.text,
              fontSize: 14,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 5),
          Text(
            '상단 동기화 버튼을 눌러 최신 데이터를 가져오세요.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: palette.muted,
              fontSize: 12,
              fontWeight: FontWeight.w700,
              letterSpacing: 0,
            ),
          ),
        ],
      ),
    );
  }
}

class _NoStockState extends StatelessWidget {
  const _NoStockState({required this.onHoldingSetupOpen});

  final VoidCallback onHoldingSetupOpen;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return AppCard(
      child: Column(
        children: [
          const Icon(Icons.add_chart_rounded, color: AppTheme.main, size: 38),
          const SizedBox(height: 10),
          Text(
            '조회할 종목이 없습니다',
            style: TextStyle(
              color: palette.text,
              fontSize: 16,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            '보유 종목을 추가하면 해당 종목의 뉴스와 공시를 모아볼 수 있습니다.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: palette.muted,
              fontSize: 12,
              height: 1.35,
              fontWeight: FontWeight.w700,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 14),
          FilledButton.icon(
            onPressed: onHoldingSetupOpen,
            icon: const Icon(Icons.add_rounded),
            label: const Text('보유 종목 추가'),
          ),
        ],
      ),
    );
  }
}

class _TimelineEntry {
  const _TimelineEntry({
    required this.isNews,
    required this.provider,
    required this.title,
    required this.description,
    required this.link,
    required this.occurredAt,
  });

  final bool isNews;
  final String provider;
  final String title;
  final String description;
  final String link;
  final DateTime? occurredAt;
}

List<_TimelineEntry> _entries(
  ResearchFeed feed,
  ResearchTimelineFilter filter,
) {
  final entries = <_TimelineEntry>[
    if (filter != ResearchTimelineFilter.disclosures)
      ...feed.news.map(
        (article) => _TimelineEntry(
          isNews: true,
          provider: article.provider,
          title: article.title,
          description: article.summary,
          link: article.link,
          occurredAt: article.publishedAt,
        ),
      ),
    if (filter != ResearchTimelineFilter.news)
      ...feed.disclosures.map(
        (disclosure) => _TimelineEntry(
          isNews: false,
          provider: disclosure.provider,
          title: disclosure.reportName,
          description: [
            disclosure.corpName,
            if (disclosure.submitterName.isNotEmpty)
              '제출인 ${disclosure.submitterName}',
            if (disclosure.receiptNumber.isNotEmpty)
              '접수 ${disclosure.receiptNumber}',
          ].join(' · '),
          link: disclosure.link,
          occurredAt: disclosure.receiptDate,
        ),
      ),
  ];
  entries.sort((left, right) {
    final leftDate = left.occurredAt ?? DateTime.fromMillisecondsSinceEpoch(0);
    final rightDate =
        right.occurredAt ?? DateTime.fromMillisecondsSinceEpoch(0);
    return rightDate.compareTo(leftDate);
  });
  return entries;
}

ResearchStock? _findStock(List<ResearchStock> stocks, String stockCode) {
  for (final stock in stocks) {
    if (stock.stockCode == stockCode) return stock;
  }
  return null;
}

String _providerLabel(String provider) {
  return switch (provider) {
    'NAVER_NEWS' => '네이버 뉴스',
    'OPEN_DART' => 'OpenDART',
    'LOCAL_DB' => '로컬 DB',
    _ => provider,
  };
}

String _formatDate(DateTime? value) {
  if (value == null) return '날짜 미상';
  final local = value.toLocal();
  final month = local.month.toString().padLeft(2, '0');
  final day = local.day.toString().padLeft(2, '0');
  return '${local.year}.$month.$day';
}

String _errorMessage(Object? error) {
  if (error is ResearchFeedRepositoryException) {
    return error.message;
  }
  return '뉴스·공시를 불러오지 못했습니다.';
}

Future<void> _openLink(BuildContext context, String link) async {
  final uri = Uri.tryParse(link);
  if (uri == null || (uri.scheme != 'https' && uri.scheme != 'http')) {
    _showLinkError(context);
    return;
  }

  try {
    if (Platform.isWindows) {
      await Process.start('rundll32.exe', [
        'url.dll,FileProtocolHandler',
        uri.toString(),
      ]);
      return;
    }
    if (Platform.isMacOS) {
      await Process.start('open', [uri.toString()]);
      return;
    }
    if (Platform.isLinux) {
      await Process.start('xdg-open', [uri.toString()]);
      return;
    }
  } on ProcessException {
    // OS 기본 브라우저 실행이 실패하면 링크를 복사해 사용자가 직접 열 수 있게 합니다.
  }

  await Clipboard.setData(ClipboardData(text: uri.toString()));
  if (!context.mounted) return;
  ScaffoldMessenger.of(
    context,
  ).showSnackBar(const SnackBar(content: Text('원문 링크를 클립보드에 복사했습니다.')));
}

void _showLinkError(BuildContext context) {
  ScaffoldMessenger.of(
    context,
  ).showSnackBar(const SnackBar(content: Text('올바른 원문 링크가 아닙니다.')));
}
