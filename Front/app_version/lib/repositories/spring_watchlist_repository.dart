import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/recommendation.dart';
import '../models/watchlist_item.dart';
import 'watchlist_repository.dart';
import 'watchlist_editor.dart';

/// Spring Boot 관심 종목 API와 통신하는 Repository입니다.
class SpringWatchlistRepository
    implements WatchlistRepository, WatchlistEditor {
  /// 개인용 모드의 선택 access token, API 설정, HTTP 클라이언트를 주입받습니다.
  SpringWatchlistRepository({
    required this.accessToken,
    ApiConfig? config,
    http.Client? client,
  }) : config = config ?? ApiConfig(),
       client = client ?? http.Client();

  /// 백엔드 API 요청에 선택적으로 사용하는 access token입니다.
  final String accessToken;

  /// 백엔드 기본 URL과 관심 종목 경로 설정입니다.
  final ApiConfig config;

  /// HTTP 요청을 실제로 보내는 클라이언트입니다.
  final http.Client client;

  @override
  Future<void> addStock({
    required String stockCode,
    required String stockName,
    required String market,
    required bool alertEnabled,
  }) async {
    final response = await client.post(
      Uri.parse(config.watchlistBaseUrl),
      headers: _headers(contentType: true),
      body: jsonEncode({
        'stockCode': stockCode,
        'stockName': stockName,
        'market': market,
        'alertEnabled': alertEnabled,
      }),
    );
    _decodeResponse(response);
  }

  @override
  Future<List<WatchlistItem>> fetchWatchlist() async {
    final response = await client.get(
      Uri.parse(config.watchlistBaseUrl),
      headers: _headers(),
    );
    final decoded = _decodeResponse(response);
    return (decoded['data'] as List<dynamic>)
        .map((item) => WatchlistItem.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  @override
  Future<WatchlistActionResult> addRecommendation(
    InvestmentRecommendation recommendation,
  ) async {
    final existing = await _findExisting(recommendation);
    if (existing != null) {
      return WatchlistActionResult(
        message: '${recommendation.stockName} 이미 관심 종목에 등록되어 있습니다.',
        changed: false,
      );
    }

    await _create(recommendation, alertEnabled: false);
    return WatchlistActionResult(
      message: '${recommendation.stockName} 관심 종목에 등록했습니다.',
    );
  }

  @override
  Future<WatchlistActionResult> enableAlert(
    InvestmentRecommendation recommendation,
  ) async {
    final existing = await _findExisting(recommendation);
    if (existing == null) {
      await _create(recommendation, alertEnabled: true);
      return WatchlistActionResult(
        message: '${recommendation.stockName} 관심 종목 등록과 알림 설정을 완료했습니다.',
      );
    }

    if (existing.alertEnabled) {
      return WatchlistActionResult(
        message: '${recommendation.stockName} 알림이 이미 켜져 있습니다.',
        changed: false,
      );
    }

    await _updateAlert(existing.watchlistId, alertEnabled: true);
    return WatchlistActionResult(
      message: '${recommendation.stockName} 알림을 켰습니다.',
    );
  }

  Future<WatchlistItem?> _findExisting(
    InvestmentRecommendation recommendation,
  ) async {
    final items = await fetchWatchlist();

    for (final item in items) {
      if (item.stockCode == recommendation.stockCode &&
          item.market == recommendation.market) {
        return item;
      }
    }

    return null;
  }

  Future<void> _create(
    InvestmentRecommendation recommendation, {
    required bool alertEnabled,
  }) async {
    await addStock(
      stockCode: recommendation.stockCode,
      stockName: recommendation.stockName,
      market: recommendation.market,
      alertEnabled: alertEnabled,
    );
  }

  Future<void> _updateAlert(
    int watchlistId, {
    required bool alertEnabled,
  }) async {
    final response = await client.patch(
      Uri.parse('${config.watchlistBaseUrl}/$watchlistId/alert'),
      headers: _headers(contentType: true),
      body: jsonEncode({'alertEnabled': alertEnabled}),
    );
    _decodeResponse(response);
  }

  Map<String, String> _headers({bool contentType = false}) {
    return {
      'Accept': 'application/json',
      if (accessToken.trim().isNotEmpty) 'Authorization': 'Bearer $accessToken',
      if (contentType) 'Content-Type': 'application/json',
    };
  }

  Map<String, dynamic> _decodeResponse(http.Response response) {
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    final success = decoded['success'] as bool? ?? false;
    if (response.statusCode >= 200 && response.statusCode < 300 && success) {
      return decoded;
    }

    final error = decoded['error'] as Map<String, dynamic>?;
    final message = error?['message'] as String? ?? '관심 종목 요청에 실패했습니다.';
    throw WatchlistRepositoryException(message);
  }
}

/// 관심 종목 Repository에서 화면으로 전달하는 실패 예외입니다.
class WatchlistRepositoryException implements Exception {
  /// 사용자에게 보여줄 수 있는 오류 메시지를 받습니다.
  const WatchlistRepositoryException(this.message);

  /// 추천 화면 스낵바에 표시할 오류 메시지입니다.
  final String message;

  @override
  String toString() => message;
}
