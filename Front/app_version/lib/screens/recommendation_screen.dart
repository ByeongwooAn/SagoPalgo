import 'package:flutter/material.dart';

import '../models/holding.dart';
import '../models/recommendation.dart';
import '../models/watchlist_item.dart';
import '../repositories/recommendation_repository.dart';
import '../repositories/watchlist_repository.dart';
import '../repositories/research_feed_repository.dart';
import '../models/research_feed.dart';
import 'watchlist_setup_sheet.dart';
import 'watchlist_management_sheet.dart';
import '../theme/app_theme.dart';
import '../widgets/app_card.dart';
import '../widgets/app_text.dart';
import '../widgets/gradient_action_button.dart';
import '../widgets/score_ring.dart';
import '../widgets/section_header.dart';
import '../widgets/status_chip.dart';
import '../widgets/responsive_layout.dart';
import 'dashboard_screen.dart';

/// 매수 추천 상세 화면입니다.
///
/// 사용자가 AI 추천을 맹목적으로 따르지 않도록 점수, 진입 가격,
/// 손절 기준, 추천 사유, AI 설명을 한 화면에 함께 배치합니다.
class RecommendationScreen extends StatefulWidget {
  /// 화면에 표시할 대표 추천 데이터를 받습니다.
  const RecommendationScreen({
    super.key,
    required this.recommendation,
    required this.holdings,
    required this.recommendationRepository,
    required this.watchlistRepository,
    required this.onRecommendationChanged,
    required this.onCapitalSetupOpen,
    required this.onHoldingSetupOpen,
    this.researchFeedRepository,
  });

  /// Repository에서 받은 매수 추천 모델입니다.
  final InvestmentRecommendation? recommendation;

  /// 수동 재분석 대상으로 선택할 현재 보유 종목입니다.
  final List<Holding> holdings;

  /// 저장 추천 목록, 상세, 수동 분석 API를 제공합니다.
  final RecommendationRepository recommendationRepository;

  /// 관심 종목 등록과 알림 설정 액션을 처리하는 Repository입니다.
  final WatchlistRepository watchlistRepository;

  /// 새 분석 저장 후 대시보드 데이터를 갱신합니다.
  final VoidCallback onRecommendationChanged;

  /// 자본금 수정 화면으로 이동하는 콜백입니다.
  final VoidCallback onCapitalSetupOpen;

  /// 보유 종목 추가 화면으로 이동하는 콜백입니다.
  final VoidCallback onHoldingSetupOpen;
  final ResearchFeedRepository? researchFeedRepository;

  @override
  State<RecommendationScreen> createState() => _RecommendationScreenState();
}

class _RecommendationScreenState extends State<RecommendationScreen> {
  bool _addingWatchlist = false;
  bool _enablingAlert = false;
  bool _loadingHistory = true;
  bool _loadingMore = false;
  int? _analyzingHoldingId;
  int? _analyzingWatchlistId;
  bool _loadingWatchlist = false;
  int _nextPage = 0;
  int _total = 0;
  Object? _historyError;
  final List<InvestmentRecommendation> _history = [];
  InvestmentRecommendation? _lastAnalyzed;
  bool _syncBeforeAnalysis = true;
  int _historyVersion = 0;

  @override
  void initState() {
    super.initState();
    _loadHistory(reset: true);
  }

