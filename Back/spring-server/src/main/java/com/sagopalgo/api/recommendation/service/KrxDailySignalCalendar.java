package com.sagopalgo.api.recommendation.service;

import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.Set;

/** The reviewed 2026 KRX calendar for the local daily prototype. */
final class KrxDailySignalCalendar {
    static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");
    static final int WINDOW = 21;
    static final LocalTime CHECK_AFTER = LocalTime.of(20, 15);

    private static final LocalDate START = LocalDate.of(2026, 1, 1);
    private static final LocalDate END = LocalDate.of(2026, 12, 31);
    private static final LocalDate CSAT = LocalDate.of(2026, 11, 19);
    // KRX annual holiday capture, 2026-11-05. See docs/project/daily-inference-integration.md.
    private static final Set<String> HOLIDAYS = Set.of(
        "01-01", "02-16", "02-17", "02-18", "03-02", "05-01", "05-05", "05-25", "06-03",
        "07-17", "08-17", "09-24", "09-25", "10-05", "10-09", "12-25", "12-31"
    );
    private static final List<LocalDate> SESSIONS = START.datesUntil(END.plusDays(1))
        .filter(date -> date.getDayOfWeek().getValue() < DayOfWeek.SATURDAY.getValue())
        .filter(date -> !HOLIDAYS.contains(date.toString().substring(5)))
        .toList();

    private KrxDailySignalCalendar() {}

    static boolean covers(LocalDate date) {
        return !date.isBefore(START) && !date.isAfter(END);
    }

    static LocalDate latestClosed(OffsetDateTime now) {
        return SESSIONS.stream().filter(date -> !now.isBefore(close(date))).reduce((a, b) -> b).orElse(null);
    }

    static List<LocalDate> window(LocalDate basisDate) {
        int index = SESSIONS.indexOf(basisDate);
        return index >= WINDOW - 1 ? SESSIONS.subList(index - WINDOW + 1, index + 1) : List.of();
    }

    static OffsetDateTime nextClose(LocalDate basisDate) {
        return SESSIONS.stream().filter(date -> date.isAfter(basisDate)).findFirst()
            .map(KrxDailySignalCalendar::close).orElse(null);
    }

    private static OffsetDateTime close(LocalDate date) {
        LocalTime time = date.equals(CSAT) ? LocalTime.of(16, 30) : LocalTime.of(15, 30);
        return date.atTime(time).atZone(SEOUL).toOffsetDateTime();
    }
}
