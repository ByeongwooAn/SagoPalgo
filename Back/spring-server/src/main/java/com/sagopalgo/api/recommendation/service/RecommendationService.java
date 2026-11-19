package com.sagopalgo.api.recommendation.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.alert.service.AlertService;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.AiAnalysisProperties;
import com.sagopalgo.api.dashboard.dto.DashboardRecommendationReasonResponse;
import com.sagopalgo.api.dashboard.dto.DashboardRecommendationResponse;
import com.sagopalgo.api.dashboard.service.DashboardRecommendationEngine;
import com.sagopalgo.api.holding.dto.HoldingResponse;
import com.sagopalgo.api.holding.dto.PortfolioCostExposure;
import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.holding.service.HoldingService;
import com.sagopalgo.api.market.dto.MarketCandleResponse;
import com.sagopalgo.api.market.model.CandleInterval;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.service.MarketCandleService;
import com.sagopalgo.api.market.service.MarketPriceService;
import com.sagopalgo.api.recommendation.client.AiAnalysisGateway;
import com.sagopalgo.api.recommendation.dto.AiInvestmentAnalysisRequest;
import com.sagopalgo.api.recommendation.dto.AiInvestmentAnalysisResponse;
import com.sagopalgo.api.recommendation.dto.DailySignal;
import com.sagopalgo.api.recommendation.dto.RecommendationListResponse;
import com.sagopalgo.api.recommendation.dto.RecommendationReasonResponse;
import com.sagopalgo.api.recommendation.dto.RecommendationResponse;
import com.sagopalgo.api.recommendation.dto.AnalysisEvidence;
import com.sagopalgo.api.recommendation.model.AnalysisSnapshotRecord;
import com.sagopalgo.api.recommendation.model.RecommendationReasonRecord;
import com.sagopalgo.api.recommendation.model.RecommendationRecord;
import com.sagopalgo.api.recommendation.model.StoredRecommendation;
import com.sagopalgo.api.research.model.ResearchRequest;
import com.sagopalgo.api.research.model.StoredResearchFeed;
import com.sagopalgo.api.research.service.ResearchFeedStore;
import com.sagopalgo.api.watchlist.mapper.WatchlistMapper;
import com.sagopalgo.api.watchlist.model.WatchlistItem;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 보유 종목의 가격·뉴스·공시를 분석하고 설명 가능한 추천 이력을 관리합니다.
 */
@Service
public class RecommendationService {

    private static final Logger log = LoggerFactory.getLogger(RecommendationService.class);
    private static final int MAX_PAGE_SIZE = 100;

    private final HoldingService holdingService;
    private final WatchlistMapper watchlistMapper;
    private final MarketPriceService marketPriceService;
    private final MarketCandleService marketCandleService;
    private final ResearchFeedStore researchFeedStore;
    private final AiAnalysisGateway aiAnalysisGateway;
    private final DashboardRecommendationEngine fallbackEngine;
    private final RecommendationStore recommendationStore;
    private final AlertService alertService;
    private final AiAnalysisProperties properties;
    private final ObjectMapper objectMapper;
    private final DailySignalService dailySignalService;

    public RecommendationService(
        HoldingService holdingService,
        WatchlistMapper watchlistMapper,
        MarketPriceService marketPriceService,
        MarketCandleService marketCandleService,
        ResearchFeedStore researchFeedStore,
        AiAnalysisGateway aiAnalysisGateway,
        DashboardRecommendationEngine fallbackEngine,
        RecommendationStore recommendationStore,
        AlertService alertService,
        AiAnalysisProperties properties,
        ObjectMapper objectMapper,
        DailySignalService dailySignalService
    ) {
        this.holdingService = holdingService;
        this.watchlistMapper = watchlistMapper;
        this.marketPriceService = marketPriceService;
        this.marketCandleService = marketCandleService;
        this.researchFeedStore = researchFeedStore;
        this.aiAnalysisGateway = aiAnalysisGateway;
        this.fallbackEngine = fallbackEngine;
        this.recommendationStore = recommendationStore;
        this.alertService = alertService;
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.dailySignalService = dailySignalService;
    }

