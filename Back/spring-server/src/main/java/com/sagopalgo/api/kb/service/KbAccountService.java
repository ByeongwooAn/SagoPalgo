package com.sagopalgo.api.kb.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.sagopalgo.api.kb.client.KbSecuritiesAccountClient;
import com.sagopalgo.api.kb.dto.KbAccountListResponse;
import com.sagopalgo.api.kb.dto.KbAccountResponse;
import com.sagopalgo.api.kb.dto.KbBalanceItemResponse;
import com.sagopalgo.api.kb.dto.KbBalanceResponse;
import com.sagopalgo.api.kb.dto.KbBalanceSummaryResponse;
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
        List<KbHoldingResponse> items = kbClient.items(response, "Record1", "holdings", "holdingList", "stocks", "stockList")
            .stream()
            .map(this::holding)
            .toList();
        return withWeights(items);
    }

    public KbBalanceResponse settlementBalance() {
        JsonNode response = kbClient.fetchSettlementBalance();
        return balance("SETTLEMENT", response);
    }

    public KbBalanceResponse executionBalance() {
        JsonNode response = kbClient.fetchExecutionBalance();
        return balance("EXECUTION", response);
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
        BigDecimal quantity = kbClient.decimal(node, "quantity", "gnrl_q", "ordr_psbl_q", "hldgQty", "hldg_qty", "qty");
        BigDecimal averageBuyPrice = kbClient.decimal(node, "averageBuyPrice", "byng_avr_prc", "avgBuyPrice", "pchsAvgPric", "buyPrice");
        BigDecimal currentPrice = kbClient.decimal(node, "currentPrice", "now_prc", "nowPrice", "prpr", "curPrice");
        BigDecimal purchaseAmount = kbClient.decimal(node, "purchaseAmount", "byng_amt", "pchsAmt", "buyAmount");
        BigDecimal valuationAmount = kbClient.decimal(node, "valuationAmount", "val_amt", "evluAmt", "evalAmount");
        BigDecimal profitAmount = kbClient.decimal(node, "profitAmount", "pl_amt", "val_pl", "evluPflsAmt", "profitLossAmount");
        BigDecimal profitRate = kbClient.decimal(node, "profitRate", "yld", "val_yld", "evluPflsRt", "profitLossRate");

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
            kbClient.text(node, "stockCode", "is_no", "is_cd", "isuNo", "isNo", "pdno", "shtnPdno"),
            defaultText(kbClient.text(node, "stockName", "is_nm", "isuNm", "isNm", "productName", "prdtName"), "알 수 없는 종목"),
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

    private KbBalanceResponse balance(String basis, JsonNode response) {
        List<KbBalanceItemResponse> items = kbClient.items(response, "Record1")
            .stream()
            .map(this::balanceItem)
            .toList();
        return new KbBalanceResponse(balanceSummary(basis, response), items);
    }

    private KbBalanceSummaryResponse balanceSummary(String basis, JsonNode response) {
        return new KbBalanceSummaryResponse(
            basis,
            money(kbClient.decimal(response, "tfnd", "dy_tfnd")),
            money(kbClient.decimal(response, "o_amt_psbl_amt", "ndy_o_amt_psbl_amt")),
            money(kbClient.decimal(response, "ordr_psbl_csh")),
            money(kbClient.decimal(response, "nt_asts_val_amt")),
            money(kbClient.decimal(response, "scrts_nt_val_amt")),
            money(kbClient.decimal(response, "byng_amt_sum", "nt_byng_amt")),
            money(kbClient.decimal(response, "val_amt_sum")),
            money(kbClient.decimal(response, "pl_amt_sum", "val_pl_sum", "val_pl")),
            rate(kbClient.decimal(response, "yld_sum", "val_yld_sum", "val_yld")),
            money(kbClient.decimal(response, "fncng_amt_sum", "fncng_amt")),
            rate(kbClient.decimal(response, "mrtg_rt")),
            kbClient.text(response, "tl_data_cnt")
        );
    }

    private KbBalanceItemResponse balanceItem(JsonNode node) {
        return new KbBalanceItemResponse(
            kbClient.text(node, "clsf"),
            kbClient.text(node, "gds_typ"),
            kbClient.text(node, "crncy_cd"),
            kbClient.text(node, "is_cd"),
            defaultText(kbClient.text(node, "is_nm"), "알 수 없는 종목"),
            money(kbClient.decimal(node, "blnc_q", "hld_q", "blnc_q_p6", "hld_q_p6")),
            money(kbClient.decimal(node, "ordr_psbl_q", "ordr_psbl_q_p6")),
            money(kbClient.decimal(node, "nstmt_s_q", "nstmt_s_q_p6")),
            money(kbClient.decimal(node, "nstmt_b_q", "nstmt_b_q_p6")),
            money(kbClient.decimal(node, "ec_q", "ec_q_p6")),
            money(kbClient.decimal(node, "now_prc")),
            money(kbClient.decimal(node, "byng_avr_prc")),
            money(kbClient.decimal(node, "byng_amt")),
            money(kbClient.decimal(node, "val_amt")),
            money(kbClient.decimal(node, "pl_amt", "val_pl")),
            rate(kbClient.decimal(node, "yld", "val_yld")),
            rate(kbClient.decimal(node, "val_sgrvt_p2")),
            kbClient.text(node, "is_dtl_typ_cd"),
            kbClient.text(node, "fnl_ccls_excg_cd")
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
