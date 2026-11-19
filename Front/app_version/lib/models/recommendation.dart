/// 추천 상세 화면에서 보여줄 매수/매도 추천 데이터입니다.
///
/// 추천 자체와 추천 이유를 분리해 두면, 이후 API에서
/// `recommendation`과 `recommendation_reasons` 테이블을 따로 내려줘도
/// 화면 코드를 크게 바꾸지 않고 연결할 수 있습니다.
class InvestmentRecommendation {
  /// 추천 카드에 필요한 핵심 정보와 설명을 모두 받습니다.
  const InvestmentRecommendation({
    this.recommendationId,
    required this.stockName,
    required this.stockCode,
    required this.market,
    required this.status,
    this.machineStatus,
    this.recommendationType = 'HOLD',
    this.analysisContext = 'HOLDING',
    required this.score,
    required this.entryPrice,
    required this.stopLossRate,
    this.takeProfitRate = 0,
    required this.aiSummary,
    required this.reasons,
    this.createdAt,
    this.evidence,
  });

  /// 저장 추천 상세와 알림을 연결할 때 사용하는 PK입니다.
  final int? recommendationId;

  /// 사용자가 보는 종목명입니다.
  final String stockName;

  /// 실제 API 호출과 DB 저장에 사용할 종목 코드입니다.
  final String stockCode;

  /// 관심 종목 등록과 추천 API에서 사용할 시장 코드입니다.
  final String market;

  /// 80점 이상일 때의 "강한 매수" 같은 추천 상태입니다.
  final String status;

  /// 상태 필터와 서버 요청에 사용하는 기계 판독용 상태 코드입니다.
  final String? machineStatus;

  /// BUY, SELL, HOLD 중 서버가 판단한 행동 분류입니다.
  final String recommendationType;

  /// HOLDING 또는 WATCHLIST입니다.
  final String analysisContext;

  /// 기획서의 점수 시스템에 따른 0~100 추천 점수입니다.
  final int score;

  /// 사용자가 진입을 검토할 기준 가격입니다.
  final int entryPrice;

  /// 리스크 관리를 위해 추천 상세에서 항상 노출할 손절 기준입니다.
  final double? stopLossRate;

  /// 수익 실현을 검토할 목표 수익률입니다.
  final double takeProfitRate;

  /// AI가 추천 이유를 자연어로 요약한 문장입니다.
  final String aiSummary;

  /// RSI, MACD, 뉴스처럼 점수를 만든 세부 근거 목록입니다.
  final List<RecommendationReason> reasons;

  /// 서버가 분석 결과를 저장한 시각입니다.
  final DateTime? createdAt;
  final AnalysisEvidence? evidence;

  /// 백엔드 대시보드 스냅샷의 `recommendation` JSON을 앱 모델로 변환합니다.
  factory InvestmentRecommendation.fromJson(Map<String, dynamic> json) {
    return InvestmentRecommendation(
      recommendationId: _readOptionalInt(json['recommendationId']),
      stockName: json['stockName'] as String,
      stockCode: json['stockCode'] as String,
      market: json['market'] as String? ?? 'KOSPI',
      status: json['statusLabel'] as String? ?? json['status'] as String,
      machineStatus:
          json['machineStatus'] as String? ?? json['status'] as String?,
      recommendationType: json['recommendationType'] as String? ?? 'HOLD',
      analysisContext: json['analysisContext'] as String? ?? 'HOLDING',
      score: _readInt(json['score']),
      entryPrice: _readInt(json['entryPrice']),
      stopLossRate: _readOptionalDouble(json['stopLossRate']),
      takeProfitRate: _readOptionalDouble(json['takeProfitRate']) ?? 0,
      aiSummary: json['aiSummary'] as String,
      reasons: (json['reasons'] as List<dynamic>? ?? const [])
          .map(
            (reason) =>
                RecommendationReason.fromJson(reason as Map<String, dynamic>),
          )
          .toList(),
      createdAt: json['createdAt'] == null
          ? null
          : DateTime.parse(json['createdAt'] as String),
      evidence: json['evidence'] is Map<String, dynamic>
          ? AnalysisEvidence.fromJson(json['evidence'] as Map<String, dynamic>)
          : null,
    );
  }
}

class AnalysisEvidence {
  const AnalysisEvidence({
    required this.modelVersion,
    this.candleCount,
    this.newsCount,
    this.disclosureCount,
    this.dailySignal,
  });
  final String? modelVersion;
  final int? candleCount;
  final int? newsCount;
  final int? disclosureCount;
  final DailyModelSignal? dailySignal;
  bool get isFallback => modelVersion?.contains('FALLBACK') ?? false;
  factory AnalysisEvidence.fromJson(Map<String, dynamic> json) =>
      AnalysisEvidence(
        modelVersion: json['modelVersion'] as String?,
        candleCount: _readOptionalInt(json['candleCount']),
        newsCount: _readOptionalInt(json['newsCount']),
        disclosureCount: _readOptionalInt(json['disclosureCount']),
        dailySignal: json['dailySignal'] is Map<String, dynamic>
            ? DailyModelSignal.fromJson(
                json['dailySignal'] as Map<String, dynamic>,
              )
            : null,
      );
}

