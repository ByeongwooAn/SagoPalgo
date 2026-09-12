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
              'orderSafetyMode': '주문 기능 기본 OFF',
              'providers': [
                {
                  'code': 'KB',
                  'displayName': 'KB증권',
                  'marketDataEnabled': false,
                  'accountEnabled': true,
                  'orderEnabled': false,
                  'configured': true,
                  'roleDescription': '계좌 조회와 추후 주문 기능의 기준 증권사',
                },
                {
                  'code': 'KIS',
                  'displayName': '한국투자증권',
                  'marketDataEnabled': true,
                  'accountEnabled': false,
                  'orderEnabled': false,
                  'configured': false,
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
    expect(settings.orderSafetyMode, '주문 기능 기본 OFF');
    expect(settings.providers, hasLength(2));
    expect(settings.providers.first.code, 'KB');
    expect(settings.providers.first.accountEnabled, isTrue);
    expect(settings.providers.first.orderEnabled, isFalse);
    expect(settings.providers.last.displayName, '한국투자증권');
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
}
