package com.sagopalgo.api.kb.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.sagopalgo.api.kb.client.KbSecuritiesAccountClient;
import com.sagopalgo.api.kb.dto.KbAccountListResponse;
import com.sagopalgo.api.kb.dto.KbAccountResponse;
import com.sagopalgo.api.kb.dto.KbHoldingResponse;
import com.sagopalgo.api.kb.dto.KbHoldingsResponse;
import com.sagopalgo.api.kb.dto.KbPortfolioSummaryResponse;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/**
 * KB증권 계좌 데이터를 앱 내부 응답 모델로 정규화합니다.
 */
@Service
public class KbAccountService {

    private static final int MONEY_SCALE = 2;
    private static final int RATE_SCALE = 2;

    private final KbSecuritiesAccountClient kbClient;

    public KbAccountService(KbSecuritiesAccountClient kbClient) {
        this.kbClient = kbClient;
    }

    public KbAccountListResponse accounts() {
        kbClient.ensureAccountEnabled();
        if (!kbClient.hasAccountsPath() && kbClient.hasConfiguredAccountFallback()) {
            return new KbAccountListResponse(List.of(configuredAccount()));
        }
        if (!kbClient.hasAccountsPath()) {
            return new KbAccountListResponse(List.of());
        }

        JsonNode response = kbClient.fetchAccounts();
        List<KbAccountResponse> accounts = kbClient.items(response, "accounts", "accountList")
            .stream()
            .map(this::account)
            .toList();
        return new KbAccountListResponse(accounts);
    }

    public KbHoldingsResponse holdings() {
        JsonNode response = kbClient.fetchHoldings();
        List<KbHoldingResponse> items = kbClient.items(response, "holdings", "holdingList", "stocks", "stockList")
            .stream()
            .map(this::holding)
            .toList();
        return withWeights(items);
    }

    private KbAccountResponse configuredAccount() {
        return new KbAccountResponse(
            "KB",
            "primary",
            maskAccountNumber(kbClient.configuredAccountNumber()),
            kbClient.configuredAccountProductCode(),
            "KB증권 연결 계좌",
            "SECURITIES",
            "KRW"
        );
    }

    private KbAccountResponse account(JsonNode node) {
        String accountNumber = kbClient.text(node, "accountNumber", "acctNo", "acntNo", "acno", "actno");
        String productCode = kbClient.text(node, "accountProductCode", "productCode", "acctPrdtCd", "prdCd", "prd_cd");
        return new KbAccountResponse(
            "KB",
            "primary",
            maskAccountNumber(accountNumber),
            productCode,
            defaultText(kbClient.text(node, "accountName", "acctName", "acntName", "account_name"), "KB증권 계좌"),
            defaultText(kbClient.text(node, "accountType", "acctType", "productName", "prdtName"), "SECURITIES"),
            defaultText(kbClient.text(node, "currency", "currencyCode", "crcyCd"), "KRW")
        );
    }

    private KbHoldingResponse holding(JsonNode node) {
        BigDecimal quantity = kbClient.decimal(node, "quantity", "hldgQty", "hldg_qty", "qty");
        BigDecimal averageBuyPrice = kbClient.decimal(node, "averageBuyPrice", "avgBuyPrice", "pchsAvgPric", "buyPrice");
        BigDecimal currentPrice = kbClient.decimal(node, "currentPrice", "nowPrice", "prpr", "curPrice");
        BigDecimal purchaseAmount = kbClient.decimal(node, "purchaseAmount", "pchsAmt", "buyAmount");
        BigDecimal valuationAmount = kbClient.decimal(node, "valuationAmount", "evluAmt", "evalAmount");
        BigDecimal profitAmount = kbClient.decimal(node, "profitAmount", "evluPflsAmt", "profitLossAmount");
        BigDecimal profitRate = kbClient.decimal(node, "profitRate", "evluPflsRt", "profitLossRate");

        if (purchaseAmount.compareTo(BigDecimal.ZERO) == 0) {
            purchaseAmount = averageBuyPrice.multiply(quantity);
        }
        if (valuationAmount.compareTo(BigDecimal.ZERO) == 0) {
            valuationAmount = currentPrice.multiply(quantity);
        }
        if (profitAmount.compareTo(BigDecimal.ZERO) == 0) {
            profitAmount = valuationAmount.subtract(purchaseAmount);
        }
        if (profitRate.compareTo(BigDecimal.ZERO) == 0 && purchaseAmount.compareTo(BigDecimal.ZERO) > 0) {
            profitRate = profitAmount.divide(purchaseAmount, 6, RoundingMode.HALF_UP)
                .multiply(new BigDecimal("100"));
        }

        return new KbHoldingResponse(
            kbClient.text(node, "stockCode", "isuNo", "isNo", "pdno", "shtnPdno"),
            defaultText(kbClient.text(node, "stockName", "isuNm", "isNm", "productName", "prdtName"), "알 수 없는 종목"),
            defaultText(kbClient.text(node, "market", "marketName", "mrktName"), "KRX"),
            money(quantity),
            money(averageBuyPrice),
            money(currentPrice),
            money(purchaseAmount),
            money(valuationAmount),
            money(profitAmount),
            rate(profitRate),
            BigDecimal.ZERO
        );
    }

