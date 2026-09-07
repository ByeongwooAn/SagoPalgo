package com.sagopalgo.api.config;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

/**
 * Spring Boot가 시작되기 전에 로컬 `.env` 파일을 JVM 시스템 프로퍼티로 적재하는 유틸리티입니다.
 *
 * <p>Spring Boot는 기본적으로 OS 환경 변수와 JVM 시스템 프로퍼티를 읽을 수 있지만, 프로젝트 루트의
 * `.env` 파일을 자동으로 읽지는 않습니다. 이 클래스는 별도 라이브러리 없이 `.env` 값을 읽어
 * `application.yml`의 `${SAGOPALGO_...}` 변수 치환에 사용할 수 있게 합니다.</p>
 */
public final class DotEnvLoader {

    /**
     * 유틸리티 클래스는 인스턴스를 만들 필요가 없으므로 private 생성자로 막아둡니다.
     */
    private DotEnvLoader() {
    }

    /**
     * 지정한 경로의 `.env` 파일을 읽어 시스템 프로퍼티에 등록합니다.
     *
     * <p>이미 OS 환경 변수나 JVM 옵션으로 같은 키가 들어온 경우에는 그 값을 우선합니다.
     * 덕분에 로컬에서는 `.env`를 쓰고, 운영 배포에서는 배포 시스템의 환경 변수를 그대로 쓸 수 있습니다.</p>
     *
     * @param envPath 읽어올 `.env` 파일 경로입니다.
     */
    public static void load(Path envPath) {
        if (!Files.exists(envPath)) {
            return;
        }

        try {
            List<String> lines = Files.readAllLines(envPath, StandardCharsets.UTF_8);
            for (String line : lines) {
                loadLine(line);
            }
        } catch (IOException exception) {
            throw new IllegalStateException(".env 파일을 읽지 못했습니다: " + envPath, exception);
        }
    }

    /**
     * `.env` 파일의 한 줄을 해석해 key=value 형태면 시스템 프로퍼티로 등록합니다.
     *
     * @param rawLine `.env` 파일에서 읽은 원본 한 줄입니다.
     */
    private static void loadLine(String rawLine) {
        String line = rawLine.trim();
        if (line.isEmpty() || line.startsWith("#")) {
            return;
        }

        int separatorIndex = line.indexOf('=');
        if (separatorIndex <= 0) {
            return;
        }

        String key = line.substring(0, separatorIndex).trim();
        String value = stripWrappingQuotes(line.substring(separatorIndex + 1).trim());
        if (System.getenv(key) == null && System.getProperty(key) == null) {
            System.setProperty(key, value);
        }
    }

    /**
     * 값이 작은따옴표나 큰따옴표로 감싸져 있으면 바깥 따옴표만 제거합니다.
     *
     * @param value `.env`의 등호 오른쪽 값입니다.
     * @return 따옴표가 제거된 설정값입니다.
     */
    private static String stripWrappingQuotes(String value) {
        if (value.length() >= 2) {
            char first = value.charAt(0);
            char last = value.charAt(value.length() - 1);
            if ((first == '"' && last == '"') || (first == '\'' && last == '\'')) {
                return value.substring(1, value.length() - 1);
            }
        }

        return value;
    }
}
