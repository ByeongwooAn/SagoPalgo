package com.sagopalgo.api.recommendation.service;

import java.io.IOException;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.Arrays;
import java.util.List;
import java.util.Properties;
import java.util.Set;
import java.util.stream.Collectors;

/** Reviewed regular-session calendar for the NASDAQ daily prototype. */
final class NasdaqDailySignalCalendar {
    static final ZoneId NEW_YORK = ZoneId.of("America/New_York");
    static final LocalTime CHECK_AFTER = LocalTime.of(20, 15);
    private static final Properties CALENDAR = load();
    private static final LocalDate START = LocalDate.parse(CALENDAR.getProperty("start"));
    private static final LocalDate END = LocalDate.parse(CALENDAR.getProperty("end"));
    private static final Set<LocalDate> CLOSED = dates("closed");
    private static final Set<LocalDate> EARLY_CLOSE = dates("earlyClose");
    private static final List<LocalDate> SESSIONS = START.datesUntil(END.plusDays(1))
        .filter(date -> date.getDayOfWeek().getValue() <= 5 && !CLOSED.contains(date))
        .toList();

    private NasdaqDailySignalCalendar() {}

    static boolean covers(LocalDate date) {
        return !date.isBefore(START) && !date.isAfter(END);
    }

    static LocalDate latestClosed(OffsetDateTime now) {
        return SESSIONS.stream().filter(date -> !now.isBefore(close(date))).reduce((a, b) -> b).orElse(null);
    }

    static List<LocalDate> window(LocalDate basisDate) {
        int index = SESSIONS.indexOf(basisDate);
        int length = KrxDailySignalCalendar.WINDOW;
        return index >= length - 1 ? SESSIONS.subList(index - length + 1, index + 1) : List.of();
    }

    static OffsetDateTime nextClose(LocalDate basisDate) {
        return SESSIONS.stream().filter(date -> date.isAfter(basisDate)).findFirst()
            .map(NasdaqDailySignalCalendar::close).orElse(null);
    }

    static boolean crossesSplit(String symbol, LocalDate first, LocalDate last) {
        String raw = CALENDAR.getProperty(symbol + ".split");
        if (raw == null) return false;
        LocalDate split = LocalDate.parse(raw);
        return first.isBefore(split) && !last.isBefore(split);
    }

    private static OffsetDateTime close(LocalDate date) {
        return date.atTime(EARLY_CLOSE.contains(date) ? LocalTime.of(13, 0) : LocalTime.of(16, 0))
            .atZone(NEW_YORK).toOffsetDateTime();
    }

    private static Set<LocalDate> dates(String key) {
        return Arrays.stream(CALENDAR.getProperty(key).split(",")).map(LocalDate::parse)
            .collect(Collectors.toUnmodifiableSet());
    }

    private static Properties load() {
        try (var stream = NasdaqDailySignalCalendar.class.getResourceAsStream("/nasdaq-daily-prototype.properties")) {
            if (stream == null) throw new IllegalStateException("NASDAQ daily prototype calendar is missing");
            Properties values = new Properties();
            values.load(stream);
            return values;
        } catch (IOException exception) {
            throw new IllegalStateException("Cannot load NASDAQ daily prototype calendar", exception);
        }
    }
}
