package com.sagopalgo.api.kb.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static com.sagopalgo.api.kb.service.AccountObservationFixtures.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Status;
import com.sagopalgo.api.kb.model.AccountObservationRecord;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class AccountObservationCodecTest {
    private final AccountObservationCodec codec = new AccountObservationCodec(new ObjectMapper().findAndRegisterModules());

    @Test void decimalStringsAndExplicitNullsSurviveStorageRoundTrip() {
        var snapshot = snapshot(Status.PARTIAL);
        var row = completed(UUID.randomUUID().toString(),"private-binding",snapshot,codec);
        var result = codec.decode(row);
        assertThat(result).isEqualTo(snapshot);
        assertThat(row.payload()).contains("\"now_prc\":null","0.123456","0.000001");
        assertThat(row.payload()).doesNotContain("private-binding");
    }

    @Test void changedPayloadIsNotReturnedEvenWhenItIsValidJson() {
        var row = completed(UUID.randomUUID().toString(),"scope",snapshot(Status.SUCCESS),codec);
        var changed = new AccountObservationRecord(row.id(),row.userId(),row.requestId(),row.accountBinding(),row.orderDate(),
            row.storageState(),row.observationId(),row.snapshotStatus(),row.payload().replace("0.123456","0.654321"),
            row.payloadSha256(),row.failureCode(),row.createdAt(),row.completedAt());
        assertThatThrownBy(() -> codec.decode(changed)).isInstanceOf(ApiException.class);
    }

    @Test void observationCannotAuthorizeTradingOrChangeRequestDay() {
        var s = snapshot(Status.SUCCESS);
        var unsafe = new KbAccountSnapshotResponse(s.contractVersion(),s.observationId(),s.provider(),s.accountAlias(),
            s.startedAt(),s.completedAt(),s.status(),false,true,s.sections());
        assertThatThrownBy(() -> codec.encode(unsafe,DATE)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> codec.encode(s,"20261101")).isInstanceOf(IllegalArgumentException.class);
    }

    @Test void bindingSupportsB2cWithoutAccountNumberAndChangesOnCredentialRotation() {
        var properties = properties(); var binding = new AccountObservationBinding(properties);
        String original = binding.current();
        assertThat(original).matches("[0-9a-f]{64}");
        properties.getKb().setAccountEnabled(false);
        assertThat(binding.current()).isEqualTo(original);
        properties.getKb().setAppKey("other-key");
        assertThat(binding.current()).isNotEqualTo(original);
        properties.getKb().setAppSecret("");
        assertThat(binding.matches(original)).isFalse();
    }
}
