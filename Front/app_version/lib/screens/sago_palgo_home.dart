import 'dart:async';

import 'package:flutter/material.dart';

import '../models/auth_session.dart';
import '../models/app_alert.dart';
import '../models/holding.dart';
import '../models/investment_snapshot.dart';
import '../models/provider_setting.dart';
import '../models/research_feed.dart';
import '../models/watchlist_item.dart';
import '../repositories/investment_repository.dart';
import '../repositories/alert_repository.dart';
import '../repositories/kb_account_repository.dart';
import '../repositories/market_data_repository.dart';
import '../repositories/portfolio_repository.dart';
import '../repositories/provider_settings_repository.dart';
import '../repositories/recommendation_repository.dart';
import '../repositories/research_feed_repository.dart';
import '../repositories/watchlist_repository.dart';
import '../services/app_security_service.dart';
import '../services/desktop_window_service.dart';
import '../services/local_notification_service.dart';
import '../theme/app_theme.dart';
import '../widgets/bottom_nav.dart';
import 'alerts_screen.dart';
import 'dashboard_screen.dart';
import 'mini_widget_screen.dart';
import 'portfolio_screen.dart';
import 'recommendation_screen.dart';
import 'research_timeline_screen.dart';
import 'settings_screen.dart';

/// 사고팔고 앱의 메인 화면 컨테이너입니다.
///
/// 이 위젯은 직접 투자 데이터를 만들지 않고 `InvestmentRepository`에서 받아옵니다.
/// 덕분에 Spring Boot API Repository의 내부 호출 방식이 바뀌어도 하단 탭과 화면 전환 로직은
/// 그대로 유지할 수 있습니다.
class SagoPalgoHome extends StatefulWidget {
  /// 테마 전환 콜백과 투자 데이터 Repository를 주입받습니다.
  const SagoPalgoHome({
    super.key,
    required this.onThemeToggle,
    required this.repository,
    required this.watchlistRepository,
    required this.portfolioRepository,
    required this.providerSettingsRepository,
    required this.recommendationRepository,
    required this.researchFeedRepository,
    required this.kbAccountRepository,
    required this.marketDataRepository,
    required this.alertRepository,
    required this.localNotificationService,
    this.desktopWindowService = const NoopDesktopWindowService(),
    required this.appSecurityService,
    required this.appLockPinConfigured,
    required this.onAppLockPinChanged,
    required this.session,
  });

  /// 상단 버튼을 눌렀을 때 앱 루트에 테마 변경을 요청하는 콜백입니다.
  final ValueChanged<Brightness> onThemeToggle;

  /// 시장, 추천, 보유 종목, 알림 데이터를 제공하는 Repository입니다.
  final InvestmentRepository repository;

  /// 추천 화면에서 관심 종목 등록과 알림 설정을 처리하는 Repository입니다.
  final WatchlistRepository watchlistRepository;

  /// 포트폴리오 화면에서 자본금과 보유 종목을 최신 API로 다시 불러오는 Repository입니다.
  final PortfolioRepository portfolioRepository;

  /// 설정 화면에서 증권사 연동 상태를 조회하는 Repository입니다.
  final ProviderSettingsRepository providerSettingsRepository;

  /// 추천 이력 조회와 보유 종목 수동 재분석을 처리합니다.
  final RecommendationRepository recommendationRepository;

  /// 소식 화면에서 저장된 뉴스·공시 조회와 수동 동기화를 처리합니다.
  final ResearchFeedRepository researchFeedRepository;

  /// 설정 화면에서 KB 계좌 조회 결과를 확인하는 Repository입니다.
  final KbAccountRepository kbAccountRepository;

  /// 종목 상세 화면에서 일·주·월봉 시세를 조회하는 Repository입니다.
  final MarketDataRepository marketDataRepository;

  /// Ubuntu 백엔드의 저장 알림을 조회하고 상태를 갱신합니다.
  final AlertRepository? alertRepository;

  /// Windows 알림 센터에 새 신호를 표시합니다.
  final LocalNotificationService localNotificationService;

