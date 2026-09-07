package com.sagopalgo.api.common.exception;

/**
 * 서비스 계층에서 의도적으로 API 실패 응답을 발생시킬 때 사용하는 예외입니다.
 *
 * <p>예를 들어 중복 이메일, 로그인 실패, 존재하지 않는 데이터처럼 비즈니스 규칙상 거절해야 하는
 * 상황을 RuntimeException 대신 의미 있는 ErrorCode와 함께 표현합니다.</p>
 */
public class ApiException extends RuntimeException {

    private final ErrorCode errorCode;

    /**
     * ErrorCode의 기본 메시지를 그대로 사용하는 생성자입니다.
     *
     * @param errorCode 응답으로 변환할 에러 코드입니다.
     */
    public ApiException(ErrorCode errorCode) {
        super(errorCode.getDefaultMessage());
        this.errorCode = errorCode;
    }

    /**
     * 상황별로 더 구체적인 메시지를 내려주고 싶을 때 사용하는 생성자입니다.
     *
     * @param errorCode 응답으로 변환할 에러 코드입니다.
     * @param message 기본 메시지 대신 사용할 상세 메시지입니다.
     */
    public ApiException(ErrorCode errorCode, String message) {
        super(message);
        this.errorCode = errorCode;
    }

    public ErrorCode getErrorCode() {
        return errorCode;
    }
}
