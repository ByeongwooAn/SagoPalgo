import '../models/research_changes.dart';

abstract class ResearchChangesAccess {
  Future<ResearchChangesPage> changes(String stockCode, {int afterId = 0});
}
