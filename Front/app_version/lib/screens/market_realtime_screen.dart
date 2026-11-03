import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../models/market_realtime.dart';
import '../repositories/realtime_market_repository.dart';
import '../widgets/app_card.dart';

class MarketRealtimeScreen extends StatefulWidget {
  const MarketRealtimeScreen({
    super.key,
    required this.stockCode,
    required this.stockName,
    required this.repository,
    this.now,
  });
  final String stockCode, stockName;
  final RealtimeMarketRepository repository;
  final DateTime Function()? now;
  @override
  State<MarketRealtimeScreen> createState() => _MarketRealtimeScreenState();
}

class _MarketRealtimeScreenState extends State<MarketRealtimeScreen> {
  StreamSubscription<MarketRealtimeSnapshot>? _subscription;
  Timer? _clock;
  MarketRealtimeSnapshot? _snapshot;
  DateTime? _arrival;
  String? _error;
  @override
  void initState() {
    super.initState();
    _connect();
    _clock = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  void _connect() {
    _subscription?.cancel();
    _snapshot = null;
    _arrival = null;
    _error = null;
    _subscription = widget.repository
        .watch(widget.stockCode)
        .listen(
          (value) {
            if (mounted) {
              setState(() {
                _snapshot = value;
                _arrival = (widget.now?.call() ?? DateTime.now()).toUtc();
                _error = null;
              });
            }
          },
          onError: (Object e) {
            if (mounted) {
              setState(() {
                _snapshot = null;
                _error = '실시간 연결을 확인하지 못했습니다. 재연결을 기다립니다.';
              });
            }
          },
        );
  }

  @override
  void dispose() {
    _clock?.cancel();
    _subscription?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = _snapshot;
    final now = (widget.now?.call() ?? DateTime.now()).toUtc();
    final delayed =
        _arrival != null &&
        (now.difference(_arrival!).inSeconds > 5 ||
            (s != null && now.difference(s.checkedAt).inSeconds.abs() > 5));
    final live =
        s?.state == 'LIVE' &&
        !delayed &&
        _error == null &&
        s!.trade != null &&
        s.quote != null &&
        now.difference(s.trade!.marketTime).inSeconds <= s.staleSeconds &&
        now.difference(s.quote!.marketTime).inSeconds <= s.staleSeconds;
    return Scaffold(
      appBar: AppBar(
        title: Text('${widget.stockName} · KRX 실시간'),
        actions: [
          IconButton(
            tooltip: '연결 다시 확인',
            icon: const Icon(Icons.refresh),
            onPressed: () {
              setState(_connect);
            },
          ),
        ],
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1120),
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              AppCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('${widget.stockCode} · KIS · KRX · KRW'),
                    Text(
                      _error ?? (delayed ? '화면 수신 지연' : _label(s?.state)),
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    Text(
                      '${live ? '현재 관측 가격' : '마지막 관측 가격'}: ${s?.trade?.price ?? '미제공'}',
                      style: Theme.of(context).textTheme.headlineMedium,
                    ),
                    Text('체결 제공 시각: ${_time(s?.trade?.marketTime)}'),
                    Text('서버 수신 시각: ${_time(s?.trade?.receivedAt)}'),
                    const Text('서버에 설정한 구독 종목만 수신합니다. 접속 상태와 시세의 최신 여부는 다릅니다.'),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              AppCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '관측 체결 분봉',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const Text(
                      '관측한 체결만 집계합니다. 접속 전·단절 구간 누락을 복구한 전체 분봉이 아닙니다.',
                    ),
                    if (s == null || s.minutes.isEmpty)
                      const Padding(
                        padding: EdgeInsets.all(24),
                        child: Text('아직 관측한 분봉이 없습니다.'),
                      )
                    else ...[
                      SizedBox(
                        height: 180,
                        width: double.infinity,
                        child: CustomPaint(
                          painter: _MinuteLine(
                            s.minutes,
                            Theme.of(context).colorScheme.primary,
                          ),
                        ),
                      ),
                      Text(
                        '최근 분봉 ${_time(s.minutes.last.minute)} · 시가 ${s.minutes.last.open} · 고가 ${s.minutes.last.high} · 저가 ${s.minutes.last.low} · 종가 ${s.minutes.last.close} · 거래량 ${s.minutes.last.volume}',
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(height: 12),
              AppCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '10단계 호가',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    Text('호가 제공 시각: ${_time(s?.quote?.marketTime)}'),
                    if (s?.quote == null)
                      const Text('수신한 호가가 없습니다.')
                    else
                      for (var i = 0; i < 10; i++)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 4),
                          child: Wrap(
                            spacing: 16,
                            runSpacing: 4,
                            children: [
                              Text('${i + 1}단계'),
                              Text(
                                '매도 ${s!.quote!.asks[i].price} · 잔량 ${s.quote!.asks[i].quantity}',
                              ),
                              Text(
                                '매수 ${s.quote!.bids[i].price} · 잔량 ${s.quote!.bids[i].quantity}',
                              ),
                            ],
                          ),
                        ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              const Text(
                '기관·외국인·개인 수급은 이 스트림에 포함되지 않습니다. 누락 구간과 호가 날짜 추정이 있어 주문 가능 판정에 사용하지 않습니다.',
              ),
            ],
          ),
        ),
      ),
    );
  }
}

String _label(String? state) => switch (state) {
  'LIVE' => '시세 수신 중',
  'DISABLED' => '서버 실시간 수집 OFF',
  'NOT_SUBSCRIBED' => '서버 구독 종목 아님',
  'CONNECTING' => '공급자 연결 중',
  'SUBSCRIBING' => '구독 응답 대기',
  'WAITING_DATA' => '체결·호가 수신 대기',
  'STALE' => '시세 지연',
  'RECONNECTING' => '공급자 재연결 중',
  'FAILED' => '공급자 연결 점검 필요',
  _ => '서버 상태 수신 대기',
};
String _time(DateTime? at) {
  if (at == null) return '미제공';
  final k = at.toUtc().add(const Duration(hours: 9));
  String two(int x) => x.toString().padLeft(2, '0');
  return '${k.year}-${two(k.month)}-${two(k.day)} ${two(k.hour)}:${two(k.minute)}:${two(k.second)} (한국)';
}

class _MinuteLine extends CustomPainter {
  _MinuteLine(this.bars, this.color);
  final List<RealtimeMinute> bars;
  final Color color;
  @override
  void paint(Canvas canvas, Size size) {
    final values = bars.map((b) => double.parse(b.close)).toList();
    final low = values.reduce(math.min), high = values.reduce(math.max);
    final spread = high == low ? 1.0 : high - low;
    final path = Path();
    for (var i = 0; i < values.length; i++) {
      final x = values.length == 1
          ? size.width / 2
          : i * size.width / (values.length - 1);
      final y =
          size.height - 12 - (values[i] - low) / spread * (size.height - 24);
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
      if (values.length == 1) {
        canvas.drawCircle(Offset(x, y), 3, Paint()..color = color);
      }
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = color
        ..strokeWidth = 2
        ..style = PaintingStyle.stroke,
    );
  }

  @override
  bool shouldRepaint(_MinuteLine old) => old.bars != bars || old.color != color;
}
