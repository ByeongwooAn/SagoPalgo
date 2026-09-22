package com.sagopalgo.api.papertrading.mapper;

import com.sagopalgo.api.papertrading.model.PaperTradeRecord;
import java.util.List;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/**
 * PAPER 실행 모드의 가상 거래 원장을 저장하고 조회합니다.
 */
@Mapper
public interface PaperTradeMapper {

    @Insert("""
        INSERT INTO trade_records (
          user_id, recommendation_id, stock_code, stock_name, market,
          trade_type, execution_mode, trade_price, quantity, realized_profit,
          trade_date, memo
        ) VALUES (
          #{userId}, #{recommendationId}, #{stockCode}, #{stockName}, #{market},
          #{tradeType}, 'PAPER', #{tradePrice}, #{quantity}, #{realizedProfit},
          #{tradeDate}, #{memo}
        )
        """)
    @Options(useGeneratedKeys = true, keyProperty = "tradeRecordId", keyColumn = "trade_record_id")
    int insert(PaperTradeRecord record);

    @Select("""
        SELECT trade_record_id, user_id, recommendation_id, stock_code, stock_name,
               market, trade_type, execution_mode, trade_price, quantity,
               realized_profit, trade_date, memo, created_at
        FROM trade_records
        WHERE user_id = #{userId}
          AND execution_mode = 'PAPER'
        ORDER BY trade_date, trade_record_id
        """)
    List<PaperTradeRecord> findAllByUserId(@Param("userId") Long userId);
}
