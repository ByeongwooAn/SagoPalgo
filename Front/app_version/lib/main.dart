import 'package:flutter/material.dart';

import 'config/app_environment.dart';
import 'models/auth_session.dart';
import 'repositories/investment_repository.dart';
import 'repositories/alert_repository.dart';
import 'repositories/kb_account_repository.dart';
import 'repositories/market_data_repository.dart';
import 'repositories/paper_trading_repository.dart';
import 'repositories/portfolio_repository.dart';
import 'repositories/provider_settings_repository.dart';
import 'repositories/recommendation_repository.dart';
import 'repositories/research_feed_repository.dart';
import 'repositories/spring_investment_repository.dart';
import 'repositories/spring_alert_repository.dart';
import 'repositories/spring_kb_account_repository.dart';
import 'repositories/spring_market_data_repository.dart';
import 'repositories/spring_paper_trading_repository.dart';
import 'repositories/spring_portfolio_repository.dart';
import 'repositories/spring_provider_settings_repository.dart';
import 'repositories/spring_recommendation_repository.dart';
import 'repositories/spring_research_feed_repository.dart';
import 'repositories/spring_watchlist_repository.dart';
import 'repositories/watchlist_repository.dart';
import 'screens/app_lock_screen.dart';
import 'screens/sago_palgo_home.dart';
import 'services/app_security_service.dart';
import 'services/desktop_window_service.dart';
import 'services/local_notification_service.dart';
import 'theme/app_theme.dart';

/// Flutter 애플리케이션의 시작점입니다.
///
/// Android와 Windows에서 앱이 실행되면 가장 먼저 이 함수가 호출되고,
/// `SagoPalgoApp`을 Flutter 위젯 트리의 루트로 올립니다.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AppEnvironment.load();
  final environment = AppEnvironment.instance;
  const securityService = AppSecurityService(WindowsCredentialStore());
  String? appLockPin;
  try {
    appLockPin = await securityService.loadPin(
      legacyPin: environment.appLockPin,
    );
  } catch (_) {
    // 네이티브 저장소가 없는 개발 환경에서는 기존 설정으로 실행합니다.
    appLockPin = environment.appLockPin;
  }
  runApp(
    SagoPalgoApp.fromEnvironment(
      appSecurityService: securityService,
      appLockPin: appLockPin,
    ),
  );
}

/// 사고팔고 앱의 최상위 위젯입니다.
///
/// 이 위젯은 MaterialApp, 다크/라이트 테마, Repository 주입을 담당합니다.
/// 실제 화면 구현은 `SagoPalgoHome` 아래로 내려서 main 파일이 앱 조립만 맡도록 했습니다.
class SagoPalgoApp extends StatefulWidget {
  /// 테스트나 실제 API 연동 단계에서 데이터 Repository를 교체할 수 있게 주입받습니다.
  const SagoPalgoApp({
    super.key,
    this.investmentRepositoryBuilder,
    this.watchlistRepositoryBuilder,
    this.portfolioRepositoryBuilder,
    this.providerSettingsRepositoryBuilder,
    this.recommendationRepositoryBuilder,
    this.researchFeedRepositoryBuilder,
    this.kbAccountRepositoryBuilder,
    this.marketDataRepositoryBuilder,
    this.paperTradingRepositoryBuilder,
    this.alertRepositoryBuilder,
    this.localNotificationService = const NoopLocalNotificationService(),
    this.desktopWindowService = const NoopDesktopWindowService(),
    this.appSecurityService = const AppSecurityService(NoopCredentialStore()),
    this.session = AuthSession.personal,
    this.appLockPin,
  });

  /// `.env`에서 읽은 API 주소로 실제 Spring 연동 Repository를 구성합니다.
  factory SagoPalgoApp.fromEnvironment({
    AppSecurityService appSecurityService = const AppSecurityService(
      WindowsCredentialStore(),
    ),
    String? appLockPin,
  }) {
    return SagoPalgoApp(
      appLockPin: appLockPin,
      appSecurityService: appSecurityService,
      alertRepositoryBuilder: (session) =>
          SpringAlertRepository(accessToken: session.accessToken),
      localNotificationService: WindowsLocalNotificationService(),
      desktopWindowService: WindowsDesktopWindowService(),
    );
  }

  /// 테스트에서 투자 데이터 Repository를 교체하기 위한 빌더입니다.
  final InvestmentRepository Function(AuthSession session)?
  investmentRepositoryBuilder;

  /// 테스트에서 관심 종목 Repository를 교체하기 위한 빌더입니다.
  final WatchlistRepository Function(AuthSession session)?
  watchlistRepositoryBuilder;

  /// 테스트에서 포트폴리오 Repository를 교체하기 위한 빌더입니다.
  final PortfolioRepository Function(AuthSession session)?
  portfolioRepositoryBuilder;

  /// 테스트에서 증권사 설정 Repository를 교체하기 위한 빌더입니다.
  final ProviderSettingsRepository Function(AuthSession session)?
  providerSettingsRepositoryBuilder;

  /// 추천 이력 조회와 수동 재분석 Repository를 교체하기 위한 빌더입니다.
  final RecommendationRepository Function(AuthSession session)?
  recommendationRepositoryBuilder;

  /// 테스트에서 뉴스·공시 Repository를 교체하기 위한 빌더입니다.
  final ResearchFeedRepository Function(AuthSession session)?
  researchFeedRepositoryBuilder;

