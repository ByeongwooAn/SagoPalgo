import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/recommendation.dart';
import 'recommendation_repository.dart';

/// Spring Boot 추천 이력과 수동 분석 API를 호출합니다.
class SpringRecommendationRepository implements RecommendationRepository {
  SpringRecommendationRepository({
    required this.accessToken,
    ApiConfig? config,
    http.Client? client,
  }) : config = config ?? ApiConfig(),
       client = client ?? http.Client();

  final String accessToken;
  final ApiConfig config;
  final http.Client client;

  @override
  Future<RecommendationPage> fetchHistory({
    String? status,
    int page = 0,
    int size = 20,
  }) async {
    final query = <String, String>{
      'page': '$page',
      'size': '$size',
      if (status != null && status.isNotEmpty) 'status': status,
    };
    final uri = Uri.parse(
      config.recommendationsBaseUrl,
    ).replace(queryParameters: query);
    final response = await client.get(uri, headers: _headers);
    final data = _decode(response)['data'] as Map<String, dynamic>;
    return RecommendationPage.fromJson(data);
  }

  @override
  Future<InvestmentRecommendation> fetchDetail(int recommendationId) async {
    final response = await client.get(
      Uri.parse('${config.recommendationsBaseUrl}/$recommendationId'),
      headers: _headers,
    );
    return _recommendation(response);
  }

  @override
  Future<InvestmentRecommendation> analyzeHolding(int holdingId) async {
    final response = await client.post(
      Uri.parse('${config.recommendationsBaseUrl}/analyze/$holdingId'),
      headers: _headers,
    );
    return _recommendation(response);
  }

  @override
  Future<InvestmentRecommendation> analyzeWatchlist(int watchlistId) async {
    final response = await client.post(
      Uri.parse(
        '${config.recommendationsBaseUrl}/analyze/watchlist/$watchlistId',
      ),
      headers: _headers,
    );
    return _recommendation(response);
  }

  InvestmentRecommendation _recommendation(http.Response response) {
    final data = _decode(response)['data'] as Map<String, dynamic>;
    return InvestmentRecommendation.fromJson(data);
  }

  Map<String, dynamic> _decode(http.Response response) {
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    final success = decoded['success'] as bool? ?? false;
    if (response.statusCode >= 200 && response.statusCode < 300 && success) {
      return decoded;
    }
    final error = decoded['error'] as Map<String, dynamic>?;
    throw RecommendationRepositoryException(
      error?['message'] as String? ?? '추천 데이터를 불러오지 못했습니다.',
    );
  }

  Map<String, String> get _headers => {
    'Accept': 'application/json',
    if (accessToken.trim().isNotEmpty) 'Authorization': 'Bearer $accessToken',
  };
}
