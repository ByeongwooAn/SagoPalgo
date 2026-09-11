package com.sagopalgo.api.watchlist.mapper;

import com.sagopalgo.api.watchlist.model.WatchlistItem;
import java.util.List;
import java.util.Optional;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

/**
 * watchlist 테이블에 접근하는 MyBatis Mapper입니다.
 */
@Mapper
public interface WatchlistMapper {

    @Select("""
        SELECT watchlist_id, user_id, stock_code, stock_name, market, alert_enabled, created_at, updated_at
        FROM watchlist
        WHERE user_id = #{userId}
        ORDER BY created_at DESC, watchlist_id DESC
        """)
    List<WatchlistItem> findAllByUserId(@Param("userId") Long userId);

    @Select("""
        SELECT watchlist_id, user_id, stock_code, stock_name, market, alert_enabled, created_at, updated_at
        FROM watchlist
        WHERE watchlist_id = #{watchlistId}
          AND user_id = #{userId}
        """)
    Optional<WatchlistItem> findByIdAndUserId(
        @Param("watchlistId") Long watchlistId,
        @Param("userId") Long userId
    );

    @Select("""
        SELECT COUNT(1)
        FROM watchlist
        WHERE user_id = #{userId}
          AND stock_code = #{stockCode}
          AND market = #{market}
        """)
    boolean existsByUserStockAndMarket(
        @Param("userId") Long userId,
        @Param("stockCode") String stockCode,
        @Param("market") String market
    );

    @Insert("""
        INSERT INTO watchlist (user_id, stock_code, stock_name, market, alert_enabled)
        VALUES (#{userId}, #{stockCode}, #{stockName}, #{market}, #{alertEnabled})
        """)
    @Options(useGeneratedKeys = true, keyProperty = "watchlistId", keyColumn = "watchlist_id")
    int insert(WatchlistItem item);

    @Update("""
        UPDATE watchlist
        SET alert_enabled = #{alertEnabled}
        WHERE watchlist_id = #{watchlistId}
          AND user_id = #{userId}
        """)
    int updateAlertEnabled(
        @Param("watchlistId") Long watchlistId,
        @Param("userId") Long userId,
        @Param("alertEnabled") Boolean alertEnabled
    );

    @Delete("""
        DELETE FROM watchlist
        WHERE watchlist_id = #{watchlistId}
          AND user_id = #{userId}
        """)
    int deleteByIdAndUserId(
        @Param("watchlistId") Long watchlistId,
        @Param("userId") Long userId
    );
}
