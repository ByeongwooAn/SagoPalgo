package com.sagopalgo.api.papertrading.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.sagopalgo.api.capital.service.CapitalService;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.service.MarketPriceService;
import com.sagopalgo.api.papertrading.controller.PaperTradingController;
import com.sagopalgo.api.papertrading.dto.UsPaperTradeRequest;
import com.sagopalgo.api.papertrading.mapper.PaperTradeMapper;
import com.sagopalgo.api.recommendation.service.RecommendationService;
import com.sagopalgo.api.user.service.LocalUserContext;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.apache.ibatis.session.Configuration;
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
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.interceptor.TransactionInterceptor;

@EnabledIfEnvironmentVariable(named = "SAGOPALGO_US_PAPER_MYSQL_PORT", matches = "[0-9]{4,5}")
class UsPaperTradingMysqlIntegrationTest {
    @Test
    void migrationAndConcurrentOrdersPreserveSeparateLedgers() throws Exception {
        String port = System.getenv("SAGOPALGO_US_PAPER_MYSQL_PORT");
        var source = new DriverManagerDataSource(
            "jdbc:mysql://127.0.0.1:" + port + "/sagopalgo_us_paper_test?allowPublicKeyRetrieval=true&sslMode=DISABLED",
            "root", "us-paper-test-only");
        var jdbc = new JdbcTemplate(source);
        assertThat(jdbc.queryForObject("SELECT DATABASE()", String.class)).isEqualTo("sagopalgo_us_paper_test");
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(connection, new FileSystemResource("../database/schema.sql"));
        }
        String owner = UUID.randomUUID().toString();
        jdbc.update("INSERT INTO users (auth_provider, provider_user_id, nickname) VALUES ('LOCAL', ?, 'USD fixture')", owner);
        Long userId = jdbc.queryForObject("SELECT user_id FROM users WHERE provider_user_id = ?", Long.class, owner);
        jdbc.update("""
            INSERT INTO trade_records (user_id, stock_code, stock_name, market, trade_type, trade_price, quantity, trade_date)
            VALUES (?, '005930', 'Samsung', 'KOSPI', 'BUY', 70000, 1, CURRENT_TIMESTAMP)
            """, userId);
        try (var connection = source.getConnection()) {
            ScriptUtils.executeSqlScript(connection, new FileSystemResource("../database/migrations/028_us_paper_trading.sql"));
        }

        var configuration = new Configuration();
        configuration.setMapUnderscoreToCamelCase(true);
        configuration.addMapper(PaperTradeMapper.class);
        var factory = new SqlSessionFactoryBean();
        factory.setDataSource(source);
        factory.setConfiguration(configuration);
        var mapper = new SqlSessionTemplate(factory.getObject()).getMapper(PaperTradeMapper.class);
        var quotes = mock(MarketPriceService.class);
        when(quotes.getUsQuote("AAPL", "NASDAQ")).thenReturn(new StockQuote(
            "TEST", "AAPL", "", "NASDAQ", new BigDecimal("80.1234"),
            BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO,
            BigDecimal.ZERO, BigDecimal.ZERO, Instant.now()));
        var proxy = new ProxyFactory(new PaperTradingService(
            mapper, mock(CapitalService.class), mock(RecommendationService.class), quotes));
        proxy.setProxyTargetClass(true);
        proxy.addAdvice(new TransactionInterceptor(
            new DataSourceTransactionManager(source), new AnnotationTransactionAttributeSource()));
        var service = (PaperTradingService) proxy.getProxy();

        var context = mock(LocalUserContext.class);
        when(context.userId()).thenReturn(userId);
        var http = MockMvcBuilders.standaloneSetup(new PaperTradingController(service, context)).build();
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
