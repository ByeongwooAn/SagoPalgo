package com.sagopalgo.api.config;

import com.sagopalgo.api.security.JsonAccessDeniedHandler;
import com.sagopalgo.api.security.JsonAuthenticationEntryPoint;
import com.sagopalgo.api.security.JwtAuthenticationFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

/**
 * Spring Security의 기본 동작을 사고팔고 API 서버 방식에 맞게 조정하는 설정입니다.
 *
 * <p>Google/Naver 소셜 로그인과 refresh token 재발급 API만 공개하고, 나머지 API는 JWT access token을
 * 요구하도록 상태 없는(stateless) 서버 구조로 설정합니다.</p>
 */
@Configuration
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtAuthenticationFilter;
    private final JsonAuthenticationEntryPoint jsonAuthenticationEntryPoint;
    private final JsonAccessDeniedHandler jsonAccessDeniedHandler;

    /**
     * JWT 필터와 JSON 오류 처리기를 생성자 주입으로 받습니다.
     *
     * @param jwtAuthenticationFilter Authorization Bearer 토큰을 검증하는 필터입니다.
     * @param jsonAuthenticationEntryPoint 인증 실패를 JSON으로 내려주는 처리기입니다.
     * @param jsonAccessDeniedHandler 권한 부족을 JSON으로 내려주는 처리기입니다.
     */
    public SecurityConfig(
        JwtAuthenticationFilter jwtAuthenticationFilter,
        JsonAuthenticationEntryPoint jsonAuthenticationEntryPoint,
        JsonAccessDeniedHandler jsonAccessDeniedHandler
    ) {
        this.jwtAuthenticationFilter = jwtAuthenticationFilter;
        this.jsonAuthenticationEntryPoint = jsonAuthenticationEntryPoint;
        this.jsonAccessDeniedHandler = jsonAccessDeniedHandler;
    }

    /**
     * HTTP 보안 규칙을 정의합니다.
     *
     * @param http Spring Security가 제공하는 HTTP 보안 설정 빌더입니다.
     * @return Spring Security 필터 체인입니다.
     * @throws Exception 설정 생성 중 오류가 발생할 수 있어 Spring Security 시그니처를 따릅니다.
     */
    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .csrf(AbstractHttpConfigurer::disable)
            .cors(Customizer.withDefaults())
            .httpBasic(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .exceptionHandling(exception -> exception
                .authenticationEntryPoint(jsonAuthenticationEntryPoint)
                .accessDeniedHandler(jsonAccessDeniedHandler)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/api/v1/auth/google",
                    "/api/v1/auth/naver",
                    "/api/v1/auth/naver/authorization-url",
                    "/api/v1/auth/refresh"
                ).permitAll()
                .anyRequest().authenticated()
            )
            .addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class)
            .build();
    }

    /**
     * Spring Boot가 개발용 임시 사용자와 generated password를 자동 생성하지 않도록 명시적인 사용자 조회 서비스를 둡니다.
     *
     * <p>사고팔고는 Google/Naver 소셜 로그인으로 사용자를 확인한 뒤 자체 JWT를 발급하는 구조이므로,
     * 서버 내부에서 username/password 로그인을 처리할 사용자가 없습니다. 따라서 이 Bean은 폼 로그인이나 HTTP Basic
     * 인증에 쓰일 사용자가 없다는 사실을 명확하게 표현하고, 인증이 필요한 API는 JwtAuthenticationFilter가 담당하게 합니다.</p>
     *
     * @return username/password 인증 요청이 들어와도 항상 사용자를 찾을 수 없다고 알리는 서비스입니다.
     */
    @Bean
    public UserDetailsService userDetailsService() {
        return username -> {
            throw new UsernameNotFoundException("사고팔고는 username/password 로그인을 지원하지 않습니다.");
        };
    }
}
