import 'dart:async';
import 'dart:convert';
import 'package:app_version/config/api_config.dart';
import 'package:app_version/repositories/spring_order_precheck_repository.dart';
import 'package:app_version/screens/unknown_order_review_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  Future<void> mount(
    WidgetTester t,
    ReviewFake r, {
    bool allowNew = true,
  }) async {
    await t.pumpWidget(
      MaterialApp(
        home: UnknownOrderReviewScreen(
          summary: '삼성전자 005930 · 매수 2주',
          load: r.load,
          prepare: r.prepare,
          confirm: r.confirm,
          simulation: true,
          allowNew: allowNew,
        ),
      ),
    );
    await t.pumpAndSettle();
  }

  Future<void> prepare(WidgetTester t) async {
    await t.enterText(find.byType(TextField), '0040000639');
    await t.pump();
    await t.tap(find.text('읽기 전용 대조 준비'));
    await t.pumpAndSettle();
  }

  Future<void> confirm(WidgetTester t) async {
    await t.ensureVisible(find.byType(CheckboxListTile));
    await t.tap(find.byType(CheckboxListTile));
    await t.pump();
    await t.ensureVisible(find.text('대조 관찰 저장'));
    await t.tap(find.text('대조 관찰 저장'));
    await t.pump();
  }

  testWidgets(
    'opening reads history only and confirmation needs checked fresh evidence',
    (t) async {
      final r = ReviewFake();
      await mount(t, r);
      expect(r.prepares, 0);
      expect(r.confirms, 0);
      await prepare(t);
      expect(r.prepares, 1);
      expect(r.confirms, 0);
      expect(find.textContaining('부분체결 관찰'), findsOneWidget);
      expect(
        t
            .widget<FilledButton>(find.widgetWithText(FilledButton, '대조 관찰 저장'))
            .onPressed,
        isNull,
      );
      await confirm(t);
      await t.pumpAndSettle();
      expect(r.confirms, 1);
      expect(find.textContaining('UNKNOWN·전송 차단은 유지'), findsOneWidget);
      expect(find.text('실제 주문 전송'), findsNothing);
      expect(find.text('대조 확정 저장'), findsNothing);
    },
  );
  testWidgets(
    'change evidence shows parent and raw code without claiming completion',
    (t) async {
      final r = ReviewFake()..kind = 'CANCEL';
      await mount(t, r);
      await prepare(t);
      expect(find.textContaining('변경 주문 연결 근거 · 완료 미확정'), findsOneWidget);
      expect(find.textContaining('구분 원문 9'), findsOneWidget);
      expect(find.text('취소 완료'), findsNothing);
      expect(r.confirms, 0);
    },
  );
  testWidgets('missing 021 storage keeps preparing disabled', (t) async {
    final r = ReviewFake()..loadFailure = true;
    await mount(t, r);
    await t.enterText(find.byType(TextField), '0040000639');
    await t.pump();
    expect(
      t
          .widget<FilledButton>(
            find.widgetWithText(FilledButton, '읽기 전용 대조 준비'),
          )
          .onPressed,
      isNull,
    );
    expect(find.textContaining('021'), findsOneWidget);
    expect(r.prepares, 0);
  });
  testWidgets('cancelled preparation never confirms', (t) async {
    final r = ReviewFake();
    await mount(t, r);
    await prepare(t);
    await t.ensureVisible(find.text('준비 취소'));
    await t.tap(find.text('준비 취소'));
    await t.pumpAndSettle();
    expect(r.confirms, 0);
    expect(find.byType(CheckboxListTile), findsNothing);
  });
  testWidgets('in flight confirmation cannot be clicked twice', (t) async {
    final r = ReviewFake()..pending = Completer<void>();
    await mount(t, r);
    await prepare(t);
    await confirm(t);
    expect(r.confirms, 1);
    expect(find.text('대조 관찰 저장'), findsNothing);
    r.pending!.complete();
    await t.pumpAndSettle();
    expect(r.confirms, 1);
    expect(r.records, hasLength(1));
  });
  testWidgets('lost response rechecks GET and never repeats confirmation', (
    t,
  ) async {
    final r = ReviewFake()..loseResponse = true;
    await mount(t, r);
    await prepare(t);
    await confirm(t);
    await t.pumpAndSettle();
    expect(r.confirms, 1);
    expect(r.records, hasLength(1));
    await t.tap(find.byTooltip('대조 관찰 이력 새로고침'));
    await t.pumpAndSettle();
    expect(r.confirms, 1);
    expect(r.gets, 3);
  });
  testWidgets(
    'changed observation failure retains blocked confirmation and asks for fresh prepare',
    (t) async {
      final r = ReviewFake()..changed = true;
      await mount(t, r);
      await prepare(t);
      await confirm(t);
      await t.pumpAndSettle();
      expect(r.records, isEmpty);
      expect(r.confirms, 1);
      expect(find.textContaining('관찰이 변경'), findsOneWidget);
      expect(
        t
            .widget<FilledButton>(
              find.widgetWithText(FilledButton, '읽기 전용 대조 준비'),
            )
            .onPressed,
        isNull,
      );
    },
  );
  testWidgets('history-only view never provides prepare or confirm', (t) async {
    final r = ReviewFake()..records = [review()];
    await mount(t, r, allowNew: false);
    expect(find.byType(TextField), findsNothing);
    expect(find.text('대조 관찰 저장'), findsNothing);
    expect(r.prepares, 0);
    expect(r.confirms, 0);
    expect(find.textContaining('전송 차단 유지'), findsOneWidget);
  });
  testWidgets('review evidence fits a narrow window with enlarged text', (
    t,
  ) async {
    await t.binding.setSurfaceSize(const Size(360, 720));
    addTearDown(() => t.binding.setSurfaceSize(null));
    final r = ReviewFake()..records = [review()];
    await t.pumpWidget(
      MaterialApp(
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(textScaler: const TextScaler.linear(1.4)),
          child: child!,
        ),
        home: UnknownOrderReviewScreen(
          summary: '삼성전자 005930 · 매수 2주',
          load: r.load,
          prepare: r.prepare,
          confirm: r.confirm,
        ),
      ),
    );
    await t.pumpAndSettle();
    expect(t.takeException(), isNull);
    await t.drag(find.byType(ListView), const Offset(0, -500));
    await t.pumpAndSettle();
    expect(t.takeException(), isNull);
  });
  test(
    'HTTP review uses distinct confirmation and GET history after failure without automatic retry',
    () async {
      final calls = <String>[];
      final r = SpringOrderPrecheckRepository(
        accessToken: '',
        config: ApiConfig(baseUrl: 'http://localhost:8080'),
        client: MockClient((request) async {
          calls.add('${request.method} ${request.url.path}');
          if (request.url.path.endsWith('/prepare')) {
            expect(jsonDecode(request.body), {'orderNo': '0040000639'});
            return http.Response(
              jsonEncode({
                'success': true,
                'data': {'reviewId': 'review', 'token': 'token'},
              }),
              200,
            );
          }
          if (request.method == 'POST') {
            expect(jsonDecode(request.body), {
              'reviewId': 'review',
              'token': 'token',
              'acknowledged': true,
              'confirmation': '잠금 유지 대조 저장',
            });
            return http.Response(
              jsonEncode({
                'success': false,
                'error': {'message': 'review failure'},
              }),
              503,
            );
          }
          return http.Response(jsonEncode({'success': true, 'data': []}), 200);
        }),
      );
      await r.prepareUnknownReview('id', '0040000639');
      await expectLater(
        r.confirmUnknownReview('id', 'review', 'token'),
        throwsException,
      );
      await r.unknownReviewHistory('id');
      expect(calls, [
        'POST /api/v1/orders/manual/id/reviews/prepare',
        'POST /api/v1/orders/manual/id/reviews/confirm',
        'GET /api/v1/orders/manual/id/reviews',
      ]);
    },
  );
}

