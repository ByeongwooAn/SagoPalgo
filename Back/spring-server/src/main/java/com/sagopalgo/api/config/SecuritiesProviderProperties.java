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
        private String appKey = "";
        private String appSecret = "";
        private String accountNumber = "";

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

        private boolean hasText(String value) {
            return value != null && !value.isBlank();
        }
    }
}
