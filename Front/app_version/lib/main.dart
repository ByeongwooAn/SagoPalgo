import 'dart:math' as math;

import 'package:flutter/material.dart';

void main() {
  runApp(const SagoPalgoApp());
}

class SagoPalgoApp extends StatefulWidget {
  const SagoPalgoApp({super.key});

  @override
  State<SagoPalgoApp> createState() => _SagoPalgoAppState();
}

class _SagoPalgoAppState extends State<SagoPalgoApp> {
  ThemeMode _themeMode = ThemeMode.system;

  void _toggleTheme(Brightness brightness) {
    setState(() {
      _themeMode = brightness == Brightness.dark
          ? ThemeMode.light
          : ThemeMode.dark;
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: '사고팔고',
      themeMode: _themeMode,
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      home: SagoPalgoHome(onThemeToggle: _toggleTheme),
    );
  }
}

class AppTheme {
  static const main = Color(0xff8d17c6);
  static const sub = Color(0xffd44b76);
  static const point = Color(0xfff3a411);

  static ThemeData get light {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorScheme: ColorScheme.fromSeed(
        seedColor: main,
        brightness: Brightness.light,
        primary: main,
        secondary: sub,
        tertiary: point,
      ),
      scaffoldBackgroundColor: const Color(0xfffbfafc),
      fontFamily: 'Roboto',
    );
  }

  static ThemeData get dark {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: ColorScheme.fromSeed(
        seedColor: main,
        brightness: Brightness.dark,
        primary: main,
        secondary: sub,
        tertiary: point,
      ),
      scaffoldBackgroundColor: const Color(0xff111018),
      fontFamily: 'Roboto',
    );
  }
}

class SagoPalgoHome extends StatefulWidget {
  const SagoPalgoHome({super.key, required this.onThemeToggle});

  final ValueChanged<Brightness> onThemeToggle;

  @override
  State<SagoPalgoHome> createState() => _SagoPalgoHomeState();
}

class _SagoPalgoHomeState extends State<SagoPalgoHome> {
  int _selectedIndex = 0;

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
              _TopBar(
                isDark: isDark,
                onThemeToggle: () =>
                    widget.onThemeToggle(Theme.of(context).brightness),
              ),
              Expanded(
                child: IndexedStack(
                  index: _selectedIndex,
                  children: const [
                    DashboardView(),
                    RecommendationView(),
                    PortfolioView(),
                    AlertsView(),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
      bottomNavigationBar: _BottomNav(
        selectedIndex: _selectedIndex,
        onSelected: (index) => setState(() => _selectedIndex = index),
      ),
    );
  }
}

class AppPalette {
  AppPalette({
    required this.isDark,
    required this.background,
    required this.surface,
    required this.softSurface,
    required this.text,
    required this.muted,
    required this.border,
    required this.pageGradient,
  });

  final bool isDark;
  final Color background;
  final Color surface;
  final Color softSurface;
  final Color text;
  final Color muted;
  final Color border;
  final LinearGradient pageGradient;

  static AppPalette of(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    if (isDark) {
      return AppPalette(
        isDark: true,
        background: const Color(0xff111018),
        surface: const Color(0xff1d1926),
        softSurface: const Color(0xff272130),
        text: const Color(0xfff8f5fb),
        muted: const Color(0xffb8aec4),
        border: Colors.white.withValues(alpha: .12),
        pageGradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xff15101b), Color(0xff211326), Color(0xff151015)],
        ),
      );
    }

    return AppPalette(
      isDark: false,
      background: const Color(0xfffbfafc),
      surface: Colors.white,
      softSurface: const Color(0xfff4eef8),
      text: const Color(0xff221729),
      muted: const Color(0xff6b5c72),
      border: const Color(0x1f32193c),
      pageGradient: const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [Color(0xfffff8fb), Color(0xfffaf7ff), Color(0xfffffdf5)],
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({required this.isDark, required this.onThemeToggle});

  final bool isDark;
  final VoidCallback onThemeToggle;

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
                  isDark ? 'AI 트레이딩 콘솔' : '친절한 투자 어시스턴트',
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
        ],
      ),
    );
  }
}

class DashboardView extends StatelessWidget {
  const DashboardView({super.key});

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final isDark = palette.isDark;

