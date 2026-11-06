plugins {
    // Java 애플리케이션을 컴파일하고 테스트하기 위한 기본 Gradle 플러그인입니다.
    java

    // Spring Boot 실행 파일 생성, bootRun, 의존성 기본값 관리를 제공하는 플러그인입니다.
    id("org.springframework.boot") version "3.5.14"

    // Spring 생태계 라이브러리 버전을 Spring Boot BOM 기준으로 맞춰주는 플러그인입니다.
    id("io.spring.dependency-management") version "1.1.7"
}

// 빌드 산출물의 그룹 이름입니다. 배포나 패키징 시 조직/프로젝트를 구분하는 값으로 사용됩니다.
group = "com.sagopalgo"

// 아직 정식 릴리즈 전이므로 개발 버전 번호로 둡니다.
version = "0.0.1-SNAPSHOT"

java {
    // 로컬 JDK가 더 높아도 프로젝트 소스는 Java 17 문법 수준에 맞춰 컴파일합니다.
    // Spring Boot 3 계열의 최소 기준이면서, 팀원 PC와 배포 서버에서 맞추기 쉬운 안정적인 기준입니다.
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

repositories {
    // Spring Boot, MyBatis, MySQL 드라이버를 내려받는 기본 공개 저장소입니다.
    mavenCentral()
}

dependencies {
    // REST API 컨트롤러, JSON 직렬화, 내장 Tomcat 실행을 위한 Spring MVC 스타터입니다.
    implementation("org.springframework.boot:spring-boot-starter-web")

    // DTO 요청값 검증(@NotBlank, @Email 등)을 위한 Jakarta Validation 구현체입니다.
    implementation("org.springframework.boot:spring-boot-starter-validation")

    // MyBatis Mapper 인터페이스를 Spring Bean으로 연결하고 SQL 실행을 담당합니다.
    implementation("org.mybatis.spring.boot:mybatis-spring-boot-starter:3.0.3")

    // MySQL 데이터베이스 연결에 필요한 JDBC 드라이버입니다.
    runtimeOnly("com.mysql:mysql-connector-j:9.7.0")

    // Spring Boot 테스트, MockMvc, JUnit 5 등 백엔드 테스트 기본 도구입니다.
    testImplementation("org.springframework.boot:spring-boot-starter-test")

}

tasks.withType<Test> {
    // JUnit 5 플랫폼을 사용하도록 지정합니다.
    useJUnitPlatform()
}

tasks.register<JavaExec>("inspectStreamOperationsJournal") {
    group = "verification"
    description = "Read-only integrity/session inspection of the local stream operations journal."
    classpath = sourceSets.main.get().runtimeClasspath
    mainClass.set("com.sagopalgo.api.market.stream.StreamOperationsJournalInspector")
}
