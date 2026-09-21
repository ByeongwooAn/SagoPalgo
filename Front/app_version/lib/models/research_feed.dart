/// 뉴스·공시 화면에서 조회할 수 있는 종목입니다.
class ResearchStock {
  const ResearchStock({required this.stockCode, required this.stockName});

  final String stockCode;
  final String stockName;

  @override
  bool operator ==(Object other) {
    return other is ResearchStock &&
        other.stockCode == stockCode &&
        other.stockName == stockName;
  }

  @override
  int get hashCode => Object.hash(stockCode, stockName);
}

/// 종목별 뉴스와 공시, Provider 상태를 함께 담는 로컬 피드입니다.
class ResearchFeed {
  const ResearchFeed({
    required this.stockCode,
    required this.stockName,
    required this.fromDate,
    required this.toDate,
    required this.news,
    required this.disclosures,
    required this.providers,
  });

  final String stockCode;
  final String stockName;
  final DateTime fromDate;
  final DateTime toDate;
  final List<ResearchNewsArticle> news;
  final List<ResearchDisclosure> disclosures;
  final List<ResearchProviderStatus> providers;

  factory ResearchFeed.fromJson(Map<String, dynamic> json) {
    return ResearchFeed(
      stockCode: json['stockCode'] as String? ?? '',
      stockName: json['stockName'] as String? ?? '',
      fromDate: DateTime.parse(json['fromDate'] as String),
      toDate: DateTime.parse(json['toDate'] as String),
      news: _readList(json['news']).map(ResearchNewsArticle.fromJson).toList(),
      disclosures: _readList(
        json['disclosures'],
      ).map(ResearchDisclosure.fromJson).toList(),
      providers: _readList(
        json['providers'],
      ).map(ResearchProviderStatus.fromJson).toList(),
    );
  }
}

class ResearchNewsArticle {
  const ResearchNewsArticle({
    required this.provider,
    required this.stockCode,
    required this.title,
    required this.link,
    required this.summary,
    required this.publishedAt,
  });

  final String provider;
  final String stockCode;
  final String title;
  final String link;
  final String summary;
  final DateTime? publishedAt;

  factory ResearchNewsArticle.fromJson(Map<String, dynamic> json) {
    return ResearchNewsArticle(
      provider: json['provider'] as String? ?? '',
      stockCode: json['stockCode'] as String? ?? '',
      title: json['title'] as String? ?? '',
      link: json['link'] as String? ?? '',
      summary: json['summary'] as String? ?? '',
      publishedAt: DateTime.tryParse(json['publishedAt'] as String? ?? ''),
    );
  }
}

class ResearchDisclosure {
  const ResearchDisclosure({
    required this.provider,
    required this.stockCode,
    required this.corpCode,
    required this.corpName,
    required this.reportName,
    required this.receiptNumber,
    required this.submitterName,
    required this.receiptDate,
    required this.link,
  });

  final String provider;
  final String stockCode;
  final String corpCode;
  final String corpName;
  final String reportName;
  final String receiptNumber;
  final String submitterName;
  final DateTime? receiptDate;
  final String link;

  factory ResearchDisclosure.fromJson(Map<String, dynamic> json) {
    return ResearchDisclosure(
      provider: json['provider'] as String? ?? '',
      stockCode: json['stockCode'] as String? ?? '',
      corpCode: json['corpCode'] as String? ?? '',
      corpName: json['corpName'] as String? ?? '',
      reportName: json['reportName'] as String? ?? '',
      receiptNumber: json['receiptNumber'] as String? ?? '',
      submitterName: json['submitterName'] as String? ?? '',
      receiptDate: DateTime.tryParse(json['receiptDate'] as String? ?? ''),
      link: json['link'] as String? ?? '',
    );
  }
}

class ResearchProviderStatus {
  const ResearchProviderStatus({
    required this.provider,
    required this.dataType,
    required this.status,
    required this.message,
  });

  final String provider;
  final String dataType;
  final String status;
  final String message;

  factory ResearchProviderStatus.fromJson(Map<String, dynamic> json) {
    return ResearchProviderStatus(
      provider: json['provider'] as String? ?? '',
      dataType: json['dataType'] as String? ?? '',
      status: json['status'] as String? ?? '',
      message: json['message'] as String? ?? '',
    );
  }
}

Iterable<Map<String, dynamic>> _readList(Object? value) {
  if (value is! List<dynamic>) {
    return const [];
  }
  return value.whereType<Map<String, dynamic>>();
}
