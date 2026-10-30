package com.sagopalgo.api.kb.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.capital.dto.CapitalResponse;
import com.sagopalgo.api.capital.dto.UpdateCapitalRequest;
import com.sagopalgo.api.capital.service.CapitalService;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.holding.mapper.HoldingMapper;
import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.kb.client.KbSecuritiesAccountClient;
import com.sagopalgo.api.kb.dto.KbPortfolioImportRequest;
import com.sagopalgo.api.kb.dto.KbPortfolioPreviewResponse;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.web.client.RestClient;

class KbPortfolioImportServiceTest {
    private final ObjectMapper json = new ObjectMapper();
    private final SecuritiesProviderProperties properties = new SecuritiesProviderProperties();
    private final HoldingMapper mapper = mock(HoldingMapper.class);
    private final CapitalService capital = mock(CapitalService.class);
    private KbSecuritiesAccountClient client;
    private KbPortfolioImportService service;

    @BeforeEach
    void setUp() throws Exception {
        properties.getKb().setAccountEnabled(true);
        properties.getKb().setBaseUrl("https://example.test");
        properties.getKb().setAppKey("private-app-key");
        properties.getKb().setAppSecret("private-app-secret");
        client = spy(new KbSecuritiesAccountClient(properties, RestClient.builder().build()));
        holdings("""
            [{"is_no":"005930","is_nm":"삼성전자","gnrl_q":"10.1256","byng_avr_prc":"70000.25"}]
            """);
        cash("100000");
        when(mapper.findActiveByUserId(any())).thenReturn(List.of());
        when(mapper.findImported(any(), any())).thenReturn(List.of());
        when(capital.findByUserId(any())).thenReturn(new CapitalResponse(
            new BigDecimal("3000000"), new BigDecimal("300000"), new BigDecimal("600000"), new BigDecimal("0.015")));
        service = new KbPortfolioImportService(new KbAccountService(client), client, capital, mapper, properties, json);
    }

    @Test
    void previewDoesNotWriteAndUsesOrderCashRatherThanDepositOrNetAssets() {
        KbPortfolioPreviewResponse preview = service.preview(1L);
        assertThat(preview.orderAvailableCash()).isEqualByComparingTo("100000");
        assertThat(preview.currentCapital()).isEqualByComparingTo("3000000");
        assertThat(preview.items().get(0).quantity()).isEqualByComparingTo("10.1256");
        assertThat(preview.items().get(0).averageBuyPrice()).isEqualByComparingTo("70000.25");
        assertThat(preview.items().get(0).market()).isEqualTo("KRX");
        assertThat(preview.expiresAt().getNano()).isZero();
        assertThat(preview.toString()).doesNotContain("private-app-key", "private-app-secret");
        verify(mapper, never()).insert(any());
        verify(capital, never()).update(any(), any());
    }

    @Test
    void selectedHoldingsAreImportedWithoutChangingCapitalOrInventingBuyDate() {
        var result = service.apply(1L, request(service.preview(1L), false, true));
        ArgumentCaptor<Holding> saved = ArgumentCaptor.forClass(Holding.class);
        verify(mapper).insert(saved.capture());
        assertThat(result.createdCount()).isEqualTo(1);
        assertThat(saved.getValue().getSource()).isEqualTo("KB");
        assertThat(saved.getValue().getSourceAccountKey()).hasSize(64);
        assertThat(saved.getValue().getBuyDate()).isNull();
        assertThat(saved.getValue().getQuantity()).isEqualByComparingTo("10.1256");
        assertThat(saved.getValue().getMarket()).isEqualTo("KOSPI");
        verify(capital, never()).update(any(), any());
    }

    @Test
    void capitalIsOptInAndPreservesRiskRate() {
        service.apply(1L, request(service.preview(1L), true, false));
        verify(capital).update(1L, new UpdateCapitalRequest(new BigDecimal("100000.00"), new BigDecimal("0.015")));
        verify(mapper, never()).insert(any());
    }

    @Test
    void repeatedPreviewAndImportUpdatesSameKbRowAndKeepsThresholds() {
        ArgumentCaptor<Holding> captured = ArgumentCaptor.forClass(Holding.class);
        service.apply(1L, request(service.preview(1L), false, true));
        verify(mapper).insert(captured.capture());
        Holding row = captured.getValue();
        row.setHoldingId(42L);
        row.setStopLossRate(new BigDecimal("-3"));
        row.setTakeProfitRate(new BigDecimal("12"));
        when(mapper.findActiveByUserId(1L)).thenReturn(List.of(row));
        when(mapper.findImported(any(), any())).thenReturn(List.of(row));

        var result = service.apply(1L, request(service.preview(1L), false, true));

        assertThat(result.createdCount()).isZero();
        assertThat(result.updatedCount()).isEqualTo(1);
        assertThat(row.getStopLossRate()).isEqualByComparingTo("-3");
        assertThat(row.getTakeProfitRate()).isEqualByComparingTo("12");
        verify(mapper, times(1)).insert(any());
        verify(mapper).updateImported(row);
    }

    @Test
    void manualSameStockIsSkippedAcrossDomesticMarketAliases() {
        when(mapper.findActiveByUserId(1L)).thenReturn(List.of(manual()));
        var preview = service.preview(1L);
        assertThat(preview.items().get(0).action()).isEqualTo("SKIP");
        var result = service.apply(1L, request(preview, false, true));
        assertThat(result.skippedCount()).isEqualTo(1);
        verify(mapper, never()).insert(any());
        verify(mapper, never()).updateImported(any());
    }

