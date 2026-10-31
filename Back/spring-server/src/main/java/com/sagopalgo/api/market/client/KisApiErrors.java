package com.sagopalgo.api.market.client;

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

/** 응답 원문·헤더·URL·예외 원문 없이 KIS 실패 원인을 식별합니다. */
final class KisApiErrors {
    private static final ObjectMapper JSON = new ObjectMapper();

    private KisApiErrors() { }

    static ApiException requestFailure(String stage, String label, RestClientException exception) {
        String details;
        if (exception instanceof RestClientResponseException response) {
            details = "httpStatus=" + response.getStatusCode().value() + " kisCode=" + errorCode(response);
        } else {
            details = "kind=" + transportKind(exception);
        }
        return failure(label + " API 호출에 실패했습니다.", stage, details);
    }

    static ApiException responseFailure(String stage, String label, String resultCode, String messageCode) {
        String result = resultCode != null && resultCode.matches("[0-9]{1,3}") ? resultCode : "UNKNOWN";
        return failure(label + " 조회에 실패했습니다.", stage,
            "httpStatus=200 rt_cd=" + result + " kisCode=" + safeCode(messageCode));
    }

    private static ApiException failure(String message, String stage, String details) {
        return new ApiException(ErrorCode.EXTERNAL_DATA_ERROR,
            "한국투자증권 " + message + " [stage=" + stage + " " + details + "]");
    }

    private static String errorCode(RestClientResponseException response) {
        byte[] body = response.getResponseBodyAsByteArray();
        if (body.length == 0 || body.length > 8192) return "UNAVAILABLE";
        try {
            JsonNode root = JSON.readTree(body);
            if (root == null || !root.isObject()) return "UNAVAILABLE";
            String code = safeCode(root.path("msg_cd").asText());
            return "UNAVAILABLE".equals(code) ? safeCode(root.path("error_code").asText()) : code;
        } catch (IOException exception) {
            return "UNAVAILABLE";
        }
    }

    private static String safeCode(String value) {
        return value != null && value.matches("[A-Z]{3,5}[0-9]{3,6}") ? value : "UNAVAILABLE";
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
