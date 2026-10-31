package com.sagopalgo.api.order.service;

import static org.assertj.core.api.Assertions.*;
import com.sagopalgo.api.order.client.KbLimitOrderContract;
import org.junit.jupiter.api.Test;

class OrderDispatchReceiptTest {
    @Test void normalizesMissingOrInvalidSuccessNumberAndDropsRawSensitiveText() {
        assertThat(OrderDispatchReceipt.from(null).status()).isEqualTo("UNKNOWN");
        for(String number:new String[]{"0000000000","private-account","123", ""}) {
            var receipt=OrderDispatchReceipt.from(new KbLimitOrderContract.Outcome(KbLimitOrderContract.Status.ACCEPTED,number,"private data","private data","raw secret"));
            assertThat(receipt.status()).isEqualTo("UNKNOWN");
            assertThat(receipt.orderNo()).isEmpty();
            assertThat(receipt.toString()).doesNotContain("private","secret");
            assertThat(receipt.valid()).isTrue();
        }
    }
    @Test void recoveryRequiresCompleteNormalizedReturnedReceiptAndSendingState() {
        var receipt=new OrderDispatchReceipt("ACCEPTED","0040000638","200","A");
        OrderDispatchReceipt.requireReplayable("SENDING","RETURNED",receipt);
        for(String phase:new String[]{"RESERVED","DISPATCHING","LEGACY_UNVERIFIED"}) {
            assertThatThrownBy(()->OrderDispatchReceipt.requireReplayable("SENDING",phase,receipt)).isInstanceOf(RuntimeException.class);
        }
        assertThatThrownBy(()->OrderDispatchReceipt.requireReplayable("SENDING","RETURNED",new OrderDispatchReceipt("ACCEPTED","0000000000","200","A"))).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(()->OrderDispatchReceipt.requireReplayable("UNKNOWN","RETURNED",receipt)).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(()->OrderDispatchReceipt.requireReplayable("SENDING","RETURNED",null)).isInstanceOf(RuntimeException.class);
    }
}
