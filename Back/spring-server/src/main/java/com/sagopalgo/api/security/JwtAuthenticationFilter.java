package com.sagopalgo.api.security;

import com.sagopalgo.api.token.service.JwtTokenProvider;
import io.jsonwebtoken.JwtException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 모든 HTTP 요청에서 Authorization Bearer 토큰을 읽어 인증 상태를 만드는 필터입니다.
 *
 * <p>토큰이 없으면 아무 인증도 만들지 않고 다음 필터로 넘깁니다. 토큰이 있지만 유효하지 않으면
 * SecurityContext를 비워서 보호된 API가 인증 실패 응답을 내리도록 합니다.</p>
 */
@Component
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private static final String AUTHORIZATION_HEADER = "Authorization";
    private static final String BEARER_PREFIX = "Bearer ";

    private final JwtTokenProvider jwtTokenProvider;

    /**
     * JWT 파싱과 검증을 담당하는 컴포넌트를 주입받습니다.
     *
     * @param jwtTokenProvider JWT 생성/검증 컴포넌트입니다.
     */
    public JwtAuthenticationFilter(JwtTokenProvider jwtTokenProvider) {
        this.jwtTokenProvider = jwtTokenProvider;
    }

    /**
     * 요청마다 한 번 실행되며, Bearer 토큰이 있으면 Spring Security 인증 객체를 구성합니다.
     *
     * @param request 현재 HTTP 요청입니다.
     * @param response 현재 HTTP 응답입니다.
     * @param filterChain 다음 필터로 요청을 넘기기 위한 체인입니다.
     * @throws ServletException 필터 처리 중 서블릿 오류가 발생할 때 던집니다.
     * @throws IOException 응답 처리 중 입출력 오류가 발생할 때 던집니다.
     */
    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain
    ) throws ServletException, IOException {
        String token = extractBearerToken(request);

        if (token != null) {
            authenticate(token);
        }

        filterChain.doFilter(request, response);
    }

    /**
     * Authorization 헤더에서 Bearer 접두사를 제거한 토큰 원문을 추출합니다.
     *
     * @param request 현재 HTTP 요청입니다.
     * @return Bearer 토큰이 있으면 토큰 문자열, 없으면 null입니다.
     */
    private String extractBearerToken(HttpServletRequest request) {
        String authorization = request.getHeader(AUTHORIZATION_HEADER);
        if (authorization == null || !authorization.startsWith(BEARER_PREFIX)) {
            return null;
        }

        return authorization.substring(BEARER_PREFIX.length());
    }

    /**
     * access token을 검증하고 SecurityContext에 인증 객체를 저장합니다.
     *
     * @param token 검증할 access token입니다.
     */
    private void authenticate(String token) {
        try {
            JwtAuthenticatedUser authenticatedUser = jwtTokenProvider.parseAccessToken(token);
            UsernamePasswordAuthenticationToken authentication = new UsernamePasswordAuthenticationToken(
                authenticatedUser,
                null,
                List.of(new SimpleGrantedAuthority("ROLE_" + authenticatedUser.role()))
            );

            SecurityContextHolder.getContext().setAuthentication(authentication);
        } catch (JwtException | IllegalArgumentException exception) {
            SecurityContextHolder.clearContext();
        }
    }
}
