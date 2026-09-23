package com.sagopalgo.api.order.mapper;

import com.sagopalgo.api.order.model.OrderDateReconciliationCheckRecord;
import java.util.List;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface OrderDateReconciliationCheckMapper {
    @Insert("""
        INSERT INTO order_date_reconciliation_checks (
          order_approval_id, user_id, order_date, complete_scan,
          pages_scanned, row_count, item_limit_reached, checked_at
        ) VALUES (
          #{orderApprovalId}, #{userId}, #{orderDate}, #{completeScan},
          #{pagesScanned}, #{rowCount}, #{itemLimitReached}, #{checkedAt}
        )
        """)
    @Options(useGeneratedKeys = true, keyProperty = "orderDateReconciliationCheckId",
        keyColumn = "order_date_reconciliation_check_id")
    int insert(OrderDateReconciliationCheckRecord record);

    @Select("""
        SELECT order_date_reconciliation_check_id, order_approval_id, user_id,
               order_date, complete_scan, pages_scanned, row_count,
               item_limit_reached, checked_at
        FROM order_date_reconciliation_checks
        WHERE order_approval_id = #{approvalId} AND user_id = #{userId}
        ORDER BY checked_at DESC, order_date_reconciliation_check_id DESC
        LIMIT 20
        """)
    List<OrderDateReconciliationCheckRecord> findRecentByApprovalId(
        @Param("approvalId") Long approvalId,
        @Param("userId") Long userId
    );
}
