/// 증권사별 연동 역할과 설정 상태입니다.
class ProviderSetting {
  /// 백엔드 설정 API 응답을 화면 모델로 변환합니다.
  const ProviderSetting({
    required this.code,
    required this.displayName,
    required this.marketDataEnabled,
    required this.accountEnabled,
    required this.orderEnabled,
    required this.configured,
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

  /// 필요한 민감정보가 로컬 환경에 설정되어 있는지 여부입니다.
  final bool configured;

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
      configured: json['configured'] as bool? ?? false,
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
    required this.providers,
  });

  /// 민감정보 저장 방식 코드입니다.
  final String secretStorageType;

  /// 민감정보 저장 방식 설명입니다.
  final String secretStorageDescription;

  /// 주문 기능 안전 모드 설명입니다.
  final String orderSafetyMode;

  /// 증권사별 설정 상태입니다.
  final List<ProviderSetting> providers;

  /// API JSON을 모델로 변환합니다.
  factory ProviderSettingsSnapshot.fromJson(Map<String, dynamic> json) {
    final providers = json['providers'] as List<dynamic>? ?? const [];
    return ProviderSettingsSnapshot(
      secretStorageType: json['secretStorageType'] as String? ?? 'ENV_FILE',
      secretStorageDescription:
          json['secretStorageDescription'] as String? ?? '.env 파일',
      orderSafetyMode: json['orderSafetyMode'] as String? ?? '주문 기능 기본 OFF',
      providers: providers
          .map((item) => ProviderSetting.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}
