package com.sagopalgo.api.config;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

/**
 * 외부 HTTP API 호출에 사용할 RestClient 설정입니다.
 *
 * <p>KIS 시세 조회, 이후 추가될 KB/Toss 연동처럼 짧은 서버 간 HTTP 호출은 Spring Framework의
 * RestClient를 공통 Bean으로 등록해 재사용합니다.</p>
 */
@Configuration
public class RestClientConfig {

    /**
     * 외부 API 호출에 사용할 기본 RestClient를 생성합니다.
     *
     * @return Spring RestClient 인스턴스입니다.
     */
    @Bean
    public RestClient restClient() {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(Duration.ofSeconds(5));
        requestFactory.setReadTimeout(Duration.ofSeconds(15));
        return RestClient.builder()
            .requestFactory(requestFactory)
            .build();
    }
}
