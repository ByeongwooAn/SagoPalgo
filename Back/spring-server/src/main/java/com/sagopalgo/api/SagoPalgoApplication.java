package com.sagopalgo.api;

import com.sagopalgo.api.config.JwtProperties;
import com.sagopalgo.api.config.OAuthProperties;
import com.sagopalgo.api.config.DotEnvLoader;
import java.nio.file.Path;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

/**
 * 사고팔고 Spring Boot API 서버의 진입점입니다.
 *
 * <p>이 클래스가 실행되면 Spring Boot가 컴포넌트 스캔을 시작하고, 컨트롤러/서비스/매퍼 같은
 * 애플리케이션 Bean을 등록한 뒤 내장 Tomcat으로 REST API 서버를 띄웁니다.</p>
 */
@SpringBootApplication
@EnableConfigurationProperties({JwtProperties.class, OAuthProperties.class})
public class SagoPalgoApplication {

    /**
     * 로컬 개발과 배포 환경 모두에서 가장 먼저 호출되는 main 메서드입니다.
     *
     * @param args 실행 시 전달되는 JVM/애플리케이션 인자입니다.
     */
    public static void main(String[] args) {
        DotEnvLoader.load(Path.of(".env"));
        SpringApplication.run(SagoPalgoApplication.class, args);
    }
}
