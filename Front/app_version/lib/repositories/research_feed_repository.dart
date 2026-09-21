import '../models/research_feed.dart';

/// 저장된 뉴스·공시 조회와 외부 Provider 동기화를 담당합니다.
abstract class ResearchFeedRepository {
  Future<ResearchFeed> fetchFeed(ResearchStock stock);

  Future<ResearchFeed> syncFeed(ResearchStock stock);

  Future<ResearchSyncOverview> fetchSyncStatus(ResearchStock stock);
}

class ResearchFeedRepositoryException implements Exception {
  const ResearchFeedRepositoryException(this.message);

  final String message;

  @override
  String toString() => message;
}
