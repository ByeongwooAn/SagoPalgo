/// 증권사별 연동 역할과 설정 상태입니다.
class ProviderSetting {
  /// 백엔드 설정 API 응답을 화면 모델로 변환합니다.
  const ProviderSetting({
    required this.code,
    required this.displayName,
    required this.marketDataEnabled,
    required this.accountEnabled,
    required this.orderEnabled,
    required this.newsEnabled,
    required this.disclosureEnabled,
    required this.configured,
    required this.missingRequiredSettings,
    required this.roleDescription,
  });

  /// `KB`, `KIS`, `TOSS` 같은 증권사 코드입니다.
  final String code;

  /// 화면에 표시할 증권사 이름입니다.
  final String displayName;

  /// 분석용 시세/종목 정보 소스로 켜져 있는지 여부입니다.
  final bool marketDataEnabled;

  /// 계좌 조회 담당으로 켜져 있는지 여부입니다.
  final bool accountEnabled;

  /// 주문 기능 담당으로 켜져 있는지 여부입니다.
  final bool orderEnabled;

  /// 뉴스 검색 역할이 켜져 있는지 여부입니다.
  final bool newsEnabled;

  /// 전자공시 조회 역할이 켜져 있는지 여부입니다.
  final bool disclosureEnabled;

  /// 필요한 민감정보가 로컬 환경에 설정되어 있는지 여부입니다.
  final bool configured;

  /// 비밀값을 노출하지 않고 화면에 표시할 누락 설정 이름입니다.
  final List<String> missingRequiredSettings;

  /// 증권사별 현재 역할 설명입니다.
  final String roleDescription;

  /// API JSON을 모델로 변환합니다.
  factory ProviderSetting.fromJson(Map<String, dynamic> json) {
    return ProviderSetting(
      code: json['code'] as String,
      displayName: json['displayName'] as String,
      marketDataEnabled: json['marketDataEnabled'] as bool? ?? false,
      accountEnabled: json['accountEnabled'] as bool? ?? false,
      orderEnabled: json['orderEnabled'] as bool? ?? false,
      newsEnabled: json['newsEnabled'] as bool? ?? false,
      disclosureEnabled: json['disclosureEnabled'] as bool? ?? false,
      configured: json['configured'] as bool? ?? false,
      missingRequiredSettings:
          (json['missingRequiredSettings'] as List<dynamic>? ?? const [])
              .map((item) => item as String)
              .toList(),
      roleDescription: json['roleDescription'] as String,
    );
  }
}

/// 증권사 설정 API의 루트 응답 모델입니다.
class ProviderSettingsSnapshot {
  /// 설정된 증권사 목록을 받습니다.
  const ProviderSettingsSnapshot({
    required this.secretStorageType,
    required this.secretStorageDescription,
    required this.orderSafetyMode,
    required this.marketDataFallbackOrder,
    required this.marketDataFallbackDescription,
    required this.providers,
  });

  /// 민감정보 저장 방식 코드입니다.
  final String secretStorageType;

  /// 민감정보 저장 방식 설명입니다.
  final String secretStorageDescription;

  /// 주문 기능 안전 모드 설명입니다.
  final String orderSafetyMode;

  /// 현재가 조회 시 시도하는 Provider 코드 순서입니다.
  final List<String> marketDataFallbackOrder;

  /// 모든 Provider 실패 이후까지 포함한 fallback 정책 설명입니다.
  final String marketDataFallbackDescription;

  /// 증권사별 설정 상태입니다.
  final List<ProviderSetting> providers;

  /// API JSON을 모델로 변환합니다.
  factory ProviderSettingsSnapshot.fromJson(Map<String, dynamic> json) {
    final providers = json['providers'] as List<dynamic>? ?? const [];
    return ProviderSettingsSnapshot(
      secretStorageType: json['secretStorageType'] as String? ?? 'ENV_FILE',
      secretStorageDescription:
          json['secretStorageDescription'] as String? ?? '.env 파일',
      orderSafetyMode:
          json['orderSafetyMode'] as String? ?? '주문 기능 OFF · 사전검증만 지원',
      marketDataFallbackOrder:
          (json['marketDataFallbackOrder'] as List<dynamic>? ?? const [])
              .map((item) => item as String)
              .toList(),
      marketDataFallbackDescription:
          json['marketDataFallbackDescription'] as String? ?? '',
      providers: providers
          .map((item) => ProviderSetting.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}
