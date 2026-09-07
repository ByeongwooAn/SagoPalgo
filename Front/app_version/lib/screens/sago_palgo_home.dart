import 'package:flutter/material.dart';

import '../models/auth_session.dart';
import '../models/investment_snapshot.dart';
import '../repositories/investment_repository.dart';
import '../theme/app_theme.dart';
import '../widgets/bottom_nav.dart';
import 'alerts_screen.dart';
import 'dashboard_screen.dart';
import 'portfolio_screen.dart';
import 'recommendation_screen.dart';

/// 사고팔고 앱의 메인 화면 컨테이너입니다.
///
/// 이 위젯은 직접 투자 데이터를 만들지 않고 `InvestmentRepository`에서 받아옵니다.
/// 덕분에 현재 Mock Repository를 실제 Spring Boot API Repository로 바꿔도
/// 하단 탭과 화면 전환 로직은 그대로 유지할 수 있습니다.
class SagoPalgoHome extends StatefulWidget {
  /// 테마 전환 콜백과 투자 데이터 Repository를 주입받습니다.
  const SagoPalgoHome({
    super.key,
    required this.onThemeToggle,
    required this.onLogout,
    required this.repository,
    required this.session,
  });

  /// 상단 버튼을 눌렀을 때 앱 루트에 테마 변경을 요청하는 콜백입니다.
  final ValueChanged<Brightness> onThemeToggle;

  /// 상단 로그아웃 버튼을 눌렀을 때 앱 루트에 세션 종료를 요청하는 콜백입니다.
  final Future<void> Function() onLogout;

  /// 시장, 추천, 보유 종목, 알림 데이터를 제공하는 Repository입니다.
  final InvestmentRepository repository;

  /// 현재 로그인한 사용자와 토큰 정보를 담고 있는 인증 세션입니다.
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

  @override
  void initState() {
    super.initState();

    /// 초기 화면을 구성할 데이터를 Repository에서 비동기로 요청합니다.
    _snapshotFuture = widget.repository.fetchSnapshot();
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final isDark = palette.isDark;

    return Scaffold(
      body: Container(
        decoration: BoxDecoration(gradient: palette.pageGradient),
        child: SafeArea(
          child: Column(
            children: [
              TopBar(
                isDark: isDark,
                user: widget.session.user,
                onThemeToggle: () =>
                    widget.onThemeToggle(Theme.of(context).brightness),
                onLogout: widget.onLogout,
              ),
              Expanded(
                child: FutureBuilder<InvestmentSnapshot>(
                  future: _snapshotFuture,
                  builder: (context, snapshot) {
                    /// 데이터가 아직 없을 때는 API 연동 이후에도 그대로 쓸 수 있는 로딩 상태를 보여줍니다.
                    if (snapshot.connectionState != ConnectionState.done) {
                      return const LoadingState();
                    }

                    /// API 오류가 생길 경우를 대비해 사용자에게 재시도 가능한 오류 화면을 제공합니다.
                    if (snapshot.hasError || !snapshot.hasData) {
                      return ErrorState(onRetry: _reloadSnapshot);
                    }

                    /// 데이터 로딩이 끝나면 하단 탭 인덱스에 맞는 화면을 IndexedStack으로 보여줍니다.
                    return _TabContent(
                      selectedIndex: _selectedIndex,
                      snapshot: snapshot.data!,
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
      bottomNavigationBar: BottomNav(
        selectedIndex: _selectedIndex,
        onSelected: (index) => setState(() => _selectedIndex = index),
      ),
    );
  }

  /// 오류 화면에서 재시도 버튼을 눌렀을 때 데이터를 다시 요청합니다.
  void _reloadSnapshot() {
    setState(() {
      _snapshotFuture = widget.repository.fetchSnapshot();
    });
  }
}

/// 상단 브랜드 바입니다.
///
/// 앱 이름, 현재 테마 콘셉트, 테마 전환 버튼을 한곳에 배치해
/// Android 앱의 첫 인상을 시안 A/B와 맞춥니다.
class TopBar extends StatelessWidget {
  /// 현재 다크모드 여부와 전환 콜백을 받습니다.
  const TopBar({
    super.key,
    required this.isDark,
    required this.user,
    required this.onThemeToggle,
    required this.onLogout,
  });

  /// true이면 A 시안 콘셉트인 AI 트레이딩 콘솔 문구를 보여줍니다.
  final bool isDark;

  /// 현재 로그인한 사용자 정보입니다.
  final AuthUser user;

  /// 사용자가 아이콘 버튼을 눌렀을 때 실행되는 테마 전환 콜백입니다.
  final VoidCallback onThemeToggle;

  /// 사용자가 로그아웃 아이콘 버튼을 눌렀을 때 실행되는 콜백입니다.
  final Future<void> Function() onLogout;

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
                  '${user.nickname} · ${_providerLabel(user.authProvider)}',
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
            onPressed: onThemeToggle,
            tooltip: isDark ? '라이트모드로 전환' : '다크모드로 전환',
            icon: Icon(isDark ? Icons.light_mode : Icons.dark_mode),
          ),
          const SizedBox(width: 6),
          IconButton.filledTonal(
            onPressed: onLogout,
            tooltip: '로그아웃',
            icon: const Icon(Icons.logout_rounded),
          ),
        ],
      ),
    );
  }

  /// 백엔드에서 내려준 provider 코드를 화면에 표시할 짧은 한글 라벨로 변환합니다.
  String _providerLabel(String authProvider) {
    return authProvider == 'NAVER' ? 'Naver 로그인' : 'Google 로그인';
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
  const _TabContent({required this.selectedIndex, required this.snapshot});

  /// 현재 선택된 하단 탭 인덱스입니다.
  final int selectedIndex;

  /// 모든 화면에 나눠 전달할 투자 데이터 묶음입니다.
  final InvestmentSnapshot snapshot;

  @override
  Widget build(BuildContext context) {
    return IndexedStack(
      index: selectedIndex,
      children: [
        DashboardScreen(snapshot: snapshot),
        RecommendationScreen(recommendation: snapshot.recommendation),
        PortfolioScreen(
          summary: snapshot.portfolioSummary,
          holdings: snapshot.holdings,
        ),
        AlertsScreen(alerts: snapshot.alerts),
      ],
    );
  }
}
