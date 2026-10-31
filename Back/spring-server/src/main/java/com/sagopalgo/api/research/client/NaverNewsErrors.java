package com.sagopalgo.api.research.client;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import java.io.IOException;
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import java.net.http.HttpTimeoutException;
import javax.net.ssl.SSLException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

/** 뉴스 수집 상태와 서버 로그에 인증값·응답/예외 원문을 노출하지 않는 진단입니다. */
final class NaverNewsErrors {
    private static final ObjectMapper JSON = new ObjectMapper();

    private NaverNewsErrors() { }

    static ApiException requestFailure(RestClientException exception) {
        String details;
        String hint;
        if (exception instanceof RestClientResponseException response) {
            int status = response.getStatusCode().value();
            details = "httpStatus=" + status + " naverCode=" + errorCode(response);
            hint = switch (status) {
                case 401 -> "NAVER API HUB Application의 Client ID/Secret과 검색 API 권한을 확인하세요.";
                case 403 -> "NAVER API HUB의 검색 API 사용 권한과 HTTPS·요청 설정을 확인하세요.";
                case 429 -> "네이버 검색 API 호출 한도를 확인하고 잠시 후 다시 시도하세요.";
                case 400, 404, 405 -> "네이버 검색 API 주소·검색어·요청 설정을 확인하세요.";
                default -> "외부 서비스 상태를 확인하고 잠시 후 다시 시도하세요.";
            };
        } else {
            details = "kind=" + transportKind(exception);
            hint = "서버의 외부 통신·DNS·인증서와 네이버 연결 상태를 확인하세요.";
        }
        return new ApiException(ErrorCode.EXTERNAL_DATA_ERROR,
            "네이버 뉴스 검색 API 호출에 실패했습니다. [stage=NEWS_SEARCH " + details + "] " + hint);
    }

    private static String errorCode(RestClientResponseException response) {
        byte[] body = response.getResponseBodyAsByteArray();
        if (body.length == 0 || body.length > 8192) return "UNAVAILABLE";
        try {
            JsonNode root = JSON.readTree(body);
            String code = root == null || !root.isObject() ? "" : root.path("errorCode").asText();
            if (code.isBlank() && root != null && root.path("error").isObject()) {
                code = root.path("error").path("errorCode").asText();
            }
            return code.matches("(?:[0-9]{3}|SE[0-9]{2})") ? code : "UNAVAILABLE";
        } catch (IOException exception) {
            return "UNAVAILABLE";
        }
    }

    private static String transportKind(RestClientException exception) {
        Throwable cause = exception;
        for (int depth = 0; cause != null && depth < 16; depth++, cause = cause.getCause()) {
            if (cause instanceof UnknownHostException) return "DNS";
            if (cause instanceof SocketTimeoutException || cause instanceof HttpTimeoutException) return "TIMEOUT";
            if (cause instanceof SSLException) return "TLS";
            if (cause instanceof ConnectException) return "CONNECT";
        }
        return exception instanceof ResourceAccessException ? "NETWORK" : "CLIENT";
    }
}
