package com.sagopalgo.api.research.service;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.common.util.ContentHash;
import com.sagopalgo.api.market.stream.MarketAvailabilityClock;
import com.sagopalgo.api.research.export.*;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class ResearchInputDeliveryTest {
    final ObjectMapper json=new ObjectMapper().findAndRegisterModules();
    final Instant from=Instant.parse("2025-11-03T00:00:00Z"),to=from.plusSeconds(60);
    final String request=UUID.randomUUID().toString();
    final StoredDatasetExportService exports=mock(StoredDatasetExportService.class);
    final MarketAvailabilityClock clock=new MarketAvailabilityClock();
    ResearchInputDeliveryController controller() {return new ResearchInputDeliveryController(exports,clock,json);}
    StoredDatasetExportService.SnapshotV2 snapshot() {
        return new StoredDatasetExportService.SnapshotV2("SAGOPALGO_STORED_EXPORT_V2","005930",from,to,to.plusSeconds(60),
            true,false,"REPEATABLE_READ","OBSERVED_ONLY","ALL_VERSIONS_OBSERVED_BEFORE_TO",List.of(),List.of());
    }
    @Test void bindsExactIsoPayloadAndFreshDeliveryToRequestWithinSameClockDomain() throws Exception {
        when(exports.exportAvailability("005930",from,to)).thenReturn(snapshot());
        var controller=controller();
        var first=(ResearchInputDeliveryController.Delivery)((com.sagopalgo.api.common.response.ApiResponse<?>)controller.deliver(request,"005930",from.toString(),to.toString()).getBody()).data();
        var second=(ResearchInputDeliveryController.Delivery)((com.sagopalgo.api.common.response.ApiResponse<?>)controller.deliver(request,"005930",from.toString(),to.toString()).getBody()).data();
        assertThat(first.requestId()).isEqualTo(request);
        assertThat(first.deliveryId()).isNotEqualTo(second.deliveryId());
        assertThat(first.producerClockDomain()).isEqualTo(clock.domain());
        assertThat(first.producerSent().elapsedNanos()).isGreaterThanOrEqualTo(first.producerReceived().elapsedNanos());
        assertThat(first.utcSynchronized()).isFalse();
        assertThat(first.payloadSha256()).isEqualTo(ContentHash.sha256(first.payloadJson()));
        assertThat(json.readTree(first.payloadJson()).get("from").asText()).isEqualTo(from.toString());
    }
    @Test void malformedRequestOrTimestampNeverReadsDatabase() {
        assertThatThrownBy(()->controller().deliver("not-a-uuid","005930",from.toString(),to.toString())).isInstanceOf(ApiException.class);
        assertThatThrownBy(()->controller().deliver(request,"005930","2025-11-03",to.toString())).isInstanceOf(ApiException.class);
        verifyNoInteractions(exports);
    }
    @Test void getOnlyNoStoreAndStorageFailuresRemainFailures() throws Exception {
        when(exports.exportAvailability("005930",from,to)).thenReturn(snapshot());
        var mvc=MockMvcBuilders.standaloneSetup(controller()).setControllerAdvice(new GlobalExceptionHandler()).build();
        var get=get("/api/v1/research/input-delivery").param("requestId",request).param("stockCode","005930").param("from",from.toString()).param("to",to.toString());
        mvc.perform(get).andExpect(status().isOk()).andExpect(header().string("Cache-Control","no-store"))
            .andExpect(jsonPath("$.data.utcSynchronized").value(false)).andExpect(jsonPath("$.data.requestId").value(request));
        // Existing global advice maps unsupported methods to a fixed failure response.
        mvc.perform(post("/api/v1/research/input-delivery")).andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.success").value(false));
        verify(exports).exportAvailability("005930",from,to);
        when(exports.exportAvailability("005930",from,to)).thenThrow(new ApiException(ErrorCode.EXTERNAL_DATA_ERROR));
        mvc.perform(get).andExpect(status().isBadGateway());
    }
}