  /// Windows 미니 위젯과 시스템 트레이 창 동작을 처리합니다.
  final DesktopWindowService desktopWindowService;

  /// 앱 잠금 PIN을 Windows Credential Manager에 저장합니다.
  final AppSecurityService appSecurityService;

  /// 현재 앱 잠금 PIN이 등록되어 있는지 여부입니다.
  final bool appLockPinConfigured;

  /// PIN 등록·변경·삭제 결과를 앱 루트에 반영합니다.
  final ValueChanged<String?> onAppLockPinChanged;

  /// 현재 로컬 사용자 프로필 정보를 담고 있는 세션입니다.
  final AuthSession session;

  @override
  State<SagoPalgoHome> createState() => _SagoPalgoHomeState();
}

class _SagoPalgoHomeState extends State<SagoPalgoHome> {
  /// 현재 선택된 하단 탭 인덱스입니다.
  int _selectedIndex = 0;

  /// 앱 시작 시 한 번 불러오는 투자 데이터 Future입니다.
  ///
  /// `build`가 여러 번 호출되어도 데이터를 계속 새로 요청하지 않도록
  /// `initState`에서 생성한 Future를 보관합니다.
  late Future<InvestmentSnapshot> _snapshotFuture;

  /// 포트폴리오 탭에서 별도로 갱신하는 자본금/보유 종목 Future입니다.
  late Future<PortfolioSnapshot> _portfolioFuture;

  /// 설정 탭에서 별도로 갱신하는 증권사 연동 상태 Future입니다.
  late Future<ProviderSettingsSnapshot> _providerSettingsFuture;

  /// 미니 위젯에 표시할 관심 종목 최신 시세입니다.
  late Future<List<WatchlistItem>> _watchlistFuture;

  /// 다른 탭의 빈 상태 CTA가 요청한 포트폴리오 초기 작업입니다.
  PortfolioSetupAction? _pendingPortfolioSetupAction;

  List<AppAlert>? _alerts;
  Timer? _alertTimer;
  bool _pollingAlerts = false;
  bool _isMiniMode = false;

  @override
  void initState() {
    super.initState();

    /// 초기 화면을 구성할 데이터를 Repository에서 비동기로 요청합니다.
    _snapshotFuture = widget.repository.fetchSnapshot();
    _portfolioFuture = widget.portfolioRepository.fetchPortfolio();
    _providerSettingsFuture = widget.providerSettingsRepository
        .fetchProviderSettings();
    _watchlistFuture = widget.watchlistRepository.fetchWatchlist();
    unawaited(
      widget.desktopWindowService.initialize(
        onShowDashboard: _showDashboard,
        onEnterMiniMode: _showMiniMode,
        onRefresh: _reloadAllInvestmentData,
        onOpenSettings: _openSettings,
      ),
    );
    if (widget.alertRepository != null) {
      unawaited(_refreshAlerts());
      unawaited(_pollPendingAlerts());
      _alertTimer = Timer.periodic(
        const Duration(seconds: 30),
        (_) => unawaited(_pollPendingAlerts()),
      );
    }
  }

