package com.sagopalgo.api.order.service;

import static org.assertj.core.api.Assertions.*;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class OrderReservationBudgetTest {
    @Test void reusesOnlySelectedReservationAndRequiresOnlyPositiveDifference() {
        var b=OrderReservationBudget.calculate("BUY","AMEND",n("75000"),n("76000"),n("2"),n("5"));
        assertThat(b.reusedCash()).isEqualByComparingTo("150000");assertThat(b.additionalCash()).isEqualByComparingTo("2000");
        assertThat(b.scope()).isEqualTo("PARTIAL");assertThat(b.releasedCash()).isZero();
        var lower=OrderReservationBudget.calculate("BUY","AMEND",n("75000"),n("74000"),n("2"),n("2"));
        assertThat(lower.releasedCash()).isEqualByComparingTo("2000");assertThat(lower.scope()).isEqualTo("ALL");
        var cancel=OrderReservationBudget.calculate("BUY","CANCEL",n("75000"),n("75000"),n("1"),n("2"));
        assertThat(cancel.releasedCash()).isEqualByComparingTo("75000");assertThat(cancel.newReservedCash()).isZero();
    }
    @Test void reservedSharesNeverBecomeCash() {
        var b=OrderReservationBudget.calculate("SELL","AMEND",n("75000"),n("76000"),n("1"),n("2"));
        assertThat(b.reusedCash()).isZero();assertThat(b.additionalCash()).isZero();assertThat(b.releasedCash()).isZero();
    }
    @ParameterizedTest @ValueSource(strings={"0","-1","1.5","3"})
    void rejectsNonWholeOrExcessSelectedQuantity(String selected) {
        assertThatThrownBy(()->OrderReservationBudget.calculate("BUY","AMEND",n("75000"),n("76000"),n(selected),n("2"))).isInstanceOf(RuntimeException.class);
    }
    private BigDecimal n(String v){return new BigDecimal(v);}
}