    @Transactional
    public RecommendationResponse analyzeHolding(Long userId, Long holdingId) {
        return analyzeHolding(userId, holdingId, true);
    }

    @Transactional
    public RecommendationResponse analyzeHolding(Long userId, Long holdingId, boolean includeDailySignal) {
        Holding record = holdingService.findRecord(userId, holdingId);
        StockQuote quote = marketPriceService.quoteMarket(MarketDataRequest.from(record));
        if (!hasRealPrice(quote)) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "실제 현재가가 없어 보유 종목을 분석할 수 없습니다.");
        }
        BigDecimal profitRate = quote.currentPrice().subtract(record.getBuyPrice())
            .divide(record.getBuyPrice(), 6, RoundingMode.HALF_UP)
            .multiply(new BigDecimal("100"))
            .setScale(2, RoundingMode.HALF_UP);
        HoldingResponse holding = HoldingResponse.from(record, quote.currentPrice(), profitRate);
        PortfolioCostExposure exposure = holdingService.costExposure(
            userId, holding.stockCode(), holding.market()
        ).orElse(null);
        AiInvestmentAnalysisRequest request = analysisRequest(holding, exposure);
        AiInvestmentAnalysisResponse analysis = aiAnalysisGateway.analyze(request)
            .filter(candidate -> isHoldingSafe(candidate, holding, exposure))
            .orElseGet(() -> fallbackAnalysis(holding));
        StoredRecommendation stored = recommendationStore.save(
            recommendationRecord(userId, request, analysis),
            reasonRecords(analysis),
            snapshotRecord(userId, analysis, request, includeDailySignal)
        );
        alertService.createFromRecommendation(stored);
        return response(stored);
    }

    @Transactional
    public RecommendationResponse analyzeWatchlist(Long userId, Long watchlistId) {
        return analyzeWatchlist(userId, watchlistId, true);
    }

    @Transactional
    public RecommendationResponse analyzeWatchlist(Long userId, Long watchlistId, boolean includeDailySignal) {
        WatchlistItem item = watchlistMapper.findByIdAndUserId(watchlistId, userId)
            .orElseThrow(() -> new ApiException(ErrorCode.RESOURCE_NOT_FOUND, "관심 종목을 찾을 수 없습니다."));
        StockQuote quote = marketPriceService.quoteMarket(
            new MarketDataRequest(item.getStockCode(), item.getMarket())
        );
        if (!hasRealPrice(quote)) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "실제 현재가가 없어 관심 종목을 분석할 수 없습니다.");
        }
        AiInvestmentAnalysisRequest request = analysisRequest(
            item.getStockCode(), item.getStockName(), item.getMarket(), quote.currentPrice(),
            null, null, null, null, "WATCHLIST", null
        );
        AiInvestmentAnalysisResponse analysis = aiAnalysisGateway.analyze(request)
            .filter(this::isWatchlistSafe)
            .orElseGet(this::watchlistFallbackAnalysis);
        StoredRecommendation stored = recommendationStore.save(
            recommendationRecord(userId, request, analysis),
            reasonRecords(analysis),
            snapshotRecord(userId, analysis, request, includeDailySignal)
        );
        alertService.createFromRecommendation(stored);
        return response(stored);
    }

    private boolean hasRealPrice(StockQuote quote) {
        return quote != null && quote.currentPrice() != null && quote.currentPrice().signum() > 0
            && quote.provider() != null && !quote.provider().isBlank()
            && !"FALLBACK".equalsIgnoreCase(quote.provider());
    }

    public RecommendationListResponse findAll(
        Long userId,
        String status,
        int page,
        int size
    ) {
        if (page < 0 || size < 1 || size > MAX_PAGE_SIZE) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "추천 페이지는 0 이상, 크기는 1~100이어야 합니다.");
        }
        String normalizedStatus = normalizeStatus(status);
        List<RecommendationResponse> items = recommendationStore.findPage(
                userId,
                normalizedStatus,
                page,
                size
            )
            .stream()
            .map(this::response)
            .toList();
        return new RecommendationListResponse(
            items,
            page,
            size,
            recommendationStore.count(userId, normalizedStatus)
        );
    }

    public RecommendationResponse findOne(Long userId, Long recommendationId) {
        return recommendationStore.findById(userId, recommendationId)
            .map(this::response)
            .orElseThrow(() -> new ApiException(ErrorCode.RESOURCE_NOT_FOUND, "추천 결과를 찾을 수 없습니다."));
    }

    public Optional<DashboardRecommendationResponse> findLatestDashboardRecommendation(Long userId) {
        return recommendationStore.findLatestRelevant(userId).map(this::dashboardResponse);
    }

    private AiInvestmentAnalysisRequest analysisRequest(
        HoldingResponse holding,
        PortfolioCostExposure exposure
    ) {
        return analysisRequest(
            holding.stockCode(), holding.stockName(), holding.market(), holding.currentPrice(),
            holding.buyPrice(), holding.profitRate(), holding.stopLossRate(), holding.takeProfitRate(),
            "HOLDING", exposure
        );
    }

    private AiInvestmentAnalysisRequest analysisRequest(
        String stockCode,
        String stockName,
        String market,
        BigDecimal currentPrice,
        BigDecimal buyPrice,
        BigDecimal profitRate,
        BigDecimal stopLossRate,
        BigDecimal takeProfitRate,
        String analysisType,
        PortfolioCostExposure exposure
    ) {
        LocalDate toDate = LocalDate.now(java.time.ZoneId.of("Asia/Seoul"));
        LocalDate fromDate = toDate.minusDays(Math.max(1, properties.getLookbackDays()));
        StoredResearchFeed research = researchFeedStore.find(new ResearchRequest(
            stockCode,
            stockName,
            fromDate,
            toDate
        ));
        List<AiInvestmentAnalysisRequest.CandleInput> candles = candles(stockCode, market);
        return new AiInvestmentAnalysisRequest(
            stockCode,
            stockName,
            market,
            currentPrice,
            buyPrice,
            profitRate,
            stopLossRate,
            takeProfitRate,
            candles,
            research.news().stream()
                .map(item -> new AiInvestmentAnalysisRequest.NewsInput(item.title(), item.summary()))
                .toList(),
            research.disclosures().stream()
                .map(item -> new AiInvestmentAnalysisRequest.DisclosureInput(item.reportName()))
                .toList(),
            analysisType,
            exposure == null ? null : exposure.portfolioWeightRate(),
            exposure == null ? null : exposure.capitalWeightRate(),
            exposure == null ? null : exposure.maxCapitalWeightRate()
        );
    }

    private List<AiInvestmentAnalysisRequest.CandleInput> candles(String stockCode, String market) {
        try {
            MarketCandleResponse response = marketCandleService.getCandles(
                stockCode,
                market,
                CandleInterval.DAILY,
                Math.max(2, Math.min(100, properties.getCandleCount()))
            );
            return response.candles().stream()
                .map(item -> new AiInvestmentAnalysisRequest.CandleInput(
                    item.dateTime(),
                    item.closePrice(),
                    item.volume()
                ))
                .toList();
        } catch (ApiException exception) {
            log.warn(
                "추천 분석용 캔들 조회 실패. stockCode={} message={}",
                stockCode,
                exception.getMessage()
            );
            return List.of();
        }
    }

    private AiInvestmentAnalysisResponse fallbackAnalysis(HoldingResponse holding) {
        DashboardRecommendationResponse fallback = fallbackEngine.recommend(List.of(holding));
        String status = machineStatus(fallback.status());
        String recommendationType = status.equals("TAKE_PROFIT") || status.equals("STOP_LOSS_WATCH")
            ? "SELL"
            : "HOLD";
        return new AiInvestmentAnalysisResponse(
            "RULE_FALLBACK_V1",
            recommendationType,
            status,
            fallback.score(),
            fallback.aiSummary(),
            fallback.reasons().stream()
                .map(reason -> new AiInvestmentAnalysisResponse.Reason(
                    reason.label(),
                    reason.description(),
                    reason.type(),
                    reason.score()
                ))
                .toList()
        );
    }

    private AiInvestmentAnalysisResponse watchlistFallbackAnalysis() {
        return new AiInvestmentAnalysisResponse(
            "RULE_FALLBACK_V1", "HOLD", "HOLD", 50,
            "AI 분석 서버에 연결할 수 없어 관심 종목의 매수·매도 판단을 보류합니다.",
            List.of(new AiInvestmentAnalysisResponse.Reason(
                "분석 대기", "가격·뉴스·공시의 종합 판단은 AI 서버 연결 후 다시 확인해 주세요.", "RISK", 0
            ))
        );
    }

    private boolean isWatchlistSafe(AiInvestmentAnalysisResponse analysis) {
        if (analysis == null || analysis.status() == null || analysis.recommendationType() == null) {
            return false;
        }
        return switch (analysis.status()) {
            case "BUY_STRONG", "BUY_WATCH" -> "BUY".equals(analysis.recommendationType());
            case "HOLD", "RISK" -> "HOLD".equals(analysis.recommendationType());
            default -> false;
        };
    }

    private boolean isHoldingSafe(
        AiInvestmentAnalysisResponse analysis,
        HoldingResponse holding,
        PortfolioCostExposure exposure
    ) {
        if (analysis == null || analysis.status() == null || analysis.recommendationType() == null) {
            return false;
        }
        boolean compatible = switch (analysis.status()) {
            case "BUY_STRONG", "BUY_WATCH" -> "BUY".equals(analysis.recommendationType());
            case "TAKE_PROFIT", "STOP_LOSS_WATCH" -> "SELL".equals(analysis.recommendationType());
            case "HOLD" -> "HOLD".equals(analysis.recommendationType());
            case "RISK" -> "HOLD".equals(analysis.recommendationType())
                || "SELL".equals(analysis.recommendationType());
            default -> false;
        };
        if (!compatible) {
            return false;
        }
        if (holding.profitRate().compareTo(holding.stopLossRate().add(BigDecimal.ONE)) <= 0) {
            return "STOP_LOSS_WATCH".equals(analysis.status());
        }
        if (holding.profitRate().compareTo(holding.takeProfitRate().subtract(BigDecimal.ONE)) >= 0) {
            return "TAKE_PROFIT".equals(analysis.status());
        }
        if ("STOP_LOSS_WATCH".equals(analysis.status()) || "TAKE_PROFIT".equals(analysis.status())) {
            return false;
        }
        return exposure == null || exposure.capitalWeightRate() == null
            || exposure.maxCapitalWeightRate() == null
            || exposure.capitalWeightRate().compareTo(exposure.maxCapitalWeightRate()) <= 0
            || !"BUY".equals(analysis.recommendationType());
    }

    private RecommendationRecord recommendationRecord(
        Long userId,
        AiInvestmentAnalysisRequest request,
        AiInvestmentAnalysisResponse analysis
    ) {
        RecommendationRecord record = new RecommendationRecord();
        record.setUserId(userId);
        record.setStockCode(request.stockCode());
        record.setStockName(request.stockName());
        record.setMarket(request.market());
        record.setAnalysisContext(request.analysisType());
        record.setRecommendationType(analysis.recommendationType());
        record.setStatus(analysis.status());
        record.setScore(Math.max(0, Math.min(100, analysis.score())));
        record.setEntryPrice(request.currentPrice());
        record.setStopLossRate(request.stopLossRate());
        record.setTakeProfitRate(request.takeProfitRate());
        record.setAiSummary(analysis.summary());
        return record;
    }

    private List<RecommendationReasonRecord> reasonRecords(AiInvestmentAnalysisResponse analysis) {
        if (analysis.reasons() == null) {
            return List.of();
        }
        return analysis.reasons().stream().map(reason -> {
            RecommendationReasonRecord record = new RecommendationReasonRecord();
            record.setReasonType(reason.type());
            record.setLabel(reason.label());
            record.setDescription(reason.description());
            record.setScore(reason.score());
            return record;
        }).toList();
    }

    private AnalysisSnapshotRecord snapshotRecord(
        Long userId,
        AiInvestmentAnalysisResponse analysis,
        AiInvestmentAnalysisRequest request,
        boolean includeDailySignal
    ) {
        AnalysisSnapshotRecord record = new AnalysisSnapshotRecord();
        record.setUserId(userId);
        record.setStockCode(request.stockCode());
        record.setMarket(request.market());
        record.setAnalysisType("WATCHLIST".equals(request.analysisType()) ? "WATCHLIST" : "TOTAL");
        record.setScore(analysis.score());
        DailySignal dailySignal = includeDailySignal ? dailySignalService.analyze(request.stockCode(), request.market()) : null;
        record.setRawPayload(rawPayload(request, analysis, dailySignal));
        return record;
    }

    private String rawPayload(
        AiInvestmentAnalysisRequest request,
        AiInvestmentAnalysisResponse analysis,
        DailySignal dailySignal
    ) {
        try {
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("request", request);
            payload.put("analysis", analysis);
            if (dailySignal != null) payload.put("dailySignal", dailySignal);
            return objectMapper.writeValueAsString(payload);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("AI 분석 원문을 JSON으로 저장할 수 없습니다.", exception);
        }
    }

    private RecommendationResponse response(StoredRecommendation stored) {
        RecommendationRecord item = stored.recommendation();
        return new RecommendationResponse(
            item.getRecommendationId(),
            item.getStockCode(),
            item.getStockName(),
            item.getMarket(),
            item.getRecommendationType(),
            item.getStatus(),
            statusLabel(item.getStatus(), item.getAnalysisContext()),
            item.getScore(),
            item.getEntryPrice(),
            item.getStopLossRate(),
            item.getTakeProfitRate(),
            item.getAiSummary(),
            item.getCreatedAt(),
            stored.reasons().stream()
                .map(reason -> new RecommendationReasonResponse(
                    reason.getReasonType(),
                    reason.getLabel(),
                    reason.getDescription(),
                    reason.getScore()
                ))
                .toList(),
            item.getAnalysisContext(),
            evidence(item)
        );
    }

    private DashboardRecommendationResponse dashboardResponse(StoredRecommendation stored) {
        RecommendationRecord item = stored.recommendation();
        return new DashboardRecommendationResponse(
            item.getRecommendationId(),
            item.getStockName(),
            item.getStockCode(),
            item.getMarket(),
            statusLabel(item.getStatus(), item.getAnalysisContext()),
            item.getScore(),
            item.getEntryPrice(),
            item.getStopLossRate(),
            item.getAiSummary(),
            stored.reasons().stream()
                .map(reason -> new DashboardRecommendationReasonResponse(
                    reason.getLabel(),
                    reason.getDescription(),
                    reason.getReasonType(),
                    reason.getScore()
                ))
                .toList(),
            item.getRecommendationType(), item.getAnalysisContext(), item.getStatus(), item.getCreatedAt(), evidence(item)
        );
    }

    private AnalysisEvidence evidence(RecommendationRecord record) {
        if (record.getAnalysisEvidence() == null || record.getAnalysisEvidence().isBlank()) return null;
        try {
            return objectMapper.readValue(record.getAnalysisEvidence(), AnalysisEvidence.class);
        } catch (JsonProcessingException exception) {
            return null; // 이전/손상된 이력의 출처를 임의로 추정하지 않습니다.
        }
    }

    private String normalizeStatus(String status) {
        return status == null || status.isBlank()
            ? null
            : status.trim().toUpperCase(Locale.ROOT);
    }

    private String machineStatus(String displayStatus) {
        if (displayStatus.contains("손절")) {
            return "STOP_LOSS_WATCH";
        }
        if (displayStatus.contains("익절")) {
            return "TAKE_PROFIT";
        }
        return "HOLD";
    }

    private String statusLabel(String status, String analysisContext) {
        if ("WATCHLIST".equals(analysisContext) && "RISK".equals(status)) {
            return "진입 보류";
        }
        return switch (status) {
            case "BUY_STRONG" -> "강한 매수";
            case "BUY_WATCH" -> "매수 관찰";
            case "TAKE_PROFIT" -> "부분 익절 검토";
            case "STOP_LOSS_WATCH" -> "손절 감시";
            case "RISK" -> "위험 축소";
            default -> "보유 유지";
        };
    }
}
