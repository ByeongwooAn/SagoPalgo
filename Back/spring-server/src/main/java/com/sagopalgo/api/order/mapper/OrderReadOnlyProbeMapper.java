package com.sagopalgo.api.order.mapper;

import com.sagopalgo.api.order.model.OrderReadOnlyProbeRecord;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import org.apache.ibatis.annotations.Arg;
import org.apache.ibatis.annotations.ConstructorArgs;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface OrderReadOnlyProbeMapper {
    @Insert("""
        INSERT INTO order_read_only_probe_checks (user_id, status, order_date, checked_at)
        VALUES (#{userId}, #{status}, #{orderDate}, #{checkedAt})
        """)
    int insert(OrderReadOnlyProbeRecord record);

    @Select("""
        SELECT user_id, status, order_date, checked_at
        FROM order_read_only_probe_checks
        WHERE user_id = #{userId}
        ORDER BY checked_at DESC, probe_check_id DESC
        LIMIT 1
        """)
    @ConstructorArgs({
        @Arg(column = "user_id", javaType = Long.class),
        @Arg(column = "status", javaType = String.class),
        @Arg(column = "order_date", javaType = String.class),
        @Arg(column = "checked_at", javaType = LocalDateTime.class)
    })
    Optional<OrderReadOnlyProbeRecord> findLatest(Long userId);

    @Select("""
        SELECT user_id, status, order_date, checked_at
        FROM order_read_only_probe_checks
        WHERE user_id = #{userId}
        ORDER BY checked_at DESC, probe_check_id DESC
        LIMIT 10
        """)
    @ConstructorArgs({
        @Arg(column = "user_id", javaType = Long.class),
        @Arg(column = "status", javaType = String.class),
        @Arg(column = "order_date", javaType = String.class),
        @Arg(column = "checked_at", javaType = LocalDateTime.class)
    })
    List<OrderReadOnlyProbeRecord> findRecent(Long userId);
}