  @override
  Widget build(BuildContext context) {
    var recommendation = _history.isNotEmpty
        ? _history.first
        : widget.recommendation;
    if (_lastAnalyzed != null &&
        recommendation != null &&
        recommendation.recommendationId == _lastAnalyzed?.recommendationId) {
      recommendation = _lastAnalyzed;
    }
    if (recommendation != null &&
        recommendation.reasons.isEmpty &&
        recommendation.recommendationId ==
            widget.recommendation?.recommendationId) {
      recommendation = widget.recommendation;
    }
    if (recommendation == null && _loadingHistory) {
      return const Center(child: CircularProgressIndicator());
    }
    if (recommendation == null && widget.holdings.isEmpty) {
      return _EmptyRecommendationState(
        onCapitalTap: widget.onCapitalSetupOpen,
        onHoldingTap: widget.onHoldingSetupOpen,
        onWatchlistTap: _openWatchlistPicker,
        onWatchlistAdd: _addWatchlist,
        onWatchlistManage: _manageWatchlist,
        historyError: _historyError,
        onRetry: () => _loadHistory(reset: true),
      );
    }

    return AppScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionHeader(
            eyebrow: '추천 분석',
            title: recommendation?.stockName ?? '첫 분석을 시작하세요',
            action: IconButton.filledTonal(
              onPressed: _loadingHistory
                  ? null
                  : () => _loadHistory(reset: true),
              tooltip: '추천 이력 새로고침',
              icon: const Icon(Icons.refresh_rounded),
            ),
          ),
          const SizedBox(height: 18),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              OutlinedButton.icon(
                onPressed: _addWatchlist,
                icon: const Icon(Icons.add),
                label: const Text('관심 종목 등록'),
              ),
              OutlinedButton.icon(
                onPressed: _manageWatchlist,
                icon: const Icon(Icons.edit_note),
                label: const Text('관심 목록 관리'),
              ),
            ],
          ),
          if (widget.researchFeedRepository != null)
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('분석 전에 뉴스·공시 수집'),
              value: _syncBeforeAnalysis,
              subtitle: const Text(
                '실제 시세와 수집된 입력으로 분석합니다. 수집 실패·미설정은 별도로 안내합니다.',
              ),
              onChanged:
                  _analyzingHoldingId != null || _analyzingWatchlistId != null
                  ? null
                  : (value) => setState(() => _syncBeforeAnalysis = value!),
            ),
          AdaptiveColumns(
            first: _AnalysisActionCard(
              holdings: widget.holdings,
              analyzingHoldingId: _analyzingHoldingId,
              onAnalyzeTap: _openHoldingPicker,
            ),
            second: _WatchlistAnalysisActionCard(
              busy: _loadingWatchlist || _analyzingWatchlistId != null,
              onAnalyzeTap: _openWatchlistPicker,
            ),
          ),
          if (recommendation != null) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(child: CardTitle('최신 추천 · ${recommendation.status}')),
                if (recommendation.createdAt != null)
                  Text(
                    _formatDateTime(recommendation.createdAt!),
                    style: TextStyle(
                      color: AppPalette.of(context).muted,
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 10),
            ScoreDetailCard(recommendation: recommendation),
            AnalysisEvidenceCard(recommendation: recommendation),
            const SizedBox(height: 12),
            RecommendationReasonCard(reasons: recommendation.reasons),
            const SizedBox(height: 12),
            AppCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const CardTitle('분석 설명'),
                  const SizedBox(height: 8),
                  TextBody(recommendation.aiSummary),
                ],
              ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: GradientActionButton(
                    label: '관심 등록',
                    icon: Icons.star_rounded,
                    gradient: AppGradients.main,
                    busy: _addingWatchlist,
                    onTap: _addingWatchlist || _enablingAlert
                        ? null
                        : () => _addRecommendation(recommendation!),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: GradientActionButton(
                    label: '알림 켜기',
                    icon: Icons.notifications_active_rounded,
                    gradient: AppGradients.point,
                    darkText: true,
                    busy: _enablingAlert,
                    onTap: _addingWatchlist || _enablingAlert
                        ? null
                        : () => _enableAlert(recommendation!),
                  ),
                ),
              ],
            ),
          ],
          const SizedBox(height: 24),
          _buildHistory(context),
          const SizedBox(height: 20),
        ],
      ),
    );
  }

  Widget _buildHistory(BuildContext context) {
    final palette = AppPalette.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Expanded(child: CardTitle('추천 이력')),
            Text(
              '총 $_total건',
              style: TextStyle(
                color: palette.muted,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        if (_historyError != null && _history.isEmpty)
          _InlineError(onRetry: () => _loadHistory(reset: true))
        else if (_history.isEmpty)
          AppCard(soft: true, child: TextBody('저장된 추천 이력이 없습니다.'))
        else
          for (final item in _history) ...[
            _RecommendationHistoryTile(
              recommendation: item,
              onTap: () => _openDetail(item),
            ),
            const SizedBox(height: 8),
          ],
        if (_history.length < _total)
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: _loadingMore ? null : () => _loadHistory(reset: false),
              icon: _loadingMore
                  ? const SizedBox.square(
                      dimension: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.expand_more_rounded),
              label: const Text('이력 더 보기'),
            ),
          ),
      ],
    );
  }

  Future<void> _loadHistory({required bool reset}) async {
    if (!reset && (_loadingMore || _loadingHistory)) return;
    final version = reset ? ++_historyVersion : _historyVersion;
    if (reset) {
      setState(() {
        _loadingHistory = true;
        _historyError = null;
        _nextPage = 0;
      });
    } else {
      setState(() => _loadingMore = true);
    }
    try {
      final page = await widget.recommendationRepository.fetchHistory(
        page: reset ? 0 : _nextPage,
      );
      if (!mounted || version != _historyVersion) return;
      setState(() {
        if (reset) _history.clear();
        final knownIds = _history.map((item) => item.recommendationId).toSet();
        _history.addAll(
          page.items.where(
            (item) =>
                item.recommendationId == null ||
                !knownIds.contains(item.recommendationId),
          ),
        );
        _total = page.total;
        _nextPage = page.page + 1;
        _historyError = null;
      });
    } catch (error) {
      if (mounted && version == _historyVersion) {
        setState(() => _historyError = error);
      }
    } finally {
      if (mounted && version == _historyVersion) {
        setState(() {
          _loadingHistory = false;
          _loadingMore = false;
        });
      }
    }
  }

  Future<void> _openHoldingPicker() async {
    if (widget.holdings.isEmpty || _analyzingHoldingId != null) return;
    final holding = await showModalBottomSheet<Holding>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          children: [
            const ListTile(title: Text('재분석할 보유 종목 선택')),
            for (final item in widget.holdings)
              ListTile(
                leading: const Icon(Icons.candlestick_chart_rounded),
                title: Text(item.stockName),
                subtitle: Text('${item.stockCode} · ${item.market}'),
                trailing: const Icon(Icons.chevron_right_rounded),
                onTap: () => Navigator.pop(context, item),
              ),
          ],
        ),
      ),
    );
    if (holding != null && mounted) {
      try {
        await _analyzeHolding(holding);
      } catch (error) {
        if (mounted) _showMessage(error.toString());
      }
    }
  }

  Future<InvestmentRecommendation> _analyzeHolding(Holding holding) async {
    setState(() => _analyzingHoldingId = holding.holdingId);
    try {
      await _prepareResearch(holding.stockCode, holding.stockName);
      final result = await widget.recommendationRepository.analyzeHolding(
        holding.holdingId,
      );
      if (mounted) setState(() => _lastAnalyzed = result);
      await _loadHistory(reset: true);
      widget.onRecommendationChanged();
      if (mounted) _showMessage('${holding.stockName} 재분석이 완료되었습니다.');
      return result;
    } finally {
      if (mounted) setState(() => _analyzingHoldingId = null);
    }
  }

  Future<void> _openWatchlistPicker() async {
    if (_loadingWatchlist || _analyzingWatchlistId != null) return;
    setState(() => _loadingWatchlist = true);
    List<WatchlistItem> items;
    try {
      items = await widget.watchlistRepository.fetchWatchlist();
    } catch (error) {
      if (mounted) _showMessage(error.toString());
      return;
    } finally {
      if (mounted) setState(() => _loadingWatchlist = false);
    }
    if (!mounted) return;
    if (items.isEmpty) {
      await _addWatchlist();
      return;
    }
    final selected = await showModalBottomSheet<WatchlistItem>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          children: [
            const ListTile(title: Text('분석할 관심 종목 선택')),
            for (final item in items)
              ListTile(
                leading: const Icon(Icons.star_outline_rounded),
                title: Text(item.stockName),
                subtitle: Text('${item.stockCode} · ${item.market}'),
                trailing: const Icon(Icons.chevron_right_rounded),
                onTap: () => Navigator.pop(context, item),
              ),
          ],
        ),
      ),
    );
    if (selected == null || !mounted) return;
    try {
      await _analyzeWatchlist(selected);
    } catch (error) {
      if (mounted) _showMessage(error.toString());
    }
  }

  Future<InvestmentRecommendation> _analyzeWatchlist(
    WatchlistItem selected,
  ) async {
    setState(() => _analyzingWatchlistId = selected.watchlistId);
    try {
      await _prepareResearch(selected.stockCode, selected.stockName);
      final result = await widget.recommendationRepository.analyzeWatchlist(
        selected.watchlistId,
      );
      if (mounted) setState(() => _lastAnalyzed = result);
      await _loadHistory(reset: true);
      widget.onRecommendationChanged();
      if (mounted) _showMessage('${selected.stockName} 분석이 완료되었습니다.');
      return result;
    } finally {
      if (mounted) setState(() => _analyzingWatchlistId = null);
    }
  }

  Future<void> _addWatchlist() async {
    if (await showWatchlistSetup(context, widget.watchlistRepository)) {
      widget.onRecommendationChanged();
    }
  }

  Future<void> _manageWatchlist() async {
    if (await showWatchlistManagement(context, widget.watchlistRepository) &&
        mounted) {
      widget.onRecommendationChanged();
    }
  }

  Future<void> _prepareResearch(String code, String name) async {
    final repository = widget.researchFeedRepository;
    if (repository == null || !_syncBeforeAnalysis) return;
    final feed = await repository.syncFeed(
      ResearchStock(stockCode: code, stockName: name),
    );
    if (feed.providers.any((item) => item.status == 'FAILED') ||
        !feed.providers.any((item) => item.status == 'SUCCESS')) {
      if (mounted) {
        _showMessage('뉴스·공시 일부가 미수집 상태입니다. 저장된 입력 범위로 분석하며 실제 입력 건수를 확인하세요.');
      }
    }
  }

  Future<void> _openDetail(InvestmentRecommendation recommendation) async {
    Holding? holding;
    for (final item in widget.holdings) {
      if (recommendation.analysisContext == 'WATCHLIST') break;
      if (item.stockCode == recommendation.stockCode) {
        holding = item;
        break;
      }
    }
    final selectedHolding = holding;
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => RecommendationDetailScreen(
          initialRecommendation: recommendation,
          recommendationRepository: widget.recommendationRepository,
          holding: selectedHolding,
          onAnalyze: recommendation.analysisContext == 'WATCHLIST'
              ? () => _reanalyzeWatchlist(recommendation)
              : selectedHolding == null
              ? null
              : () => _analyzeHolding(selectedHolding),
        ),
      ),
    );
  }

  Future<InvestmentRecommendation> _reanalyzeWatchlist(
    InvestmentRecommendation recommendation,
  ) async {
    final items = await widget.watchlistRepository.fetchWatchlist();
    for (final item in items) {
      if (item.stockCode == recommendation.stockCode &&
          item.market == recommendation.market) {
        return _analyzeWatchlist(item);
      }
    }
    throw StateError('현재 관심 목록에 없는 종목입니다. 관심 종목 등록 상태를 확인하세요.');
  }

  Future<void> _addRecommendation(
    InvestmentRecommendation recommendation,
  ) async {
    await _runAction(
      setBusy: (busy) => _addingWatchlist = busy,
      action: () =>
          widget.watchlistRepository.addRecommendation(recommendation),
    );
  }

  Future<void> _enableAlert(InvestmentRecommendation recommendation) async {
    await _runAction(
      setBusy: (busy) => _enablingAlert = busy,
      action: () => widget.watchlistRepository.enableAlert(recommendation),
    );
  }

  Future<void> _runAction({
    required ValueChanged<bool> setBusy,
    required Future<WatchlistActionResult> Function() action,
  }) async {
    setState(() => setBusy(true));

    try {
      final result = await action();
      if (!mounted) {
        return;
      }
      _showMessage(result.message);
      if (result.changed) widget.onRecommendationChanged();
    } catch (error) {
      if (!mounted) {
        return;
      }
      _showMessage(error.toString());
    } finally {
      if (mounted) {
        setState(() => setBusy(false));
      }
    }
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }
}

