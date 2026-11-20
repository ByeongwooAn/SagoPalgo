# Java4Shell 운영 영향 평가와 대응 · 2026-11-20

SagoPalgo의 로컬 Spring API 컨테이너와 장중 수집 관찰 컨테이너에서 **패치 이전 Temurin `17.0.21+9`**를 확인했습니다. 두 컨테이너에서 JVM에 노출된 CPU에는 `AVX-512 VBMI`가 없어 **관찰한 로컬 환경은 Java4Shell의 하드웨어 조건을 충족하지 않습니다.** 별도 Ubuntu 운영 서버의 JVM 빌드, CPU 기능, 실제 접근 범위와 침해 여부는 미확인입니다. 운영 서버가 패치 전이면 Java 17 패치를 적용하고, 공개 인터넷에서 API에 접근할 수 있다면 즉시 사설망 또는 VPN으로 접근 범위를 제한합니다.

## 취약점과 확인 범위

Java4Shell(`CVE-2026-114938`)은 HotSpot의 Base64 디코딩 가속 코드에서 발생하는 메모리 손상 취약점입니다. 해당 코드가 활성화된 취약 JVM에서 외부 입력이 그 경로에 도달하면 프로세스 장애가 발생할 수 있고, 조건에 따라 인증 없는 원격 코드 실행으로 이어질 수 있습니다. 공개된 Temurin 경로는 `x86-64`와 `AVX-512 VBMI`를 요구합니다. OpenJDK 17 계열의 영향 범위는 `17.0.6`~`17.0.21`이며 수정 버전은 `17.0.21.1`, Temurin의 최초 수정 빌드는 `17.0.21.1+2`입니다. Oracle의 CVSS v3.1 기본 점수는 8.1입니다. [Adoptium 권고](https://adoptium.net/news/2026/11/temurin-november-2026-cspu-java4shell) · [CERT-EU 영향 범위](https://www.cert.europa.eu/publications/security-advisories/2026-021/) · [Oracle 11월 보안 공지](https://www.oracle.com/security-alerts/cspunov2026.html#AppendixJAVA) · [KISA 권고](https://boho.or.kr/kr/bbs/view.do?bbsId=B0000133&menuNo=205020&nttId=72313&pageIndex=1)

| 확인 대상 | 관찰 결과와 판정 |
| --- | --- |
| Spring 빌드·실행 | Spring Boot `3.5.14`, Java 17 대상으로 컴파일합니다. Dockerfile의 `eclipse-temurin:17-jdk-jammy`와 `eclipse-temurin:17-jre-jammy`는 가변 태그입니다. 배포마다 실제 설치된 Java 빌드를 확인해야 합니다. [Gradle 설정](../../Back/spring-server/build.gradle.kts) · [Dockerfile](../../Back/spring-server/Dockerfile) |
| 로컬 Docker | 실행 중인 Spring 컨테이너 두 개에서 `17.0.21+9`, `amd64`, 컨테이너 PID 1의 UID `0`을 확인했습니다. 두 컨테이너 모두 `/proc/cpuinfo`의 CPU 행 12개에서 `avx512vbmi`가 없었고, 각 컨테이너에서 진단용으로 실행한 새 JVM은 `UseBASE64Intrinsics=false`를 보고했습니다. 기본 Spring API `8080`은 루프백에 바인딩됐고, 로컬 Nginx `8081`은 사설 인터페이스에 바인딩되어 `allow` 한 항목과 `deny all`을 적용했습니다. Docker 네트워크를 거친 실제 클라이언트별 접근 결과는 미검증입니다. |
| 애플리케이션 입력 | 백엔드 소스에서 찾은 `java.util.Base64` 두 사용처는 서버가 만든 주문 토큰을 인코딩합니다. 요청 입력을 JDK Base64 디코더에 직접 넘기는 프로젝트 코드는 발견되지 않았습니다. 포함 라이브러리의 모든 입력 처리 흐름은 확인 범위 밖이어서 SagoPalgo HTTP API를 통한 Java4Shell 도달성은 미확인입니다. [주문 처리 규칙](../../Back/spring-server/src/main/java/com/sagopalgo/api/order/service/OrderWorkflowRules.java) · [수동 주문 대조 서비스](../../Back/spring-server/src/main/java/com/sagopalgo/api/order/service/ManualOrderReconciliationService.java) |
| 기타 구성 요소 | AI 서버는 Python 이미지입니다. Flutter Android의 Java 17 표기는 빌드 대상이며, Android 앱 실행 환경은 이번 서버 HotSpot 평가 범위 밖입니다. 로컬·CI에서 별도로 사용하는 HotSpot JDK는 인벤토리에 포함합니다. [AI Dockerfile](../../AI/ai-server/Dockerfile) · [Android 빌드 설정](../../Front/app_version/android/app/build.gradle.kts) |

## 실운영 위협과 대응 우선순위

| 우선순위 | 위협 | 대응 |
| --- | --- | --- |
| 즉시 · 공개 접근 가능 시 | 현재 개인용 API에는 서버 로그인이나 요청 단위 인증·권한검사가 없습니다. HTTP 프록시가 공개되거나 허용 범위가 넓으면 계좌·포트폴리오·설정의 열람이나 변경 요청을 받을 수 있고, 신뢰할 수 없는 경로에서는 HTTP 트래픽도 노출될 수 있습니다. Java4Shell 패치와 별개인 운영 위험입니다. | Spring `8080`, MySQL `3306`, AI `8000`의 직접 접근은 루프백으로 유지합니다. Nginx `8081`은 지정한 LAN/VPN 경로로만 열고, 호스트 방화벽과 허용 목록을 함께 적용합니다. 프록시가 실제로 보는 요청 출발지를 확인해 Docker나 상위 프록시가 주소를 변경해도 허용·차단이 의도대로 동작하는지 확인합니다. 외부 공개가 필요하면 HTTPS와 서버 인증·권한 검사를 적용한 뒤 공개합니다. [현재 배포 기준](../architecture/docker-architecture.md#4-네트워크-기준) · [Nginx 설정](../../docker/nginx/templates/default.conf.template) |
| 즉시 확인 · 패치 전이면 교체 | 운영 JVM에 필요한 CPU 기능과 취약 코드 경로가 활성화되고 외부 입력이 도달하면 Spring API 장애 또는 JVM 권한으로 코드 실행이 가능할 수 있습니다. 그러면 시세 수집·알림·주문 상태 확인이 중단되거나, 컨테이너가 받은 DB 인증정보, 증권사 API 키·토큰, 주문·잔고 데이터가 노출 또는 변조될 수 있습니다. | 모든 운영 Spring JVM의 빌드와 CPU 기능을 확인하고 수정판으로 이미지를 교체합니다. CPU 조건이 있는 패치 전 JVM에서 교체가 지연되면 Base64 가속을 임시로 끄고 접근 범위를 제한합니다. 장애·침해 징후가 있으면 아래 사고 대응을 따릅니다. [Adoptium 권고](https://adoptium.net/news/2026/11/temurin-november-2026-cspu-java4shell) |
| 실거래 허용 전 | 기본 Compose는 MySQL `root` 계정으로 연결합니다. Spring 프로세스에서 코드가 실행되면 DB 피해 범위가 커질 수 있고, 실거래 권한이 있는 키·토큰이 노출되면 허용된 권한 범위에서 비인가 주문·정정·취소로 이어질 수 있습니다. 실주문 스위치는 기본 `false`이며 운영 값과 증권사 권한은 미확인입니다. | 런타임 DB 계정을 서비스 스키마의 필요한 권한으로 제한하고 마이그레이션·관리 권한을 분리합니다. 컨테이너를 비루트로 실행하고 필요한 쓰기 경로만 허용합니다. 쓰지 않는 실주문 권한과 기능은 끄고, 계좌 조회와 주문 권한 및 출발지 제한을 증권사가 제공하는 범위에서 분리합니다. [Compose 설정](../../docker-compose.yml) · [KB 수동 주문 운영 기준](../orders/kb-manual-orders.md) |

## Ubuntu에서 확인하고 패치를 적용하는 순서

1. 배포에 사용하는 Ubuntu 프로젝트 디렉터리와 Docker 컨텍스트에서 읽기 전용 확인을 합니다. 운영 기록에는 실제 JVM 빌드, CPU 기능, 이미지 다이제스트, 접근 검증 결과를 남깁니다. 전체 컨테이너 환경변수와 렌더링한 Compose 설정에는 비밀값이 포함될 수 있습니다.

   ```sh
   docker compose ps spring-api reverse-proxy mysql ai-server
   docker compose exec -T spring-api java -version
   docker compose exec -T spring-api uname -m
   docker compose exec -T spring-api sh -c 'if grep -qw avx512vbmi /proc/cpuinfo; then echo VBMI-present; else echo VBMI-absent; fi'
   docker compose images spring-api
   ```

   `VBMI-present`는 CPU 전제 조건만 확인합니다. Spring 인스턴스가 여러 개라면 각각 확인합니다. 프록시에 대해서는 허용된 기기와 허용되지 않은 관리 가능한 기기에서 무해한 API 조회로 접근 결과를 확인합니다. Nginx의 `/health`는 자체 응답이므로 Spring 기동과 API 접근 제어는 별도의 읽기 전용 GET으로 점검합니다. [수동 테스트 가이드](manual-test-guide.md)

2. 운영 아키텍처에 맞는 Temurin Java 17의 `17.0.21.1+2` 이상 공식 빌드를 확보해 Dockerfile의 **빌드용 JDK 및 런타임 JRE**를 함께 갱신합니다. 2026-11-20 Docker Hub 공식 이미지의 `17.0.21.1` 태그 조회에는 결과가 없었습니다. 배포 시점의 아키텍처별 발행 여부를 확인하고 검증한 태그와 다이제스트를 기록합니다. 호스트 Java 업데이트와 컨테이너 이미지 교체는 각각 수행합니다. [Adoptium 배포 상태](https://github.com/adoptium/temurin/issues/326) · [공식 이미지](https://hub.docker.com/_/eclipse-temurin) · [Compose 빌드 옵션](https://docs.docker.com/reference/cli/docker/compose/build/)

3. 패치 이미지가 아직 준비되지 않았고 CPU 조건에 해당하거나 운영 CPU가 미확인이라면 `spring-api` 서비스의 `JAVA_TOOL_OPTIONS`에 `-XX:-UseBASE64Intrinsics`를 기존 옵션과 함께 넣고, 점검 시간에 Spring 컨테이너를 재생성합니다. 시작 로그에서 해당 옵션이 적용됐는지 확인하고 민감값이 포함된 로그 원문은 외부에 공유하지 않습니다. 이 옵션의 완화 범위는 Java4Shell입니다. 11월 공지에는 다른 Java 보안 수정도 포함되므로 공급자 패치 적용까지 진행합니다. [Adoptium 임시 완화](https://adoptium.net/news/2026/11/temurin-november-2026-cspu-java4shell) · [KISA 권고](https://boho.or.kr/kr/bbs/view.do?bbsId=B0000133&menuNo=205020&nttId=72313&pageIndex=1)

4. 패치 적용 후보를 `docker compose build --pull spring-api`로 빌드하고, 교체 전에 `docker compose run --rm --no-deps --entrypoint java spring-api -version`으로 실행 이미지의 빌드를 확인합니다. 점검 시간에 `docker compose up -d --no-deps --force-recreate spring-api`로 교체한 뒤 실행 컨테이너에서 1단계의 조회를 반복합니다. 허용된 앱의 정상 읽기, 허용되지 않은 기기의 차단, MySQL 연결, 수집·주문 상태 조회를 확인합니다. 주문 제출·정정·취소 없이 점검하고, 수집 중단 구간과 미결 주문 상태는 재처리 전에 대조합니다. [Compose 일회성 실행](https://docs.docker.com/reference/cli/docker/compose/run/) · [수동 테스트 가이드](manual-test-guide.md)

## 침해가 의심될 때

반복된 JVM 비정상 종료, 예상하지 못한 자식 프로세스나 외부 통신, 증권사 토큰 이상 사용 또는 주문 불일치가 보이면 프록시 접근과 주문 전송을 먼저 제한합니다. 시간대와 이미지 정보를 포함해 Nginx·애플리케이션·Docker 이벤트·DB 및 증권사 감사 기록을 보존합니다. 노출이 의심되는 증권사 키·토큰과 DB 자격증명은 안전한 환경에서 폐기·교체하고, 주문·미체결·체결 내역을 증권사 원장과 대조한 뒤 검증한 이미지로 복구합니다.

이번 점검은 저장소 `9cb24ce`의 정적 검토와 로컬 Docker의 읽기 전용 관찰을 수행했습니다. 실제 Ubuntu 호스트의 배포 상태, 외부 노출과 로그는 미확인입니다.
