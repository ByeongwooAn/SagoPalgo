class RealtimeLevel {
  RealtimeLevel(Map<String, dynamic> json)
    : price = _number(json['price']),
      quantity = _integerText(json['quantity']);
  final String price, quantity;
}

class RealtimeEvent {
  RealtimeEvent(Map<String, dynamic> json)
    : stockCode = _text(json['stockCode']),
      type = _choice(json['type'], ['TRADE', 'QUOTE']),
      marketTime = _time(json['marketTime']),
      receivedAt = _time(json['receivedAt']),
      price = json['price'] == null ? null : _number(json['price']),
      volume = json['volume'] == null ? null : _integerText(json['volume']),
      asks = _list(json['asks']).map((e) => RealtimeLevel(_object(e))).toList(),
      bids = _list(
        json['bids'],
      ).map((e) => RealtimeLevel(_object(e))).toList() {
    if ((type == 'TRADE' && (price == null || volume == null)) ||
        (type == 'QUOTE' && (asks.length != 10 || bids.length != 10))) {
      throw const FormatException('실시간 구간 계약 오류');
    }
  }
  final String stockCode, type;
  final DateTime marketTime, receivedAt;
  final String? price, volume;
  final List<RealtimeLevel> asks, bids;
}

class RealtimeMinute {
  RealtimeMinute(Map<String, dynamic> json)
    : minute = _time(json['minute']),
      open = _number(json['open']),
      high = _number(json['high']),
      low = _number(json['low']),
      close = _number(json['close']),
      volume = _integerText(json['volume']) {
    if (json['coverage'] != 'OBSERVED_ONLY') {
      throw const FormatException('분봉 범위 오류');
    }
  }
  final DateTime minute;
  final String open, high, low, close, volume;
}

class MarketRealtimeSnapshot {
  MarketRealtimeSnapshot.fromJson(Map<String, dynamic> json)
    : stockCode = _text(json['stockCode']),
      enabled = _bool(json['enabled']),
      staleSeconds = json['staleSeconds'] as int,
      state = _choice(json['state'], [
        'DISABLED',
        'NOT_SUBSCRIBED',
        'CONNECTING',
        'SUBSCRIBING',
        'CONNECTED',
        'RECONNECTING',
        'FAILED',
        'WAITING_DATA',
        'LIVE',
        'STALE',
      ]),
      checkedAt = _time(json['checkedAt']),
      trade = json['trade'] == null
          ? null
          : RealtimeEvent(_object(json['trade'])),
      quote = json['quote'] == null
          ? null
          : RealtimeEvent(_object(json['quote'])),
      minutes = _list(
        json['minutes'],
      ).map((e) => RealtimeMinute(_object(e))).toList() {
    if (staleSeconds < 5 ||
        staleSeconds > 300 ||
        json['contractVersion'] != 'KIS_KRX_STREAM_V1' ||
        json['provider'] != 'KIS' ||
        json['exchange'] != 'KRX' ||
        json['currency'] != 'KRW' ||
        json['usableForTrading'] != false ||
        json['gapDetected'] is! bool ||
        !RegExp(r'^\d{6}$').hasMatch(stockCode) ||
        minutes.length > 120 ||
        (trade != null &&
            (trade!.stockCode != stockCode || trade!.type != 'TRADE')) ||
        (quote != null &&
            (quote!.stockCode != stockCode || quote!.type != 'QUOTE')) ||
        (state == 'LIVE' &&
            (!enabled ||
                trade == null ||
                quote == null ||
                json['connectionState'] != 'CONNECTED'))) {
      throw const FormatException('실시간 시세 계약 오류');
    }
  }
  final String stockCode, state;
  final bool enabled;
  final int staleSeconds;
  final DateTime checkedAt;
  final RealtimeEvent? trade, quote;
  final List<RealtimeMinute> minutes;
}

Map<String, dynamic> _object(dynamic x) {
  if (x is! Map<String, dynamic>) throw const FormatException();
  return x;
}

List<dynamic> _list(dynamic x) {
  if (x is! List) throw const FormatException();
  return x;
}

String _text(dynamic x) {
  if (x is! String) throw const FormatException();
  return x;
}

bool _bool(dynamic x) {
  if (x is! bool) throw const FormatException();
  return x;
}

String _number(dynamic x) {
  final s = _text(x);
  if (!RegExp(r'^\d{1,24}(\.\d{1,6})?$').hasMatch(s)) {
    throw const FormatException();
  }
  return s;
}

String _integerText(dynamic x) {
  final s = _text(x);
  if (!RegExp(r'^\d{1,30}$').hasMatch(s)) throw const FormatException();
  return s;
}

String _choice(dynamic x, List<String> allowed) {
  final s = _text(x);
  if (!allowed.contains(s)) throw const FormatException();
  return s;
}

DateTime _time(dynamic x) {
  final s = _text(x);
  if (!RegExp(r'(Z|[+-]\d{2}:\d{2})$').hasMatch(s)) {
    throw const FormatException();
  }
  return DateTime.parse(s).toUtc();
}
