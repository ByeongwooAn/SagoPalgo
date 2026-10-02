import 'dart:convert';

import 'package:app_version/config/api_config.dart';
import 'package:app_version/repositories/provider_settings_repository.dart';
import 'package:app_version/repositories/spring_provider_settings_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('fetchProviderSettings maps provider settings response', () async {
    final repository = SpringProviderSettingsRepository(
      accessToken: '',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        expect(
          request.url.toString(),
          'http://localhost:8080/api/v1/settings/providers',
        );
        expect(request.headers.containsKey('Authorization'), isFalse);

        return http.Response(
          jsonEncode({
            'success': true,
            'data': {
              'secretStorageType': 'ENV_FILE',
              'secretStorageDescription': '.env 파일로 민감정보를 관리합니다.',
              'orderSafetyMode': '주문 기능 OFF · 사전검증만 지원',
              'marketDataFallbackOrder': ['KB', 'KIS', 'TOSS'],
              'marketDataFallbackDescription':
                  '앞 Provider가 실패하면 다음 Provider를 시도합니다.',
              'providers': [
                {
                  'code': 'KB',
                  'displayName': 'KB증권',
                  'marketDataEnabled': false,
                  'accountEnabled': true,
                  'orderEnabled': false,
                  'newsEnabled': false,
                  'disclosureEnabled': false,
                  'configured': true,
                  'missingRequiredSettings': <String>[],
                  'roleDescription': '계좌 조회와 추후 주문 기능의 기준 증권사',
                },
                {
                  'code': 'KIS',
                  'displayName': '한국투자증권',
                  'marketDataEnabled': true,
                  'accountEnabled': false,
                  'orderEnabled': false,
                  'newsEnabled': false,
                  'disclosureEnabled': false,
                  'configured': false,
                  'missingRequiredSettings': ['App Key', 'App Secret'],
                  'roleDescription': '국내 주식 시세 조회용 데이터 소스',
                },
              ],
            },
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    );

    final settings = await repository.fetchProviderSettings();

    expect(settings.secretStorageType, 'ENV_FILE');
    expect(settings.orderSafetyMode, '주문 기능 OFF · 사전검증만 지원');
    expect(settings.marketDataFallbackOrder, ['KB', 'KIS', 'TOSS']);
    expect(settings.providers, hasLength(2));
    expect(settings.providers.first.code, 'KB');
    expect(settings.providers.first.accountEnabled, isTrue);
    expect(settings.providers.first.orderEnabled, isFalse);
    expect(settings.providers.last.displayName, '한국투자증권');
    expect(settings.providers.last.missingRequiredSettings, [
      'App Key',
      'App Secret',
    ]);
  });

  test('fetchProviderSettings throws readable exception when API fails', () {
    final repository = SpringProviderSettingsRepository(
      accessToken: '',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        return http.Response(
          jsonEncode({
            'success': false,
            'error': {'code': 'INTERNAL_ERROR', 'message': '설정 조회 실패'},
          }),
          500,
          headers: {'content-type': 'application/json'},
        );
      }),
    );

    expect(
      repository.fetchProviderSettings(),
      throwsA(
        isA<ProviderSettingsRepositoryException>().having(
          (exception) => exception.message,
          'message',
          '설정 조회 실패',
        ),
      ),
    );
  });

  test(
    'probeReadOnlyOrderHistory uses manual POST and maps safe result',
    () async {
      final repository = SpringProviderSettingsRepository(
        accessToken: '',
        config: ApiConfig(baseUrl: 'http://localhost:8080'),
        client: MockClient((request) async {
          expect(request.method, 'POST');
          expect(
            request.url.toString(),
            'http://localhost:8080/api/v1/orders/readiness/probe',
          );
          return http.Response(
            jsonEncode({
              'success': true,
              'data': {
                'status': 'VERIFIED',
                'orderDate': '20260930',
                'checkedAt': '2026-09-30T10:00:00',
                'readOnly': true,
                'message': '조회 응답 확인',
              },
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }),
      );

      final result = await repository.probeReadOnlyOrderHistory();

      expect(result.status, 'VERIFIED');
      expect(result.readOnly, isTrue);
      expect(result.orderDate, '20260930');
    },
  );

  test(
    'fetchLatestReadOnlyOrderHistoryProbe reads saved result only',
    () async {
      final repository = SpringProviderSettingsRepository(
        accessToken: '',
        config: ApiConfig(baseUrl: 'http://localhost:8080'),
        client: MockClient((request) async {
          expect(request.method, 'GET');
          expect(request.url.path, '/api/v1/orders/readiness/probe/latest');
          return http.Response(
            jsonEncode({
              'success': true,
              'data': {
                'status': 'UNVERIFIED',
                'orderDate': '20260930',
                'checkedAt': '2026-09-30T10:00:00',
                'readOnly': true,
                'message': '읽기 전용 조회를 확인하지 못했습니다.',
              },
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }),
      );

      final result = await repository.fetchLatestReadOnlyOrderHistoryProbe();

      expect(result?.status, 'UNVERIFIED');
      expect(result?.checkedAt, DateTime(2026, 9, 30, 10));
    },
  );

  test('fetchLatestReadOnlyOrderHistoryProbe accepts empty history', () async {
    final repository = SpringProviderSettingsRepository(
      accessToken: '',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient(
        (request) async =>
            http.Response(jsonEncode({'success': true, 'data': null}), 200),
      ),
    );

    expect(await repository.fetchLatestReadOnlyOrderHistoryProbe(), isNull);
  });

  test('fetchReadOnlyOrderProbeHistory maps recent saved results', () async {
    final repository = SpringProviderSettingsRepository(
      accessToken: '',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/api/v1/orders/readiness/probe/history');
        expect(request.url.query, isEmpty);
        return http.Response(
          jsonEncode({
            'success': true,
            'data': [
              {
                'status': 'UNVERIFIED',
                'orderDate': '20261002',
                'checkedAt': '2026-10-02T11:00:00',
                'readOnly': true,
                'message': '조회 미확인',
              },
              {
                'status': 'VERIFIED',
                'orderDate': '20261002',
                'checkedAt': '2026-10-02T10:00:00',
                'readOnly': true,
                'message': '조회 확인',
              },
            ],
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    final history = await repository.fetchReadOnlyOrderProbeHistory();

    expect(history.map((item) => item.status), ['UNVERIFIED', 'VERIFIED']);
    expect(history.every((item) => item.readOnly), isTrue);
  });

  test('fetchReadOnlyOrderProbeHistory accepts an empty list', () async {
    final repository = SpringProviderSettingsRepository(
      accessToken: '',
      config: ApiConfig(baseUrl: 'http://localhost:8080'),
      client: MockClient(
        (request) async =>
            http.Response(jsonEncode({'success': true, 'data': []}), 200),
      ),
    );

    expect(await repository.fetchReadOnlyOrderProbeHistory(), isEmpty);
  });

  test(
    'probe storage failure preserves only the safe API error code',
    () async {
      final repository = SpringProviderSettingsRepository(
        accessToken: '',
        config: ApiConfig(baseUrl: 'http://localhost:8080'),
        client: MockClient(
          (request) async => http.Response(
            jsonEncode({
              'success': false,
              'error': {
                'code': 'PROBE_STORAGE_UNAVAILABLE',
                'message': '점검 기록 저장소를 사용할 수 없습니다.',
              },
            }),
            503,
            headers: {'content-type': 'application/json; charset=utf-8'},
          ),
        ),
      );

      await expectLater(
        repository.probeReadOnlyOrderHistory(),
        throwsA(
          isA<ProviderSettingsRepositoryException>().having(
            (exception) => exception.code,
            'code',
            'PROBE_STORAGE_UNAVAILABLE',
          ),
        ),
      );
    },
  );
}