  /// 테스트에서 KB증권 계좌 Repository를 교체하기 위한 빌더입니다.
  final KbAccountRepository Function(AuthSession session)?
  kbAccountRepositoryBuilder;

  /// 테스트에서 캔들 시세 Repository를 교체하기 위한 빌더입니다.
  final MarketDataRepository Function(AuthSession session)?
  marketDataRepositoryBuilder;

  /// AI 신호 기반 모의매매 Repository를 교체하기 위한 빌더입니다.
  final PaperTradingRepository Function(AuthSession session)?
  paperTradingRepositoryBuilder;

  /// 저장 알림 조회와 전달 상태를 처리하는 Repository 빌더입니다.
  final AlertRepository Function(AuthSession session)? alertRepositoryBuilder;

  /// Windows 네이티브 알림 표시 구현입니다.
  final LocalNotificationService localNotificationService;

  /// Windows 창 크기와 시스템 트레이 메뉴를 제어합니다.
  final DesktopWindowService desktopWindowService;

  /// Windows Credential Manager의 앱 잠금 PIN 저장 정책입니다.
  final AppSecurityService appSecurityService;

  /// 개인용 프로그램에서 사용할 로컬 프로필 세션입니다.
  final AuthSession session;

  /// 설정되어 있으면 앱 시작 시 로컬 PIN 잠금 화면을 표시합니다.
  final String? appLockPin;

  @override
  State<SagoPalgoApp> createState() => _SagoPalgoAppState();
}

class _SagoPalgoAppState extends State<SagoPalgoApp> {
  /// 시스템 설정을 기본으로 따르되, 사용자가 상단 버튼을 누르면 명시적으로 바뀝니다.
  ThemeMode _themeMode = ThemeMode.system;

  /// 앱 잠금 PIN이 설정된 경우 홈 화면 진입 전 잠금 해제를 기다립니다.
  late bool _isLocked;
  String? _appLockPin;

  @override
  void initState() {
    super.initState();
    _appLockPin = widget.appLockPin;
    _isLocked = _appLockPin != null;
  }

  /// 현재 화면 밝기를 기준으로 반대 테마를 선택합니다.
  ///
  /// 다크모드에서는 라이트모드로, 라이트모드에서는 다크모드로 전환해
  /// A/B 시안을 앱 안에서 바로 비교할 수 있게 합니다.
  void _toggleTheme(Brightness brightness) {
    setState(() {
      _themeMode = brightness == Brightness.dark
          ? ThemeMode.light
          : ThemeMode.dark;
    });
  }

  @override
  Widget build(BuildContext context) {
    final session = widget.session;
    final appLockPin = _appLockPin;

    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'SagoPalgo',
      themeMode: _themeMode,
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      home: _isLocked && appLockPin != null
          ? AppLockScreen(
              pin: appLockPin,
              onUnlocked: _unlockApp,
              onThemeToggle: _toggleTheme,
            )
          : SagoPalgoHome(
              onThemeToggle: _toggleTheme,
              repository:
                  widget.investmentRepositoryBuilder?.call(session) ??
                  SpringInvestmentRepository(accessToken: session.accessToken),
              watchlistRepository:
                  widget.watchlistRepositoryBuilder?.call(session) ??
                  SpringWatchlistRepository(accessToken: session.accessToken),
              portfolioRepository:
                  widget.portfolioRepositoryBuilder?.call(session) ??
                  SpringPortfolioRepository(accessToken: session.accessToken),
              providerSettingsRepository:
                  widget.providerSettingsRepositoryBuilder?.call(session) ??
                  SpringProviderSettingsRepository(
                    accessToken: session.accessToken,
                  ),
              recommendationRepository:
                  widget.recommendationRepositoryBuilder?.call(session) ??
                  SpringRecommendationRepository(
                    accessToken: session.accessToken,
                  ),
              researchFeedRepository:
                  widget.researchFeedRepositoryBuilder?.call(session) ??
                  SpringResearchFeedRepository(
                    accessToken: session.accessToken,
                  ),
              kbAccountRepository:
                  widget.kbAccountRepositoryBuilder?.call(session) ??
                  SpringKbAccountRepository(accessToken: session.accessToken),
              marketDataRepository:
                  widget.marketDataRepositoryBuilder?.call(session) ??
                  SpringMarketDataRepository(accessToken: session.accessToken),
              paperTradingRepository:
                  widget.paperTradingRepositoryBuilder?.call(session) ??
                  SpringPaperTradingRepository(
                    accessToken: session.accessToken,
                  ),
              alertRepository: widget.alertRepositoryBuilder?.call(session),
              localNotificationService: widget.localNotificationService,
              desktopWindowService: widget.desktopWindowService,
              appSecurityService: widget.appSecurityService,
              appLockPinConfigured: appLockPin != null,
              onAppLockPinChanged: _updateAppLockPin,
              session: session,
            ),
    );
  }

  void _unlockApp() {
    setState(() => _isLocked = false);
  }

  void _updateAppLockPin(String? pin) {
    setState(() => _appLockPin = pin);
  }
}

/// 기존 Flutter 기본 테스트나 외부 import가 `MyApp`을 찾을 가능성을 고려한 별칭입니다.
///
/// 새 코드에서는 `SagoPalgoApp`을 직접 사용하는 것을 권장합니다.
@Deprecated('Use SagoPalgoApp instead.')
typedef MyApp = SagoPalgoApp;
