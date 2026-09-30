package com.sagopalgo.api.order.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDateTime;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Update;
import org.junit.jupiter.api.Test;

class OrderApprovalMapperSqlTest {
    @Test
    void storesAccountFingerprintAndRequiresItWhenAcknowledging() throws Exception {
        String insert = String.join(" ", OrderApprovalMapper.class.getMethod("insert",
            com.sagopalgo.api.order.model.OrderApprovalRecord.class).getAnnotation(Insert.class).value());
        String acknowledge = String.join(" ", OrderApprovalMapper.class.getMethod("acknowledge",
            Long.class, Long.class, String.class, String.class, LocalDateTime.class)
            .getAnnotation(Update.class).value());

        assertThat(insert).contains("account_fingerprint", "#{accountFingerprint}");
        assertThat(acknowledge).contains("account_fingerprint = #{accountFingerprint}");
    }
}
