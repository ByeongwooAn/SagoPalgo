package com.sagopalgo.api.recommendation.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.AiAnalysisProperties;
import com.sagopalgo.api.dashboard.dto.DashboardRecommendationReasonResponse;
import com.sagopalgo.api.dashboard.dto.DashboardRecommendationResponse;
import com.sagopalgo.api.dashboard.service.DashboardRecommendationEngine;
import com.sagopalgo.api.holding.dto.HoldingResponse;
import com.sagopalgo.api.holding.service.HoldingService;
import com.sagopalgo.api.market.dto.MarketCandleResponse;
import com.sagopalgo.api.market.model.CandleInterval;
import com.sagopalgo.api.market.service.MarketCandleService;
import com.sagopalgo.api.recommendation.client.AiAnalysisGateway;
import com.sagopalgo.api.recommendation.dto.AiInvestmentAnalysisRequest;
import com.sagopalgo.api.recommendation.dto.AiInvestmentAnalysisResponse;
import com.sagopalgo.api.recommendation.dto.RecommendationListResponse;
import com.sagopalgo.api.recommendation.dto.RecommendationReasonResponse;
import com.sagopalgo.api.recommendation.dto.RecommendationResponse;
import com.sagopalgo.api.recommendation.model.AnalysisSnapshotRecord;
import com.sagopalgo.api.recommendation.model.RecommendationReasonRecord;
import com.sagopalgo.api.recommendation.model.RecommendationRecord;
import com.sagopalgo.api.recommendation.model.StoredRecommendation;
import com.sagopalgo.api.research.model.ResearchRequest;
import com.sagopalgo.api.research.model.StoredResearchFeed;
import com.sagopalgo.api.research.service.ResearchFeedStore;
import java.time.LocalDate;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * 보유 종목의 가격·뉴스·공시를 분석하고 설명 가능한 추천 이력을 관리합니다.
 */
@Service
public class RecommendationService {

    private static final Logger log = LoggerFactory.getLogger(RecommendationService.class);
    private static final int MAX_PAGE_SIZE = 100;

    private final HoldingService holdingService;
    private final MarketCandleService marketCandleService;
    private final ResearchFeedStore researchFeedStore;
    private final AiAnalysisGateway aiAnalysisGateway;
    private final DashboardRecommendationEngine fallbackEngine;
    private final RecommendationStore recommendationStore;
    private final AiAnalysisProperties properties;
    private final ObjectMapper objectMapper;

    public RecommendationService(
        HoldingService holdingService,
        MarketCandleService marketCandleService,
        ResearchFeedStore researchFeedStore,
        AiAnalysisGateway aiAnalysisGateway,
        DashboardRecommendationEngine fallbackEngine,
        RecommendationStore recommendationStore,
        AiAnalysisProperties properties,
        ObjectMapper objectMapper
    ) {
        this.holdingService = holdingService;
        this.marketCandleService = marketCandleService;
        this.researchFeedStore = researchFeedStore;
        this.aiAnalysisGateway = aiAnalysisGateway;
        this.fallbackEngine = fallbackEngine;
        this.recommendationStore = recommendationStore;
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    public RecommendationResponse analyzeHolding(Long userId, Long holdingId) {
        HoldingResponse holding = holdingService.findOne(userId, holdingId);
        AiInvestmentAnalysisRequest request = analysisRequest(holding);
        AiInvestmentAnalysisResponse analysis = aiAnalysisGateway.analyze(request)
            .orElseGet(() -> fallbackAnalysis(holding));
        StoredRecommendation stored = recommendationStore.save(
            recommendationRecord(userId, holding, analysis),
            reasonRecords(analysis),
            snapshotRecord(userId, holding, analysis, request)
        );
        return response(stored);
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
        return recommendationStore.findLatest(userId).map(this::dashboardResponse);
    }

    private AiInvestmentAnalysisRequest analysisRequest(HoldingResponse holding) {
        LocalDate toDate = LocalDate.now();
        LocalDate fromDate = toDate.minusDays(Math.max(1, properties.getLookbackDays()));
        StoredResearchFeed research = researchFeedStore.find(new ResearchRequest(
            holding.stockCode(),
            holding.stockName(),
            fromDate,
            toDate
        ));
        List<AiInvestmentAnalysisRequest.CandleInput> candles = candles(holding);
        return new AiInvestmentAnalysisRequest(
            holding.stockCode(),
            holding.stockName(),
            holding.market(),
            holding.currentPrice(),
            holding.buyPrice(),
            holding.profitRate(),
            holding.stopLossRate(),
            holding.takeProfitRate(),
            candles,
            research.news().stream()
                .map(item -> new AiInvestmentAnalysisRequest.NewsInput(item.title(), item.summary()))
                .toList(),
            research.disclosures().stream()
                .map(item -> new AiInvestmentAnalysisRequest.DisclosureInput(item.reportName()))
                .toList()
        );
    }

    private List<AiInvestmentAnalysisRequest.CandleInput> candles(HoldingResponse holding) {
        try {
            MarketCandleResponse response = marketCandleService.getCandles(
                holding.stockCode(),
                holding.market(),
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
                holding.stockCode(),
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

    private RecommendationRecord recommendationRecord(
        Long userId,
        HoldingResponse holding,
        AiInvestmentAnalysisResponse analysis
    ) {
        RecommendationRecord record = new RecommendationRecord();
        record.setUserId(userId);
        record.setStockCode(holding.stockCode());
        record.setStockName(holding.stockName());
        record.setMarket(holding.market());
        record.setRecommendationType(analysis.recommendationType());
        record.setStatus(analysis.status());
        record.setScore(Math.max(0, Math.min(100, analysis.score())));
        record.setEntryPrice(holding.currentPrice());
        record.setStopLossRate(holding.stopLossRate());
        record.setTakeProfitRate(holding.takeProfitRate());
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
        HoldingResponse holding,
        AiInvestmentAnalysisResponse analysis,
        AiInvestmentAnalysisRequest request
    ) {
        AnalysisSnapshotRecord record = new AnalysisSnapshotRecord();
        record.setUserId(userId);
        record.setStockCode(holding.stockCode());
        record.setMarket(holding.market());
        record.setAnalysisType("TOTAL");
        record.setScore(analysis.score());
        record.setRawPayload(rawPayload(request, analysis));
        return record;
    }

    private String rawPayload(
        AiInvestmentAnalysisRequest request,
        AiInvestmentAnalysisResponse analysis
    ) {
        try {
            return objectMapper.writeValueAsString(Map.of(
                "request", request,
                "analysis", analysis
            ));
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
            statusLabel(item.getStatus()),
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
                .toList()
        );
    }

    private DashboardRecommendationResponse dashboardResponse(StoredRecommendation stored) {
        RecommendationRecord item = stored.recommendation();
        return new DashboardRecommendationResponse(
            item.getRecommendationId(),
            item.getStockName(),
            item.getStockCode(),
            item.getMarket(),
            statusLabel(item.getStatus()),
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
                .toList()
        );
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

    private String statusLabel(String status) {
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
