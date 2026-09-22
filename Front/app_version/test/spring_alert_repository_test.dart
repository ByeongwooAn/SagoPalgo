import 'dart:convert';

import 'package:app_version/config/api_config.dart';
import 'package:app_version/models/app_alert.dart';
import 'package:app_version/repositories/spring_alert_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('fetchPending maps Windows delivery queue', () async {
    final repository = SpringAlertRepository(
      accessToken: 'token',
      config: ApiConfig(baseUrl: 'http://ubuntu-server:8081'),
      client: MockClient((request) async {
        expect(
          request.url.toString(),
          'http://ubuntu-server:8081/api/v1/alerts/pending?limit=20',
        );
        expect(request.headers['Authorization'], 'Bearer token');
        return http.Response(
          jsonEncode({
            'success': true,
            'data': [
              {
                'alertId': 7,
                'recommendationId': 99,
                'type': 'RISK',
                'title': '삼성전자 위험 신호',
                'body': '손절 기준에 도달했습니다.',
                'read': false,
                'createdAt': '2026-09-22T09:00:00',
                'timeLabel': '방금 전',
              },
            ],
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    final alerts = await repository.fetchPending();

    expect(alerts.single.alertId, 7);
    expect(alerts.single.recommendationId, 99);
    expect(alerts.single.type, AppAlertType.sell);
    expect(alerts.single.isRead, isFalse);
  });

  test('markSent records successful Windows notification delivery', () async {
    final repository = SpringAlertRepository(
      accessToken: '',
      config: ApiConfig(baseUrl: 'http://ubuntu-server:8081'),
      client: MockClient((request) async {
        expect(request.method, 'PATCH');
        expect(
          request.url.toString(),
          'http://ubuntu-server:8081/api/v1/alerts/7/sent',
        );
        return http.Response(jsonEncode({'success': true, 'data': {}}), 200);
      }),
    );

    await repository.markSent(7);
  });
}