class _AnalysisActionCard extends StatelessWidget {
  const _AnalysisActionCard({
    required this.holdings,
    required this.analyzingHoldingId,
    required this.onAnalyzeTap,
  });

  final List<Holding> holdings;
  final int? analyzingHoldingId;
  final VoidCallback onAnalyzeTap;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final analyzing = analyzingHoldingId != null;
    return AppCard(
      soft: true,
      child: Row(
        children: [
          const Icon(Icons.model_training_rounded, color: AppTheme.main),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const CardTitle('보유 종목 다시 분석', fontSize: 17),
                const SizedBox(height: 4),
                Text(
                  holdings.isEmpty
                      ? '분석할 보유 종목을 먼저 등록해 주세요.'
                      : '${holdings.length}개 보유 종목 중 하나를 선택합니다.',
                  style: TextStyle(
                    color: palette.muted,
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          FilledButton.icon(
            onPressed: holdings.isEmpty || analyzing ? null : onAnalyzeTap,
            icon: analyzing
                ? const SizedBox.square(
                    dimension: 16,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  )
                : const Icon(Icons.play_arrow_rounded),
            label: Text(analyzing ? '분석 중' : '분석'),
          ),
        ],
      ),
    );
  }
}

class _WatchlistAnalysisActionCard extends StatelessWidget {
  const _WatchlistAnalysisActionCard({
    required this.busy,
    required this.onAnalyzeTap,
  });

