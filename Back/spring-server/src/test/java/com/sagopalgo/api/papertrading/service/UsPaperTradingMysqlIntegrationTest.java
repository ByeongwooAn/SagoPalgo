package com.sagopalgo.api.papertrading.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.SerializationFeature;
import com.jayway.jsonpath.JsonPath;
import com.sagopalgo.api.capital.dto.CapitalResponse;
import com.sagopalgo.api.capital.service.CapitalService;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.common.exception.GlobalExceptionHandler;
import com.sagopalgo.api.market.client.KisMarketPriceClient;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.service.MarketPriceService;
import com.sagopalgo.api.papertrading.controller.PaperTradingController;
import com.sagopalgo.api.papertrading.dto.UsPaperTradeRequest;
import com.sagopalgo.api.papertrading.mapper.PaperTradeMapper;
import com.sagopalgo.api.papertrading.model.PaperTradeRecord;
import com.sagopalgo.api.recommendation.dto.AnalysisEvidence;
import com.sagopalgo.api.recommendation.dto.DailySignal;
import com.sagopalgo.api.recommendation.dto.RecommendationResponse;
import com.sagopalgo.api.recommendation.service.DailySignalService;
import com.sagopalgo.api.recommendation.service.RecommendationService;
import com.sagopalgo.api.user.service.LocalUserContext;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.core.io.FileSystemResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ScriptUtils;
import org.springframework.http.MediaType;
import org.springframework.http.converter.json.Jackson2ObjectMapperBuilder;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.interceptor.TransactionInterceptor;

@EnabledIfEnvironmentVariable(named = "SAGOPALGO_US_PAPER_MYSQL_PORT", matches = "[0-9]{4,5}")
class UsPaperTradingMysqlIntegrationTest {
    private static final String PAPER = "/api/v1/paper-trading";
    private static final Instant KRX_AT = Instant.parse("2026-11-23T01:00:00Z");
    private static final Instant NASDAQ_AT = Instant.parse("2026-11-23T15:00:00Z");
    private static final String MODEL_HASH = "a".repeat(64);
    private Instant now = KRX_AT;
    private DriverManagerDataSource dataSource;
    private JdbcTemplate jdbc;
    private Long userId;
    private PaperTradeMapper mapper;
    private MarketPriceService quotes;
    private KisMarketPriceClient ticks;
    private DailySignalService signals;
    private RecommendationService recommendations;
    private PaperTradingService service;
    private MockMvc http;

