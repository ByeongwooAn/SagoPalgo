package com.sagopalgo.api.order.mapper;

import com.sagopalgo.api.order.model.OrderPrecheckRecord;
import java.util.List;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/**
 * 주문 사전검증 감사 로그를 저장하고 조회합니다.
 */
@Mapper
public interface OrderPrecheckMapper {

    @Insert("""
        INSERT INTO order_prechecks (
          user_id, stock_code, stock_name, market, order_side, order_type,
          requested_price, quantity, estimated_amount, quote_provider,
          current_price, order_available_cash, orderable_quantity,
          order_enabled, eligible, blocker_summary, created_at
        ) VALUES (
          #{userId}, #{stockCode}, #{stockName}, #{market}, #{orderSide}, #{orderType},
          #{requestedPrice}, #{quantity}, #{estimatedAmount}, #{quoteProvider},
          #{currentPrice}, #{orderAvailableCash}, #{orderableQuantity},
          #{orderEnabled}, #{eligible}, #{blockerSummary}, #{createdAt}
        )
        """)
    @Options(useGeneratedKeys = true, keyProperty = "orderPrecheckId", keyColumn = "order_precheck_id")
    int insert(OrderPrecheckRecord record);

    @Select("""
        SELECT order_precheck_id, user_id, stock_code, stock_name, market,
               order_side, order_type, requested_price, quantity, estimated_amount,
               quote_provider, current_price, order_available_cash,
               orderable_quantity, order_enabled, eligible, blocker_summary, created_at
        FROM order_prechecks
        WHERE user_id = #{userId}
        ORDER BY created_at DESC, order_precheck_id DESC
        LIMIT #{limit}
        """)
    List<OrderPrecheckRecord> findRecentByUserId(
        @Param("userId") Long userId,
        @Param("limit") int limit
    );
}
