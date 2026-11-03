package com.sagopalgo.api.config;

import java.util.Arrays;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix="sagopalgo.market.stream")
public record MarketStreamProperties(boolean enabled, boolean rightsConfirmed,
    @DefaultValue("0") int approvedSubscriptions, @DefaultValue("") String symbols,
    @DefaultValue("15") int staleSeconds) {
    public MarketStreamProperties {
        if (staleSeconds < 5 || staleSeconds > 300 || approvedSubscriptions < 0 || approvedSubscriptions > 40)
            throw new IllegalArgumentException("실시간 시세 설정 범위를 확인하세요.");
        var list = parse(symbols);
        if (list.size() > 10 || list.stream().anyMatch(s -> !s.matches("[0-9]{6}")) || list.stream().distinct().count()!=list.size())
            throw new IllegalArgumentException("KRX 실시간 종목은 중복 없는 6자리 코드 최대 10개입니다.");
        if (enabled && (!rightsConfirmed || list.isEmpty() || approvedSubscriptions < list.size()*2))
            throw new IllegalArgumentException("실시간 권한·구독 예산과 종목을 먼저 확인하세요.");
    }
    public List<String> stockCodes() { return parse(symbols); }
    private static List<String> parse(String value) {
        return value==null || value.isBlank() ? List.of() : Arrays.stream(value.split(",",-1)).map(String::trim).toList();
    }
}
