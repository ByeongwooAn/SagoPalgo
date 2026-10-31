package com.sagopalgo.api.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 한국투자증권 Open API를 통한 국내 주식 현재가 조회 설정입니다.
 */
@ConfigurationProperties(prefix = "sagopalgo.market.kis")
public class KisMarketProperties {

    private boolean enabled = false;
    private String baseUrl = "https://openapi.koreainvestment.com:9443";
    private String appKey = "";
    private String appSecret = "";
    private String grantType = "client_credentials";
    private String tokenPath = "/oauth2/tokenP";
    private String pricePath = "/uapi/domestic-stock/v1/quotations/inquire-price";
    private String transactionId = "FHKST01010100";
    private String candlePath = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice";
    private String candleTransactionId = "FHKST03010100";
    private String customerType = "P";
    private String indexPath = "/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice";
    private String indexTransactionId = "FHKUP03500100";
    private String stockInfoPath = "/uapi/domestic-stock/v1/quotations/search-stock-info";
    private String stockInfoTransactionId = "CTPF1002R";

    public String getStockInfoPath() { return stockInfoPath; }
    public void setStockInfoPath(String value) { stockInfoPath = value; }
    public String getStockInfoTransactionId() { return stockInfoTransactionId; }
    public void setStockInfoTransactionId(String value) { stockInfoTransactionId = value; }

    public String getIndexPath() { return indexPath; }
    public void setIndexPath(String value) { indexPath = value; }
    public String getIndexTransactionId() { return indexTransactionId; }
    public void setIndexTransactionId(String value) { indexTransactionId = value; }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
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

    public String getPricePath() {
        return pricePath;
    }

    public void setPricePath(String pricePath) {
        this.pricePath = pricePath;
    }

    public String getTransactionId() {
        return transactionId;
    }

    public void setTransactionId(String transactionId) {
        this.transactionId = transactionId;
    }

    public String getCandlePath() {
        return candlePath;
    }

    public void setCandlePath(String candlePath) {
        this.candlePath = candlePath;
    }

    public String getCandleTransactionId() {
        return candleTransactionId;
    }

    public void setCandleTransactionId(String candleTransactionId) {
        this.candleTransactionId = candleTransactionId;
    }

    public String getCustomerType() {
        return customerType;
    }

    public void setCustomerType(String customerType) {
        this.customerType = customerType;
    }
}
