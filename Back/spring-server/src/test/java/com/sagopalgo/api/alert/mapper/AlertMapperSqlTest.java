package com.sagopalgo.api.alert.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import org.apache.ibatis.annotations.Select;
import org.junit.jupiter.api.Test;

class AlertMapperSqlTest {
    @Test
    void pendingQueryKeepsUserScopeAndUsesMonotonicCursor() throws Exception {
        String sql = String.join(" ", AlertMapper.class
            .getMethod("findPending", Long.class, int.class, Long.class)
            .getAnnotation(Select.class).value());

        assertThat(sql).contains("user_id = #{userId}");
        assertThat(sql).contains("sent_at IS NULL");
        assertThat(sql).contains("alert_id > #{afterAlertId}");
        assertThat(sql).contains("ORDER BY alert_id");
    }
}