    return AppScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionHeader(
            eyebrow: '사고팔고',
            title: isDark ? 'AI 시장 관제' : '오늘의 투자 브리핑',
            action: StatusChip(
              label: 'AI 분석중',
              icon: Icons.auto_awesome_rounded,
              gradient: AppGradients.main,
            ),
          ),
          const SizedBox(height: 18),
          const CapitalCard(),
          const SizedBox(height: 12),
          const Row(
            children: [
              Expanded(
                child: MetricCard(
                  label: '코스피 흐름',
                  value: '강세',
                  caption: '시장 점수 76',
                  color: AppTheme.point,
                ),
              ),
              SizedBox(width: 12),
              Expanded(
                child: MetricCard(
                  label: '뉴스 감성',
                  value: '긍정',
                  caption: '호재 12건',
                  color: AppTheme.sub,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          const CandidateCard(),
          const SizedBox(height: 12),
          const MarketBarsCard(),
          const SizedBox(height: 20),
        ],
      ),
    );
  }
}

class RecommendationView extends StatelessWidget {
  const RecommendationView({super.key});

  @override
  Widget build(BuildContext context) {
    return AppScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionHeader(
            eyebrow: '매수 추천',
            title: '삼성전자',
            action: StatusChip(
              label: '강한 매수',
              icon: Icons.bolt_rounded,
              gradient: AppGradients.point,
              darkText: true,
            ),
          ),
          const SizedBox(height: 18),
          const ScoreDetailCard(),
          const SizedBox(height: 12),
          AppCard(
            soft: true,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: const [
                CardTitle('추천 사유'),
                SizedBox(height: 8),
                ReasonRow(
                  label: 'RSI',
                  text: '과매도 구간에서 반등 신호가 확인되었습니다.',
                  color: AppTheme.main,
                ),
                ReasonRow(
                  label: 'MACD',
                  text: '골든크로스 초기 구간으로 추세 전환 가능성이 있습니다.',
                  color: AppTheme.sub,
                ),
                ReasonRow(
                  label: '뉴스',
                  text: 'AI 반도체 수주 관련 긍정 감성이 증가했습니다.',
                  color: AppTheme.point,
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          AppCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: const [
                CardTitle('AI 설명'),
                SizedBox(height: 8),
                TextBody(
                  '시장 강세와 거래량 증가가 동시에 나타나 단기 관심 종목으로 분류됩니다. 전체 자산의 1~2% 손실 제한을 유지하세요.',
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          const Row(
            children: [
              Expanded(
                child: GradientActionButton(
                  label: '관심 등록',
                  icon: Icons.star_rounded,
                  gradient: AppGradients.main,
                ),
              ),
              SizedBox(width: 10),
              Expanded(
                child: GradientActionButton(
                  label: '알림 켜기',
                  icon: Icons.notifications_active_rounded,
                  gradient: AppGradients.point,
                  darkText: true,
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
        ],
      ),
    );
  }
}

class PortfolioView extends StatelessWidget {
  const PortfolioView({super.key});

  @override
  Widget build(BuildContext context) {
    return AppScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: const [
          SectionHeader(
            eyebrow: '보유 종목',
            title: '손익과 리스크',
            action: StatusChip(
              label: '3종목',
              icon: Icons.account_balance_wallet_rounded,
            ),
          ),
          SizedBox(height: 18),
          ProfitCard(),
          SizedBox(height: 12),
          PortfolioRow(
            name: '삼성전자',
            detail: '매수가 69,100 · 12주',
            change: '+9.0%',
            status: '부분 익절',
            color: AppTheme.point,
          ),
          SizedBox(height: 10),
          PortfolioRow(
            name: 'NAVER',
            detail: '매수가 181,000 · 4주',
            change: '+2.1%',
            status: '보유',
            color: AppTheme.main,
          ),
          SizedBox(height: 10),
          PortfolioRow(
            name: '현대차',
            detail: '매수가 224,000 · 2주',
            change: '-3.6%',
            status: '손절 감시',
            color: AppTheme.sub,
          ),
          SizedBox(height: 12),
          SellAlertCard(),
          SizedBox(height: 12),
          RiskRuleCard(),
          SizedBox(height: 20),
        ],
      ),
    );
  }
}

class AlertsView extends StatelessWidget {
  const AlertsView({super.key});

  @override
  Widget build(BuildContext context) {
    return AppScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: const [
          SectionHeader(
            eyebrow: '실시간 알림',
            title: '추천 신호',
            action: StatusChip(
              label: 'FCM',
              icon: Icons.notifications_rounded,
              gradient: AppGradients.main,
            ),
          ),
          SizedBox(height: 18),
          AlertItem(
            title: '삼성전자 매도 검토',
            body: '현재 수익률 +9%. 목표 수익 도달로 부분 익절을 추천합니다.',
            time: '방금 전',
            icon: Icons.sell_rounded,
            color: AppTheme.sub,
          ),
          SizedBox(height: 10),
          AlertItem(
            title: '관심 종목 신규 후보',
            body: 'RSI 과매도 탈출과 거래량 2.1배 증가가 동시에 감지되었습니다.',
            time: '3분 전',
            icon: Icons.add_chart_rounded,
            color: AppTheme.point,
          ),
          SizedBox(height: 10),
          AlertItem(
            title: '시장 흐름 업데이트',
            body: '코스피와 나스닥 지표가 모두 강세 구간으로 전환되었습니다.',
            time: '5분 전',
            icon: Icons.public_rounded,
            color: AppTheme.main,
          ),
          SizedBox(height: 20),
        ],
      ),
    );
  }
}

class AppScrollView extends StatelessWidget {
  const AppScrollView({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 10, 20, 20),
      physics: const BouncingScrollPhysics(),
      child: child,
    );
  }
}

class SectionHeader extends StatelessWidget {
  const SectionHeader({
    super.key,
    required this.eyebrow,
    required this.title,
    required this.action,
  });

