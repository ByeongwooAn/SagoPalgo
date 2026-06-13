import 'package:app_version/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('SagoPalgo UI renders and navigates', (tester) async {
    await tester.pumpWidget(const SagoPalgoApp());

    expect(find.text('사고팔고'), findsAtLeastNWidgets(1));
    expect(find.text('3,000,000원'), findsOneWidget);

    await tester.tap(find.text('추천'));
    await tester.pumpAndSettle();

    expect(find.text('매수 추천'), findsOneWidget);
    expect(find.text('강한 매수'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.dark_mode));
    await tester.pumpAndSettle();

    expect(find.byIcon(Icons.light_mode), findsOneWidget);
  });
}
