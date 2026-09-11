package com.sagopalgo.api.common.exception;

import com.sagopalgo.api.common.response.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * 컨트롤러에서 발생한 예외를 공통 JSON 응답으로 바꿔주는 전역 예외 처리기입니다.
 *
 * <p>각 컨트롤러가 try/catch를 반복하지 않아도 되고, 프론트엔드는 항상 ApiResponse 형태만
 * 처리하면 되므로 앱과 서버 사이의 응답 계약이 단순해집니다.</p>
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    /**
     * 서비스 계층에서 발생시킨 비즈니스 예외를 처리합니다.
     *
     * @param exception ApiException에 담긴 ErrorCode와 메시지입니다.
     * @param request 오류가 발생한 HTTP 요청입니다.
     * @return ErrorCode에 맞는 HTTP 상태와 공통 실패 응답입니다.
     */
    @ExceptionHandler(ApiException.class)
    public ResponseEntity<ApiResponse<Void>> handleApiException(ApiException exception, HttpServletRequest request) {
        ErrorCode errorCode = exception.getErrorCode();
        logApiException(exception, errorCode, request);
        return ResponseEntity
            .status(errorCode.getHttpStatus())
            .body(ApiResponse.failure(errorCode.getCode(), exception.getMessage()));
    }

    /**
     * @Valid 검증 실패를 처리합니다.
     *
     * @param exception 어떤 필드가 왜 실패했는지 담고 있는 Spring Validation 예외입니다.
     * @param request 오류가 발생한 HTTP 요청입니다.
     * @return 400 상태와 검증 실패 메시지입니다.
     */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiResponse<Void>> handleValidationException(MethodArgumentNotValidException exception, HttpServletRequest request) {
        String message = exception.getBindingResult()
            .getFieldErrors()
            .stream()
            .map(this::formatFieldError)
            .collect(Collectors.joining(", "));

        log.debug("Validation failed for {} {}: {}", request.getMethod(), request.getRequestURI(), message);

        return ResponseEntity
            .status(ErrorCode.VALIDATION_ERROR.getHttpStatus())
            .body(ApiResponse.failure(ErrorCode.VALIDATION_ERROR.getCode(), message));
    }

    /**
     * 아직 예상하지 못한 예외를 마지막 안전망으로 처리합니다.
     *
     * @param exception 원인을 알 수 없는 서버 내부 예외입니다.
     * @param request 오류가 발생한 HTTP 요청입니다.
     * @return 500 상태와 일반화된 오류 메시지입니다.
     */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResponse<Void>> handleUnexpectedException(Exception exception, HttpServletRequest request) {
        log.error("Unexpected exception for {} {}", request.getMethod(), request.getRequestURI(), exception);
        return ResponseEntity
            .status(ErrorCode.INTERNAL_ERROR.getHttpStatus())
            .body(ApiResponse.failure(ErrorCode.INTERNAL_ERROR.getCode(), ErrorCode.INTERNAL_ERROR.getDefaultMessage()));
    }

    /**
     * 검증 실패 필드명을 메시지 앞에 붙여 프론트엔드 디버깅을 쉽게 만듭니다.
     *
     * @param fieldError 검증에 실패한 단일 필드 정보입니다.
     * @return "field: message" 형태의 문자열입니다.
     */
    private String formatFieldError(FieldError fieldError) {
        return fieldError.getField() + ": " + fieldError.getDefaultMessage();
    }

    /**
     * API 예외 중 5xx는 원인 추적을 위해 스택트레이스를 남기고, 4xx는 필요할 때만 볼 수 있게 debug로 남깁니다.
     *
     * @param exception 처리할 API 예외입니다.
     * @param errorCode 예외에 매핑된 API 에러 코드입니다.
     * @param request 오류가 발생한 HTTP 요청입니다.
     */
    private void logApiException(ApiException exception, ErrorCode errorCode, HttpServletRequest request) {
        if (errorCode.getHttpStatus().is5xxServerError()) {
            log.error(
                "API exception for {} {}: {} - {}",
                request.getMethod(),
                request.getRequestURI(),
                errorCode.getCode(),
                exception.getMessage(),
                exception
            );
            return;
        }

        log.debug(
            "API request rejected for {} {}: {} - {}",
            request.getMethod(),
            request.getRequestURI(),
            errorCode.getCode(),
            exception.getMessage()
        );
    }
}
