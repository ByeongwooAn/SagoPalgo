package com.sagopalgo.api.research.service;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.research.export.*;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.*;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.annotation.*;

class StoredDatasetExportTest {
    final Instant from = Instant.parse("2025-11-03T00:00:00Z");
    final Instant to = from.plusSeconds(120);
    @Test void invalidScopeNeverReadsDatabase() {
        var jdbc = mock(JdbcTemplate.class);
        var service = new StoredDatasetExportService(jdbc, new ObjectMapper());
        for (String stock : List.of("../bad", "123", "005930 "))
            assertThatThrownBy(() -> service.export(stock, from, to)).isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> service.export("005930", to, from)).isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> service.export("005930", from.plusSeconds(1), to)).isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> service.export("005930", from, from.plusSeconds(86460))).isInstanceOf(ApiException.class);
        verifyNoInteractions(jdbc);
    }
    @Test void transactionDeclaresSingleReadOnlyRepeatableReadSnapshot() throws Exception {
        var annotation = StoredDatasetExportService.class.getMethod("export", String.class, Instant.class, Instant.class).getAnnotation(Transactional.class);
        assertThat(annotation.readOnly()).isTrue();
        assertThat(annotation.isolation()).isEqualTo(Isolation.REPEATABLE_READ);
        assertThat(annotation.timeout()).isEqualTo(30);
    }
    @Test void storageFailureDoesNotExposeSqlOrExternalMessages() {
        var jdbc = mock(JdbcTemplate.class);
        when(jdbc.queryForObject("SELECT UTC_TIMESTAMP(6)", LocalDateTime.class)).thenThrow(new IllegalStateException("private-password"));
        var service = new StoredDatasetExportService(jdbc, new ObjectMapper());
        assertThatThrownBy(() -> service.export("005930", from, to)).isInstanceOf(ApiException.class)
            .hasMessage("저장 자료의 025·026 적용 상태와 무결성을 확인하세요.");
    }
    @Test void futureWindowDoesNotReadDataTables() {
        var jdbc = mock(JdbcTemplate.class);
        when(jdbc.queryForObject("SELECT UTC_TIMESTAMP(6)", LocalDateTime.class)).thenReturn(LocalDateTime.ofInstant(from, ZoneOffset.UTC));
        var service = new StoredDatasetExportService(jdbc, new ObjectMapper());
        assertThatThrownBy(() -> service.export("005930", from, to)).isInstanceOf(ApiException.class).hasMessage("종료된 구간만 내보낼 수 있습니다.");
        verify(jdbc).queryForObject("SELECT UTC_TIMESTAMP(6)", LocalDateTime.class);
        verifyNoMoreInteractions(jdbc);
    }
    @Test void controllerIsGetOnlyNoStoreAndKeepsObservationSemantics() throws Exception {
        var service = mock(StoredDatasetExportService.class);
        when(service.export("005930", from, to)).thenReturn(new StoredDatasetExportService.Snapshot(
            "SAGOPALGO_STORED_EXPORT_V1", "005930", from, to, to.plusSeconds(60), true, false,
            "REPEATABLE_READ", "OBSERVED_ONLY", "ALL_VERSIONS_OBSERVED_BEFORE_TO", List.of(), List.of()));
        var mvc = MockMvcBuilders.standaloneSetup(new StoredDatasetExportController(service)).setControllerAdvice(new GlobalExceptionHandler()).build();
        mvc.perform(get("/api/v1/research/dataset-export").param("stockCode", "005930").param("from", from.toString()).param("to", to.toString()))
            .andExpect(status().isOk()).andExpect(header().string("Cache-Control", "no-store"))
            .andExpect(jsonPath("$.data.readOnly").value(true)).andExpect(jsonPath("$.data.usableForTrading").value(false))
            .andExpect(jsonPath("$.data.streamCoverage").value("OBSERVED_ONLY"));
        mvc.perform(get("/api/v1/research/dataset-export").param("stockCode", "005930").param("from", "2025-11-03").param("to", to.toString()))
            .andExpect(status().isBadRequest());
        verify(service).export("005930", from, to);
        verifyNoMoreInteractions(service);
    }
}