  final bool busy;
  final VoidCallback onAnalyzeTap;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      soft: true,
      child: Row(
        children: [
          const Icon(Icons.star_outline_rounded, color: AppTheme.main),
          const SizedBox(width: 12),
          const Expanded(child: CardTitle('관심 종목 분석', fontSize: 17)),
          FilledButton.icon(
            onPressed: busy ? null : onAnalyzeTap,
            icon: busy
                ? const SizedBox.square(
                    dimension: 16,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  )
                : const Icon(Icons.play_arrow_rounded),
            label: Text(busy ? '분석 중' : '분석'),
          ),
        ],
      ),
    );
  }
}

class _RecommendationHistoryTile extends StatelessWidget {
  const _RecommendationHistoryTile({
    required this.recommendation,
    required this.onTap,
  });

  final InvestmentRecommendation recommendation;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Semantics(
      button: true,
      label: '${recommendation.stockName} 추천 상세',
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: AppCard(
          child: Row(
            children: [
              SizedBox(
                width: 46,
                height: 46,
                child: ScoreRing(score: recommendation.score, size: 46),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      recommendation.stockName,
                      style: TextStyle(
                        color: palette.text,
                        fontSize: 15,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      '${recommendation.stockCode} · ${recommendation.market}'
                      '${recommendation.analysisContext == 'WATCHLIST' ? ' · 관심 종목' : ''}'
                      '${recommendation.createdAt == null ? '' : ' · ${_formatDateTime(recommendation.createdAt!)}'}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: palette.muted,
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
              StatusChip(
                label: recommendation.status,
                icon: _statusIcon(recommendation.machineStatus),
              ),
              const SizedBox(width: 4),
              Icon(Icons.chevron_right_rounded, color: palette.muted),
            ],
          ),
        ),
      ),
    );
  }
}

