package com.sagopalgo.api.papertrading.mapper;

import com.sagopalgo.api.papertrading.model.PaperTradeRecord;
import java.math.BigDecimal;
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

    @Select("SELECT user_id FROM users WHERE user_id = #{userId} FOR UPDATE")
    Long lockUser(@Param("userId") Long userId);

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

    @Select("SELECT initial_capital FROM paper_us_accounts WHERE user_id = #{userId}")
    BigDecimal findUsCapital(@Param("userId") Long userId);

    @Insert("INSERT INTO paper_us_accounts (user_id, initial_capital) VALUES (#{userId}, #{capital})")
    int insertUsAccount(@Param("userId") Long userId, @Param("capital") BigDecimal capital);

    @Insert("""
        INSERT INTO paper_us_trades (
          user_id, request_id, stock_code, stock_name, market, trade_type,
          trade_price, quantity, realized_profit, trade_date, memo
        ) VALUES (
          #{userId}, #{requestId}, #{stockCode}, #{stockName}, #{market}, #{tradeType},
          #{tradePrice}, #{quantity}, #{realizedProfit}, #{tradeDate}, #{memo}
        )
        """)
    @Options(useGeneratedKeys = true, keyProperty = "tradeRecordId", keyColumn = "trade_record_id")
    int insertUsTrade(PaperTradeRecord record);

    @Select("""
        SELECT trade_record_id, user_id, request_id, stock_code, stock_name, market,
               trade_type, trade_price, quantity, realized_profit, trade_date, memo
        FROM paper_us_trades
        WHERE user_id = #{userId}
        ORDER BY trade_record_id
        """)
    List<PaperTradeRecord> findUsTrades(@Param("userId") Long userId);
}
