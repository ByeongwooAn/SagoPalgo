package com.sagopalgo.api.order.simulation;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.*;
import java.time.*;
import java.util.function.Function;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

/** 세션별 가상 계좌·명령을 직렬화합니다. 실주문 테이블·설정·네트워크 클라이언트를 참조하지 않습니다. */
@Service
public class OrderSimulationStore {
    private final OrderSimulationMapper mapper;
    private final ObjectMapper json;
    private final TransactionTemplate transaction;

    public OrderSimulationStore(OrderSimulationMapper mapper, ObjectMapper json, PlatformTransactionManager manager) {
        this.mapper = mapper;
        this.json = json;
        this.transaction = new TransactionTemplate(manager);
        this.transaction.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    public <T> T mutate(Long userId, String id, Function<OrderSimulationState, T> mutation) {
        try {
            return transaction.execute(status -> {
                var row = mapper.lock(id, userId);
                if (row == null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
                var state = decode(row.stateJson());
                T result = mutation.apply(state);
                if (mapper.update(new OrderSimulationMapper.Row(id, userId, encode(state), row.revision(), row.createdAt(), now())) != 1) {
                    throw new ApiException(ErrorCode.DUPLICATE_RESOURCE, "모의 세션 상태가 변경되었습니다. 다시 조회하세요.");
                }
                return result;
            });
        } catch (DataAccessException exception) { throw new ApiException(ErrorCode.SIMULATION_STORAGE_UNAVAILABLE); }
    }

    public OrderSimulationState decode(String value) {
        try { return json.readValue(value, OrderSimulationState.class); }
        catch (JsonProcessingException exception) { throw new ApiException(ErrorCode.INTERNAL_ERROR, "모의 주문 저장 상태를 읽을 수 없습니다."); }
    }
    public String encode(OrderSimulationState state) {
        try { return json.writeValueAsString(state); }
        catch (JsonProcessingException exception) { throw new ApiException(ErrorCode.INTERNAL_ERROR); }
    }
    public static LocalDateTime now() { return LocalDateTime.now(ZoneId.of("Asia/Seoul")); }
}
