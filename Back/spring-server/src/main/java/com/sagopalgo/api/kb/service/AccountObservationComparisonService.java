package com.sagopalgo.api.kb.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.kb.dto.AccountObservationComparisonResponse;
import org.springframework.stereotype.Service;

@Service
public class AccountObservationComparisonService {
    private final AccountObservationHistoryService history;
    private final AccountObservationBinding binding;
    private final AccountObservationComparison comparison;

    public AccountObservationComparisonService(AccountObservationHistoryService history,
        AccountObservationBinding binding, AccountObservationComparison comparison) {
        this.history = history;
        this.binding = binding;
        this.comparison = comparison;
    }

    public AccountObservationComparisonResponse compare(Long user, String beforeRequestId, String afterRequestId) {
        if (user == null || user <= 0) throw new ApiException(ErrorCode.VALIDATION_ERROR, "로컬 사용자 설정이 필요합니다.");
        String before = AccountObservationInput.requestId(beforeRequestId);
        String after = AccountObservationInput.requestId(afterRequestId);
        if (before.equals(after)) throw new ApiException(ErrorCode.VALIDATION_ERROR, "서로 다른 두 관찰 요청 ID가 필요합니다.");
        String scope = binding.current();
        var left = history.detail(user,before);
        assertBinding(scope);
        var right = history.detail(user,after);
        assertBinding(scope);
        var result = comparison.compare(left,right);
        assertBinding(scope);
        return result;
    }

    private void assertBinding(String scope) {
        if (!binding.matches(scope)) {
            throw new ApiException(ErrorCode.DUPLICATE_RESOURCE, "계좌 연결이 변경되었습니다. 현재 연결의 이력을 다시 조회하세요.");
        }
    }
}
