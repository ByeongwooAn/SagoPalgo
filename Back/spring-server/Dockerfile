# Spring Boot 애플리케이션을 빌드하는 단계입니다.
# Gradle Wrapper를 사용하므로 로컬 PC에 Gradle이 설치되어 있지 않아도 컨테이너 안에서 빌드됩니다.
FROM eclipse-temurin:17-jdk-jammy AS builder

# 애플리케이션 소스가 놓일 컨테이너 내부 작업 디렉터리입니다.
WORKDIR /workspace

# Gradle 의존성 캐시 효율을 위해 빌드 설정과 Wrapper를 먼저 복사합니다.
COPY gradlew gradlew.bat settings.gradle.kts build.gradle.kts ./
COPY gradle ./gradle

# 전체 소스를 복사하기 전에 Gradle 버전 확인을 실행해 Wrapper 배포판을 미리 준비합니다.
RUN chmod +x ./gradlew && ./gradlew --version --no-daemon

# 실제 Spring Boot 소스를 복사합니다.
COPY src ./src

# 테스트는 로컬/CI에서 별도로 돌리고, 컨테이너 이미지는 실행 가능한 jar 생성에 집중합니다.
RUN ./gradlew bootJar -x test --no-daemon

# 빌드된 jar만 담는 가벼운 런타임 단계입니다.
FROM eclipse-temurin:17-jre-jammy

# Spring Boot 서버가 컨테이너 안에서 사용할 작업 디렉터리입니다.
WORKDIR /app

# 빌드 단계에서 생성된 실행 jar를 런타임 이미지로 복사합니다.
COPY --from=builder /workspace/build/libs/*.jar app.jar

# Spring Boot가 컨테이너 내부에서 여는 포트입니다.
EXPOSE 8080

# Compose가 주입한 환경 변수를 Spring Boot가 읽어 서버를 시작합니다.
ENTRYPOINT ["java", "-jar", "app.jar"]