class _InlineError extends StatelessWidget {
  const _InlineError({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      soft: true,
      child: Row(
        children: [
          const Icon(Icons.error_outline_rounded, color: AppTheme.sub),
          const SizedBox(width: 10),
          const Expanded(child: TextBody('추천 이력을 불러오지 못했습니다.')),
          IconButton(
            onPressed: onRetry,
            tooltip: '추천 이력 다시 시도',
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
    );
  }
}

/// 추천 이력에서 선택한 분석 결과를 서버 상세 데이터로 보여줍니다.
class RecommendationDetailScreen extends StatefulWidget {
  const RecommendationDetailScreen({
    super.key,
    required this.initialRecommendation,
    required this.recommendationRepository,
    this.holding,
    this.onAnalyze,
  });

  final InvestmentRecommendation initialRecommendation;
  final RecommendationRepository recommendationRepository;
  final Holding? holding;
  final Future<InvestmentRecommendation> Function()? onAnalyze;

  @override
  State<RecommendationDetailScreen> createState() =>
      _RecommendationDetailScreenState();
}

class _RecommendationDetailScreenState
    extends State<RecommendationDetailScreen> {
  late Future<InvestmentRecommendation> _detailFuture;
  bool _analyzing = false;

  @override
  void initState() {
    super.initState();
    _detailFuture = _fetchDetail();
  }

  Future<InvestmentRecommendation> _fetchDetail() {
    final id = widget.initialRecommendation.recommendationId;
    return id == null
        ? Future.value(widget.initialRecommendation)
        : widget.recommendationRepository.fetchDetail(id);
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('추천 상세')),
      body: Container(
        decoration: BoxDecoration(gradient: palette.pageGradient),
        child: FutureBuilder<InvestmentRecommendation>(
          future: _detailFuture,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError || !snapshot.hasData) {
              return Center(
                child: FilledButton.icon(
                  onPressed: () =>
                      setState(() => _detailFuture = _fetchDetail()),
                  icon: const Icon(Icons.refresh_rounded),
                  label: const Text('상세 다시 불러오기'),
                ),
              );
            }
            final recommendation = snapshot.data!;
            return AppScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SectionHeader(
                    eyebrow:
                        '${recommendation.stockCode} · ${recommendation.market}'
                        '${recommendation.analysisContext == 'WATCHLIST' ? ' · 관심 종목' : ''}',
                    title: recommendation.stockName,
                    action: StatusChip(
                      label: recommendation.status,
                      icon: _statusIcon(recommendation.machineStatus),
                    ),
                  ),
                  if (recommendation.createdAt != null) ...[
                    const SizedBox(height: 8),
                    Text(
                      '분석 시각 ${_formatDateTime(recommendation.createdAt!)}',
                      style: TextStyle(
                        color: palette.muted,
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                  const SizedBox(height: 16),
                  ScoreDetailCard(recommendation: recommendation),
                  AnalysisEvidenceCard(recommendation: recommendation),
                  const SizedBox(height: 12),
                  RecommendationReasonCard(reasons: recommendation.reasons),
                  const SizedBox(height: 12),
                  AppCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const CardTitle('분석 설명'),
                        const SizedBox(height: 8),
                        TextBody(recommendation.aiSummary),
                      ],
                    ),
                  ),
                  if (widget.onAnalyze != null) ...[
                    const SizedBox(height: 14),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        onPressed: _analyzing ? null : _reanalyze,
                        icon: _analyzing
                            ? const SizedBox.square(
                                dimension: 16,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: Colors.white,
                                ),
                              )
                            : const Icon(Icons.replay_rounded),
                        label: Text(_analyzing ? '재분석 중' : '이 종목 다시 분석'),
                      ),
                    ),
                  ],
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Future<void> _reanalyze() async {
    setState(() => _analyzing = true);
    try {
      final result = await widget.onAnalyze!();
      if (mounted) setState(() => _detailFuture = Future.value(result));
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.toString())));
      }
    } finally {
      if (mounted) setState(() => _analyzing = false);
    }
  }
}

