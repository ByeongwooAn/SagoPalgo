package com.sagopalgo.api.common.response;

/**
 * 실패 응답의 error 필드에 들어가는 상세 정보입니다.
 *
 * @param code 프론트엔드가 분기 처리에 사용할 안정적인 에러 코드입니다.
 * @param message 사용자 안내 또는 디버깅에 사용할 에러 메시지입니다.
 */
public record ErrorResponse(
    String code,
    String message
) {
}
