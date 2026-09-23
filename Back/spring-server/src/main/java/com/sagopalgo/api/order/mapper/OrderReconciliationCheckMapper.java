package com.sagopalgo.api.order.mapper;

import com.sagopalgo.api.order.model.OrderReconciliationCheckRecord;
import java.util.List;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface OrderReconciliationCheckMapper {
    @Insert("""
        INSERT INTO order_reconciliation_checks (
          order_approval_id, user_id, order_date, order_no, complete_scan,
          pages_scanned, match_count, review_status, checked_at
        ) VALUES (
          #{orderApprovalId}, #{userId}, #{orderDate}, #{orderNo}, #{completeScan},
          #{pagesScanned}, #{matchCount}, #{reviewStatus}, #{checkedAt}
        )
        """)
    @Options(useGeneratedKeys = true, keyProperty = "orderReconciliationCheckId",
        keyColumn = "order_reconciliation_check_id")
    int insert(OrderReconciliationCheckRecord record);

    @Select("""
        SELECT order_reconciliation_check_id, order_approval_id, user_id, order_date,
               order_no, complete_scan, pages_scanned, match_count, review_status, checked_at
        FROM order_reconciliation_checks
        WHERE order_approval_id = #{approvalId} AND user_id = #{userId}
        ORDER BY checked_at DESC, order_reconciliation_check_id DESC
        LIMIT 20
        """)
    List<OrderReconciliationCheckRecord> findRecentByApprovalId(
        @Param("approvalId") Long approvalId,
        @Param("userId") Long userId
    );
}