IconData _statusIcon(String? status) {
  return switch (status) {
    'BUY_STRONG' || 'BUY_WATCH' => Icons.trending_up_rounded,
    'TAKE_PROFIT' => Icons.savings_rounded,
    'STOP_LOSS_WATCH' || 'RISK' => Icons.warning_amber_rounded,
    _ => Icons.horizontal_rule_rounded,
  };
}

String _formatDateTime(DateTime value) {
  final local = value.toLocal();
  String two(int number) => number.toString().padLeft(2, '0');
  return '${local.year}.${two(local.month)}.${two(local.day)} '
      '${two(local.hour)}:${two(local.minute)}';
}

class _EmptyRecommendationState extends StatelessWidget {
  const _EmptyRecommendationState({
    required this.onCapitalTap,
    required this.onHoldingTap,
    required this.onWatchlistTap,
    required this.onWatchlistAdd,
    required this.onWatchlistManage,
    this.historyError,
    this.onRetry,
  });

  final VoidCallback onCapitalTap;
  final VoidCallback onHoldingTap;
  final VoidCallback onWatchlistTap;
  final VoidCallback onWatchlistAdd;
  final VoidCallback onWatchlistManage;
  final Object? historyError;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return AppScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionHeader(
            eyebrow: '매수 추천',
            title: historyError == null ? '추천 데이터 없음' : '추천 이력 조회 실패',
            action: StatusChip(
              label: historyError == null ? '대기' : '재조회 필요',
              icon: Icons.hourglass_empty,
            ),
          ),
          const SizedBox(height: 18),
          if (historyError != null) _InlineError(onRetry: onRetry ?? () {}),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              OutlinedButton.icon(
                onPressed: onWatchlistAdd,
                icon: const Icon(Icons.add),
                label: const Text('관심 종목 등록'),
              ),
              OutlinedButton.icon(
                onPressed: onWatchlistManage,
                icon: const Icon(Icons.edit_note),
                label: const Text('관심 목록 관리'),
              ),
            ],
          ),
          const SizedBox(height: 8),
          AppCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(
                      Icons.info_outline_rounded,
                      color: AppTheme.main,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        historyError == null
                            ? '저장된 추천 결과가 없습니다. 보유 주식 없이도 관심 종목을 등록해 분석할 수 있습니다.'
                            : '추천 이력을 불러오지 못했습니다. 다시 조회하거나 등록된 종목을 분석하세요.',
                        style: TextStyle(
                          color: palette.text,
                          fontSize: 14,
                          height: 1.4,
                          fontWeight: FontWeight.w800,
                          letterSpacing: 0,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: onCapitalTap,
                    icon: const Icon(Icons.savings_rounded),
                    label: const Text('자본금 설정하기'),
                  ),
                ),
                const SizedBox(height: 8),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    onPressed: onHoldingTap,
                    icon: const Icon(Icons.add_rounded),
                    label: const Text('보유 종목 추가하기'),
                  ),
                ),
                const SizedBox(height: 8),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    onPressed: onWatchlistTap,
                    icon: const Icon(Icons.star_outline_rounded),
                    label: const Text('관심 종목 분석'),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// 추천 점수, 진입 가격, 손절 기준을 묶어서 보여주는 카드입니다.
