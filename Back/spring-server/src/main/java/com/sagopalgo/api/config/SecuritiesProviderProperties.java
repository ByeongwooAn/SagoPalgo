package com.sagopalgo.api.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 개인용 프로그램에서 사용할 증권사 연동 설정입니다.
 */
@ConfigurationProperties(prefix = "sagopalgo.securities")
public class SecuritiesProviderProperties {

    private Provider kb = new Provider();
    private Provider toss = new Provider();

    public Provider getKb() {
        return kb;
    }

    public void setKb(Provider kb) {
        this.kb = kb;
    }

    public Provider getToss() {
        return toss;
    }

    public void setToss(Provider toss) {
        this.toss = toss;
    }

    public static class Provider {
        private boolean marketDataEnabled = false;
        private boolean accountEnabled = false;
        private boolean orderEnabled = false;
        private String baseUrl = "";
        private String grantType = "client_credentials";
        private String tokenPath = "";
        private String accountsPath = "";
        private String holdingsPath = "";
        private String settlementBalancePath = "";
        private String executionBalancePath = "";
        private String currentPricePath = "";
        private String stockInfoPath = "";
        private String candlePath = "";
        private String accountsTransactionId = "";
        private String holdingsTransactionId = "";
        private String currentPriceTransactionId = "";
        private String customerType = "P";
        private String holdingsInquiryClassification = "0";
        private String holdingsMarketTimeCode = "1";
        private String holdingsStockCode = "";
        private String balanceInquiryClassification = "1";
        private String balanceExchangeMarketPriceCode = "A";
        private String currentPriceExchangeClassification = "0";
        private String appKey = "";
        private String appSecret = "";
        private String accountNumber = "";
        private String accountProductCode = "";
        private String accountNumberField = "accountNumber";
        private String accountProductCodeField = "accountProductCode";
        private java.math.BigDecimal maxOrderAmount = new java.math.BigDecimal("1000000");
        private java.math.BigDecimal maxPriceDeviationRate = new java.math.BigDecimal("5.0");

        public boolean isMarketDataEnabled() {
            return marketDataEnabled;
        }

        public void setMarketDataEnabled(boolean marketDataEnabled) {
            this.marketDataEnabled = marketDataEnabled;
        }

        public boolean isAccountEnabled() {
            return accountEnabled;
        }

        public void setAccountEnabled(boolean accountEnabled) {
            this.accountEnabled = accountEnabled;
        }

        public boolean isOrderEnabled() {
            return orderEnabled;
        }

        public void setOrderEnabled(boolean orderEnabled) {
            this.orderEnabled = orderEnabled;
        }

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }

        public String getGrantType() {
            return grantType;
        }

        public void setGrantType(String grantType) {
            this.grantType = grantType;
        }

        public String getTokenPath() {
            return tokenPath;
        }

        public void setTokenPath(String tokenPath) {
            this.tokenPath = tokenPath;
        }

        public String getAccountsPath() {
            return accountsPath;
        }

        public void setAccountsPath(String accountsPath) {
            this.accountsPath = accountsPath;
        }

        public String getHoldingsPath() {
            return holdingsPath;
        }

        public void setHoldingsPath(String holdingsPath) {
            this.holdingsPath = holdingsPath;
        }

        public String getSettlementBalancePath() {
            return settlementBalancePath;
        }

        public void setSettlementBalancePath(String settlementBalancePath) {
            this.settlementBalancePath = settlementBalancePath;
        }

        public String getExecutionBalancePath() {
            return executionBalancePath;
        }

        public void setExecutionBalancePath(String executionBalancePath) {
            this.executionBalancePath = executionBalancePath;
        }

        public String getCurrentPricePath() {
            return currentPricePath;
        }

        public void setCurrentPricePath(String currentPricePath) {
            this.currentPricePath = currentPricePath;
        }

        public String getStockInfoPath() {
            return stockInfoPath;
        }

        public void setStockInfoPath(String stockInfoPath) {
            this.stockInfoPath = stockInfoPath;
        }

        public String getCandlePath() {
            return candlePath;
        }

        public void setCandlePath(String candlePath) {
            this.candlePath = candlePath;
        }

