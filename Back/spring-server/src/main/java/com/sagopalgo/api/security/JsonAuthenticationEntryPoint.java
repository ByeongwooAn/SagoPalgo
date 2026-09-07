package com.sagopalgo.api.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.common.response.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.http.MediaType;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.stereotype.Component;

/**
 * 인증되지 않은 사용자가 보호된 API에 접근했을 때 JSON 오류 응답을 내려주는 진입점입니다.
 *
 * <p>Spring Security의 기본 응답은 빈 401 또는 HTML 로그인 페이지일 수 있으므로, 앱에서 처리하기
 * 쉬운 ApiResponse 실패 구조로 명시적으로 변환합니다.</p>
 */
@Component
public class JsonAuthenticationEntryPoint implements AuthenticationEntryPoint {

    private final ObjectMapper objectMapper;

    /**
     * ApiResponse 객체를 JSON 문자열로 바꾸기 위한 ObjectMapper를 주입받습니다.
     *
     * @param objectMapper Spring Boot가 설정한 Jackson ObjectMapper입니다.
     */
    public JsonAuthenticationEntryPoint(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    /**
     * 인증 실패 응답을 공통 JSON 포맷으로 작성합니다.
     *
     * @param request 인증 실패가 발생한 요청입니다.
     * @param response JSON 오류를 작성할 응답입니다.
     * @param authException Spring Security가 전달한 인증 예외입니다.
     * @throws IOException 응답 본문 작성 중 오류가 발생할 때 던집니다.
     */
    @Override
    public void commence(
        HttpServletRequest request,
        HttpServletResponse response,
        AuthenticationException authException
    ) throws IOException {
        ErrorCode errorCode = ErrorCode.AUTH_INVALID_TOKEN;
        response.setStatus(errorCode.getHttpStatus().value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding("UTF-8");
        objectMapper.writeValue(
            response.getWriter(),
            ApiResponse.failure(errorCode.getCode(), errorCode.getDefaultMessage())
        );
    }
}