class DailyModelSignal {
  const DailyModelSignal({
    required this.decision,
    required this.contributions,
    this.holdReason,
    this.modelVersion,
    this.basisDate,
    this.evaluatedAt,
    this.expiresAt,
    this.probability,
    this.threshold,
  });

  final String decision;
  final String? holdReason;
  final String? modelVersion;
  final String? basisDate;
  final DateTime? evaluatedAt;
  final DateTime? expiresAt;
  final double? probability;
  final double? threshold;
  final Map<String, double> contributions;

  factory DailyModelSignal.fromJson(Map<String, dynamic> json) {
    final contributions =
        json['contributions'] as Map<String, dynamic>? ?? const {};
    return DailyModelSignal(
      decision: json['decision'] as String,
      holdReason: json['holdReason'] as String?,
      modelVersion: json['modelVersion'] as String?,
      basisDate: json['basisDate'] as String?,
      evaluatedAt: DateTime.tryParse(json['evaluatedAt'] as String? ?? ''),
      expiresAt: DateTime.tryParse(json['expiresAt'] as String? ?? ''),
      probability: _readOptionalDouble(json['probability']),
      threshold: _readOptionalDouble(json['threshold']),
      contributions: contributions.map(
        (key, value) => MapEntry(key, _readDouble(value)),
      ),
    );
  }
}

/// 추천 이력 API의 페이지 정보와 항목을 함께 보관합니다.
class RecommendationPage {
  const RecommendationPage({
    required this.items,
    required this.page,
    required this.size,
    required this.total,
  });

  final List<InvestmentRecommendation> items;
  final int page;
  final int size;
  final int total;

  factory RecommendationPage.fromJson(Map<String, dynamic> json) {
    return RecommendationPage(
      items: (json['items'] as List<dynamic>? ?? const [])
          .map(
            (item) =>
                InvestmentRecommendation.fromJson(item as Map<String, dynamic>),
          )
          .toList(),
      page: _readInt(json['page']),
      size: _readInt(json['size']),
      total: _readInt(json['total']),
    );
  }
}

/// 추천 점수에 영향을 준 단일 근거입니다.
class RecommendationReason {
  /// 라벨과 설명을 분리해 두어 UI에서 라벨은 강조색으로, 설명은 본문으로 그립니다.
  const RecommendationReason({
    required this.label,
    required this.description,
    required this.type,
  });

  /// 예: RSI, MACD, 뉴스.
  final String label;

  /// 사용자가 이해할 수 있는 추천 근거 설명입니다.
  final String description;

  /// 화면에서 어떤 색상으로 강조할지 결정하는 분류값입니다.
  final RecommendationReasonType type;

  /// 추천 사유 JSON을 앱 모델로 변환합니다.
  factory RecommendationReason.fromJson(Map<String, dynamic> json) {
    return RecommendationReason(
      label: json['label'] as String,
      description: json['description'] as String,
      type: _recommendationReasonTypeFromApiValue(json['type'] as String?),
    );
  }
}

/// 추천 근거별 강조색을 안정적으로 고르기 위한 타입입니다.
enum RecommendationReasonType {
  /// 메인 컬러를 쓰는 기술 지표 근거입니다.
  technical,

  /// 서브 컬러를 쓰는 추세 또는 위험 관련 근거입니다.
  trend,

  /// 포인트 컬러를 쓰는 뉴스/호재 근거입니다.
  news,
}

/// 백엔드 reason type 문자열을 화면 색상 분류로 변환합니다.
RecommendationReasonType _recommendationReasonTypeFromApiValue(String? value) {
  return switch (value) {
    'TECHNICAL' || 'RSI' || 'VOLUME' => RecommendationReasonType.technical,
    'NEWS' => RecommendationReasonType.news,
    _ => RecommendationReasonType.trend,
  };
}

int _readInt(Object? value) {
  return switch (value) {
    int number => number,
    double number => number.round(),
    String text => double.parse(text).round(),
    _ => throw FormatException('정수로 변환할 수 없는 값입니다: $value'),
  };
}

double _readDouble(Object? value) {
  return switch (value) {
    int number => number.toDouble(),
    double number => number,
    String text => double.parse(text),
    _ => throw FormatException('실수로 변환할 수 없는 값입니다: $value'),
  };
}

int? _readOptionalInt(Object? value) {
  return value == null ? null : _readInt(value);
}

double? _readOptionalDouble(Object? value) {
  return value == null ? null : _readDouble(value);
}
