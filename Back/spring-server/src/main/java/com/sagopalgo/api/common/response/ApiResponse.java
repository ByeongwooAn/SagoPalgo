package com.sagopalgo.api.common.response;

/**
 * 모든 REST API가 공통으로 사용하는 응답 포맷입니다.
 *
 * <p>프론트엔드는 success 값만 먼저 확인하면 성공/실패를 빠르게 구분할 수 있고,
 * 성공 시에는 data를, 실패 시에는 error를 읽도록 단순한 계약을 유지합니다.</p>
 *
 * @param success 요청 성공 여부입니다.
 * @param data 성공 응답 본문입니다. 실패 시에는 null입니다.
 * @param error 실패 응답 본문입니다. 성공 시에는 null입니다.
 * @param message 사용자 또는 개발자가 읽을 수 있는 짧은 결과 메시지입니다.
 * @param <T> 성공 응답 data의 타입입니다.
 */
public record ApiResponse<T>(
    boolean success,
    T data,
    ErrorResponse error,
    String message
) {

    /**
     * 성공 응답을 만들 때 사용하는 정적 팩토리 메서드입니다.
     *
     * @param data 컨트롤러가 내려줄 실제 성공 데이터입니다.
     * @param message 성공 상황을 설명하는 메시지입니다.
     * @param <T> 성공 데이터 타입입니다.
     * @return 공통 성공 응답 객체입니다.
     */
    public static <T> ApiResponse<T> success(T data, String message) {
        return new ApiResponse<>(true, data, null, message);
    }

    /**
     * 실패 응답을 만들 때 사용하는 정적 팩토리 메서드입니다.
     *
     * @param errorCode 기획서/API 명세서에 정의한 에러 코드입니다.
     * @param errorMessage 실패 원인을 설명하는 메시지입니다.
     * @return 공통 실패 응답 객체입니다.
     */
    public static ApiResponse<Void> failure(String errorCode, String errorMessage) {
        return new ApiResponse<>(false, null, new ErrorResponse(errorCode, errorMessage), errorMessage);
    }
}