class AnalysisEvidenceCard extends StatelessWidget {
  const AnalysisEvidenceCard({super.key, required this.recommendation});
  final InvestmentRecommendation recommendation;
  @override
  Widget build(BuildContext context) {
    final evidence = recommendation.evidence;
    return AppCard(
      soft: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            recommendation.analysisContext == 'WATCHLIST'
                ? '관심 종목 분석'
                : '보유 종목 분석',
            style: const TextStyle(fontWeight: FontWeight.w800),
          ),
          if (evidence == null || evidence.modelVersion == null)
            const Text('이 이력의 분석 모델·입력 건수 정보는 미제공입니다.')
          else ...[
            Text(
              '${evidence.isFallback ? '대체 규칙 결과' : '분석 모델'} · ${evidence.modelVersion}',
            ),
            Text(
              '저장 당시 입력 · 캔들 ${evidence.candleCount ?? '미제공'} · 뉴스 ${evidence.newsCount ?? '미제공'} · 공시 ${evidence.disclosureCount ?? '미제공'}',
            ),
          ],
          if (recommendation.createdAt != null)
            TextCaption(
              '분석 저장 ${_formatDateTime(recommendation.createdAt!.toLocal())}',
            ),
          const TextCaption('저장 당시의 결과입니다. 현재 시세·수집 상태와 다를 수 있습니다.'),
        ],
      ),
    );
  }
}

class ScoreDetailCard extends StatelessWidget {
  /// 추천 모델을 받아 세부 지표를 표시합니다.
  const ScoreDetailCard({super.key, required this.recommendation});

