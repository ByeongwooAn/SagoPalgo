import 'package:flutter/services.dart';

/// Flutter 앱이 `.env` 파일에서 읽은 설정값을 보관하는 전역 환경 설정입니다.
///
/// Windows 실행 번들에 포함되는 `.env` 값은 사용자 PC에 남으므로 진짜 비밀키는 이후 로컬 보안 저장소로
/// 옮기는 것을 목표로 합니다.
/// 이 파일은 API 주소와 공개 가능한 client id처럼 앱에 노출되어도 되는 값만 관리합니다.
class AppEnvironment {
  /// `.env` 파일을 읽은 뒤 만들어지는 설정 Map입니다.
  AppEnvironment._(this._values);

  /// `.env`의 key=value 값을 저장하는 내부 Map입니다.
  final Map<String, String> _values;

  /// 앱 전체에서 공유하는 현재 환경 설정입니다.
  static AppEnvironment? _instance;

  /// 앱 시작 전에 `.env` 파일을 읽어 전역 환경 설정을 초기화합니다.
  ///
  /// @param assetPath pubspec.yaml assets에 등록된 `.env` 파일 경로입니다.
  static Future<void> load({String assetPath = '.env'}) async {
    final raw = await rootBundle.loadString(assetPath);
    _instance = AppEnvironment._({..._parse(raw), ..._dartDefines()});
  }

  /// 초기화된 환경 설정을 반환합니다.
  ///
  /// `main()`에서 `AppEnvironment.load()`를 먼저 호출하지 않으면 설정을 안전하게 읽을 수 없으므로
  /// 명확한 오류를 던져 초기화 순서 문제를 빨리 발견하게 합니다.
  static AppEnvironment get instance {
    final environment = _instance;
    if (environment == null) {
      throw StateError('AppEnvironment.load()를 먼저 호출해야 합니다.');
    }

    return environment;
  }

  /// Spring Boot 백엔드의 기본 API 주소입니다.
  String get apiBaseUrl {
    final explicitBaseUrl = _blankToNull(_optional('SAGOPALGO_API_BASE_URL'));
    if (explicitBaseUrl != null) {
      return explicitBaseUrl;
    }

    final serverName = _blankToNull(_optional('SAGOPALGO_NGINX_SERVER_NAME'));
    final proxyPort = _blankToNull(_optional('SAGOPALGO_PROXY_HTTP_PORT'));
    final apiPort = _blankToNull(_optional('SAGOPALGO_API_PORT'));
    final port = proxyPort ?? apiPort;
    if (serverName != null && port != null) {
      return 'http://$serverName:$port';
    }

    throw StateError(
      'SAGOPALGO_API_BASE_URL 또는 SAGOPALGO_NGINX_SERVER_NAME/SAGOPALGO_PROXY_HTTP_PORT 환경 변수가 필요합니다.',
    );
  }

  /// 앱 시작 시 사용할 선택형 로컬 잠금 PIN입니다.
  ///
  /// 값이 없으면 개인용 프로그램은 별도 잠금 화면 없이 바로 홈으로 진입합니다.
  String? get appLockPin {
    return _blankToNull(_optional('SAGOPALGO_APP_LOCK_PIN'));
  }

  /// 선택 환경 변수를 읽고 없으면 fallback을 반환합니다.
  String _optional(String key, {String fallback = ''}) {
    return _values[key] ?? fallback;
  }

  /// 빈 문자열은 null로 변환해 아직 설정하지 않은 client id를 쉽게 구분합니다.
  String? _blankToNull(String value) {
    return value.isBlank ? null : value;
  }

  /// `.env` 원문을 key=value Map으로 파싱합니다.
  ///
  /// 주석(`#`)과 빈 줄은 무시하고, 값이 따옴표로 감싸져 있으면 바깥 따옴표만 제거합니다.
  static Map<String, String> _parse(String raw) {
    final values = <String, String>{};

    for (final line in raw.split('\n')) {
      final trimmed = line.trim();
      if (trimmed.isEmpty || trimmed.startsWith('#')) {
        continue;
      }

      final separatorIndex = trimmed.indexOf('=');
      if (separatorIndex <= 0) {
        continue;
      }

      final key = trimmed.substring(0, separatorIndex).trim();
      final value = trimmed.substring(separatorIndex + 1).trim();
      values[key] = _stripWrappingQuotes(value);
    }

    return values;
  }

  /// `flutter run --dart-define`으로 넘어온 값이 있으면 asset 값보다 우선합니다.
  static Map<String, String> _dartDefines() {
    const values = <String, String>{
      'SAGOPALGO_API_BASE_URL': String.fromEnvironment(
        'SAGOPALGO_API_BASE_URL',
      ),
      'SAGOPALGO_API_PORT': String.fromEnvironment('SAGOPALGO_API_PORT'),
      'SAGOPALGO_PROXY_HTTP_PORT': String.fromEnvironment(
        'SAGOPALGO_PROXY_HTTP_PORT',
      ),
      'SAGOPALGO_NGINX_SERVER_NAME': String.fromEnvironment(
        'SAGOPALGO_NGINX_SERVER_NAME',
      ),
      'SAGOPALGO_APP_LOCK_PIN': String.fromEnvironment(
        'SAGOPALGO_APP_LOCK_PIN',
      ),
    };

    return Map.fromEntries(
      values.entries.where((entry) => entry.value.trim().isNotEmpty),
    );
  }

  /// 작은따옴표나 큰따옴표로 감싼 값에서 바깥 따옴표만 제거합니다.
  static String _stripWrappingQuotes(String value) {
    if (value.length < 2) {
      return value;
    }

    final first = value[0];
    final last = value[value.length - 1];
    final isWrappedWithDoubleQuotes = first == '"' && last == '"';
    final isWrappedWithSingleQuotes = first == "'" && last == "'";
    if (isWrappedWithDoubleQuotes || isWrappedWithSingleQuotes) {
      return value.substring(1, value.length - 1);
    }

    return value;
  }
}

/// 문자열 공백 여부를 의미 있게 읽기 위한 작은 확장입니다.
extension _BlankString on String {
  /// trim 후 비어 있으면 true입니다.
  bool get isBlank => trim().isEmpty;
}
