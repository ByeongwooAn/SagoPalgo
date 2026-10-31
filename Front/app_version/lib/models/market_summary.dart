/// 홈 대시보드가 보여줘야 하는 시장과 사용자 자본 요약 데이터입니다.
///
/// Spring Boot API의 `/dashboard/snapshot` 응답을 그대로 매핑할 수 있도록
/// 화면 표시값과 계산값을 하나의 모델로 묶어 둡니다.
class MarketSummary {
  /// API 응답의 시장/자본 요약 필드를 받습니다.
  const MarketSummary({
    required this.availableCapital,
    required this.monthlyReturnRate,
    required this.recommendedPositionRange,
    required this.marketTrend,
    required this.marketScore,
    required this.newsSentiment,
    required this.positiveNewsCount,
    required this.marketBars,
    this.index,
    this.news,
    this.checkedAt,
  });

  /// 사용자가 설정한 투자 가능 자본금입니다.
  final int availableCapital;

  /// 호환 필드. 실제 값은 보유 종목의 평가 수익률이며 월간 수익률이 아닙니다.
  final double monthlyReturnRate;

  /// 기획서의 리스크 관리 기준인 종목당 권장 투자금 범위입니다.
  final String recommendedPositionRange;

  /// 코스피/나스닥/업종 흐름을 요약한 표시 텍스트입니다.
  final String marketTrend;

  /// 시장 강세 조건을 추천 점수에 반영하기 위한 0~100 점수입니다.
  final int marketScore;

  /// 뉴스 감성 분석 결과를 사람이 읽기 쉬운 단어로 표현한 값입니다.
  final String newsSentiment;

  /// 긍정 뉴스 개수는 뉴스 감성 근거를 짧게 보여줄 때 사용합니다.
  final int positiveNewsCount;

  /// 대시보드 막대 그래프에 사용할 0~1 사이의 시장 지표 값들입니다.
  final List<double> marketBars;
  final MarketIndexSummary? index;
  final NewsSummary? news;
  final DateTime? checkedAt;

  /// 백엔드 대시보드 스냅샷의 `marketSummary` JSON을 앱 모델로 변환합니다.
  factory MarketSummary.fromJson(Map<String, dynamic> json) {
    return MarketSummary(
      availableCapital: _readInt(json['availableCapital']),
      monthlyReturnRate: _readDouble(
        json['portfolioReturnRate'] ?? json['monthlyReturnRate'] ?? 0,
      ),
      recommendedPositionRange: json['recommendedPositionRange'] as String,
      marketTrend: json['marketTrend'] as String,
      marketScore: _readInt(json['marketScore']),
      newsSentiment: json['newsSentiment'] as String,
      positiveNewsCount: _readInt(json['positiveNewsCount']),
      marketBars: (json['marketBars'] as List<dynamic>)
          .map(_readDouble)
          .toList(),
      index: json['index'] is Map<String, dynamic>
          ? MarketIndexSummary.fromJson(json['index'] as Map<String, dynamic>)
          : null,
      news: json['news'] is Map<String, dynamic>
          ? NewsSummary.fromJson(json['news'] as Map<String, dynamic>)
          : null,
      checkedAt: DateTime.tryParse(json['checkedAt'] as String? ?? ''),
    );
  }
}

class MarketIndexSummary {
  const MarketIndexSummary({
    required this.status,
    required this.provider,
    required this.message,
    required this.value,
    required this.changeRate,
    required this.receivedAt,
    required this.points,
  });
  final String status;
  final String provider;
  final String message;
  final double? value;
  final double? changeRate;
  final DateTime? receivedAt;
  final List<MarketIndexPoint> points;
  factory MarketIndexSummary.fromJson(Map<String, dynamic> json) =>
      MarketIndexSummary(
        status: json['status'] as String,
        provider: json['provider'] as String,
        message: json['message'] as String,
        value: json['value'] == null ? null : _readDouble(json['value']),
        changeRate: json['changeRate'] == null
            ? null
            : _readDouble(json['changeRate']),
        receivedAt: DateTime.tryParse(json['receivedAt'] as String? ?? ''),
        points: (json['points'] as List<dynamic>? ?? [])
            .map(
              (point) => MarketIndexPoint(
                DateTime.parse(point['date'] as String),
                _readDouble(point['close']),
              ),
            )
            .toList(),
      );
}

class MarketIndexPoint {
  const MarketIndexPoint(this.date, this.close);
  final DateTime date;
  final double close;
}

class NewsSummary {
  const NewsSummary({
    required this.status,
    required this.method,
    required this.articleCount,
    required this.positiveCount,
    required this.negativeCount,
    required this.latestPublishedAt,
  });
  final String status;
  final String method;
  final int articleCount;
  final int positiveCount;
  final int negativeCount;
  final DateTime? latestPublishedAt;
  factory NewsSummary.fromJson(Map<String, dynamic> json) => NewsSummary(
    status: json['status'] as String,
    method: json['method'] as String,
    articleCount: _readInt(json['articleCount']),
    positiveCount: _readInt(json['positiveCount']),
    negativeCount: _readInt(json['negativeCount']),
    latestPublishedAt: DateTime.tryParse(
      json['latestPublishedAt'] as String? ?? '',
    ),
  );
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