  @override
  void dispose() {
    _alertTimer?.cancel();
    unawaited(widget.desktopWindowService.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final isDark = palette.isDark;

    return Scaffold(
      body: Container(
        decoration: BoxDecoration(gradient: palette.pageGradient),
        child: FutureBuilder<InvestmentSnapshot>(
          future: _snapshotFuture,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const LoadingState();
            }
            if (snapshot.hasError || !snapshot.hasData) {
              return ErrorState(onRetry: _reloadSnapshot);
            }

            final investment = snapshot.data!;
            if (_isMiniMode) {
              return FutureBuilder<List<WatchlistItem>>(
                future: _watchlistFuture,
                builder: (context, watchlistSnapshot) => MiniWidgetScreen(
                  snapshot: investment,
                  watchlist: watchlistSnapshot.data ?? const [],
                  onExpand: _expandDashboard,
                  onRefresh: _reloadAllInvestmentData,
                  onHide: _hideToTray,
                ),
              );
            }

            return SafeArea(
              child: Column(
                children: [
                  TopBar(
                    isDark: isDark,
                    user: widget.session.user,
                    onMiniMode: _enterMiniMode,
                    onThemeToggle: () =>
                        widget.onThemeToggle(Theme.of(context).brightness),
                  ),
                  Expanded(
                    child: _TabContent(
                      selectedIndex: _selectedIndex,
                      snapshot: investment,
                      watchlistRepository: widget.watchlistRepository,
                      portfolioRepository: widget.portfolioRepository,
                      kbAccountRepository: widget.kbAccountRepository,
                      marketDataRepository: widget.marketDataRepository,
                      researchFeedRepository: widget.researchFeedRepository,
                      recommendationRepository: widget.recommendationRepository,
                      appSecurityService: widget.appSecurityService,
                      appLockPinConfigured: widget.appLockPinConfigured,
                      onAppLockPinChanged: widget.onAppLockPinChanged,
                      alerts: _alerts ?? investment.alerts,
                      onAlertsRefresh: _refreshAlerts,
                      onAlertRead: _markAlertRead,
                      providerSettingsFuture: _providerSettingsFuture,
                      portfolioFuture: _portfolioFuture,
                      onPortfolioRetry: _reloadPortfolio,
                      onProviderSettingsRetry: _reloadProviderSettings,
                      onPortfolioChanged: _reloadAllInvestmentData,
                      pendingPortfolioSetupAction: _pendingPortfolioSetupAction,
                      onCapitalSetupOpen: () =>
                          _openPortfolioSetup(PortfolioSetupAction.editCapital),
                      onHoldingSetupOpen: () =>
                          _openPortfolioSetup(PortfolioSetupAction.addHolding),
                      onPendingPortfolioSetupActionConsumed:
                          _clearPendingPortfolioSetupAction,
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
      bottomNavigationBar: _isMiniMode
          ? null
          : BottomNav(
              selectedIndex: _selectedIndex,
              onSelected: (index) => setState(() => _selectedIndex = index),
            ),
    );
  }

  void _enterMiniMode() {
    unawaited(widget.desktopWindowService.enterMiniMode());
    _showMiniMode();
  }

  void _showMiniMode() {
    if (mounted) {
      setState(() => _isMiniMode = true);
    }
  }

  void _expandDashboard() {
    unawaited(widget.desktopWindowService.showDashboard());
    _showDashboard();
  }

  void _showDashboard() {
    if (mounted) {
      setState(() => _isMiniMode = false);
    }
  }

  void _hideToTray() {
    unawaited(widget.desktopWindowService.hideToTray());
  }

  void _openSettings() {
    if (mounted) {
      setState(() {
        _isMiniMode = false;
        _selectedIndex = 5;
      });
    }
  }

  /// 오류 화면에서 재시도 버튼을 눌렀을 때 데이터를 다시 요청합니다.
  void _reloadSnapshot() {
    _reloadAllInvestmentData();
  }

  /// 자본금/보유 종목 변경 후 대시보드와 포트폴리오 데이터를 함께 다시 요청합니다.
  void _reloadAllInvestmentData() {
    setState(() {
      _snapshotFuture = widget.repository.fetchSnapshot();
      _portfolioFuture = widget.portfolioRepository.fetchPortfolio();
      _watchlistFuture = widget.watchlistRepository.fetchWatchlist();
    });
  }

  /// 포트폴리오 탭에서 최신 자본금/보유 종목만 다시 요청합니다.
  void _reloadPortfolio() {
    setState(() {
      _portfolioFuture = widget.portfolioRepository.fetchPortfolio();
    });
  }

  /// 설정 탭에서 증권사 연동 상태만 다시 요청합니다.
  void _reloadProviderSettings() {
    setState(() {
      _providerSettingsFuture = widget.providerSettingsRepository
          .fetchProviderSettings();
    });
  }

  /// 빈 상태 CTA에서 포트폴리오 관리 탭으로 이동하고 필요한 입력 시트를 엽니다.
  void _openPortfolioSetup(PortfolioSetupAction action) {
    setState(() {
      _selectedIndex = 2;
      _pendingPortfolioSetupAction = action;
    });
  }

  /// 포트폴리오 입력 시트를 연 뒤 pending action을 비웁니다.
  void _clearPendingPortfolioSetupAction() {
    setState(() => _pendingPortfolioSetupAction = null);
  }

  Future<void> _pollPendingAlerts() async {
    final repository = widget.alertRepository;
    if (repository == null || _pollingAlerts) {
      return;
    }
    _pollingAlerts = true;
    try {
      final pending = await repository.fetchPending();
      for (final alert in pending) {
        await widget.localNotificationService.show(alert);
        final alertId = alert.alertId;
        if (alertId != null) {
          await repository.markSent(alertId);
        }
      }
      if (pending.isNotEmpty) {
        await _refreshAlerts();
      }
    } catch (_) {
      // 알림 서버가 잠시 응답하지 않아도 투자 화면 사용은 계속할 수 있어야 합니다.
    } finally {
      _pollingAlerts = false;
    }
  }

  Future<void> _refreshAlerts() async {
    final repository = widget.alertRepository;
    if (repository == null) {
      return;
    }
    try {
      final alerts = await repository.fetchAlerts();
      if (mounted) {
        setState(() => _alerts = alerts);
      }
    } catch (_) {
      // 마지막으로 조회한 목록을 유지하고 다음 주기에서 다시 시도합니다.
    }
  }

  Future<void> _markAlertRead(AppAlert alert) async {
    final repository = widget.alertRepository;
    final alertId = alert.alertId;
    if (repository == null || alertId == null || alert.isRead) {
      return;
    }
    await repository.markRead(alertId);
    if (!mounted || _alerts == null) {
      return;
    }
    setState(() {
      _alerts = _alerts!
          .map(
            (item) =>
                item.alertId == alertId ? item.copyWith(isRead: true) : item,
          )
          .toList();
    });
  }
}

/// 상단 브랜드 바입니다.
///
/// 앱 이름, 현재 테마 콘셉트, 테마 전환 버튼을 한곳에 배치해
/// Windows 프로그램의 첫 인상을 시안 A/B와 맞춥니다.
class TopBar extends StatelessWidget {
  /// 현재 다크모드 여부와 전환 콜백을 받습니다.
  const TopBar({
    super.key,
    required this.isDark,
    required this.user,
    required this.onMiniMode,
    required this.onThemeToggle,
  });

  /// true이면 A 시안 콘셉트인 AI 트레이딩 콘솔 문구를 보여줍니다.
  final bool isDark;

  /// 현재 로그인한 사용자 정보입니다.
  final AuthUser user;

  /// 사용자가 아이콘 버튼을 눌렀을 때 실행되는 테마 전환 콜백입니다.
  final VoidCallback onThemeToggle;

  /// 현재 창을 항상 위 미니 위젯으로 전환합니다.
  final VoidCallback onMiniMode;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 14, 20, 8),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: const BoxDecoration(
              shape: BoxShape.circle,
              gradient: LinearGradient(colors: [AppTheme.main, AppTheme.sub]),
            ),
            child: const Icon(
              Icons.trending_up_rounded,
              color: Colors.white,
              size: 24,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '사고팔고',
                  style: TextStyle(
                    color: palette.text,
                    fontSize: 22,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  '${user.nickname} · ${_profileLabel(user.authProvider)}',
                  style: TextStyle(
                    color: palette.muted,
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
          ),
          IconButton.filledTonal(
            onPressed: onMiniMode,
            tooltip: '미니 위젯',
            icon: const Icon(Icons.picture_in_picture_alt_rounded),
          ),
          const SizedBox(width: 6),
          IconButton.filledTonal(
            onPressed: onThemeToggle,
            tooltip: isDark ? '라이트모드로 전환' : '다크모드로 전환',
            icon: Icon(isDark ? Icons.light_mode : Icons.dark_mode),
          ),
        ],
      ),
    );
  }

  /// 프로필 출처 코드를 화면에 표시할 짧은 한글 라벨로 변환합니다.
  String _profileLabel(String authProvider) {
    if (authProvider == 'LOCAL') {
      return '개인 모드';
    }

    return authProvider;
  }
}

/// 로딩 중일 때 표시되는 화면입니다.
class LoadingState extends StatelessWidget {
  /// 별도 설정 없이 브랜드 색상의 진행 표시기를 보여줍니다.
  const LoadingState({super.key});

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const CircularProgressIndicator(color: AppTheme.point),
          const SizedBox(height: 14),
          Text(
            '투자 데이터를 불러오는 중입니다',
            style: TextStyle(
              color: palette.muted,
              fontSize: 13,
              fontWeight: FontWeight.w700,
              letterSpacing: 0,
            ),
          ),
        ],
      ),
    );
  }
}

