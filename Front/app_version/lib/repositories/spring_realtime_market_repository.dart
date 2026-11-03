import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config/api_config.dart';
import '../models/market_realtime.dart';
import 'market_data_repository.dart';
import 'realtime_market_repository.dart';

class SpringRealtimeMarketRepository implements RealtimeMarketRepository {
  SpringRealtimeMarketRepository({
    required this.accessToken,
    required this.config,
    http.Client Function()? clientFactory,
    this.retryDelay = const Duration(seconds: 1),
  }) : clientFactory = clientFactory ?? http.Client.new;
  final String accessToken;
  final ApiConfig config;
  final http.Client Function() clientFactory;
  final Duration retryDelay;
  @override
  Stream<MarketRealtimeSnapshot> watch(String stockCode) {
    if (!RegExp(r'^\d{6}$').hasMatch(stockCode)) {
      return Stream.error(
        const MarketDataRepositoryException('6자리 KRX 종목코드를 선택하세요.'),
      );
    }
    late StreamController<MarketRealtimeSnapshot> controller;
    http.Client? client;
    Timer? retry;
    StreamIterator<String>? lines;
    bool closed = false;
    int failures = 0;
    Future<void> connect() async {
      if (closed) return;
      final current = clientFactory();
      client = current;
      try {
        final request = http.Request(
          'GET',
          Uri.parse(
            '${config.baseUrl}/api/v1/market/realtime/events',
          ).replace(queryParameters: {'stockCode': stockCode}),
        );
        request.headers['Accept'] = 'text/event-stream';
        if (accessToken.isNotEmpty) {
          request.headers['Authorization'] = 'Bearer $accessToken';
        }
        final response = await current
            .send(request)
            .timeout(const Duration(seconds: 15));
        if (response.statusCode != 200 ||
            !(response.headers['content-type'] ?? '').startsWith(
              'text/event-stream',
            )) {
          throw const FormatException();
        }
        var data = StringBuffer();
        var pendingBytes = 0;
        String? event;
        final iterator = StreamIterator(
          response.stream
              .transform(
                StreamTransformer<List<int>, List<int>>.fromHandlers(
                  handleData: (chunk, sink) {
                    pendingBytes += chunk.length;
                    if (pendingBytes > 524288) {
                      sink.addError(const FormatException());
                    } else {
                      sink.add(chunk);
                    }
                  },
                ),
              )
              .transform(utf8.decoder)
              .transform(const LineSplitter())
              .timeout(const Duration(seconds: 20)),
        );
        lines = iterator;
        while (await iterator.moveNext()) {
          final line = iterator.current;
          if (closed) break;
          if (line.isEmpty) {
            pendingBytes = 0;
            if (event == 'snapshot' && data.isNotEmpty) {
              final value = MarketRealtimeSnapshot.fromJson(
                jsonDecode(data.toString()) as Map<String, dynamic>,
              );
              if (value.stockCode != stockCode) throw const FormatException();
              failures = 0;
              controller.add(value);
            }
            event = null;
            data = StringBuffer();
          } else if (line.startsWith('event:')) {
            event = line.substring(6).trim();
          } else if (line.startsWith('data:')) {
            if (data.isNotEmpty) data.write('\n');
            data.write(line.substring(5).trimLeft());
            if (data.length > 262144) throw const FormatException();
          }
        }
        if (!closed) {
          controller.addError(
            const MarketDataRepositoryException('실시간 연결이 종료되어 다시 연결합니다.'),
          );
        }
      } catch (_) {
        if (!closed) {
          controller.addError(
            const MarketDataRepositoryException(
              '실시간 연결을 확인하지 못했습니다. 다시 연결합니다.',
            ),
          );
        }
      } finally {
        await lines?.cancel();
        lines = null;
        current.close();
        if (identical(client, current)) client = null;
        if (!closed) {
          failures = (failures + 1).clamp(1, 5);
          retry = Timer(retryDelay * (1 << (failures - 1)), connect);
        }
      }
    }

    controller = StreamController(
      onListen: connect,
      onCancel: () {
        closed = true;
        retry?.cancel();
        client?.close();
        lines?.cancel();
      },
    );
    return controller.stream;
  }
}
