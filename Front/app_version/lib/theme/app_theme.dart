import 'package:flutter/material.dart';

/// 사고팔고 앱 전체에서 사용하는 Material 테마 정의입니다.
///
/// 기획서의 3개 브랜드 색상(`#8d17c6`, `#d44b76`, `#f3a411`)을
/// Material `ColorScheme`에 넣어 버튼, 칩, 아이콘의 기본 색이
/// 앱 전체에서 일관되게 유지되도록 합니다.
class AppTheme {
  /// 기획서에 명시된 메인 컬러입니다.
  static const main = Color(0xff8d17c6);

  /// 기획서에 명시된 서브 컬러입니다.
  static const sub = Color(0xffd44b76);

  /// 기획서에 명시된 포인트 컬러입니다.
  static const point = Color(0xfff3a411);

  /// B 시안 기반 라이트모드 테마입니다.
  ///
  /// 배경은 밝고 부드럽게 두고, 주요 액션은 브랜드 컬러가
  /// 선명하게 보이도록 Material3 색상 체계를 구성합니다.
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

  /// A 시안 기반 다크모드 테마입니다.
  ///
  /// 투자 콘솔 느낌을 살리기 위해 어두운 배경과 고채도 포인트를
  /// 조합하고, 화면별 카드 색상은 `AppPalette`에서 추가로 제어합니다.
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

/// Material 테마만으로 표현하기 어려운 앱 전용 색상 묶음입니다.
///
/// `ThemeData`는 버튼이나 기본 컴포넌트에 좋고, `AppPalette`는
/// 카드 배경, 은은한 표면색, 페이지 그라데이션처럼 사고팔고 UI만의
/// 세부 표현을 한곳에서 관리하기 위해 사용합니다.
class AppPalette {
  /// 화면이 필요로 하는 색상 토큰을 모두 명시적으로 주입합니다.
  const AppPalette({
    required this.isDark,
    required this.background,
    required this.surface,
    required this.softSurface,
    required this.text,
    required this.muted,
    required this.border,
    required this.pageGradient,
  });

  /// 현재 팔레트가 다크모드인지 알려주는 플래그입니다.
  final bool isDark;

  /// 화면의 기본 배경색입니다.
  final Color background;

  /// 일반 카드에 사용하는 표면색입니다.
  final Color surface;

  /// 추천 사유, 알림처럼 살짝 강조된 카드에 사용하는 표면색입니다.
  final Color softSurface;

  /// 제목과 주요 수치에 사용하는 텍스트 색상입니다.
  final Color text;

  /// 라벨과 보조 설명에 사용하는 낮은 강조 텍스트 색상입니다.
  final Color muted;

  /// 카드와 구분선에 쓰는 얇은 테두리 색상입니다.
  final Color border;

  /// 전체 페이지 배경에 깔리는 그라데이션입니다.
  final LinearGradient pageGradient;

  /// 현재 `BuildContext`의 밝기 값으로 다크/라이트 팔레트를 선택합니다.
  ///
  /// 화면과 위젯은 이 메서드를 통해 색상을 가져오므로, 테마 전환 시
  /// 모든 카드와 텍스트가 같은 규칙으로 자연스럽게 바뀝니다.
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

/// 사고팔고 UI에서 반복적으로 쓰는 브랜드 그라데이션입니다.
///
/// 버튼과 상태 칩이 같은 색상 방향을 공유하도록 별도 클래스로 분리했습니다.
class AppGradients {
  /// 메인 컬러에서 서브 컬러로 이어지는 기본 액션 그라데이션입니다.
  static const main = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [AppTheme.main, AppTheme.sub],
  );

  /// 포인트 컬러에서 서브 컬러로 이어지는 강한 추천/알림 그라데이션입니다.
  static const point = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [AppTheme.point, AppTheme.sub],
  );
}