        public String getAccountsTransactionId() {
            return accountsTransactionId;
        }

        public void setAccountsTransactionId(String accountsTransactionId) {
            this.accountsTransactionId = accountsTransactionId;
        }

        public String getHoldingsTransactionId() {
            return holdingsTransactionId;
        }

        public void setHoldingsTransactionId(String holdingsTransactionId) {
            this.holdingsTransactionId = holdingsTransactionId;
        }

        public String getCurrentPriceTransactionId() {
            return currentPriceTransactionId;
        }

        public void setCurrentPriceTransactionId(String currentPriceTransactionId) {
            this.currentPriceTransactionId = currentPriceTransactionId;
        }

        public String getCustomerType() {
            return customerType;
        }

        public void setCustomerType(String customerType) {
            this.customerType = customerType;
        }

        public String getHoldingsInquiryClassification() {
            return holdingsInquiryClassification;
        }

        public void setHoldingsInquiryClassification(String holdingsInquiryClassification) {
            this.holdingsInquiryClassification = holdingsInquiryClassification;
        }

        public String getHoldingsMarketTimeCode() {
            return holdingsMarketTimeCode;
        }

        public void setHoldingsMarketTimeCode(String holdingsMarketTimeCode) {
            this.holdingsMarketTimeCode = holdingsMarketTimeCode;
        }

        public String getHoldingsStockCode() {
            return holdingsStockCode;
        }

        public void setHoldingsStockCode(String holdingsStockCode) {
            this.holdingsStockCode = holdingsStockCode;
        }

        public String getBalanceInquiryClassification() {
            return balanceInquiryClassification;
        }

        public void setBalanceInquiryClassification(String balanceInquiryClassification) {
            this.balanceInquiryClassification = balanceInquiryClassification;
        }

        public String getBalanceExchangeMarketPriceCode() {
            return balanceExchangeMarketPriceCode;
        }

        public void setBalanceExchangeMarketPriceCode(String balanceExchangeMarketPriceCode) {
            this.balanceExchangeMarketPriceCode = balanceExchangeMarketPriceCode;
        }

        public String getCurrentPriceExchangeClassification() {
            return currentPriceExchangeClassification;
        }

        public void setCurrentPriceExchangeClassification(String currentPriceExchangeClassification) {
            this.currentPriceExchangeClassification = currentPriceExchangeClassification;
        }

        public String getAppKey() {
            return appKey;
        }

        public void setAppKey(String appKey) {
            this.appKey = appKey;
        }

        public String getAppSecret() {
            return appSecret;
        }

        public void setAppSecret(String appSecret) {
            this.appSecret = appSecret;
        }

        public String getAccountNumber() {
            return accountNumber;
        }

        public void setAccountNumber(String accountNumber) {
            this.accountNumber = accountNumber;
        }

        public boolean hasRequiredSecrets() {
            return hasText(appKey) && hasText(appSecret);
        }

        public boolean hasAccountNumber() {
            return hasText(accountNumber);
        }

        public String getAccountProductCode() {
            return accountProductCode;
        }

        public void setAccountProductCode(String accountProductCode) {
            this.accountProductCode = accountProductCode;
        }

        public String getAccountNumberField() {
            return accountNumberField;
        }

        public void setAccountNumberField(String accountNumberField) {
            this.accountNumberField = accountNumberField;
        }

        public String getAccountProductCodeField() {
            return accountProductCodeField;
        }

        public void setAccountProductCodeField(String accountProductCodeField) {
            this.accountProductCodeField = accountProductCodeField;
        }

        public java.math.BigDecimal getMaxOrderAmount() {
            return maxOrderAmount;
        }

        public void setMaxOrderAmount(java.math.BigDecimal maxOrderAmount) {
            this.maxOrderAmount = maxOrderAmount;
        }

        public java.math.BigDecimal getMaxPriceDeviationRate() {
            return maxPriceDeviationRate;
        }

        public void setMaxPriceDeviationRate(java.math.BigDecimal maxPriceDeviationRate) {
            this.maxPriceDeviationRate = maxPriceDeviationRate;
        }

        private boolean hasText(String value) {
            return value != null && !value.isBlank();
        }
    }
}
