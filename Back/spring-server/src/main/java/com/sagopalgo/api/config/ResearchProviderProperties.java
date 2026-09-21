package com.sagopalgo.api.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 종목 뉴스와 전자공시를 조회하는 외부 Provider 설정입니다.
 */
@ConfigurationProperties(prefix = "sagopalgo.research")
public class ResearchProviderProperties {

    private NaverNews naverNews = new NaverNews();
    private OpenDart openDart = new OpenDart();
    private Sync sync = new Sync();

    public NaverNews getNaverNews() {
        return naverNews;
    }

    public void setNaverNews(NaverNews naverNews) {
        this.naverNews = naverNews;
    }

    public OpenDart getOpenDart() {
        return openDart;
    }

    public void setOpenDart(OpenDart openDart) {
        this.openDart = openDart;
    }

    public Sync getSync() {
        return sync;
    }

    public void setSync(Sync sync) {
        this.sync = sync;
    }

    public static class NaverNews {
        private boolean enabled = false;
        private String baseUrl = "https://openapi.naver.com";
        private String searchPath = "/v1/search/news.json";
        private String clientId = "";
        private String clientSecret = "";
        private int display = 10;

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

        public String getSearchPath() {
            return searchPath;
        }

        public void setSearchPath(String searchPath) {
            this.searchPath = searchPath;
        }

        public String getClientId() {
            return clientId;
        }

        public void setClientId(String clientId) {
            this.clientId = clientId;
        }

        public String getClientSecret() {
            return clientSecret;
        }

        public void setClientSecret(String clientSecret) {
            this.clientSecret = clientSecret;
        }

        public int getDisplay() {
            return display;
        }

        public void setDisplay(int display) {
            this.display = display;
        }
    }

    public static class OpenDart {
        private boolean enabled = false;
        private String baseUrl = "https://opendart.fss.or.kr";
        private String disclosurePath = "/api/list.json";
        private String corpCodePath = "/api/corpCode.xml";
        private String apiKey = "";
        private int defaultLookbackDays = 30;
        private int pageCount = 20;

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

        public String getDisclosurePath() {
            return disclosurePath;
        }

        public void setDisclosurePath(String disclosurePath) {
            this.disclosurePath = disclosurePath;
        }

        public String getCorpCodePath() {
            return corpCodePath;
        }

        public void setCorpCodePath(String corpCodePath) {
            this.corpCodePath = corpCodePath;
        }

        public String getApiKey() {
            return apiKey;
        }

        public void setApiKey(String apiKey) {
            this.apiKey = apiKey;
        }

        public int getDefaultLookbackDays() {
            return defaultLookbackDays;
        }

        public void setDefaultLookbackDays(int defaultLookbackDays) {
            this.defaultLookbackDays = defaultLookbackDays;
        }

        public int getPageCount() {
            return pageCount;
        }

        public void setPageCount(int pageCount) {
            this.pageCount = pageCount;
        }
    }

    public static class Sync {
        private boolean enabled = false;
        private String cron = "0 0/30 * * * *";
        private String zone = "Asia/Seoul";

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public String getCron() {
            return cron;
        }

        public void setCron(String cron) {
            this.cron = cron;
        }

        public String getZone() {
            return zone;
        }

        public void setZone(String zone) {
            this.zone = zone;
        }
    }
}