    @Test
    void changedCashOrLocalDataRequiresNewPreview() throws Exception {
        var preview = service.preview(1L);
        cash("99999");
        assertThatThrownBy(() -> service.apply(1L, request(preview, true, true)))
            .isInstanceOf(ApiException.class).hasMessageContaining("변경");
        verify(mapper, never()).insert(any());
        verify(capital, never()).update(any(), any());
        cash("100000");
        when(mapper.findActiveByUserId(1L)).thenReturn(List.of(manual()));
        assertThatThrownBy(() -> service.apply(1L, request(preview, true, true))).hasMessageContaining("변경");
    }

    @Test
    void previewIsBoundToUserAndConnection() {
        var preview = service.preview(1L);
        assertThatThrownBy(() -> service.apply(2L, request(preview, false, true))).hasMessageContaining("변경");
        properties.getKb().setAppKey("changed-key");
        assertThatThrownBy(() -> service.apply(1L, request(preview, false, true))).hasMessageContaining("변경");
        verify(mapper, never()).insert(any());
    }

    @Test
    void expiredPreviewAndEmptySelectionDoNotWrite() {
        var preview = service.preview(1L);
        var expired = new KbPortfolioImportRequest(preview.previewToken(), Instant.now().minusSeconds(1),
            false, true, Map.of("005930", "KOSPI"), new BigDecimal("-5"), new BigDecimal("9"));
        assertThatThrownBy(() -> service.apply(1L, expired)).hasMessageContaining("만료");
        assertThatThrownBy(() -> service.apply(1L, request(preview, false, false))).hasMessageContaining("선택");
        verify(mapper, never()).insert(any());
    }

    @Test
    void absentMalformedAndNegativeCashAreNotTreatedAsZero() throws Exception {
        for (String value : List.of("", "not-a-number", "-1")) {
            cash(value);
            var preview = service.preview(1L);
            assertThat(preview.orderAvailableCash()).isNull();
            assertThatThrownBy(() -> service.apply(1L, request(preview, true, false))).hasMessageContaining("미제공");
        }
        cash("0");
        assertThat(service.preview(1L).orderAvailableCash()).isEqualByComparingTo("0");
        verify(capital, never()).update(any(), any());
    }

    @Test
    void missingAverageOrDuplicateRowsBlockHoldingsBeforeWriting() throws Exception {
        for (String rows : List.of(
            "[{\"is_no\":\"005930\",\"is_nm\":\"삼성전자\",\"gnrl_q\":\"10\"}]",
            "[{\"is_no\":\"005930\",\"gnrl_q\":\"10\",\"byng_avr_prc\":\"100\"},"
                + "{\"is_no\":\"005930\",\"gnrl_q\":\"5\",\"byng_avr_prc\":\"90\"}]")) {
            holdings(rows);
            var preview = service.preview(1L);
            assertThatThrownBy(() -> service.apply(1L, request(preview, false, true))).hasMessageContaining("가져올 수 없는");
        }
        verify(mapper, never()).insert(any());
    }

    @Test
    void marketMustBeConfirmedWhenKbDoesNotProvideIt() {
        var preview = service.preview(1L);
        var request = new KbPortfolioImportRequest(preview.previewToken(), preview.expiresAt(), false, true,
            Map.of(), new BigDecimal("-5"), new BigDecimal("9"));
        assertThatThrownBy(() -> service.apply(1L, request)).hasMessageContaining("시장");
        verify(mapper, never()).insert(any());
    }

    @Test
    void missingRemoteHoldingIsRetainedAndNotDeleted() throws Exception {
        ArgumentCaptor<Holding> captured = ArgumentCaptor.forClass(Holding.class);
        service.apply(1L, request(service.preview(1L), false, true));
        verify(mapper).insert(captured.capture());
        Holding row = captured.getValue();
        row.setHoldingId(42L);
        when(mapper.findActiveByUserId(1L)).thenReturn(List.of(row));
        when(mapper.findImported(any(), any())).thenReturn(List.of(row));
        holdings("[]");

        var preview = service.preview(1L);
        assertThat(preview.retainedImportedCount()).isEqualTo(1);
        service.apply(1L, request(preview, true, false));
        verify(mapper, never()).deleteByIdAndUserId(any(), any());
    }

    @Test
    void existingDifferentConnectionCannotBeMixed() {
        Holding row = manual();
        row.setSource("KB");
        row.setSourceAccountKey("old-account-fingerprint");
        when(mapper.findActiveByUserId(1L)).thenReturn(List.of(row));
        assertThatThrownBy(() -> service.preview(1L)).hasMessageContaining("연결 설정이 다릅니다");
    }

    private Holding manual() {
        Holding holding = new Holding();
        holding.setHoldingId(7L); holding.setUserId(1L); holding.setStockCode("005930");
        holding.setStockName("삼성전자"); holding.setMarket("KOSPI");
        holding.setBuyPrice(new BigDecimal("60000")); holding.setQuantity(new BigDecimal("2"));
        holding.setStopLossRate(new BigDecimal("-5")); holding.setTakeProfitRate(new BigDecimal("9"));
        return holding;
    }

    private KbPortfolioImportRequest request(KbPortfolioPreviewResponse preview, boolean cash, boolean holdings) {
        return new KbPortfolioImportRequest(preview.previewToken(), preview.expiresAt(), cash, holdings,
            Map.of("005930", "KOSPI"), new BigDecimal("-5"), new BigDecimal("9"));
    }

    private void holdings(String rows) throws Exception {
        doReturn(json.readTree("{\"dataBody\":{\"Record1\":" + rows + "}}" )).when(client).fetchHoldings();
    }

    private void cash(String value) throws Exception {
        doReturn(json.readTree("{\"dataBody\":{\"tfnd\":\"55\",\"nt_asts_val_amt\":\"999999\","
            + "\"ordr_psbl_csh\":\"" + value + "\"}}" )).when(client).fetchSettlementBalance();
    }
}