Map<String, dynamic> evidence() => {
  'kind': 'NEW',
  'observation': 'PARTIAL',
  'stockCode': '005930',
  'side': 'BUY',
  'price': 75000,
  'quantity': 2,
  'filledQuantity': 1,
  'openQuantity': 1,
  'orderDate': '20261101',
  'orderNo': '0040000639',
  'orderTime': '090001',
  'originalOrderNo': '',
  'changeCode': '',
  'correctedQuantity': 0,
  'sorCancelledQuantity': 0,
};
Map<String, dynamic> review() => {
  'reviewId': 'review-id',
  'evidence': evidence(),
  'confirmedAt': '2026-11-01T09:00:02',
  'lockMaintained': true,
};

class ReviewFake {
  String kind = 'NEW';
  bool loadFailure = false;
  int gets = 0, prepares = 0, confirms = 0;
  bool loseResponse = false, changed = false;
  Completer<void>? pending;
  List<Map<String, dynamic>> records = [];
  Future<List<Map<String, dynamic>>> load() async {
    gets++;
    if (loadFailure) throw Exception('021 저장소 확인');
    return records;
  }

  Future<Map<String, dynamic>> prepare(String number) async {
    prepares++;
    expect(number, '0040000639');
    return {
      'reviewId': 'review-id',
      'token': 'one-use-token',
      'expiresAt': '2026-11-01T09:01:30',
      'evidence': {
        ...evidence(),
        if (kind != 'NEW') 'kind': kind,
        if (kind != 'NEW') 'observation': 'CHANGE_REFERENCE',
        if (kind != 'NEW') 'originalOrderNo': '0040000638',
        if (kind != 'NEW') 'changeCode': '9',
      },
    };
  }

  Future<void> confirm(String id, String token) async {
    confirms++;
    expect(id, 'review-id');
    expect(token, 'one-use-token');
    if (pending != null) await pending!.future;
    if (changed) throw Exception('관찰이 변경되었습니다. 다시 준비하세요.');
    records = [review()];
    if (loseResponse) throw TimeoutException('test lost response');
  }
}