  /// 추천 점수와 가격 정보를 담은 모델입니다.
  final InvestmentRecommendation recommendation;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      child: Column(
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const LabelText('분석 점수'),
                    const SizedBox(height: 8),
                    Text(
                      '${recommendation.score}점',
                      style: const TextStyle(
                        color: AppTheme.point,
                        fontSize: 33,
                        fontWeight: FontWeight.w900,
                        letterSpacing: 0,
                      ),
                    ),
                  ],
                ),
              ),
              ScoreRing(score: recommendation.score, size: 110),
            ],
          ),
          const AppDivider(),
          Row(
            children: [
              Expanded(
                child: DetailMetric(
                  label: recommendation.analysisContext == 'WATCHLIST'
                      ? '현재가'
                      : '진입 가격대',
                  value: '${formatCurrency(recommendation.entryPrice)}원',
                ),
              ),
              if (recommendation.analysisContext != 'WATCHLIST' &&
                  recommendation.stopLossRate != null) ...[
                const SizedBox(width: 16),
                Expanded(
                  child: DetailMetric(
                    label: '손절 기준',
                    value: formatSignedPercent(recommendation.stopLossRate!),
                    color: AppTheme.sub,
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: DetailMetric(
                    label: '익절 기준',
                    value: formatSignedPercent(recommendation.takeProfitRate),
                    color: AppTheme.point,
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

/// 라벨과 큰 수치를 세로로 배치하는 작은 지표 위젯입니다.
class DetailMetric extends StatelessWidget {
  /// 라벨, 값, 선택 강조색을 받습니다.
  const DetailMetric({
    super.key,
    required this.label,
    required this.value,
    this.color,
  });

  /// 지표 이름입니다.
  final String label;

  /// 사용자가 보는 지표 값입니다.
  final String value;

  /// 값에 적용할 선택 강조색입니다.
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        LabelText(label),
        const SizedBox(height: 6),
        FittedBox(
          fit: BoxFit.scaleDown,
          alignment: Alignment.centerLeft,
          child: Text(
            value,
            style: TextStyle(
              color: color ?? palette.text,
              fontSize: 24,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
        ),
      ],
    );
  }
}

/// RSI, MACD, 뉴스 등 추천 근거 목록을 표시하는 카드입니다.
class RecommendationReasonCard extends StatelessWidget {
  /// 추천 근거 리스트를 받습니다.
  const RecommendationReasonCard({super.key, required this.reasons});

  /// 점수에 반영된 추천 근거 목록입니다.
  final List<RecommendationReason> reasons;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      soft: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const CardTitle('추천 사유'),
          const SizedBox(height: 8),
          for (final reason in reasons)
            ReasonRow(
              label: reason.label,
              text: reason.description,
              color: reasonColor(reason.type),
            ),
        ],
      ),
    );
  }
}

/// 추천 근거 타입을 브랜드 색상에 매핑합니다.
Color reasonColor(RecommendationReasonType type) {
  switch (type) {
    case RecommendationReasonType.technical:
      return AppTheme.main;
    case RecommendationReasonType.trend:
      return AppTheme.sub;
    case RecommendationReasonType.news:
      return AppTheme.point;
  }
}

/// 추천 사유 한 줄을 라벨과 설명으로 보여주는 위젯입니다.
class ReasonRow extends StatelessWidget {
  /// 라벨, 설명, 강조색을 받습니다.
  const ReasonRow({
    super.key,
    required this.label,
    required this.text,
    required this.color,
  });

  /// 예: RSI, MACD, 뉴스.
  final String label;

  /// 추천 근거 설명 문장입니다.
  final String text;

  /// 라벨에 적용할 강조색입니다.
  final Color color;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: palette.border)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 52,
            child: Text(
              label,
              style: TextStyle(
                color: color,
                fontSize: 13,
                fontWeight: FontWeight.w900,
                letterSpacing: 0,
              ),
            ),
          ),
          Expanded(
            child: Text(
              text,
              style: TextStyle(
                color: palette.muted,
                fontSize: 13,
                height: 1.35,
                fontWeight: FontWeight.w700,
                letterSpacing: 0,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
