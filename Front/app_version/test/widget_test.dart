import 'package:app_version/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// 사고팔고 앱의 기본 위젯 스모크 테스트입니다.
///
/// 이 테스트는 세부 디자인 픽셀을 검증하기보다, 앱이 정상 렌더링되고
/// 핵심 사용자 흐름인 탭 이동과 테마 전환이 깨지지 않는지 확인합니다.
void main() {
  testWidgets('SagoPalgo UI renders and navigates', (tester) async {
    /// 앱 루트를 테스트 환경에 올려 실제 Android 앱과 같은 위젯 트리를 만듭니다.
    await tester.pumpWidget(const SagoPalgoApp());

    /// 앱은 로그인 화면에서 시작하므로 Google Mock 로그인 버튼이 보이는지 먼저 확인합니다.
    await tester.pumpAndSettle();
    expect(find.text('Google로 계속하기'), findsOneWidget);

    /// Google 로그인 버튼을 눌러 Mock AuthSession을 만들고 홈 화면으로 진입합니다.
    await tester.tap(find.text('Google로 계속하기'));
    await tester.pumpAndSettle();

    /// 홈 화면에는 앱 브랜드명, 로그인 사용자명, 자본금 카드가 보여야 합니다.
    expect(find.text('사고팔고'), findsAtLeastNWidgets(1));
    expect(find.text('구글사용자 · Google 로그인'), findsOneWidget);
    expect(find.text('3,000,000원'), findsOneWidget);

    /// 하단 네비게이션의 추천 탭을 눌러 추천 상세 화면으로 이동합니다.
    await tester.tap(find.text('추천'));
    await tester.pumpAndSettle();

    /// 추천 상세 화면에는 매수 추천 제목과 강한 매수 상태가 보여야 합니다.
    expect(find.text('매수 추천'), findsOneWidget);
    expect(find.text('강한 매수'), findsOneWidget);

    /// 라이트모드에서 다크모드로 전환되는지 상단 테마 버튼을 눌러 확인합니다.
    await tester.tap(find.byIcon(Icons.dark_mode));
    await tester.pumpAndSettle();

    /// 다크모드가 되면 버튼 아이콘이 다시 라이트모드 전환 아이콘으로 바뀝니다.
    expect(find.byIcon(Icons.light_mode), findsOneWidget);
  });
}
