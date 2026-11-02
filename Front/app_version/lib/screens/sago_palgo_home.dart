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
import '../repositories/account_observation_repository.dart';
import '../repositories/market_data_repository.dart';
import '../repositories/order_precheck_repository.dart';
import '../repositories/paper_trading_repository.dart';
import '../repositories/portfolio_repository.dart';
import '../repositories/provider_settings_repository.dart';
import '../repositories/recommendation_repository.dart';
import '../repositories/research_feed_repository.dart';
import '../repositories/watchlist_repository.dart';
import '../services/app_security_service.dart';
import '../services/alert_delivery_service.dart';
import '../services/alert_display_journal.dart';
import '../services/desktop_window_service.dart';
import '../services/local_notification_service.dart';
import '../theme/app_theme.dart';
import '../widgets/bottom_nav.dart';
import '../widgets/responsive_layout.dart';
import 'watchlist_setup_sheet.dart';
import 'alerts_screen.dart';
import 'dashboard_screen.dart';
import 'mini_widget_screen.dart';
import 'paper_trading_screen.dart';
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
    this.accountObservationRepository,
    required this.marketDataRepository,
    required this.orderPrecheckRepository,
    required this.paperTradingRepository,
    required this.alertRepository,
    required this.localNotificationService,
    this.alertDisplayJournal = const NoopAlertDisplayJournal(),
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

  final AccountObservationRepository? accountObservationRepository;

  /// 종목 상세 화면에서 일·주·월봉 시세를 조회하는 Repository입니다.
  final MarketDataRepository marketDataRepository;

  /// 포트폴리오 종목의 주문안을 실제 전송 없이 검증합니다.
  final OrderPrecheckRepository orderPrecheckRepository;

  /// 모의매매 현황 조회와 가상 체결을 처리합니다.
  final PaperTradingRepository paperTradingRepository;

  /// Ubuntu 백엔드의 저장 알림을 조회하고 상태를 갱신합니다.
  final AlertRepository? alertRepository;

  /// Windows 알림 센터에 새 신호를 표시합니다.
  final LocalNotificationService localNotificationService;

  /// 표시 후 서버 확인을 기다리는 알림을 저장합니다.
  final AlertDisplayJournal alertDisplayJournal;

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
  InvestmentSnapshot? _lastInvestment;
  String? _alertsFetchError;
  DateTime? _alertsCheckedAt;
  final Set<int> _readingAlertIds = {};

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
  AlertDeliveryService? _alertDeliveryService;
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
      _alertDeliveryService = AlertDeliveryService(
        repository: widget.alertRepository!,
        notificationService: widget.localNotificationService,
        displayJournal: widget.alertDisplayJournal,
      );
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

    return LayoutBuilder(
      builder: (context, constraints) {
        final desktopNavigation =
            !_isMiniMode &&
            constraints.maxWidth >= AppLayout.desktopNavigationWidth;
        return Scaffold(
          body: Container(
            decoration: BoxDecoration(gradient: palette.pageGradient),
            child: FutureBuilder<InvestmentSnapshot>(
              future: _snapshotFuture,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done &&
                    !snapshot.hasData &&
                    _lastInvestment == null) {
                  return const LoadingState();
                }
                if (!snapshot.hasData && _lastInvestment == null) {
                  return ErrorState(onRetry: _reloadSnapshot);
                }

                final investment = snapshot.data ?? _lastInvestment!;
                if (snapshot.hasData &&
                    snapshot.connectionState == ConnectionState.done) {
                  _lastInvestment = investment;
                }
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
                      if (snapshot.hasError)
                        TextButton.icon(
                          onPressed: _reloadAllInvestmentData,
                          icon: const Icon(Icons.sync_problem),
                          label: const Text(
                            '최근 투자 데이터 갱신 실패 · 이전 표시 유지 · 다시 조회',
                          ),
                        ),
                      Expanded(
                        child: Row(
                          children: [
                            if (desktopNavigation)
                              DesktopNav(
                                selectedIndex: _selectedIndex,
                                onSelected: (index) =>
                                    setState(() => _selectedIndex = index),
                              ),
                            Expanded(
                              key: const ValueKey('main-content'),
                              child: _TabContent(
                                selectedIndex: _selectedIndex,
                                snapshot: investment,
                                watchlistFuture: _watchlistFuture,
                                alertsFetchError: _alertsFetchError,
                                alertsCheckedAt: _alertsCheckedAt,
                                watchlistRepository: widget.watchlistRepository,
                                portfolioRepository: widget.portfolioRepository,
                                kbAccountRepository: widget.kbAccountRepository,
                                accountObservationRepository:
                                    widget.accountObservationRepository,
                                marketDataRepository:
                                    widget.marketDataRepository,
                                orderPrecheckRepository:
                                    widget.orderPrecheckRepository,
                                paperTradingRepository:
                                    widget.paperTradingRepository,
                                researchFeedRepository:
                                    widget.researchFeedRepository,
                                recommendationRepository:
                                    widget.recommendationRepository,
                                appSecurityService: widget.appSecurityService,
                                appLockPinConfigured:
                                    widget.appLockPinConfigured,
                                onAppLockPinChanged: widget.onAppLockPinChanged,
                                alerts: _alerts ?? investment.alerts,
                                deliveryStatus: _alertDeliveryService?.status,
                                onAlertsRefresh: _refreshAlertsAndDelivery,
                                onAlertRead: _markAlertRead,
                                providerSettingsFuture: _providerSettingsFuture,
                                providerSettingsRepository:
                                    widget.providerSettingsRepository,
                                portfolioFuture: _portfolioFuture,
                                onPortfolioRetry: _reloadPortfolio,
                                onProviderSettingsRetry:
                                    _reloadProviderSettings,
                                onPortfolioChanged: _reloadAllInvestmentData,
                                pendingPortfolioSetupAction:
                                    _pendingPortfolioSetupAction,
                                onCapitalSetupOpen: () => _openPortfolioSetup(
                                  PortfolioSetupAction.editCapital,
                                ),
                                onHoldingSetupOpen: () => _openPortfolioSetup(
                                  PortfolioSetupAction.addHolding,
                                ),
                                onWatchlistSetupOpen: _openWatchlistSetup,
                                onAnalysisOpen: () =>
                                    setState(() => _selectedIndex = 1),
                                onSettingsOpen: _openSettings,
                                onPendingPortfolioSetupActionConsumed:
                                    _clearPendingPortfolioSetupAction,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                );
              },
            ),
          ),
          bottomNavigationBar: _isMiniMode || desktopNavigation
              ? null
              : BottomNav(
                  selectedIndex: _selectedIndex,
                  onSelected: (index) => setState(() => _selectedIndex = index),
                ),
        );
      },
    );
  }

  Future<void> _openWatchlistSetup() async {
    if (await showWatchlistSetup(context, widget.watchlistRepository) &&
        mounted) {
      _reloadAllInvestmentData();
    }
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
        _selectedIndex = 6;
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
    unawaited(_refreshAlertsAndDelivery());
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
    final deliveryService = _alertDeliveryService;
    if (deliveryService == null || _pollingAlerts) {
      return;
    }
    _pollingAlerts = true;
    try {
      if (await deliveryService.deliverPending()) {
        await _refreshAlerts();
      }
    } catch (_) {
      // 알림 서버가 잠시 응답하지 않아도 투자 화면 사용은 계속할 수 있어야 합니다.
    } finally {
      _pollingAlerts = false;
      if (mounted) {
        setState(() {});
      }
    }
  }

  Future<void> _refreshAlertsAndDelivery() async {
    await _pollPendingAlerts();
    await _refreshAlerts();
  }

  Future<void> _refreshAlerts() async {
    final repository = widget.alertRepository;
    if (repository == null) {
      return;
    }
    try {
      final alerts = await repository.fetchAlerts();
      if (mounted) {
        setState(() {
          _alerts = alerts;
          _alertsFetchError = null;
          _alertsCheckedAt = DateTime.now();
        });
      }
    } catch (_) {
      if (mounted) {
        setState(
          () => _alertsFetchError =
              '알림 목록을 불러오지 못했습니다. 기존 목록이 있으면 유지합니다. 새로고침을 다시 시도하세요.',
        );
      }
    }
  }

  Future<void> _markAlertRead(AppAlert alert) async {
    final repository = widget.alertRepository;
    final alertId = alert.alertId;
    if (repository == null ||
        alertId == null ||
        alert.isRead ||
        !_readingAlertIds.add(alertId)) {
      return;
    }
    try {
      await repository.markRead(alertId);
      if (!mounted) return;
      if (_alerts == null) {
        await _refreshAlerts();
      } else {
        setState(
          () => _alerts = _alerts!
              .map(
                (item) => item.alertId == alertId
                    ? item.copyWith(isRead: true)
                    : item,
              )
              .toList(),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('알림 읽음 처리에 실패했습니다. 다시 눌러 주세요.')),
        );
      }
    } finally {
      _readingAlertIds.remove(alertId);
    }
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
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
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
    required this.watchlistFuture,
    required this.alertsFetchError,
    required this.alertsCheckedAt,
    required this.watchlistRepository,
    required this.portfolioRepository,
    required this.kbAccountRepository,
    required this.accountObservationRepository,
    required this.marketDataRepository,
    required this.orderPrecheckRepository,
    required this.paperTradingRepository,
    required this.researchFeedRepository,
    required this.recommendationRepository,
    required this.appSecurityService,
    required this.appLockPinConfigured,
    required this.onAppLockPinChanged,
    required this.alerts,
    required this.deliveryStatus,
    required this.onAlertsRefresh,
    required this.onAlertRead,
    required this.providerSettingsFuture,
    required this.providerSettingsRepository,
    required this.portfolioFuture,
    required this.onPortfolioRetry,
    required this.onProviderSettingsRetry,
    required this.onPortfolioChanged,
    required this.pendingPortfolioSetupAction,
    required this.onCapitalSetupOpen,
    required this.onHoldingSetupOpen,
    required this.onWatchlistSetupOpen,
    required this.onAnalysisOpen,
    required this.onSettingsOpen,
    required this.onPendingPortfolioSetupActionConsumed,
  });

  /// 현재 선택된 하단 탭 인덱스입니다.
  final int selectedIndex;

  /// 모든 화면에 나눠 전달할 투자 데이터 묶음입니다.
  final InvestmentSnapshot snapshot;
  final Future<List<WatchlistItem>> watchlistFuture;
  final String? alertsFetchError;
  final DateTime? alertsCheckedAt;

  /// 추천 화면 관심 종목 액션을 처리하는 Repository입니다.
  final WatchlistRepository watchlistRepository;

  /// 포트폴리오 화면 자본금/보유 종목 액션을 처리하는 Repository입니다.
  final PortfolioRepository portfolioRepository;

  /// 설정 화면 KB 계좌 조회 액션을 처리하는 Repository입니다.
  final KbAccountRepository kbAccountRepository;

  final AccountObservationRepository? accountObservationRepository;

  /// 포트폴리오 종목 상세 캔들을 조회하는 Repository입니다.
  final MarketDataRepository marketDataRepository;

  /// 주문 안전 조건 사전검증 Repository입니다.
  final OrderPrecheckRepository orderPrecheckRepository;

  /// 모의매매 현황과 체결 액션을 처리하는 Repository입니다.
  final PaperTradingRepository paperTradingRepository;

  /// 뉴스·공시 조회와 동기화를 처리하는 Repository입니다.
  final ResearchFeedRepository researchFeedRepository;

  /// 추천 이력과 수동 재분석을 처리하는 Repository입니다.
  final RecommendationRepository recommendationRepository;

  final AppSecurityService appSecurityService;

  final bool appLockPinConfigured;

  final ValueChanged<String?> onAppLockPinChanged;

  final List<AppAlert> alerts;

  final AlertDeliveryStatus? deliveryStatus;

  final Future<void> Function() onAlertsRefresh;

  final ValueChanged<AppAlert> onAlertRead;

  /// 설정 화면에서 사용할 증권사 연동 상태 Future입니다.
  final Future<ProviderSettingsSnapshot> providerSettingsFuture;

  final ProviderSettingsRepository providerSettingsRepository;

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
  final VoidCallback onWatchlistSetupOpen;
  final VoidCallback onAnalysisOpen;
  final VoidCallback onSettingsOpen;

  /// 포트폴리오 초기 작업을 실행한 뒤 pending 상태를 비우는 콜백입니다.
  final VoidCallback onPendingPortfolioSetupActionConsumed;

  @override
  Widget build(BuildContext context) {
    return IndexedStack(
      index: selectedIndex,
      children: [
        FutureBuilder<List<WatchlistItem>>(
          future: watchlistFuture,
          builder: (context, state) => DashboardScreen(
            snapshot: snapshot,
            onCapitalSetupOpen: onCapitalSetupOpen,
            onHoldingSetupOpen: onHoldingSetupOpen,
            onRefresh: onPortfolioChanged,
            watchlistCount: state.data?.length,
            watchlistLoadFailed: state.hasError,
            onWatchlistSetupOpen: onWatchlistSetupOpen,
            onAnalysisOpen: onAnalysisOpen,
            onSettingsOpen: onSettingsOpen,
          ),
        ),
        RecommendationScreen(
          recommendation: snapshot.recommendation,
          holdings: snapshot.holdings,
          recommendationRepository: recommendationRepository,
          watchlistRepository: watchlistRepository,
          onRecommendationChanged: onPortfolioChanged,
          onCapitalSetupOpen: onCapitalSetupOpen,
          onHoldingSetupOpen: onHoldingSetupOpen,
          researchFeedRepository: researchFeedRepository,
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
          accountObservationRepository: accountObservationRepository,
          marketDataRepository: marketDataRepository,
          orderPrecheckRepository: orderPrecheckRepository,
          portfolioFuture: portfolioFuture,
          pendingSetupAction: pendingPortfolioSetupAction,
          onRetry: onPortfolioRetry,
          onChanged: onPortfolioChanged,
          onPendingSetupActionConsumed: onPendingPortfolioSetupActionConsumed,
        ),
        FutureBuilder<List<WatchlistItem>>(
          future: watchlistFuture,
          builder: (context, state) => Column(
            children: [
              if (state.hasError)
                TextButton(
                  onPressed: onPortfolioChanged,
                  child: const Text('관심 종목 조회 실패 · 다시 조회'),
                ),
              Expanded(
                key: const ValueKey('research-panel'),
                child: ResearchTimelineScreen(
                  repository: researchFeedRepository,
                  stocks: _researchStocks(snapshot, state.data ?? const []),
                  active: selectedIndex == 3,
                  onHoldingSetupOpen: onHoldingSetupOpen,
                  watchlistRepository: watchlistRepository,
                  onStocksChanged: onPortfolioChanged,
                  onFeedChanged: onPortfolioChanged,
                ),
              ),
            ],
          ),
        ),
        AlertsScreen(
          alerts: alerts,
          deliveryStatus: deliveryStatus,
          onRefresh: onAlertsRefresh,
          onAlertTap: onAlertRead,
          fetchError: alertsFetchError,
          checkedAt: alertsCheckedAt,
          onAnalysisOpen: onAnalysisOpen,
        ),
        PaperTradingScreen(
          repository: paperTradingRepository,
          recommendation: snapshot.recommendation,
          active: selectedIndex == 5,
          availableCapital: snapshot.marketSummary.availableCapital,
          onCapitalSetupOpen: onCapitalSetupOpen,
          onAnalysisOpen: onAnalysisOpen,
        ),
        SettingsScreen(
          providerSettingsFuture: providerSettingsFuture,
          providerSettingsRepository: providerSettingsRepository,
          kbAccountRepository: kbAccountRepository,
          accountObservationRepository: accountObservationRepository,
          appSecurityService: appSecurityService,
          appLockPinConfigured: appLockPinConfigured,
          onAppLockPinChanged: onAppLockPinChanged,
          onRetry: onProviderSettingsRetry,
        ),
      ],
    );
  }
}

List<ResearchStock> _researchStocks(
  InvestmentSnapshot snapshot,
  List<WatchlistItem> watchlist,
) {
  final stocks = <String, ResearchStock>{};
  for (final holding in snapshot.holdings) {
    stocks[holding.stockCode] = ResearchStock(
      stockCode: holding.stockCode,
      stockName: holding.stockName,
    );
  }
  for (final item in watchlist) {
    stocks.putIfAbsent(
      item.stockCode,
      () => ResearchStock(stockCode: item.stockCode, stockName: item.stockName),
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