  final String eyebrow;
  final String title;
  final Widget action;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Row(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                eyebrow,
                style: TextStyle(
                  color: palette.muted,
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                title,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: palette.text,
                  fontSize: 27,
                  height: 1.08,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(width: 12),
        action,
      ],
    );
  }
}

class CapitalCard extends StatelessWidget {
  const CapitalCard({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(8),
        gradient: AppGradients.main,
        boxShadow: [
          BoxShadow(
            color: AppTheme.main.withValues(alpha: .18),
            blurRadius: 24,
            offset: const Offset(0, 16),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text(
                  '투자 가능 자본금',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0,
                  ),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: .18),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: const Text(
                  '월간 +3.8%',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 12,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          const FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              '3,000,000원',
              style: TextStyle(
                color: Colors.white,
                fontSize: 34,
                fontWeight: FontWeight.w900,
                letterSpacing: 0,
              ),
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            '종목당 권장 투자금 30~60만원',
            style: TextStyle(
              color: Colors.white,
              fontSize: 13,
              fontWeight: FontWeight.w800,
              letterSpacing: 0,
            ),
          ),
        ],
      ),
    );
  }
}

class MetricCard extends StatelessWidget {
  const MetricCard({
    super.key,
    required this.label,
    required this.value,
    required this.caption,
    required this.color,
  });

  final String label;
  final String value;
  final String caption;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return AppCard(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LabelText(label),
          const SizedBox(height: 8),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 24,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 3),
          Text(
            caption,
            style: TextStyle(
              color: palette.text,
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

class CandidateCard extends StatelessWidget {
  const CandidateCard({super.key});

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    LabelText('실시간 후보'),
                    SizedBox(height: 8),
                    CardTitle('삼성전자', fontSize: 24),
                  ],
                ),
              ),
              ScoreRing(score: 87, size: 108),
            ],
          ),
          const SizedBox(height: 16),
          ScoreProgress(value: .87),
          const SizedBox(height: 10),
          Text(
            'RSI 과매도 탈출 + 거래량 2.1배 + 긍정 뉴스 증가',
            style: TextStyle(
              color: palette.text,
              fontSize: 13,
              fontWeight: FontWeight.w800,
              letterSpacing: 0,
            ),
          ),
        ],
      ),
    );
  }
}

class MarketBarsCard extends StatelessWidget {
  const MarketBarsCard({super.key});

