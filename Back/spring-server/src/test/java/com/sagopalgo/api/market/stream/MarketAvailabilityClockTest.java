package com.sagopalgo.api.market.stream;

import static org.assertj.core.api.Assertions.*;
import java.time.*;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;

class MarketAvailabilityClockTest {
    @Test void microsecondCeilingNeverMovesAReceiptEarlier() {
        assertThat(MarketAvailabilityClock.ceil(Instant.parse("2026-11-06T00:00:00.123456001Z")))
            .isEqualTo(Instant.parse("2026-11-06T00:00:00.123457Z"));
    }
    @Test void stableClockAndRepeatedNanoReadProduceIncreasingLogicalMarks() {
        var nano=new AtomicLong(0);var wall=Clock.fixed(Instant.parse("2026-11-06T00:00:00Z"),ZoneOffset.UTC);
        var clock=new MarketAvailabilityClock(wall,nano::get);
        var a=clock.mark();var b=clock.mark();
        assertThat(b.at()).isAfter(a.at());assertThat(b.stable()).isTrue();assertThat(clock.domain()).hasSize(36);
    }
    @Test void wallDiscontinuityIsLatchedAndNeverRewritesTheAnchor() {
        var nano=new AtomicLong(0);var wall=Clock.fixed(Instant.parse("2026-11-06T00:00:00Z"),ZoneOffset.UTC);
        var clock=new MarketAvailabilityClock(wall,nano::get);var before=clock.mark();
        nano.set(1000000000L);var after=clock.mark();
        assertThat(after.stable()).isFalse();assertThat(after.at()).isAfter(before.at());
        nano.set(0);assertThat(clock.mark().stable()).isFalse();
    }
}
