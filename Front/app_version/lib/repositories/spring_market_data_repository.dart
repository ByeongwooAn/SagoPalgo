import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/market_candle.dart';
import 'market_data_repository.dart';

/// Spring Boot 시장 데이터 API에서 정규화된 캔들을 조회합니다.
class SpringMarketDataRepository implements MarketDataRepository {
  SpringMarketDataRepository({
    required this.accessToken,
    ApiConfig? config,
    http.Client? client,
  }) : config = config ?? ApiConfig(),
       client = client ?? http.Client();

  final String accessToken;
  final ApiConfig config;
  final http.Client client;

  @override
  Future<MarketCandleSnapshot> fetchCandles({
    required String stockCode,
    required String market,
    required MarketCandleInterval interval,
    int count = 60,
  }) async {
    final uri = Uri.parse(config.marketCandlesUrl).replace(
      queryParameters: {
        'stockCode': stockCode,
        'market': market,
        'interval': interval.apiValue,
        'count': count.toString(),
      },
    );
    final response = await client.get(uri, headers: _headers);
    final decoded = _decodeResponse(response);
    final data = decoded['data'];
    if (data is! Map<String, dynamic>) {
      throw const MarketDataRepositoryException('캔들 시세 응답 형식이 올바르지 않습니다.');
    }
    return MarketCandleSnapshot.fromJson(data);
  }

  Map<String, String> get _headers => {
    'Accept': 'application/json',
    if (accessToken.trim().isNotEmpty) 'Authorization': 'Bearer $accessToken',
  };

  Map<String, dynamic> _decodeResponse(http.Response response) {
    try {
      final decoded = jsonDecode(response.body) as Map<String, dynamic>;
      final success = decoded['success'] as bool? ?? false;
      if (response.statusCode >= 200 && response.statusCode < 300 && success) {
        return decoded;
      }

      final error = decoded['error'] as Map<String, dynamic>?;
      final message = error?['message'] as String?;
      throw MarketDataRepositoryException(message ?? '캔들 시세를 불러오지 못했습니다.');
    } on MarketDataRepositoryException {
      rethrow;
    } on FormatException {
      throw const MarketDataRepositoryException('캔들 시세 서버 응답을 해석하지 못했습니다.');
    }
  }
}
