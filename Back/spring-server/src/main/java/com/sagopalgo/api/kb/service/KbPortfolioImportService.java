package com.sagopalgo.api.kb.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.capital.dto.CapitalResponse;
import com.sagopalgo.api.capital.dto.UpdateCapitalRequest;
import com.sagopalgo.api.capital.service.CapitalService;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import com.sagopalgo.api.holding.mapper.HoldingMapper;
import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.kb.client.KbSecuritiesAccountClient;
import com.sagopalgo.api.kb.dto.KbHoldingResponse;
import com.sagopalgo.api.kb.dto.KbPortfolioImportRequest;
import com.sagopalgo.api.kb.dto.KbPortfolioImportResponse;
import com.sagopalgo.api.kb.dto.KbPortfolioPreviewResponse;
import com.sagopalgo.api.kb.dto.KbPortfolioPreviewResponse.Item;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 명시적인 미리보기/적용으로만 KB 스냅샷을 반영합니다. 조회 누락을 매도로 추정하지 않습니다. */
@Service
public class KbPortfolioImportService {
    private static final Set<String> MARKETS = Set.of("KOSPI", "KOSDAQ", "KONEX");
    private final KbAccountService accountService;
    private final KbSecuritiesAccountClient client;
    private final CapitalService capitalService;
    private final HoldingMapper holdingMapper;
    private final Provider kb;
    private final ObjectMapper objectMapper;

    public KbPortfolioImportService(KbAccountService accountService, KbSecuritiesAccountClient client,
        CapitalService capitalService, HoldingMapper holdingMapper,
        SecuritiesProviderProperties properties, ObjectMapper objectMapper) {
        this.accountService = accountService;
        this.client = client;
        this.capitalService = capitalService;
        this.holdingMapper = holdingMapper;
        this.kb = properties.getKb();
        this.objectMapper = objectMapper;
    }

    public KbPortfolioPreviewResponse preview(Long userId) {
        Instant expiresAt = Instant.now().plusSeconds(300).truncatedTo(ChronoUnit.SECONDS);
        State state = read(userId);
        return new KbPortfolioPreviewResponse(token(userId, expiresAt, state), expiresAt, Instant.now(),
            state.capital().availableCapital(), state.cash(), state.items(), state.retainedCount());
    }

    @Transactional
    public KbPortfolioImportResponse apply(Long userId, KbPortfolioImportRequest request) {
        Instant now = Instant.now();
        if (!request.expiresAt().isAfter(now) || request.expiresAt().isAfter(now.plusSeconds(300))) {
            throw invalid("미리보기가 만료되었습니다. KB 데이터를 다시 조회하세요.");
        }
        if (!request.importCapital() && !request.importHoldings()) {
            throw invalid("반영할 자본금 또는 보유 종목을 선택하세요.");
        }
        holdingMapper.lockUser(userId);
        State state = read(userId);
        if (!MessageDigest.isEqual(token(userId, request.expiresAt(), state).getBytes(StandardCharsets.UTF_8),
            request.previewToken().getBytes(StandardCharsets.UTF_8))) {
            throw invalid("KB 잔고·앱 데이터 또는 연결 설정이 변경되었습니다. 미리보기를 다시 확인하세요.");
        }
        if (request.importCapital() && state.cash() == null) {
            throw invalid("KB 주문가능 현금이 미제공 또는 잘못된 값이어서 자본금으로 반영할 수 없습니다.");
        }
        Map<String, Holding> imported = holdingMapper.findImported(userId, state.accountKey()).stream()
            .collect(Collectors.toMap(Holding::getStockCode, Function.identity()));
        int created = 0;
        int updated = 0;
        int skipped = 0;
        if (request.importHoldings()) {
            for (Item item : state.items()) {
                if ("INVALID".equals(item.action())) {
                    throw invalid("가져올 수 없는 KB 종목이 있습니다. 수량·평균 매수가·중복 행을 확인하세요.");
                }
                String market = request.markets().getOrDefault(item.stockCode(), item.market());
                if (!"SKIP".equals(item.action()) && (market == null || !MARKETS.contains(market))) {
                    throw invalid(item.stockName() + "의 실제 시장(KOSPI/KOSDAQ/KONEX)을 선택하세요.");
                }
            }
            for (Item item : state.items()) {
                if ("SKIP".equals(item.action())) { skipped++; continue; }
                Holding existing = imported.get(item.stockCode());
                String market = request.markets().getOrDefault(item.stockCode(), item.market());
                Holding holding = existing == null ? new Holding() : existing;
                holding.setUserId(userId);
                holding.setStockCode(item.stockCode());
                holding.setStockName(item.stockName());
                holding.setMarket(market);
                holding.setBuyPrice(item.averageBuyPrice());
                holding.setQuantity(item.quantity());
                holding.setSource("KB");
                holding.setSourceAccountKey(state.accountKey());
                holding.setSourceSyncedAt(LocalDateTime.ofInstant(now, ZoneOffset.UTC));
                if (existing == null) {
                    holding.setStatus("HOLDING");
                    holding.setStopLossRate(request.stopLossRate());
                    holding.setTakeProfitRate(request.takeProfitRate());
                    // 실제 매수일은 KB 응답에 없으므로 임의의 날짜를 만들지 않습니다.
                    holdingMapper.insert(holding);
                    created++;
                } else {
                    holdingMapper.updateImported(holding);
                    updated++;
                }
            }
        }
        if (request.importCapital()) {
            capitalService.update(userId, new UpdateCapitalRequest(state.cash(), state.capital().riskPerTradeRate()));
        }
        return new KbPortfolioImportResponse(request.importCapital(), created, updated, skipped, now);
    }

