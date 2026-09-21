import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/research_feed.dart';
import 'research_feed_repository.dart';

/// Spring Boot 뉴스·공시 저장/동기화 API와 통신합니다.
class SpringResearchFeedRepository implements ResearchFeedRepository {
  SpringResearchFeedRepository({
    required this.accessToken,
    ApiConfig? config,
    http.Client? client,
  }) : config = config ?? ApiConfig(),
       client = client ?? http.Client();

  final String accessToken;
  final ApiConfig config;
  final http.Client client;

  @override
  Future<ResearchFeed> fetchFeed(ResearchStock stock) {
    return _request(stock, sync: false);
  }

  @override
  Future<ResearchFeed> syncFeed(ResearchStock stock) {
    return _request(stock, sync: true);
  }

  @override
  Future<ResearchSyncOverview> fetchSyncStatus(ResearchStock stock) async {
    final uri = Uri.parse(
      config.researchSyncStatusUrl,
    ).replace(queryParameters: {'stockCode': stock.stockCode});
    final response = await client.get(uri, headers: _headers());
    final decoded = _decodeResponse(response);
    final data = decoded['data'];
    if (data is! Map<String, dynamic>) {
      throw const ResearchFeedRepositoryException(
        '뉴스·공시 동기화 상태 형식이 올바르지 않습니다.',
      );
    }
    return ResearchSyncOverview.fromJson(data);
  }

  Future<ResearchFeed> _request(
    ResearchStock stock, {
    required bool sync,
  }) async {
    final baseUri = Uri.parse(
      sync ? config.researchFeedSyncUrl : config.researchFeedUrl,
    );
    final uri = baseUri.replace(
      queryParameters: {
        'stockCode': stock.stockCode,
        'stockName': stock.stockName,
      },
    );
    final response = sync
        ? await client.post(uri, headers: _headers())
        : await client.get(uri, headers: _headers());
    final decoded = _decodeResponse(response);
    final data = decoded['data'];
    if (data is! Map<String, dynamic>) {
      throw const ResearchFeedRepositoryException('뉴스·공시 응답 형식이 올바르지 않습니다.');
    }
    return ResearchFeed.fromJson(data);
  }

  Map<String, String> _headers() {
    return {
      'Accept': 'application/json',
      if (accessToken.trim().isNotEmpty) 'Authorization': 'Bearer $accessToken',
    };
  }

  Map<String, dynamic> _decodeResponse(http.Response response) {
    try {
      final decoded = jsonDecode(response.body) as Map<String, dynamic>;
      final success = decoded['success'] as bool? ?? false;
      if (response.statusCode >= 200 && response.statusCode < 300 && success) {
        return decoded;
      }

      final error = decoded['error'] as Map<String, dynamic>?;
      final message = error?['message'] as String?;
      throw ResearchFeedRepositoryException(message ?? '뉴스·공시 요청에 실패했습니다.');
    } on ResearchFeedRepositoryException {
      rethrow;
    } on FormatException {
      throw const ResearchFeedRepositoryException('뉴스·공시 서버 응답을 해석하지 못했습니다.');
    }
  }
}
