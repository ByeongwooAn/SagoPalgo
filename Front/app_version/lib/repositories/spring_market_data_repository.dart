import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/market_candle.dart';
import '../models/recommendation.dart';
import 'market_data_repository.dart';
import 'realtime_market_repository.dart';
import 'spring_realtime_market_repository.dart';

/// Spring Boot 시장 데이터 API에서 정규화된 캔들을 조회합니다.
class SpringMarketDataRepository
    implements
        MarketDataRepository,
        RealtimeMarketAccess,
        UsStockLookup,
        UsDailySignalAccess {
  @override
  RealtimeMarketRepository get realtime =>
      SpringRealtimeMarketRepository(accessToken: accessToken, config: config);
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
  Future<DailyModelSignal> fetchUsDailySignal(
    String ticker,
    String market,
  ) async {
    final data = await _fetchStock(ticker, market, 'daily-signal');
    return DailyModelSignal.fromJson(data);
  }

  @override
  Future<({String provider, double price})> fetchUsQuote(
    String ticker,
    String market,
  ) async {
    final data = await _fetchStock(ticker, market, 'quote');
    final price = double.tryParse(data['currentPrice'].toString());
    final provider = data['provider'];
    if (data['stockCode'] != ticker ||
        data['market'] != market ||
        data['currency'] != 'USD' ||
        price == null ||
        !price.isFinite ||
        price <= 0 ||
        provider is! String ||
        provider.isEmpty) {
      throw const MarketDataRepositoryException('미국주식 현재가 응답 형식이 올바르지 않습니다.');
    }
    return (provider: provider, price: price);
  }

  @override
  Future<String> fetchUsStockName(String ticker, String market) async {
    final data = await _fetchStock(ticker, market);
    final name = data['stockName'];
    if (data['stockCode'] != ticker ||
        data['market'] != market ||
        data['currency'] != 'USD' ||
        name is! String ||
        name.trim().isEmpty) {
      throw const MarketDataRepositoryException('미국주식 종목정보 응답 형식이 올바르지 않습니다.');
    }
    return name;
  }

  Future<Map<String, dynamic>> _fetchStock(
    String ticker,
    String market, [
    String? operation,
  ]) async {
    final base = Uri.parse(config.marketStocksUrl);
    final uri = base.replace(
      pathSegments: [...base.pathSegments, ticker, ?operation],
      queryParameters: {'market': market},
    );
    final response = await client.get(uri, headers: _headers);
    return _responseData(response);
  }

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
    return MarketCandleSnapshot.fromJson(_responseData(response));
  }

  Map<String, dynamic> _responseData(http.Response response) {
    final data = _decodeResponse(response)['data'];
    if (data is! Map<String, dynamic>) {
      throw const MarketDataRepositoryException('시장 데이터 응답 형식이 올바르지 않습니다.');
    }
    return data;
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
      throw MarketDataRepositoryException(message ?? '시장 데이터를 불러오지 못했습니다.');
    } on MarketDataRepositoryException {
      rethrow;
    } on FormatException {
      throw const MarketDataRepositoryException('시장 데이터 서버 응답을 해석하지 못했습니다.');
    }
  }
}