    private State read(Long userId) {
        // API Key에 연결된 B2C 계좌 조회는 주문용 계좌번호 설정과 독립적입니다.
        List<KbHoldingResponse> remote = accountService.holdings().items();
        JsonNode balance = client.fetchSettlementBalance();
        BigDecimal cash = optionalCash(client.text(balance, "ordr_psbl_csh"));
        String accountKey = sign(List.of("KB_PORTFOLIO_ACCOUNT", text(kb.getBaseUrl()),
            text(kb.getAppKey()), text(kb.getAccountNumber()), text(kb.getAccountProductCode())));
        List<Holding> active = holdingMapper.findActiveByUserId(userId);
        if (active.stream().anyMatch(holding -> "KB".equals(holding.getSource())
            && !accountKey.equals(holding.getSourceAccountKey()))) {
            throw invalid("기존 KB 보유분과 현재 연결 설정이 다릅니다. 계좌를 확인하고 기존 KB 보유분을 정리한 뒤 다시 시도하세요.");
        }
        Map<String, Holding> imported = holdingMapper.findImported(userId, accountKey).stream()
            .collect(Collectors.toMap(Holding::getStockCode, Function.identity()));
        Set<String> manualCodes = active.stream().filter(holding -> !"KB".equals(holding.getSource()))
            .filter(holding -> Set.of("KOSPI", "KOSDAQ", "KONEX", "KRX", "KR", "KR_ETC")
                .contains(holding.getMarket().toUpperCase(Locale.ROOT)))
            .map(holding -> holding.getStockCode().trim()).collect(Collectors.toSet());
        Map<String, Long> counts = remote.stream().collect(Collectors.groupingBy(KbHoldingResponse::stockCode, Collectors.counting()));
        List<Item> items = new ArrayList<>();
        for (KbHoldingResponse row : remote) {
            String action = imported.containsKey(row.stockCode()) ? "UPDATE" : "CREATE";
            String message = "CREATE".equals(action) ? "새 KB 보유분으로 추가" : "기존 KB 수량·평균 매수가 갱신";
            String market = imported.containsKey(row.stockCode()) ? imported.get(row.stockCode()).getMarket() : row.market();
            if (manualCodes.contains(row.stockCode())) {
                action = "SKIP"; message = "동일 종목의 수동 등록분이 있어 보존하고 건너뜁니다.";
            } else if (!row.stockCode().matches("[0-9]{6}") || counts.get(row.stockCode()) > 1
                || row.quantity().signum() <= 0 || row.averageBuyPrice().signum() <= 0
                || row.quantity().precision() - row.quantity().scale() > 14
                || row.averageBuyPrice().precision() - row.averageBuyPrice().scale() > 16) {
                action = "INVALID"; message = "국내 주식 코드·수량·평균 매수가·중복 행 확인 필요";
            }
            items.add(new Item(row.stockCode(), row.stockName(), market,
                row.quantity(), row.averageBuyPrice(), action, message));
        }
        items.sort(Comparator.comparing(Item::stockCode).thenComparing(Item::quantity));
        Set<String> received = items.stream().map(Item::stockCode).collect(Collectors.toSet());
        int retained = (int) active.stream().filter(holding -> "KB".equals(holding.getSource()))
            .filter(holding -> !received.contains(holding.getStockCode())).count();
        // 사용자 확인 뒤 앱 값이 바뀐 경우에도 다시 확인하도록 토큰에 현재 DB 상태를 포함합니다.
        List<String> local = active.stream().sorted(Comparator.comparing(Holding::getHoldingId))
            .map(holding -> holding.getHoldingId() + ":" + holding.getStockCode() + ":" + holding.getMarket()
                + ":" + holding.getBuyPrice() + ":" + holding.getQuantity() + ":" + holding.getSource()
                + ":" + holding.getStopLossRate() + ":" + holding.getTakeProfitRate()).toList();
        return new State(accountKey, capitalService.findByUserId(userId), cash, items, retained, local);
    }

    private BigDecimal optionalCash(String value) {
        if (value == null || value.isBlank()) return null;
        try {
            BigDecimal cash = new BigDecimal(value.replace(",", "").trim());
            return cash.signum() < 0 || cash.precision() - cash.scale() > 16 ? null : cash.setScale(2, RoundingMode.HALF_UP);
        } catch (NumberFormatException exception) { return null; }
    }

    private String token(Long userId, Instant expiresAt, State state) {
        return sign(List.of("KB_PORTFOLIO_PREVIEW", userId, expiresAt.toString(), state));
    }

    private String sign(Object value) {
        if (kb.getAppSecret() == null || kb.getAppSecret().isBlank()) throw invalid("KB 인증 설정이 필요합니다.");
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(kb.getAppSecret().getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return HexFormat.of().formatHex(mac.doFinal(objectMapper.writeValueAsBytes(value)));
        } catch (Exception exception) { throw new IllegalStateException("KB 가져오기 확인값을 생성하지 못했습니다.", exception); }
    }

    private static String text(String value) { return value == null ? "" : value.trim(); }
    private static ApiException invalid(String message) { return new ApiException(ErrorCode.VALIDATION_ERROR, message); }
    private record State(String accountKey, CapitalResponse capital, BigDecimal cash, List<Item> items,
        int retainedCount, List<String> local) {}
}