  @override
  Widget build(BuildContext context) {
    return AppCard(
      soft: true,
      child: Column(
        children: [
          const Row(
            children: [
              Expanded(child: LabelText('시장 지표')),
              TextCaption('1분 전 업데이트'),
            ],
          ),
          const SizedBox(height: 18),
          SizedBox(
            height: 112,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: const [
                MarketBar(height: .42, color: AppTheme.main),
                MarketBar(height: .68, color: AppTheme.sub),
                MarketBar(height: .54, color: AppTheme.point),
                MarketBar(height: .82, color: AppTheme.main),
                MarketBar(height: .61, color: AppTheme.sub),
                MarketBar(height: .94, color: AppTheme.point),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class MarketBar extends StatelessWidget {
  const MarketBar({super.key, required this.height, required this.color});

  final double height;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Align(
        alignment: Alignment.bottomCenter,
        child: FractionallySizedBox(
          heightFactor: height,
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 5),
            decoration: BoxDecoration(
              color: color,
              borderRadius: const BorderRadius.vertical(
                top: Radius.circular(8),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class ScoreDetailCard extends StatelessWidget {
  const ScoreDetailCard({super.key});

  @override
  Widget build(BuildContext context) {
    return AppCard(
      child: Column(
        children: [
          Row(
            children: [
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    LabelText('AI 확률 점수'),
                    SizedBox(height: 8),
                    Text(
                      '87점',
                      style: TextStyle(
                        color: AppTheme.point,
                        fontSize: 33,
                        fontWeight: FontWeight.w900,
                        letterSpacing: 0,
                      ),
                    ),
                  ],
                ),
              ),
              ScoreRing(score: 87, size: 110),
            ],
          ),
          const AppDivider(),
          const Row(
            children: [
              Expanded(
                child: DetailMetric(label: '진입 가격대', value: '72,000원'),
              ),
              SizedBox(width: 16),
              Expanded(
                child: DetailMetric(
                  label: '손절 기준',
                  value: '-5%',
                  color: AppTheme.sub,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class DetailMetric extends StatelessWidget {
  const DetailMetric({
    super.key,
    required this.label,
    required this.value,
    this.color,
  });

  final String label;
  final String value;
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

class ProfitCard extends StatelessWidget {
  const ProfitCard({super.key});

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Expanded(child: LabelText('총 평가 손익')),
              StatusChip(label: '목표 5%', darkText: true),
            ],
          ),
          const SizedBox(height: 12),
          const FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              '+128,400원',
              style: TextStyle(
                color: AppTheme.point,
                fontSize: 34,
                fontWeight: FontWeight.w900,
                letterSpacing: 0,
              ),
            ),
          ),
          const SizedBox(height: 6),
          Text(
            '수익률 +4.2% · 최대 허용 손실 60,000원',
            style: TextStyle(
              color: palette.text,
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

class PortfolioRow extends StatelessWidget {
  const PortfolioRow({
    super.key,
    required this.name,
    required this.detail,
    required this.change,
    required this.status,
    required this.color,
  });

  final String name;
  final String detail;
  final String change;
  final String status;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return AppCard(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  style: TextStyle(
                    color: palette.text,
                    fontSize: 18,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 4),
                TextCaption(detail),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                change,
                style: TextStyle(
                  color: color,
                  fontSize: 16,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0,
                ),
              ),
              const SizedBox(height: 4),
              TextCaption(status),
            ],
          ),
        ],
      ),
    );
  }
}

class SellAlertCard extends StatelessWidget {
  const SellAlertCard({super.key});

  @override
  Widget build(BuildContext context) {
    return AppCard(
      soft: true,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                LabelText('실시간 알림'),
                SizedBox(height: 6),
                CardTitle('매도 검토', fontSize: 24),
                SizedBox(height: 8),
                TextBody('삼성전자 현재 수익률 +9%. 목표 수익 도달로 부분 익절을 추천합니다.'),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: AppTheme.sub,
              borderRadius: BorderRadius.circular(999),
            ),
            child: const Text(
              'FCM',
              style: TextStyle(
                color: Colors.white,
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

class RiskRuleCard extends StatelessWidget {
  const RiskRuleCard({super.key});

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const LabelText('리스크 규칙'),
          const SizedBox(height: 12),
          ScoreProgress(
            value: .42,
            colors: const [AppTheme.sub, AppTheme.point],
          ),
          const SizedBox(height: 8),
          Text(
            '오늘 사용한 위험 한도 42%',
            style: TextStyle(
              color: palette.text,
              fontSize: 13,
              fontWeight: FontWeight.w800,
              letterSpacing: 0,
            ),
          ),
        ],
      ),
    );
  }
}

class AlertItem extends StatelessWidget {
  const AlertItem({
    super.key,
    required this.title,
    required this.body,
    required this.time,
    required this.icon,
    required this.color,
  });

  final String title;
  final String body;
  final String time;
  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return AppCard(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: color.withValues(alpha: .14),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(icon, color: color),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(child: CardTitle(title, fontSize: 17)),
                    TextCaption(time),
                  ],
                ),
                const SizedBox(height: 6),
                Text(
                  body,
                  style: TextStyle(
                    color: palette.text,
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    height: 1.35,
                    letterSpacing: 0,
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

class AppCard extends StatelessWidget {
  const AppCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.soft = false,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final bool soft;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Container(
      width: double.infinity,
      padding: padding,
      decoration: BoxDecoration(
        color: soft ? palette.softSurface : palette.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: palette.border),
      ),
      child: child,
    );
  }
}

class StatusChip extends StatelessWidget {
  const StatusChip({
    super.key,
    required this.label,
    this.icon,
    this.gradient,
    this.darkText = false,
  });

  final String label;
  final IconData? icon;
  final Gradient? gradient;
  final bool darkText;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final foreground = gradient == null
        ? palette.text
        : darkText
        ? const Color(0xff21120a)
        : Colors.white;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 8),
      decoration: BoxDecoration(
        color: gradient == null
            ? (palette.isDark
                  ? Colors.white.withValues(alpha: .08)
                  : AppTheme.point.withValues(alpha: .14))
            : null,
        gradient: gradient,
        borderRadius: BorderRadius.circular(999),
        border: gradient == null ? Border.all(color: palette.border) : null,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 14, color: foreground),
            const SizedBox(width: 5),
          ],
          Text(
            label,
            style: TextStyle(
              color: foreground,
              fontSize: 12,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
        ],
      ),
    );
  }
}

class ScoreRing extends StatelessWidget {
  const ScoreRing({super.key, required this.score, required this.size});

  final int score;
  final double size;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        painter: ScoreRingPainter(
          score: score,
          trackColor: palette.isDark
              ? const Color(0xff332a3c)
              : const Color(0xffeee7f3),
        ),
        child: Center(
          child: Text(
            '$score',
            style: TextStyle(
              color: palette.text,
              fontSize: size * .29,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
        ),
      ),
    );
  }
}

class ScoreRingPainter extends CustomPainter {
  ScoreRingPainter({required this.score, required this.trackColor});

  final int score;
  final Color trackColor;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 8;
    final stroke = size.width * .16;
    final rect = Rect.fromCircle(center: center, radius: radius);
    final trackPaint = Paint()
      ..color = trackColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke
      ..strokeCap = StrokeCap.butt;
    final scorePaint = Paint()
      ..shader = const SweepGradient(
        colors: [AppTheme.point, AppTheme.sub, AppTheme.point],
      ).createShader(rect)
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke
      ..strokeCap = StrokeCap.butt;

    canvas.drawCircle(center, radius, trackPaint);
    canvas.drawArc(
      rect,
      -math.pi / 2,
      math.pi * 2 * (score / 100),
      false,
      scorePaint,
    );
  }

  @override
  bool shouldRepaint(covariant ScoreRingPainter oldDelegate) {
    return score != oldDelegate.score || trackColor != oldDelegate.trackColor;
  }
}

class ScoreProgress extends StatelessWidget {
  const ScoreProgress({
    super.key,
    required this.value,
    this.colors = const [AppTheme.main, AppTheme.point],
  });

  final double value;
  final List<Color> colors;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return ClipRRect(
      borderRadius: BorderRadius.circular(999),
      child: Container(
        height: 9,
        color: palette.isDark
            ? Colors.white.withValues(alpha: .09)
            : Colors.black.withValues(alpha: .08),
        child: FractionallySizedBox(
          alignment: Alignment.centerLeft,
          widthFactor: value,
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(colors: colors),
              borderRadius: BorderRadius.circular(999),
            ),
          ),
        ),
      ),
    );
  }
}

class ReasonRow extends StatelessWidget {
  const ReasonRow({
    super.key,
    required this.label,
    required this.text,
    required this.color,
  });

  final String label;
  final String text;
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

class GradientActionButton extends StatelessWidget {
  const GradientActionButton({
    super.key,
    required this.label,
    required this.icon,
    required this.gradient,
    this.darkText = false,
  });

  final String label;
  final IconData icon;
  final Gradient gradient;
  final bool darkText;

  @override
  Widget build(BuildContext context) {
    final foreground = darkText ? const Color(0xff21120a) : Colors.white;

    return Container(
      height: 48,
      decoration: BoxDecoration(
        gradient: gradient,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, color: foreground, size: 18),
          const SizedBox(width: 7),
          Flexible(
            child: Text(
              label,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: foreground,
                fontSize: 15,
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

class _BottomNav extends StatelessWidget {
  const _BottomNav({required this.selectedIndex, required this.onSelected});

  final int selectedIndex;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return SafeArea(
      top: false,
      child: Container(
        margin: const EdgeInsets.fromLTRB(18, 0, 18, 12),
        padding: const EdgeInsets.all(7),
        decoration: BoxDecoration(
          color: palette.isDark
              ? const Color(0xff16121e).withValues(alpha: .94)
              : Colors.white.withValues(alpha: .94),
          borderRadius: BorderRadius.circular(22),
          border: Border.all(color: palette.border),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: palette.isDark ? .28 : .1),
              blurRadius: 24,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: Row(
          children: [
            _NavItem(
              label: '홈',
              icon: Icons.home_rounded,
              active: selectedIndex == 0,
              onTap: () => onSelected(0),
            ),
            _NavItem(
              label: '추천',
              icon: Icons.auto_graph_rounded,
              active: selectedIndex == 1,
              onTap: () => onSelected(1),
            ),
            _NavItem(
              label: '보유',
              icon: Icons.pie_chart_rounded,
              active: selectedIndex == 2,
              onTap: () => onSelected(2),
            ),
            _NavItem(
              label: '알림',
              icon: Icons.notifications_rounded,
              active: selectedIndex == 3,
              onTap: () => onSelected(3),
            ),
          ],
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  const _NavItem({
    required this.label,
    required this.icon,
    required this.active,
    required this.onTap,
  });

  final String label;
  final IconData icon;
  final bool active;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Expanded(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          height: 44,
          decoration: BoxDecoration(
            color: active ? AppTheme.main : Colors.transparent,
            borderRadius: BorderRadius.circular(16),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 18, color: active ? Colors.white : palette.text),
              const SizedBox(height: 2),
              Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: active ? Colors.white : palette.text,
                  fontSize: 10,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class LabelText extends StatelessWidget {
  const LabelText(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Text(
      text,
      style: TextStyle(
        color: palette.muted,
        fontSize: 12,
        fontWeight: FontWeight.w800,
        letterSpacing: 0,
      ),
    );
  }
}

class TextCaption extends StatelessWidget {
  const TextCaption(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Text(
      text,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: TextStyle(
        color: palette.muted,
        fontSize: 12,
        fontWeight: FontWeight.w700,
        letterSpacing: 0,
      ),
    );
  }
}

class TextBody extends StatelessWidget {
  const TextBody(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Text(
      text,
      style: TextStyle(
        color: palette.text,
        fontSize: 13,
        height: 1.36,
        fontWeight: FontWeight.w700,
        letterSpacing: 0,
      ),
    );
  }
}

class CardTitle extends StatelessWidget {
  const CardTitle(this.text, {super.key, this.fontSize = 18});

  final String text;
  final double fontSize;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Text(
      text,
      maxLines: 2,
      overflow: TextOverflow.ellipsis,
      style: TextStyle(
        color: palette.text,
        fontSize: fontSize,
        height: 1.12,
        fontWeight: FontWeight.w900,
        letterSpacing: 0,
      ),
    );
  }
}

class AppDivider extends StatelessWidget {
  const AppDivider({super.key});

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Container(
      height: 1,
      margin: const EdgeInsets.symmetric(vertical: 16),
      color: palette.border,
    );
  }
}

class AppGradients {
  static const main = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [AppTheme.main, AppTheme.sub],
  );

  static const point = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [AppTheme.point, AppTheme.sub],
  );
}

@Deprecated('Use SagoPalgoApp instead.')
typedef MyApp = SagoPalgoApp;
