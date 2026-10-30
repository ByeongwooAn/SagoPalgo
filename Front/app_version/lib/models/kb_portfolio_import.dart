class KbPortfolioPreview {
  const KbPortfolioPreview({
    required this.token,
    required this.expiresAt,
    required this.checkedAt,
    required this.currentCapital,
    required this.orderAvailableCash,
    required this.items,
    required this.retainedImportedCount,
  });

  final String token;
  final DateTime expiresAt;
  final DateTime checkedAt;
  final num currentCapital;
  final num? orderAvailableCash;
  final List<KbPortfolioImportItem> items;
  final int retainedImportedCount;

  factory KbPortfolioPreview.fromJson(Map<String, dynamic> json) =>
      KbPortfolioPreview(
        token: json['previewToken'] as String,
        expiresAt: DateTime.parse(json['expiresAt'] as String),
        checkedAt: DateTime.parse(json['checkedAt'] as String),
        currentCapital: json['currentCapital'] as num,
        orderAvailableCash: json['orderAvailableCash'] as num?,
        items: (json['items'] as List<dynamic>)
            .map(
              (item) =>
                  KbPortfolioImportItem.fromJson(item as Map<String, dynamic>),
            )
            .toList(),
        retainedImportedCount: json['retainedImportedCount'] as int,
      );
}

class KbPortfolioImportItem {
  const KbPortfolioImportItem({
    required this.stockCode,
    required this.stockName,
    required this.market,
    required this.quantity,
    required this.averageBuyPrice,
    required this.action,
    required this.message,
  });

  final String stockCode;
  final String stockName;
  final String market;
  final num quantity;
  final num averageBuyPrice;
  final String action;
  final String message;
  bool get canImport => action == 'CREATE' || action == 'UPDATE';

  factory KbPortfolioImportItem.fromJson(Map<String, dynamic> json) =>
      KbPortfolioImportItem(
        stockCode: json['stockCode'] as String,
        stockName: json['stockName'] as String,
        market: json['market'] as String,
        quantity: json['quantity'] as num,
        averageBuyPrice: json['averageBuyPrice'] as num,
        action: json['action'] as String,
        message: json['message'] as String,
      );
}

class KbPortfolioImportResult {
  const KbPortfolioImportResult({
    required this.capitalImported,
    required this.createdCount,
    required this.updatedCount,
    required this.skippedCount,
  });

  final bool capitalImported;
  final int createdCount;
  final int updatedCount;
  final int skippedCount;

  factory KbPortfolioImportResult.fromJson(Map<String, dynamic> json) =>
      KbPortfolioImportResult(
        capitalImported: json['capitalImported'] as bool,
        createdCount: json['createdCount'] as int,
        updatedCount: json['updatedCount'] as int,
        skippedCount: json['skippedCount'] as int,
      );
}
