import 'package:flutter/services.dart';

/// Flutter 앱이 `.env` 파일에서 읽은 설정값을 보관하는 전역 환경 설정입니다.
///
/// 모바일 앱에 포함되는 `.env` 값은 APK 안에 함께 들어가므로 진짜 비밀키를 넣으면 안 됩니다.
/// 이 파일은 API 주소, Mock 사용 여부, 공개 가능한 client id처럼 앱에 노출되어도 되는 값만 관리합니다.
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
    _instance = AppEnvironment._(_parse(raw));
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
  String get apiBaseUrl => _required('SAGOPALGO_API_BASE_URL');

  /// 현재 앱이 Mock 인증 Repository를 사용할지 결정합니다.
  bool get useMockAuth {
    return _optional('SAGOPALGO_USE_MOCK_AUTH', fallback: 'true') == 'true';
  }

  /// Google SDK 초기화에 사용할 server client id입니다.
  ///
  /// 실제 Google SDK 연결 단계에서 `google_sign_in` 초기화에 전달합니다.
  String? get googleServerClientId {
    return _blankToNull(_optional('SAGOPALGO_GOOGLE_SERVER_CLIENT_ID'));
  }

  /// Naver SDK 초기화에 사용할 공개 client id입니다.
  ///
  /// Naver client secret은 모바일 앱에 넣지 않고 백엔드 `.env`에서만 관리해야 합니다.
  String? get naverClientId {
    return _blankToNull(_optional('SAGOPALGO_NAVER_CLIENT_ID'));
  }

  /// 필수 환경 변수를 읽고 값이 비어 있으면 오류를 던집니다.
  String _required(String key) {
    final value = _values[key];
    if (value == null || value.isBlank) {
      throw StateError('$key 환경 변수가 .env에 설정되어 있지 않습니다.');
    }

    return value;
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
