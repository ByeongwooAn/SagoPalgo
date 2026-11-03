package com.sagopalgo.api.research.mapper;

import java.time.*;
import java.util.List;
import org.apache.ibatis.annotations.*;

@Mapper
public interface ResearchJournalMapper {
    record Head(long revision,String hash) {}
    record Version(long changeId,String kind,String provider,String stockCode,String itemKey,
        long revision,String contentHash,String payload,LocalDateTime observedAt,String origin) {}
    record Coverage(String provider,String stockCode,String scope,LocalDate throughDate) {}
    @Select("SELECT last_id FROM research_journal_clock WHERE singleton=1 FOR UPDATE") Long lockClock();
    @Select("SELECT (SELECT COUNT(*) FROM research_journal_clock WHERE singleton=1)+(SELECT COUNT(*) FROM research_versions WHERE 1=0)+(SELECT COUNT(*) FROM research_item_heads WHERE 1=0)+(SELECT COUNT(*) FROM research_checkpoints WHERE 1=0)") int verify();
    @Update("UPDATE research_journal_clock SET last_id=#{id} WHERE singleton=1") int advance(long id);
    @Insert("INSERT IGNORE INTO research_item_heads(kind,provider,stock_code,item_key,revision) VALUES(#{kind},#{provider},#{stock},#{key},0)")
    int seed(@Param("kind") String kind,@Param("provider") String provider,@Param("stock") String stock,@Param("key") String key);
    @Select("SELECT revision,content_hash FROM research_item_heads WHERE kind=#{kind} AND provider=#{provider} AND stock_code=#{stock} AND item_key=#{key} FOR UPDATE")
    @ConstructorArgs({@Arg(column="revision",javaType=long.class),@Arg(column="content_hash",javaType=String.class)})
    Head head(@Param("kind") String kind,@Param("provider") String provider,@Param("stock") String stock,@Param("key") String key);
    @Update("UPDATE research_item_heads SET revision=#{revision},content_hash=#{hash} WHERE kind=#{kind} AND provider=#{provider} AND stock_code=#{stock} AND item_key=#{key}")
    int update(@Param("kind") String kind,@Param("provider") String provider,@Param("stock") String stock,@Param("key") String key,@Param("revision") long revision,@Param("hash") String hash);
    @Insert("INSERT INTO research_versions(change_id,kind,provider,stock_code,item_key,revision,content_hash,payload,observed_at,origin) VALUES(#{changeId},#{kind},#{provider},#{stockCode},#{itemKey},#{revision},#{contentHash},#{payload},UTC_TIMESTAMP(6),#{origin})")
    int insert(Version value);
    @Select("SELECT through_date FROM research_checkpoints WHERE provider=#{provider} AND stock_code=#{stock} AND scope_key=#{scope}")
    LocalDate loadCheckpoint(@Param("provider") String provider,@Param("stock") String stock,@Param("scope") String scope);
    @Insert("INSERT INTO research_checkpoints(provider,stock_code,scope_key,through_date,updated_at) VALUES(#{provider},#{stockCode},#{scope},#{throughDate},UTC_TIMESTAMP(6)) ON DUPLICATE KEY UPDATE through_date=IF(scope_key=VALUES(scope_key),GREATEST(through_date,VALUES(through_date)),VALUES(through_date)),scope_key=VALUES(scope_key),updated_at=UTC_TIMESTAMP(6)")
    int saveCheckpoint(Coverage coverage);
    @Select("SELECT change_id,kind,provider,stock_code,item_key,revision,content_hash,payload,observed_at,origin FROM research_versions WHERE stock_code=#{stock} AND change_id>#{after} ORDER BY change_id LIMIT #{limit}")
    List<Version> changes(@Param("stock") String stock,@Param("after") long after,@Param("limit") int limit);
}
