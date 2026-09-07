package com.sagopalgo.api.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.common.response.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.stereotype.Component;

/**
 * 인증은 되었지만 권한이 부족한 요청을 JSON 오류 응답으로 변환하는 처리기입니다.
 *
 * <p>관리자 API 같은 권한 분기가 생겼을 때도 프론트엔드는 동일한 ApiResponse 실패 구조를
 * 받을 수 있습니다.</p>
 */
@Component
public class JsonAccessDeniedHandler implements AccessDeniedHandler {

    private final ObjectMapper objectMapper;

    /**
     * 오류 응답 객체를 JSON으로 변환하기 위한 ObjectMapper를 주입받습니다.
     *
     * @param objectMapper Spring Boot가 설정한 Jackson ObjectMapper입니다.
     */
    public JsonAccessDeniedHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    /**
     * 권한 부족 응답을 공통 JSON 포맷으로 작성합니다.
     *
     * @param request 권한 부족이 발생한 요청입니다.
     * @param response JSON 오류를 작성할 응답입니다.
     * @param accessDeniedException Spring Security가 전달한 권한 예외입니다.
     * @throws IOException 응답 본문 작성 중 오류가 발생할 때 던집니다.
     */
    @Override
    public void handle(
        HttpServletRequest request,
        HttpServletResponse response,
        AccessDeniedException accessDeniedException
    ) throws IOException {
        ErrorCode errorCode = ErrorCode.AUTH_FORBIDDEN;
        response.setStatus(errorCode.getHttpStatus().value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding("UTF-8");
        objectMapper.writeValue(
            response.getWriter(),
            ApiResponse.failure(errorCode.getCode(), errorCode.getDefaultMessage())
        );
    }
}
