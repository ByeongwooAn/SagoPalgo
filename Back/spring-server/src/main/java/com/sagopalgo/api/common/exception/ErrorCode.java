package com.sagopalgo.api.common.exception;

import org.springframework.http.HttpStatus;

/**
 * 사고팔고 API에서 사용할 대표 에러 코드 모음입니다.
 *
 * <p>각 에러 코드는 HTTP 상태와 기본 메시지를 함께 가지므로, 서비스 계층에서는 어떤 문제가
 * 발생했는지만 선택하고 실제 응답 변환은 전역 예외 처리기가 맡을 수 있습니다.</p>
 */
public enum ErrorCode {
    VALIDATION_ERROR(HttpStatus.BAD_REQUEST, "VALIDATION_ERROR", "요청값이 올바르지 않습니다."),
    DUPLICATE_RESOURCE(HttpStatus.CONFLICT, "DUPLICATE_RESOURCE", "이미 존재하는 데이터입니다."),
    RESOURCE_NOT_FOUND(HttpStatus.NOT_FOUND, "RESOURCE_NOT_FOUND", "대상 데이터를 찾을 수 없습니다."),
    EXTERNAL_DATA_ERROR(HttpStatus.BAD_GATEWAY, "EXTERNAL_DATA_ERROR", "외부 데이터 조회 중 오류가 발생했습니다."),
    PAPER_CAPITAL_REQUIRED(HttpStatus.CONFLICT, "PAPER_CAPITAL_REQUIRED", "모의매매를 시작하려면 투자 가능 자본금을 먼저 설정하세요."),
    ORDER_STORAGE_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE, "ORDER_STORAGE_UNAVAILABLE",
        "주문 저장소를 사용할 수 없습니다. DB 마이그레이션 016·017과 연결 상태를 확인하세요."),
    SIMULATION_STORAGE_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE, "SIMULATION_STORAGE_UNAVAILABLE",
        "모의 주문 저장소를 사용할 수 없습니다. DB 마이그레이션 018과 연결 상태를 확인하세요."),
    SIMULATION_RESULT_FAILURE(HttpStatus.SERVICE_UNAVAILABLE, "SIMULATION_RESULT_FAILURE",
        "[SIMULATION] 결과 저장 실패를 재현했습니다. 주문을 반복하지 말고 세션 기록을 새로고침하세요."),
    PROBE_STORAGE_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE, "PROBE_STORAGE_UNAVAILABLE",
        "KB 점검 기록 저장소를 사용할 수 없습니다. DB 마이그레이션 014와 연결 상태를 확인해 주세요."),
    INTERNAL_ERROR(HttpStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", "서버 내부 오류가 발생했습니다.");

    private final HttpStatus httpStatus;
    private final String code;
    private final String defaultMessage;

    /**
     * 에러 코드마다 HTTP 상태와 기본 메시지를 고정하기 위한 생성자입니다.
     *
     * @param httpStatus REST 응답에 사용할 HTTP 상태입니다.
     * @param code JSON error.code에 내려갈 문자열 코드입니다.
     * @param defaultMessage 별도 메시지가 없을 때 사용할 기본 설명입니다.
     */
    ErrorCode(HttpStatus httpStatus, String code, String defaultMessage) {
        this.httpStatus = httpStatus;
        this.code = code;
        this.defaultMessage = defaultMessage;
    }

    public HttpStatus getHttpStatus() {
        return httpStatus;
    }

    public String getCode() {
        return code;
    }

    public String getDefaultMessage() {
        return defaultMessage;
    }
}