    private KbHoldingsResponse withWeights(List<KbHoldingResponse> items) {
        BigDecimal totalPurchaseAmount = BigDecimal.ZERO;
        BigDecimal totalValuationAmount = BigDecimal.ZERO;
        BigDecimal totalProfitAmount = BigDecimal.ZERO;

        for (KbHoldingResponse item : items) {
            totalPurchaseAmount = totalPurchaseAmount.add(item.purchaseAmount());
            totalValuationAmount = totalValuationAmount.add(item.valuationAmount());
            totalProfitAmount = totalProfitAmount.add(item.profitAmount());
        }

        BigDecimal portfolioProfitRate = BigDecimal.ZERO;
        if (totalPurchaseAmount.compareTo(BigDecimal.ZERO) > 0) {
            portfolioProfitRate = totalProfitAmount.divide(totalPurchaseAmount, 6, RoundingMode.HALF_UP)
                .multiply(new BigDecimal("100"));
        }

        BigDecimal totalValuation = totalValuationAmount;
        List<KbHoldingResponse> weightedItems = items.stream()
            .map(item -> withWeight(item, totalValuation))
            .toList();

        return new KbHoldingsResponse(
            new KbPortfolioSummaryResponse(
                money(totalPurchaseAmount),
                money(totalValuationAmount),
                money(totalProfitAmount),
                rate(portfolioProfitRate)
            ),
            weightedItems
        );
    }

    private KbHoldingResponse withWeight(KbHoldingResponse item, BigDecimal totalValuationAmount) {
        BigDecimal weightRate = BigDecimal.ZERO;
        if (totalValuationAmount.compareTo(BigDecimal.ZERO) > 0) {
            weightRate = item.valuationAmount()
                .divide(totalValuationAmount, 6, RoundingMode.HALF_UP)
                .multiply(new BigDecimal("100"));
        }

        return new KbHoldingResponse(
            item.stockCode(),
            item.stockName(),
            item.market(),
            item.quantity(),
            item.averageBuyPrice(),
            item.currentPrice(),
            item.purchaseAmount(),
            item.valuationAmount(),
            item.profitAmount(),
            item.profitRate(),
            rate(weightRate)
        );
    }

    private String maskAccountNumber(String accountNumber) {
        if (!StringUtils.hasText(accountNumber)) {
            return "";
        }
        String compact = accountNumber.replaceAll("[^0-9A-Za-z]", "");
        if (compact.length() <= 4) {
            return "****";
        }
        return "****" + compact.substring(compact.length() - 4);
    }

    private String defaultText(String value, String fallback) {
        return StringUtils.hasText(value) ? value : fallback;
    }

    private BigDecimal money(BigDecimal value) {
        return value.setScale(MONEY_SCALE, RoundingMode.HALF_UP).stripTrailingZeros();
    }

    private BigDecimal rate(BigDecimal value) {
        return value.setScale(RATE_SCALE, RoundingMode.HALF_UP).stripTrailingZeros();
    }
}
