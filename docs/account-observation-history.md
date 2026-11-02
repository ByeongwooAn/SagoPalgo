# R1 계좌 관찰 저장·이력 조회

기준일: 2026-11-02 · 상태: 백엔드 구현·전용 MySQL 검증. 운영 DB 적용·백엔드 배포·실계좌 대조·앱 화면·자동 수집은 후속입니다.

[읽기 스냅샷 계약](account-snapshot-contract.md)을 변경하지 않고 **명시적인 새 저장 요청**으로 관찰을 실행합니다. 저장되는 결과는 서버가 만든 `KB_ACCOUNT_OBSERVATION_V1`이며, 클라이언트가 보낸 잔고/수량/스냅샷을 저장하는 API는 아닙니다. [R1 로드맵](realtime-trading-roadmap.md#r1-계좌-자동-동기화와-원장-기반)의 관찰 이력 단계이며 거래 원장은 아닙니다.

## 1. API

| 메서드·경로 | 역할 | 외부 KB 조회 |
|---|---|---|
| POST `/api/v1/kb/accounts/primary/observations` | 새 관찰을 실행하고 결과 저장. 같은 요청 ID는 기존 상태 반환 | DB 예약에 처음 성공한 요청만 실행 |
| GET `/api/v1/kb/accounts/primary/observations?limit=20&beforeId=...` | 현재 로컬 사용자·계좌 연결의 최근 이력 요약 | 없음 |
| GET `/api/v1/kb/accounts/primary/observations/{requestId}` | 현재 연결의 저장 상태와 완료된 관찰 상세 | 없음 |

세 API의 정상 응답은 공통 `ApiResponse`와 `Cache-Control: no-store`를 사용합니다. 기존 GET `/snapshot`은 계속 **조회만 수행하고 DB에 저장하지 않습니다**. 새 API에도 스케줄러·자동 폴링은 없습니다.

### 저장 요청

```json
{
  "requestId": "7a982bdf-79a0-4ef0-b4ea-f9e7410c3d0e",
  "orderDate": "20261102"
}
```

두 필드는 필수입니다. UUID는 표준 형식으로 검사하고 소문자로 정규화합니다. 날짜는 실제 존재하는 `YYYYMMDD`로 검증합니다. 잘못된 입력은 DB 예약·KB 조회 전에 400입니다. 저장 API의 날짜를 필수로 두어 자정 이후 같은 요청을 복구할 때 기본 날짜가 바뀌지 않도록 했습니다.

클라이언트는 처음 요청 전에 UUID·날짜를 보관하고 응답 유실 시 **같은 ID로 GET 상세**를 확인합니다. 같은 ID로 POST를 다시 보내도 외부 관찰을 재실행하지 않습니다. 다른 날짜나 다른 계좌 연결에 같은 사용자·요청 ID를 재사용하면 409입니다. 조회 필터 등 서버 설정이 바뀌어도 같은 ID는 기존 결과를 반환하므로 새 범위의 관찰에는 새 ID를 사용합니다.

### 목록과 상세

목록 `data`는 `items`와 `nextBeforeId`입니다. `limit`는 1~100, `beforeId`는 양수입니다. 내부 순번 내림차순 keyset 방식이므로 페이지 사이에 새 관찰이 추가돼도 이전 항목을 중복 반환하지 않습니다. `nextBeforeId`가 없으면 다음 페이지가 없습니다. 커서는 인증/승인 토큰이 아니며 서버의 사용자·연결 필터를 우회하지 않습니다.

목록은 요약만 조회해 payload 전체를 읽지 않습니다. 각 항목에는 `requestId`, `orderDate`, `storageState`, `observationId`, `snapshotStatus`, UTC `createdAt/completedAt`, `failureCode`, `readOnly=true`가 있습니다. 상세는 같은 메타데이터와 완료된 `observation`을 제공합니다. 메타데이터의 null은 공통 JSON 설정에 따라 생략될 수 있습니다.

다른 사용자·연결의 상세는 404이고 목록은 해당 범위의 항목만 반환합니다. 이력 GET은 KB 토큰 발급·계좌 조회·주문 호출을 수행하지 않습니다. 인증 설정이 없으면 현재 연결 범위를 식별할 수 없어 400이며 전체 계좌 기록으로 fallback하지 않습니다.

## 2. 저장 상태와 재시작/응답 유실

| `storageState` | 의미 | 재요청/재시작 후 동작 |
|---|---|---|
| `PENDING` | 저장 요청 예약은 커밋됐지만 종료 결과가 없음 | 같은 ID는 대기 상태만 반환. 실제 실행 중인지 프로세스 중단인지 추정하지 않고 재조회·자동 재실행하지 않음 |
| `COMPLETED` | 서버 생성 관찰을 JSON·메타데이터로 불변 저장 | 같은 ID는 저장 결과 반환. KB 재조회 없음 |
| `FAILED` | 관찰 처리 예외 또는 연결 변경으로 결과를 저장할 수 없음 | 고정 `OBSERVATION_FAILED`/`CONTEXT_CHANGED`와 메타데이터만 반환. 같은 ID 자동 재실행 없음 |

`storageState`와 `snapshotStatus`는 다릅니다. 예를 들어 외부 구간 일부가 실패한 관찰은 `storageState=COMPLETED`, `snapshotStatus=PARTIAL`로 저장됩니다. 정상 계약의 전체 조회 실패/설정 OFF 결과도 관찰 상태 `FAILED`/`DISABLED`를 보존해 저장할 수 있습니다. 저장 완료는 실제 조회 성공·계좌 일치·거래 가능을 뜻하지 않습니다.

실행 순서는 다음과 같습니다.

1. 로컬 사용자·요청 ID·날짜·현재 연결 식별값을 검증합니다.
2. `(user_id,request_id)`를 UNIQUE로 예약하고 **독립 트랜잭션을 커밋**합니다. 저장소 오류/023 미적용이면 KB 조회를 시작하지 않습니다.
3. 중복 INSERT는 해당 트랜잭션을 롤백하고 새 트랜잭션으로 기존 기록을 읽습니다. 외부 호출자의 오래된 REPEATABLE READ 스냅샷으로 중복 기록을 놓치지 않습니다.
4. 예약에 성공한 요청만 DB 잠금·트랜잭션 없이 스냅샷 서비스를 호출합니다.
5. 연결 변경 여부와 서버 관찰 계약을 확인한 뒤 별도 트랜잭션으로 `PENDING → COMPLETED/FAILED`를 확정합니다.
6. 결과 저장 중 오류가 발생하면 그 쓰기는 롤백되고 예약은 남습니다. 같은 ID가 다시 KB 조회를 실행하지 않습니다.

결과 저장 실패는 503 `OBSERVATION_STORAGE_UNAVAILABLE`이며 원문 SQL·payload·외부 예외를 응답에 복사하지 않습니다. 중단된 `PENDING`을 완료/실패로 강제 전환하는 API는 없습니다. 새로운 관찰이 필요하면 사용자가 새 ID로 명시적으로 요청합니다. 이것은 이전 요청의 복구/완료가 아니라 별도 관찰입니다.

## 3. 계좌 연결 구분과 정밀도

- 내부 연결 지문은 도메인을 분리한 HMAC-SHA256으로 endpoint·토큰 경로·App Key·선택적 계좌번호/상품코드를 구분합니다. 입력은 길이 구분해 연결하고 App Secret을 HMAC 키로 사용합니다. 지문·키·계좌번호는 API 응답에 포함하지 않습니다.
- 계좌번호가 없는 B2C 연결도 지원합니다. 이 값은 **검증된 증권사 계좌 ID가 아니라 연결 설정의 namespace**입니다. endpoint·키/Secret·계좌 설정이 바뀌면 기존 이력을 새 연결에 자동 합치지 않습니다. 키 교체 후 동일 실계좌 이력의 승계는 후속 과제이며 이전 데이터는 DB에 남습니다.
- 수집 도중 연결이 바뀌거나 기존 스냅샷이 `CONTEXT_CHANGED`를 보고하면 관찰 본문은 저장하지 않습니다. 목록/상세를 읽는 도중 연결이 바뀌어도 이전 범위의 본문을 반환하지 않습니다.
- 금액·수량·6자리 P6 값은 기존 계약의 십진 문자열 그대로, 숫자 누락은 명시적 null 그대로 JSON에 보존합니다. 요약 금액을 계산하거나 평가/원장에 자동 반영하지 않습니다.
- payload는 LONGTEXT + `JSON_VALID` 제약으로 원문 직렬화를 유지하고 SHA-256을 함께 저장합니다. MySQL의 JSON 재정렬/재직렬화에 의존하지 않습니다. 상세 조회에서 체크섬·버전·관찰 ID·상태·조회 날짜와 읽기 전용 계약을 검증하며 불일치는 503으로 차단합니다.
- 저장 본문은 여전히 `atomic=false`, `usableForTrading=false`입니다. 공급자 `providerProcessTime`의 시간대도 추정하지 않습니다.

사용자/요청 ID 및 사용자/관찰 ID의 두 UNIQUE 제약으로 같은 저장 요청과 같은 서버 관찰의 중복 저장을 막습니다. 상태 CHECK는 SQL의 NULL 통과 의미까지 고려해 완료 상태·실패 코드·본문·완료 시각의 일관성을 검사합니다.

## 4. DB와 배포

신규 [023 마이그레이션](../Back/database/migrations/023_account_observation_history.sql)은 `kb_account_observations`만 생성합니다. 새 설치용 [schema.sql](../Back/database/schema.sql)에도 같은 정의를 포함했습니다. 기존 보유·자본금·주문·승인·가드·거래 원장은 수정하지 않습니다.

| 컬럼/제약 | 역할 |
|---|---|
| `record_id` PK | 커서용 내부 순번 |
| `user_id` FK, `request_id` UNIQUE | 사용자별 저장 요청과 중복 방지 |
| `account_binding`, scope index | 현재 연결의 이력 조회 |
| `order_date`, `storage_state` | 요청 범위와 저장 진행 상태 |
| `observation_id` UNIQUE, `snapshot_status` | 서버 관찰 식별과 조회 결과 상태 |
| `payload`, `payload_sha256` | 허용된 관찰 본문과 무결성 |
| `failure_code`, `created_at/completed_at` | 고정 실패 사유·UTC 마이크로초 메타데이터 |

기존 설치는 [DB 백업·마이그레이션 방식](docker-architecture.md#기존-ubuntu-db의-kb-점검-이력-테이블)에 따라 백업 후 023을 적용하고 백엔드를 재배포해야 합니다. **이번 작업은 운영 DB에 적용하지 않았습니다.** 023이 없으면 새 저장/이력 경로는 저장소 오류로 실패하고 기존 `/snapshot` GET은 독립적으로 유지됩니다. Flutter 변경이 없어 이번 기능 때문에 새 EXE를 빌드할 필요는 없습니다.

관찰 이력은 금융 데이터이므로 기존 서버/DB 접근 범위와 백업 관리에 포함합니다. 이번 범위에는 이력 삭제·자동 만료·암호화 키 이전·다른 연결 이력 병합을 추가하지 않았습니다.

## 5. 격리 검증과 재현

전용 [테스트 Compose](../Back/spring-server/compose.account-observation-test.yml)는 MySQL 8.4·루프백 33317·전용 DB `sagopalgo_account_observation_test`·tmpfs를 사용합니다. 운영 환경 파일·볼륨·증권사 키를 마운트하지 않습니다. 테스트는 DB 이름과 전용 마커를 확인한 뒤에만 관찰 테이블 fixture를 초기화하며 KB 스냅샷 서비스는 항상 mock입니다.

백엔드 디렉터리 `Back/spring-server`에서 전용 포트/프로젝트가 다른 작업에 사용되지 않는지 확인한 후 실행합니다. 아래 명령은 새로 띄운 임시 테스트 환경을 정리하는 예시이며 운영 Compose를 사용하지 않습니다.

```powershell
$previousFlag = $env:SAGOPALGO_ACCOUNT_OBSERVATION_MYSQL_TEST
try {
    docker compose -f compose.account-observation-test.yml up -d --wait
    if ($LASTEXITCODE -ne 0) { throw '격리 MySQL 시작 실패' }
    $env:SAGOPALGO_ACCOUNT_OBSERVATION_MYSQL_TEST = 'true'
    ./gradlew.bat test
    if ($LASTEXITCODE -ne 0) { throw '관찰 이력 검증 실패' }
} finally {
    $env:SAGOPALGO_ACCOUNT_OBSERVATION_MYSQL_TEST = $previousFlag
    docker compose -f compose.account-observation-test.yml down
}
```

기존 build 디렉터리가 Windows에서 잠겼다면 별도 임시 Gradle init script의 `allprojects { layout.buildDirectory.set(layout.projectDirectory.dir("build-codex-account-history")) }`와 `--init-script <파일>`을 사용합니다. 저장소 빌드 설정을 바꿀 필요는 없습니다.

검증 항목은 다음과 같습니다.

- 단위: 정상/부분 결과·null/소수점 직렬화, 기존 완료/대기 요청 재사용, 잘못된 ID/날짜/페이지, 연결 변경·외부 예외 비노출, 저장 실패 시 재관찰 차단.
- 실제 MySQL: 실제 023 적용/재적용, 불가능한 상태의 CHECK, 서버 관찰 중복 제약, 8개 동시 요청의 단일 관찰, 오래된 외부 트랜잭션의 중복 조회, 결과 저장 후 조회 실패 롤백, 계좌/사용자 격리, 새 Mapper/서비스 구성의 DB 재조회, keyset 페이지, 본문 변조 차단.
- HTTP→실제 서비스→MySQL: POST 저장과 GET 목록/상세, no-store·6자리 수량·비공개 식별값 비노출, GET에서 KB 재호출 없음.

새 서비스/Mapper 구성은 기존 메모리를 사용하지 않음을 검증하지만 실제 운영 JVM·컨테이너 종료/재시작 및 실계좌 연결을 실행한 것은 아닙니다. 전용 테스트 컨테이너는 검증 후 정리합니다. 구체적인 실행 건수는 [개발 진척도](development-progress.md)에 기록합니다.

## 6. 남은 R1 범위

운영 023 적용·배포·실계좌 대조, 앱 이력 화면, 자동 동기화, 같은 범위의 관찰 비교, 일별 자산·입출금·체결 원장은 후속입니다. 관찰에서 사라진 종목/주문을 매도/종결로 간주하지 않으며 KB 답변이 필요한 주문 완료 판정·추가 정정·예약금 재사용은 계속 보류합니다.
