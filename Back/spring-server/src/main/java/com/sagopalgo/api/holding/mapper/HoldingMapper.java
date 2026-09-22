package com.sagopalgo.api.holding.mapper;

import com.sagopalgo.api.holding.model.Holding;
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
 * holdings 테이블에 접근하는 MyBatis Mapper입니다.
 */
@Mapper
public interface HoldingMapper {

    @Select("""
        SELECT holding_id, user_id, stock_code, stock_name, market, buy_price, quantity,
               buy_date, stop_loss_rate, take_profit_rate, status, created_at, updated_at
        FROM holdings
        WHERE user_id = #{userId}
          AND status <> 'SOLD'
        ORDER BY created_at DESC, holding_id DESC
        """)
    List<Holding> findActiveByUserId(@Param("userId") Long userId);

    @Select("""
        SELECT holding_id
        FROM holdings
        WHERE user_id = #{userId}
          AND status != 'SOLD'
        ORDER BY holding_id
        """)
    List<Long> findActiveIdsByUserId(@Param("userId") Long userId);

    @Select("""
        SELECT holding_id, user_id, stock_code, stock_name, market, buy_price, quantity,
               buy_date, stop_loss_rate, take_profit_rate, status, created_at, updated_at
        FROM holdings
        WHERE holding_id = #{holdingId}
          AND user_id = #{userId}
        """)
    Optional<Holding> findByIdAndUserId(
        @Param("holdingId") Long holdingId,
        @Param("userId") Long userId
    );

    @Insert("""
        INSERT INTO holdings (
            user_id, stock_code, stock_name, market, buy_price, quantity,
            buy_date, stop_loss_rate, take_profit_rate, status
        )
        VALUES (
            #{userId}, #{stockCode}, #{stockName}, #{market}, #{buyPrice}, #{quantity},
            #{buyDate}, #{stopLossRate}, #{takeProfitRate}, #{status}
        )
        """)
    @Options(useGeneratedKeys = true, keyProperty = "holdingId", keyColumn = "holding_id")
    int insert(Holding holding);

    @Update("""
        UPDATE holdings
        SET stock_code = #{stockCode},
            stock_name = #{stockName},
            market = #{market},
            buy_price = #{buyPrice},
            quantity = #{quantity},
            buy_date = #{buyDate},
            stop_loss_rate = #{stopLossRate},
            take_profit_rate = #{takeProfitRate}
        WHERE holding_id = #{holdingId}
          AND user_id = #{userId}
        """)
    int updateByIdAndUserId(Holding holding);

    @Delete("""
        DELETE FROM holdings
        WHERE holding_id = #{holdingId}
          AND user_id = #{userId}
        """)
    int deleteByIdAndUserId(
        @Param("holdingId") Long holdingId,
        @Param("userId") Long userId
    );
}