    @BeforeEach
    void initializeIsolatedDatabase() throws Exception {
        String port = System.getenv("SAGOPALGO_US_PAPER_MYSQL_PORT");
        var source = new DriverManagerDataSource(
            "jdbc:mysql://127.0.0.1:" + port + "/sagopalgo_us_paper_test?allowPublicKeyRetrieval=true&sslMode=DISABLED",
            "root", "us-paper-test-only");
        jdbc = new JdbcTemplate(source);
        assertThat(jdbc.queryForObject("SELECT DATABASE()", String.class)).isEqualTo("sagopalgo_us_paper_test");
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(connection, new FileSystemResource("../database/schema.sql"));
        }
        String owner = UUID.randomUUID().toString();
        jdbc.update("INSERT INTO users (auth_provider, provider_user_id, nickname) VALUES ('LOCAL', ?, 'USD fixture')", owner);
        userId = jdbc.queryForObject("SELECT user_id FROM users WHERE provider_user_id = ?", Long.class, owner);
        dataSource = source;
    }

    @Test
    void migrationAndConcurrentOrdersPreserveSeparateLedgers() throws Exception {
        jdbc.update("""
            INSERT INTO trade_records (user_id, stock_code, stock_name, market, trade_type, trade_price, quantity, trade_date)
            VALUES (?, '005930', 'Samsung', 'KOSPI', 'BUY', 70000, 1, CURRENT_TIMESTAMP)
            """, userId);
        try (var connection = dataSource.getConnection()) {
            ScriptUtils.executeSqlScript(connection, new FileSystemResource("../database/migrations/028_us_paper_trading.sql"));
        }

        initializePaperTrading();
        now = NASDAQ_AT;
        var aapl = new MarketDataRequest("AAPL", "NASDAQ");
        var quote = quote("AAPL", "NASDAQ", "80.1234", NASDAQ_AT);
        when(ticks.todayTradeQuote(aapl, NASDAQ_AT)).thenReturn(quote);
        when(quotes.getUsQuote("AAPL", "NASDAQ")).thenReturn(quote);
        when(signals.analyze("AAPL", "NASDAQ")).thenReturn(signal("BUY_WATCH", NASDAQ_AT.plusSeconds(3600)));
        http.perform(put("/api/v1/paper-trading/us/account")
                .contentType(MediaType.APPLICATION_JSON).content("""
                    {"initialCapital":"100.00"}
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.currency").value("USD"));
        var executor = Executors.newFixedThreadPool(2);
        try {
            var first = executor.submit(place(service, userId, 1));
            var second = executor.submit(place(service, userId, 2));
            assertThat(first.get(10, TimeUnit.SECONDS) + second.get(10, TimeUnit.SECONDS)).isEqualTo(1);
        } finally {
            executor.shutdownNow();
        }
        var saved = mapper.findUsTrades(userId).get(0);
        http.perform(post("/api/v1/paper-trading/us/trades")
                .contentType(MediaType.APPLICATION_JSON).content("""
                    {"stockCode":"AAPL","market":"NASDAQ","side":"BUY","quantity":"1.0000","requestId":"%s"}
                    """.formatted(saved.getRequestId())))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.summary.cashBalance").value(19.88));
        assertThat(mapper.findUsTrades(userId)).singleElement().satisfies(row ->
            assertThat(row.getTradePrice()).isEqualByComparingTo("80.1234"));
        assertThat(mapper.findAllByUserId(userId)).singleElement().satisfies(row ->
            assertThat(row.getStockCode()).isEqualTo("005930"));
    }

    @Test
    void fourSymbolsPersistPricesQuantitiesTimesAndProfitInTheirOwnLedgers() throws Exception {
        initializePaperTrading();
        stageFourQuotesAndSignals();
        openUsdAccount();
        krwBuy(41, "2", 1).andExpect(status().isOk());
        krwSell("005930", "1", 2).andExpect(status().isOk())
            .andExpect(jsonPath("$.data.trades[0].realizedProfit").value(1200));
        krwBuy(42, "1", 3).andExpect(status().isOk());
        krwSell("000660", "1", 4).andExpect(status().isOk())
            .andExpect(jsonPath("$.data.trades[0].realizedProfit").value(-4000));

        now = NASDAQ_AT;
        usdTrade("AAPL", "BUY", "2", 1).andExpect(status().isOk());
        usdTrade("AAPL", "SELL", "1", 2).andExpect(status().isOk())
            .andExpect(jsonPath("$.data.trades[0].realizedProfit").value(2.37));
        usdTrade("NVDA", "BUY", "1", 3).andExpect(status().isOk());
        usdTrade("NVDA", "SELL", "1", 4).andExpect(status().isOk())
            .andExpect(jsonPath("$.data.trades[0].realizedProfit").value(-1.01));

        var krw = mapper.findAllByUserId(userId);
        var usd = mapper.findUsTrades(userId);
        assertThat(krw).hasSize(4).allSatisfy(row -> {
            assertThat(row.getExecutionMode()).isEqualTo("PAPER");
            assertEvidence(row, KRX_AT);
        });
        assertThat(usd).hasSize(4).allSatisfy(row -> assertEvidence(row, NASDAQ_AT));
        assertTrade(krw.get(0), "005930", "BUY", "70000", "2", "0");
        assertTrade(krw.get(1), "005930", "SELL", "71200", "1", "1200");
        assertTrade(krw.get(2), "000660", "BUY", "188000", "1", "0");
        assertTrade(krw.get(3), "000660", "SELL", "184000", "1", "-4000");
        assertThat(krw.get(0).getRecommendationId()).isEqualTo(41L);
        assertThat(krw.get(2).getRecommendationId()).isEqualTo(42L);
        assertTrade(usd.get(0), "AAPL", "BUY", "180.1250", "2", "0");
        assertTrade(usd.get(1), "AAPL", "SELL", "182.5000", "1", "2.37");
        assertTrade(usd.get(2), "NVDA", "BUY", "120.1250", "1", "0");
        assertTrade(usd.get(3), "NVDA", "SELL", "119.1150", "1", "-1.01");

        assertSnapshot(PAPER, "KRW", krw, 927200, -2800, 1200);
        assertSnapshot(PAPER + "/us", "USD", usd, 821.24, 1.36, 2.38);
    }

    @Test
    void insufficientBalancesAndRequestReplayPreserveLedgerRows() throws Exception {
        initializePaperTrading();
        stageFourQuotesAndSignals();
        openUsdAccount();
        krwBuy(41, "2", 1).andExpect(status().isOk());
        krwBuy(42, "100000", 2).andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error.message").value("모의매매 현금 잔액이 부족합니다."));
        krwSell("005930", "3", 2).andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error.message").value("보유한 모의 수량보다 많이 매도할 수 없습니다."));
        krwBuy(41, "2", 1).andExpect(status().isOk())
            .andExpect(jsonPath("$.data.summary.cashBalance").value(860000));
        krwBuy(42, "2", 1).andExpect(status().isConflict());
        krwSell("005930", "2", 1).andExpect(status().isConflict());

        now = NASDAQ_AT;
        usdTrade("AAPL", "BUY", "2", 1).andExpect(status().isOk());
        usdTrade("AAPL", "BUY", "100000", 2).andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error.message").value("USD 모의 현금 잔액이 부족합니다."));
        usdTrade("AAPL", "SELL", "3", 2).andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error.message").value("보유한 미국주식 모의 수량보다 많이 매도할 수 없습니다."));
        usdTrade("AAPL", "BUY", "2", 1).andExpect(status().isOk())
            .andExpect(jsonPath("$.data.summary.cashBalance").value(639.75));
        usdTrade("AAPL", "BUY", "1", 1).andExpect(status().isConflict())
            .andExpect(jsonPath("$.error.code").value("DUPLICATE_RESOURCE"));

        assertThat(mapper.findAllByUserId(userId)).singleElement()
            .satisfies(row -> assertTrade(row, "005930", "BUY", "70000", "2", "0"));
        assertThat(mapper.findUsTrades(userId)).singleElement()
            .satisfies(row -> assertTrade(row, "AAPL", "BUY", "180.1250", "2", "0"));
    }

    @Test
    void expiredSignalsAndOldOrMissingTradeTimesCannotWriteAnOrder() throws Exception {
        initializePaperTrading();
        openUsdAccount();
        stubRecommendation(41, "005930", signal("BUY_WATCH", KRX_AT));
        krwBuy(41, "1", 1).andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error.message").value("장 마감 모델의 매수 신호가 만료되었습니다."));
        stubRecommendation(41, "005930", signal("BUY_WATCH", KRX_AT.plusSeconds(3600)));
        when(ticks.todayTradeQuote(new MarketDataRequest("005930", "KOSPI"), KRX_AT))
            .thenReturn(new StockQuote("KIS", "005930", "", "KOSPI", new BigDecimal("70000"),
                null, null, null, null, null, null, null, KRX_AT, KRX_AT.minusSeconds(900)));
        krwBuy(41, "1", 1).andExpect(status().isBadGateway());

        now = NASDAQ_AT;
        when(signals.analyze("AAPL", "NASDAQ")).thenReturn(signal("WAIT", NASDAQ_AT.plusSeconds(3600)));
        usdTrade("AAPL", "BUY", "1", 1).andExpect(status().isBadRequest());
        when(signals.analyze("AAPL", "NASDAQ")).thenReturn(signal("BUY_WATCH", NASDAQ_AT.plusSeconds(3600)));
        when(ticks.todayTradeQuote(new MarketDataRequest("AAPL", "NASDAQ"), NASDAQ_AT))
            .thenReturn(new StockQuote("KIS", "AAPL", "", "NASDAQ", new BigDecimal("180"),
                null, null, null, null, null, null, null, NASDAQ_AT));
        usdTrade("AAPL", "BUY", "1", 1).andExpect(status().isBadGateway());
        when(ticks.todayTradeQuote(new MarketDataRequest("AAPL", "NASDAQ"), NASDAQ_AT))
            .thenReturn(new StockQuote("KIS", "AAPL", "", "NASDAQ", new BigDecimal("180"),
                null, null, null, null, null, null, null, NASDAQ_AT, NASDAQ_AT.minusSeconds(900)));
        usdTrade("AAPL", "BUY", "1", 1).andExpect(status().isBadGateway());

        assertThat(mapper.findAllByUserId(userId)).isEmpty();
        assertThat(mapper.findUsTrades(userId)).isEmpty();
        assertThat(service.getSnapshot(userId).summary().cashBalance()).isEqualByComparingTo("1000000");
        assertThat(service.getUsSnapshot(userId).summary().cashBalance()).isEqualByComparingTo("1000");
    }

    @Test
    void completedKrwSellReplaysEvenAfterPositionClosesAndSessionEnds() throws Exception {
        initializePaperTrading();
        stageFourQuotesAndSignals();
        krwBuy(41, "1", 1).andExpect(status().isOk());
        krwSell("005930", "1", 2).andExpect(status().isOk());
        now = NASDAQ_AT;
        krwSell("005930", "1", 2).andExpect(status().isOk())
            .andExpect(jsonPath("$.data.positions.length()").value(0));
        assertThat(mapper.findAllByUserId(userId)).hasSize(2);
    }

    private void initializePaperTrading() throws Exception {
        var configuration = new Configuration();
        configuration.setMapUnderscoreToCamelCase(true);
        configuration.addMapper(PaperTradeMapper.class);
        var factory = new SqlSessionFactoryBean();
        factory.setDataSource(dataSource);
        factory.setConfiguration(configuration);
        mapper = new SqlSessionTemplate(factory.getObject()).getMapper(PaperTradeMapper.class);
        quotes = mock(MarketPriceService.class);
        ticks = mock(KisMarketPriceClient.class);
        signals = mock(DailySignalService.class);
        var clock = mock(Clock.class);
        when(clock.instant()).thenAnswer(ignored -> now);
        when(clock.getZone()).thenReturn(ZoneOffset.UTC);
        var capital = mock(CapitalService.class);
        recommendations = mock(RecommendationService.class);
        when(capital.findByUserId(userId))
            .thenReturn(new CapitalResponse(new BigDecimal("1000000"), null, null, null));

        var proxy = new ProxyFactory(new PaperTradingService(mapper, capital, recommendations, quotes, ticks, signals, clock));
        proxy.setProxyTargetClass(true);
        proxy.addAdvice(new TransactionInterceptor(
            new DataSourceTransactionManager(dataSource), new AnnotationTransactionAttributeSource()));
        service = (PaperTradingService) proxy.getProxy();

        var context = mock(LocalUserContext.class);
        when(context.userId()).thenReturn(userId);
        var json = Jackson2ObjectMapperBuilder.json()
            .featuresToDisable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS).build();
        http = MockMvcBuilders.standaloneSetup(new PaperTradingController(service, context))
            .setControllerAdvice(new GlobalExceptionHandler())
            .setMessageConverters(new MappingJackson2HttpMessageConverter(json))
            .build();
    }

    private void stageFourQuotesAndSignals() {
        stubRecommendation(41, "005930", signal("BUY_WATCH", KRX_AT.plusSeconds(3600)));
        stubRecommendation(42, "000660", signal("BUY_WATCH", KRX_AT.plusSeconds(3600)));
        when(signals.analyze("AAPL", "NASDAQ")).thenReturn(signal("BUY_WATCH", NASDAQ_AT.plusSeconds(3600)));
        when(signals.analyze("NVDA", "NASDAQ")).thenReturn(signal("BUY_WATCH", NASDAQ_AT.plusSeconds(3600)));
        stubPrices("005930", "KOSPI", "70000", "71200", KRX_AT);
        stubPrices("000660", "KOSPI", "188000", "184000", KRX_AT);
        stubPrices("AAPL", "NASDAQ", "180.1250", "182.5000", NASDAQ_AT);
        stubPrices("NVDA", "NASDAQ", "120.1250", "119.1150", NASDAQ_AT);
    }

    private void stubPrices(String ticker, String market, String buy, String sell, Instant at) {
        var request = new MarketDataRequest(ticker, market);
        var exit = quote(ticker, market, sell, at);
        when(ticks.todayTradeQuote(request, at)).thenReturn(quote(ticker, market, buy, at), exit);
        if ("NASDAQ".equals(market)) {
            when(quotes.getUsQuote(ticker, market)).thenReturn(exit);
        } else {
            when(quotes.quoteMarket(request)).thenReturn(exit);
        }
    }

    private DailySignal signal(String decision, Instant expires) {
        return new DailySignal(decision, null, "test", MODEL_HASH, "test",
            LocalDate.parse("2026-11-20"), null, expires.minusSeconds(7200).atOffset(ZoneOffset.UTC),
            expires.atOffset(ZoneOffset.UTC), 0.6, 0.5, Map.of());
    }

    private void stubRecommendation(long id, String ticker, DailySignal signal) {
        when(recommendations.findOne(userId, id)).thenReturn(new RecommendationResponse(
            id, ticker, ticker, "KOSPI", "HOLD", "HOLD", "보유 유지", 80, null, null, null,
            "테스트 신호", LocalDateTime.now(), List.of(), null, new AnalysisEvidence("test", 21, 0, 0, signal)));
    }

    private StockQuote quote(String ticker, String market, String price, Instant receivedAt) {
        return new StockQuote("KIS", ticker, "", market, new BigDecimal(price),
            null, null, null, null, null, null, null, receivedAt.minusSeconds(1), receivedAt.minusSeconds(2));
    }

    private void openUsdAccount() throws Exception {
        http.perform(put(PAPER + "/us/account").contentType(MediaType.APPLICATION_JSON)
            .content("{\"initialCapital\":\"1000.00\"}")).andExpect(status().isOk());
    }

    private ResultActions krwBuy(long id, String quantity, int requestId) throws Exception {
        return http.perform(post(PAPER + "/recommendations/{recommendationId}/buy", id)
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"quantity\":%s,\"requestId\":\"%032x\"}".formatted(quantity, requestId)));
    }

    private ResultActions krwSell(String ticker, String quantity, int requestId) throws Exception {
        return http.perform(post(PAPER + "/sell").contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"stockCode":"%s","market":"KOSPI","quantity":%s,"requestId":"%032x"}
                """.formatted(ticker, quantity, requestId)));
    }

    private ResultActions usdTrade(String ticker, String side, String quantity, int requestId) throws Exception {
        return http.perform(post(PAPER + "/us/trades").contentType(MediaType.APPLICATION_JSON).content("""
            {"stockCode":"%s","market":"NASDAQ","side":"%s","quantity":"%s","requestId":"%032x"}
            """.formatted(ticker, side, quantity, requestId)));
    }

    private void assertTrade(PaperTradeRecord row, String ticker, String side, String price, String quantity, String profit) {
        assertThat(row.getStockCode()).isEqualTo(ticker);
        assertThat(row.getTradeType()).isEqualTo(side);
        assertThat(row.getTradePrice()).isEqualByComparingTo(price);
        assertThat(row.getQuantity()).isEqualByComparingTo(quantity);
        assertThat(row.getRealizedProfit()).isEqualByComparingTo(profit);
    }

    private void assertEvidence(PaperTradeRecord row, Instant at) {
        var executed = LocalDateTime.ofInstant(at, ZoneOffset.UTC);
        assertThat(row.getTradeDate()).isEqualTo(executed);
        assertThat(row.getQuoteProvider()).isEqualTo("KIS");
        assertThat(row.getQuoteMarketAt()).isEqualTo(executed.minusSeconds(2));
        assertThat(row.getQuoteReceivedAt()).isEqualTo(executed.minusSeconds(1));
        if ("BUY".equals(row.getTradeType())) {
            assertThat(row.getSignalBasisDate()).isEqualTo(LocalDate.parse("2026-11-20"));
            assertThat(row.getSignalModelSha256()).isEqualTo(MODEL_HASH);
            assertThat(row.getSignalExpiresAt()).isEqualTo(executed.plusHours(1));
        } else {
            assertThat(row.getSignalBasisDate()).isNull();
        }
    }

    private void assertSnapshot(String path, String currency, List<PaperTradeRecord> ledger,
        double cash, double realized, double unrealized) throws Exception {
        var response = http.perform(get(path)).andExpect(status().isOk())
            .andExpect(jsonPath("$.data.currency").value(currency))
            .andExpect(jsonPath("$.data.summary.cashBalance").value(cash))
            .andExpect(jsonPath("$.data.summary.realizedProfit").value(realized))
            .andExpect(jsonPath("$.data.summary.unrealizedProfit").value(unrealized))
            .andExpect(jsonPath("$.data.trades.length()").value(ledger.size()));
        var json = JsonPath.parse(response.andReturn().getResponse().getContentAsString());
        for (int index = 0; index < ledger.size(); index++) {
            var saved = ledger.get(ledger.size() - 1 - index);
            String trade = "$.data.trades[" + index + "]";
            response.andExpect(jsonPath(trade + ".tradeRecordId").value(saved.getTradeRecordId()))
                .andExpect(jsonPath(trade + ".stockCode").value(saved.getStockCode()))
                .andExpect(jsonPath(trade + ".tradeType").value(saved.getTradeType()))
                .andExpect(jsonPath(trade + ".tradePrice").value(saved.getTradePrice().doubleValue()))
                .andExpect(jsonPath(trade + ".quantity").value(saved.getQuantity().doubleValue()))
                .andExpect(jsonPath(trade + ".realizedProfit").value(saved.getRealizedProfit().doubleValue()));
            assertThat(LocalDateTime.parse(json.read(trade + ".tradeDate", String.class)))
                .isEqualTo(saved.getTradeDate());
            assertThat(OffsetDateTime.parse(json.read(trade + ".quoteMarketAt", String.class)).toLocalDateTime())
                .isEqualTo(saved.getQuoteMarketAt());
        }
    }

    private Callable<Integer> place(PaperTradingService service, Long userId, int id) {
        return () -> {
            var order = new UsPaperTradeRequest("AAPL", "NASDAQ", UsPaperTradeRequest.Side.BUY,
                BigDecimal.ONE, "%032x".formatted(id));
            try {
                service.tradeUs(userId, order);
                return 1;
            } catch (ApiException exception) {
                assertThat(exception.getErrorCode()).isEqualTo(ErrorCode.VALIDATION_ERROR);
                assertThat(exception).hasMessage("USD 모의 현금 잔액이 부족합니다.");
                return 0;
            }
        };
    }
}
