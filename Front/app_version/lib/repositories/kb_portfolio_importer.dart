import '../models/kb_portfolio_import.dart';

abstract interface class KbPortfolioImporter {
  Future<KbPortfolioPreview> previewKbImport();

  Future<KbPortfolioImportResult> applyKbImport({
    required KbPortfolioPreview preview,
    required bool importCapital,
    required bool importHoldings,
    required Map<String, String> markets,
    required double stopLossRate,
    required double takeProfitRate,
  });
}
