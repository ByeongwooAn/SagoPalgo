package com.sagopalgo.api.market.model;

import java.time.ZoneId;
import java.util.Locale;
import java.util.Optional;

public enum UsStockExchange {
    NASDAQ("NAS", "NAS", "512"),
    NYSE("NYS", "NYS", "513"),
    AMEX("AMX", "AMS", "529");

    public static final ZoneId ZONE = ZoneId.of("America/New_York");

    private final String kbCode;
    private final String kisCode;
    private final String kisProductCode;

    UsStockExchange(String kbCode, String kisCode, String kisProductCode) {
        this.kbCode = kbCode;
        this.kisCode = kisCode;
        this.kisProductCode = kisProductCode;
    }

    public String kbCode() { return kbCode; }
    public String kisCode() { return kisCode; }
    public String kisProductCode() { return kisProductCode; }

    public static Optional<UsStockExchange> fromMarket(String market) {
        if (market == null) return Optional.empty();
        return switch (market.trim().toUpperCase(Locale.ROOT)) {
            case "NASDAQ" -> Optional.of(NASDAQ);
            case "NYSE" -> Optional.of(NYSE);
            case "AMEX" -> Optional.of(AMEX);
            default -> Optional.empty();
        };
    }

    public static boolean isTicker(String ticker) {
        return ticker != null && ticker.matches("[A-Z][A-Z0-9]{0,14}(?:[.-][A-Z0-9]{1,4})?")
            && ticker.length() <= 16;
    }
}
