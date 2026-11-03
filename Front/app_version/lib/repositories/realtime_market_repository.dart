import '../models/market_realtime.dart';

abstract class RealtimeMarketRepository {
  Stream<MarketRealtimeSnapshot> watch(String stockCode);
}

abstract class RealtimeMarketAccess {
  RealtimeMarketRepository get realtime;
}
