class ResearchChange {
  ResearchChange(Map<String, dynamic> json)
    : id = _positive(json['changeId']),
      revision = _positive(json['revision']),
      kind = json['kind'] as String,
      provider = json['provider'] as String,
      stockCode = json['stockCode'] as String,
      origin = json['origin'] as String,
      observedAt = DateTime.parse(json['observedAt'] as String).toUtc(),
      content = Map<String, dynamic>.unmodifiable(
        json['content'] as Map<String, dynamic>,
      ) {
    if (!['NEWS', 'DISCLOSURE'].contains(kind) ||
        !['LEGACY_BASELINE', 'OBSERVED'].contains(origin) ||
        !RegExp(r'(Z|[+-]\d{2}:\d{2})$').hasMatch(json['observedAt'] as String)) {
      throw const FormatException();
    }
  }
  final int id, revision;
  final String kind, provider, stockCode, origin;
  final DateTime observedAt;
  final Map<String, dynamic> content;
}

class ResearchChangesPage {
  ResearchChangesPage.fromJson(Map<String, dynamic> json)
    : enabled = json['enabled'] as bool,
      nextAfterId = json['nextAfterId'] as int,
      items = (json['items'] as List)
          .map((x) => ResearchChange(x as Map<String, dynamic>))
          .toList() {
    if (nextAfterId < 0 || items.length > 100 || (!enabled && items.isNotEmpty)) {
      throw const FormatException();
    }
  }
  final bool enabled;
  final int nextAfterId;
  final List<ResearchChange> items;
}

int _positive(dynamic x) {
  if (x is! int || x < 1) throw const FormatException();
  return x;
}
