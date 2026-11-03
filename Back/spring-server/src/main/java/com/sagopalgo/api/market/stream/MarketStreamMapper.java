package com.sagopalgo.api.market.stream;

import java.time.LocalDateTime;
import java.util.List;
import org.apache.ibatis.annotations.*;

@Mapper
public interface MarketStreamMapper {
    @Select("SELECT (SELECT COUNT(*) FROM market_stream_events WHERE 1=0)+(SELECT COUNT(*) FROM market_stream_minutes WHERE 1=0)") int verify();
    @Insert("INSERT IGNORE INTO market_stream_events(event_id,stock_code,event_type,market_at,received_at,payload) VALUES(#{id},#{stock},#{type},#{at},#{received},#{json})")
    int insert(@Param("id") String id,@Param("stock") String stock,@Param("type") String type,
        @Param("at") LocalDateTime at,@Param("received") LocalDateTime received,@Param("json") String json);
    @Select("SELECT payload FROM market_stream_events WHERE event_id=#{id}") String event(String id);
    @Insert("INSERT IGNORE INTO market_stream_minutes(stock_code,minute_at,payload) VALUES(#{stock},#{at},#{json})")
    int seed(@Param("stock") String stock,@Param("at") LocalDateTime at,@Param("json") String json);
    @Select("SELECT payload FROM market_stream_minutes WHERE stock_code=#{stock} AND minute_at=#{at} FOR UPDATE")
    String lock(@Param("stock") String stock,@Param("at") LocalDateTime at);
    @Update("UPDATE market_stream_minutes SET payload=#{json} WHERE stock_code=#{stock} AND minute_at=#{at}")
    int update(@Param("stock") String stock,@Param("at") LocalDateTime at,@Param("json") String json);
    @Select("SELECT payload FROM market_stream_minutes WHERE stock_code=#{stock} AND minute_at>=#{from} ORDER BY minute_at DESC LIMIT 120")
    List<String> minutes(@Param("stock") String stock,@Param("from") LocalDateTime from);
}
