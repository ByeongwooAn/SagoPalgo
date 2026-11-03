Map<String, dynamic> realtimeJson({
  String state = 'LIVE',
  String price = '100.123456',
}) {
  final now = DateTime.now().toUtc().toIso8601String();
  return {
    'contractVersion': 'KIS_KRX_STREAM_V1',
    'staleSeconds': 15,
    'enabled': state != 'DISABLED',
    'provider': 'KIS',
    'exchange': 'KRX',
    'currency': 'KRW',
    'stockCode': '005930',
    'connectionState': state == 'LIVE' ? 'CONNECTED' : state,
    'state': state,
    'checkedAt': now,
    'gapDetected': true,
    'usableForTrading': false,
    'investorFlowStatus': 'NOT_SUBSCRIBED',
    if (state == 'LIVE' || state == 'STALE') ...{
      'trade': {
        'stockCode': '005930',
        'type': 'TRADE',
        'marketTime': now,
        'receivedAt': now,
        'price': price,
        'volume': '1',
        'asks': [],
        'bids': [],
      },
      'quote': {
        'stockCode': '005930',
        'type': 'QUOTE',
        'marketTime': now,
        'receivedAt': now,
        'asks': List.generate(
          10,
          (i) => {'price': '${101 + i}', 'quantity': '2'},
        ),
        'bids': List.generate(
          10,
          (i) => {'price': '${100 - i}', 'quantity': '3'},
        ),
      },
    },
    'minutes': state == 'LIVE'
        ? [
            {
              'minute': now,
              'open': price,
              'high': price,
              'low': price,
              'close': price,
              'volume': '100000000000000000001',
              'coverage': 'OBSERVED_ONLY',
            },
          ]
        : [],
  };
}

Map<String, dynamic> researchChangesJson({bool enabled = true}) => {
  'enabled': enabled,
  'nextAfterId': enabled ? 1 : 0,
  'items': enabled
      ? [
          {
            'changeId': 1,
            'kind': 'NEWS',
            'provider': 'NAVER_NEWS',
            'stockCode': '005930',
            'itemKey': 'key',
            'revision': 1,
            'origin': 'OBSERVED',
            'observedAt': DateTime.now().toUtc().toIso8601String(),
            'content': {
              'title': '수정 전 뉴스',
              'summary': '요약',
              'publishedAt': null,
              'link': 'https://news.test/article',
            },
          },
        ]
      : [],
};