/// 데이터 로딩 실패 시 표시되는 오류 화면입니다.
class ErrorState extends StatelessWidget {
  /// 재시도 버튼에서 실행할 콜백을 받습니다.
  const ErrorState({super.key, required this.onRetry});

  /// Repository 요청을 다시 시작하는 콜백입니다.
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.error_outline_rounded,
              color: AppTheme.sub,
              size: 38,
            ),
            const SizedBox(height: 12),
            Text(
              '데이터를 불러오지 못했습니다',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: palette.text,
                fontSize: 18,
                fontWeight: FontWeight.w900,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              '네트워크 연결이나 서버 상태를 확인한 뒤 다시 시도해 주세요.',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: palette.muted,
                fontSize: 13,
                height: 1.35,
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

/// 하단 탭 선택에 따라 실제 화면을 교체하는 콘텐츠 영역입니다.
class _TabContent extends StatelessWidget {
  /// 선택된 탭 인덱스와 로딩 완료된 투자 데이터를 받습니다.
  const _TabContent({
    required this.selectedIndex,
    required this.snapshot,
    required this.watchlistRepository,
    required this.portfolioRepository,
    required this.kbAccountRepository,
    required this.marketDataRepository,
    required this.researchFeedRepository,
    required this.recommendationRepository,
    required this.appSecurityService,
    required this.appLockPinConfigured,
    required this.onAppLockPinChanged,
    required this.alerts,
    required this.onAlertsRefresh,
    required this.onAlertRead,
    required this.providerSettingsFuture,
    required this.portfolioFuture,
    required this.onPortfolioRetry,
    required this.onProviderSettingsRetry,
    required this.onPortfolioChanged,
    required this.pendingPortfolioSetupAction,
    required this.onCapitalSetupOpen,
    required this.onHoldingSetupOpen,
    required this.onPendingPortfolioSetupActionConsumed,
  });

  /// 현재 선택된 하단 탭 인덱스입니다.
  final int selectedIndex;

  /// 모든 화면에 나눠 전달할 투자 데이터 묶음입니다.
  final InvestmentSnapshot snapshot;

  /// 추천 화면 관심 종목 액션을 처리하는 Repository입니다.
  final WatchlistRepository watchlistRepository;

  /// 포트폴리오 화면 자본금/보유 종목 액션을 처리하는 Repository입니다.
  final PortfolioRepository portfolioRepository;

  /// 설정 화면 KB 계좌 조회 액션을 처리하는 Repository입니다.
  final KbAccountRepository kbAccountRepository;

  /// 포트폴리오 종목 상세 캔들을 조회하는 Repository입니다.
  final MarketDataRepository marketDataRepository;

  /// 뉴스·공시 조회와 동기화를 처리하는 Repository입니다.
  final ResearchFeedRepository researchFeedRepository;

  /// 추천 이력과 수동 재분석을 처리하는 Repository입니다.
  final RecommendationRepository recommendationRepository;

  final AppSecurityService appSecurityService;

  final bool appLockPinConfigured;

  final ValueChanged<String?> onAppLockPinChanged;

  final List<AppAlert> alerts;

  final Future<void> Function() onAlertsRefresh;

  final ValueChanged<AppAlert> onAlertRead;

  /// 설정 화면에서 사용할 증권사 연동 상태 Future입니다.
  final Future<ProviderSettingsSnapshot> providerSettingsFuture;

  /// 포트폴리오 탭에서 사용할 최신 자본금/보유 종목 Future입니다.
  final Future<PortfolioSnapshot> portfolioFuture;

  /// 포트폴리오 데이터 재시도 콜백입니다.
  final VoidCallback onPortfolioRetry;

  /// 설정 화면 데이터 재시도 콜백입니다.
  final VoidCallback onProviderSettingsRetry;

  /// 포트폴리오 데이터가 변경됐을 때 전체 투자 데이터를 다시 불러오는 콜백입니다.
  final VoidCallback onPortfolioChanged;

  /// 다른 탭의 빈 상태 CTA가 요청한 포트폴리오 초기 작업입니다.
  final PortfolioSetupAction? pendingPortfolioSetupAction;

  /// 데이터 없음 상태에서 자본금 수정 시트를 여는 콜백입니다.
  final VoidCallback onCapitalSetupOpen;

  /// 데이터 없음 상태에서 보유 종목 추가 시트를 여는 콜백입니다.
  final VoidCallback onHoldingSetupOpen;

  /// 포트폴리오 초기 작업을 실행한 뒤 pending 상태를 비우는 콜백입니다.
  final VoidCallback onPendingPortfolioSetupActionConsumed;

  @override
  Widget build(BuildContext context) {
    return IndexedStack(
      index: selectedIndex,
      children: [
        DashboardScreen(
          snapshot: snapshot,
          onCapitalSetupOpen: onCapitalSetupOpen,
          onHoldingSetupOpen: onHoldingSetupOpen,
        ),
        RecommendationScreen(
          recommendation: snapshot.recommendation,
          holdings: snapshot.holdings,
          recommendationRepository: recommendationRepository,
          watchlistRepository: watchlistRepository,
          onRecommendationChanged: onPortfolioChanged,
          onCapitalSetupOpen: onCapitalSetupOpen,
          onHoldingSetupOpen: onHoldingSetupOpen,
        ),
        PortfolioScreen(
          capital: CapitalSettings(
            availableCapital: snapshot.marketSummary.availableCapital,
            recommendedMinPosition: 0,
            recommendedMaxPosition: 0,
            riskPerTradeRate: 0.02,
          ),
          summary: snapshot.portfolioSummary,
          holdings: snapshot.holdings,
          repository: portfolioRepository,
          marketDataRepository: marketDataRepository,
          portfolioFuture: portfolioFuture,
          pendingSetupAction: pendingPortfolioSetupAction,
          onRetry: onPortfolioRetry,
          onChanged: onPortfolioChanged,
          onPendingSetupActionConsumed: onPendingPortfolioSetupActionConsumed,
        ),
        ResearchTimelineScreen(
          repository: researchFeedRepository,
          stocks: _researchStocks(snapshot),
          active: selectedIndex == 3,
          onHoldingSetupOpen: onHoldingSetupOpen,
        ),
        AlertsScreen(
          alerts: alerts,
          onRefresh: onAlertsRefresh,
          onAlertTap: onAlertRead,
        ),
        SettingsScreen(
          providerSettingsFuture: providerSettingsFuture,
          kbAccountRepository: kbAccountRepository,
          appSecurityService: appSecurityService,
          appLockPinConfigured: appLockPinConfigured,
          onAppLockPinChanged: onAppLockPinChanged,
          onRetry: onProviderSettingsRetry,
        ),
      ],
    );
  }
}

List<ResearchStock> _researchStocks(InvestmentSnapshot snapshot) {
  final stocks = <String, ResearchStock>{};
  for (final holding in snapshot.holdings) {
    stocks[holding.stockCode] = ResearchStock(
      stockCode: holding.stockCode,
      stockName: holding.stockName,
    );
  }
  final recommendation = snapshot.recommendation;
  if (recommendation != null) {
    stocks.putIfAbsent(
      recommendation.stockCode,
      () => ResearchStock(
        stockCode: recommendation.stockCode,
        stockName: recommendation.stockName,
      ),
    );
  }
  return stocks.values.toList();
}
