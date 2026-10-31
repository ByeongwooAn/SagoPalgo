# KB 수동 주문: 구현 범위와 배포 확인

2026-10-31 D(10) 제한 범위 구현입니다. 사용자가 운영 DB의 016 두 테이블·제약조건 생성을 확인했습니다. 에이전트는 실제 주문·운영 DB 변경을 실행하지 않았습니다. 후속 대조 기능은 별도 017, 전송 결과 기록/복구는 019 적용이 필요합니다.

## 지원 범위

보유 탭 상단 `KB 수동 주문`에서 KOSPI/KOSDAQ 종목코드·종목명·방향·정수 지정가/수량을 입력합니다. 보유 등록은 필요하지 않습니다. 종목코드와 이름을 직접 확인해야 하며 이 주문 화면은 종목명 자동 조회를 제공하지 않습니다.

1. `안전 조건 검증 및 주문안 확인`: 서버의 실제 시세·계좌 자원·한도를 검증합니다.
2. `승인 기록 저장`: 최신 검증한 주문안을 90초 토큰으로 승인합니다. 아직 전송하지 않습니다.
3. 최종 확인 창에서 실제 계좌 주문임을 체크하고 `실제 주문 전송`을 선택합니다. 승인 ID에 저장된 주문안만 사용하며 입력을 바꿔 전송하지 않습니다.
4. 신규 제출 전 계좌·시세·한도와 읽기 전용 주문 이력 접근을 다시 확인합니다. DB 예약과 감사 기록을 독립 트랜잭션으로 커밋한 후 실제 HTTP 요청을 한 번 보냅니다.

정규장 KRX 지정가만 지원합니다. [매수·매도 공식 문서](https://openapi.kbsec.com/apidoc_b2c#O_5e895db9-9f4c-4c98-aeb1-efc9c57df6f8#G_domestic#A_b5c9ce31-f3f8-4f9c-a4cd-987ce047c39f)의 `SSAM1802/SSAM1801`을 사용합니다. 인증·서버 주소는 [KB 공식 예제](https://github.com/kbsecurities/kb-openapi/blob/main/example/python/README.md)에 따릅니다.

## 접수와 체결

| 저장 상태 | 의미 |
|---|---|
| PREPARED | 정정·취소 승인 준비. 전송하지 않음 |
| SENDING | DB 예약을 커밋함. 처리 중이거나 프로세스 종료·결과 저장 실패로 남았을 수 있음 |
| ACCEPTED | 명시적 정상 응답과 숫자 10자리 KB 주문번호 수신. 체결 완료 아님 |
| REJECTED | 정상 API 응답의 명시적 업무 거절. 같은 요청을 재전송하지 않음 |
| UNKNOWN | HTTP 오류·타임아웃·불완전/모순 응답 등. 접수 여부 미확정 |

동일 승인 재호출은 저장 결과만 반환합니다. 사용자 DB 행 잠금과 미확정 전송 검사로 동시 제출을 직렬화합니다. `SENDING/UNKNOWN`이 있으면 다른 새 승인으로도 전송할 수 없습니다. 전송 후 DB 실패는 예약을 취소하지 않습니다. 자동 재전송·토큰 갱신 후 주문 재시도·자동 가드 해제는 없습니다.

앱도 응답이 끊긴 뒤에는 기록이 아직 조회되지 않더라도 새 주문을 차단하고 GET으로만 결과를 재조회합니다. `주문 기록 새로고침`은 주문을 보내지 않습니다. 서버 재시작으로 `SENDING/UNKNOWN`이 풀리지 않습니다. `UNKNOWN` 신규 주문은 아래의 명시적 전량 체결 대조를 확정한 경우에만 해당 차단이 해소됩니다. 빈 조회 결과나 날짜별 비슷한 주문을 성공·미접수 근거로 자동 사용하지 않습니다.

`KB 체결 조회`는 알려진 주문번호를 최대 10페이지 조회합니다. 전체 조회, 단일 행, 종목·방향·단가·수량이 모두 맞을 때만 `OPEN/PARTIAL/FILLED`로 표시합니다. 미일치·빈 결과·중복 행·불완전 페이지는 `UNKNOWN`입니다. 조회 결과는 별도 이력으로 저장하고 원래 접수 기록은 보존합니다. 앱 보유분·자본금·모의매매 원장은 자동 변경하지 않습니다.

## 미확정 신규 주문의 전량 체결 대조

`UNKNOWN` 신규 주문 카드의 `KB 주문번호로 전량 체결 대조`를 사용합니다. KB 앱에서 이 원주문의 주문번호와 전량 체결을 먼저 확인해야 합니다. 실주문 스위치 OFF 상태에서도 읽기 전용 조회와 감사 기록 저장은 가능합니다.

1. 숫자 10자리 KB 주문번호를 입력해 `읽기 전용 대조`를 누릅니다. 원주문에 저장된 주문일로 최대 10페이지를 조회합니다.
2. 전체 조회가 끝나고 단일 행의 주문일·번호·종목·방향·지정가·주문수량이 맞아야 합니다. 전량 체결·미체결 0·거절 사유 없음과 주문 시각도 확인합니다. 시각은 저장된 명령 생성 시각의 -2초~+300초 범위로 제한합니다. 서버/KB 시계 차이나 응답 표기 때문에 확인이 안 되면 잠금을 유지합니다.
3. 다른 앱 명령에 이미 저장한 주문번호는 연결하지 못합니다. 같은 조건의 다른 주문은 자동으로 구별할 수 없으므로 KB 앱에서 원주문인지 직접 대조해야 합니다.
4. 검토 창에서 원주문·전량 체결 확인을 체크하고 90초 안에 `대조 확정 저장`을 누릅니다. 서버는 다시 조회하고 일회용 토큰을 소비하면서 감사 기록을 저장합니다. 새 준비 요청은 이전 확인 토큰을 무효화합니다.
5. 최초 상태 `UNKNOWN`과 원래 제출 가드는 보존하고 별도 `reconciliation`을 표시합니다. 확정된 이 주문은 신규 제출 차단 집계에서 제외합니다. 다른 `SENDING/UNKNOWN`이 있으면 차단은 계속됩니다. 이 절차는 매수·매도·정정·취소 POST를 보내지 않습니다.

전송 중이거나 프로세스 종료로 남은 `SENDING`, 정정/취소의 `UNKNOWN`, 미체결·부분체결·빈 결과는 이번 복구 범위에 포함하지 않습니다. 취소·미접수·실패를 추정해 잠금을 해제하지 않습니다. 보유분·자본금 자동 변경이나 원래 요청 재전송도 없습니다.

## 제한적 정정·취소

당일 앱에서 신규 접수한 주문 중 전량 미체결이 확인된 건에 한 차례 지원합니다. 준비 및 제출 직전에 상태를 다시 조회하고 별도 90초 일회용 토큰·계좌 지문·원주문 사용 가드를 확인합니다. 조회 직후 체결되는 거래소 경쟁 상황까지 제거할 수는 없으므로 최종 결과는 KB에서 확인해야 합니다.

- [전부 정정 SSAM1805](https://openapi.kbsec.com/apidoc_b2c#O_5e895db9-9f4c-4c98-aeb1-efc9c57df6f8#G_domestic#A_28577def-666f-4d77-b9dc-5904db58ba49): 동일 수량, 지정가 인하만 지원합니다. 기존 주문으로 예약된 계좌 자원은 신규 가용 현금/수량에서 차감되어 있을 수 있어 두 자원 검사는 제외하고 실제 시세·가격 이탈률·한도·계좌/주문 스위치를 재검증합니다. 가격 증액은 지원하지 않습니다.
- [전부 취소 SSAM1806](https://openapi.kbsec.com/apidoc_b2c#O_5e895db9-9f4c-4c98-aeb1-efc9c57df6f8#G_domestic#A_48815fb5-53fd-4b58-905b-c04431a1e882): 원주문번호·종목·전부 구분으로 제출합니다. 취소 접수는 취소 완료를 뜻하지 않으며 완료를 자동 판정하지 않습니다.
- 부분체결·일부 수량 변경·가격 증액·추가 정정/취소·외부에서 접수한 주문은 KB 앱에서 처리합니다. 거절·불명확 결과도 원주문 사용 가드를 자동 복구하지 않습니다.

## API

모든 ID는 현재 로컬 사용자 소유 범위로 확인합니다. 이력 응답에는 계좌 지문·토큰 해시·API 키·KB 원문 메시지를 포함하지 않습니다.

| 메서드와 경로 (`/api/v1/orders` 기준) | 동작 |
|---|---|
| POST `/approvals/prepare`, `/approvals/confirm` | 기존 승인 기록. 실제 전송 없음 |
| POST `/manual` | `{approvalId, acknowledged:true, confirmation:"실제 주문 전송"}` 신규 전송 |
| GET `/manual` | 최근 100건 감사 기록. KB 호출 없음 |
| GET `/manual/{id}` | 저장된 단일 결과. KB 호출 없음 |
| POST `/manual/{id}/observations` | KB 체결 수동 조회 및 저장 |
| GET `/manual/{id}/observations` | 최근 20건 저장 조회. KB 호출 없음 |
| POST `/manual/{id}/changes/prepare` | `{kind:"AMEND",price:정수}` 또는 `{kind:"CANCEL"}` 준비. KB 읽기만 수행 |
| POST `/manual/{id}/submit` | `{token,acknowledged:true,confirmation:"실제 주문 전송"}` 준비된 변경 전송 |
| POST `/manual/{id}/reconciliation/prepare` | `{orderNo:"숫자10자리"}` 미확정 신규 주문의 전량 체결 대조·90초 확인 준비 |
| POST `/manual/{id}/reconciliation/confirm` | `{token,acknowledged:true,confirmation:"전량 체결 대조 확정"}` 재조회 후 대조 확정 저장. 실제 주문 전송 없음 |

## 기존 DB 적용과 배포

실제 주문 스위치는 계속 OFF로 둡니다. PR 병합 후 Ubuntu 프로젝트 루트에서 아래를 실행합니다. 새 DB는 `schema.sql`에 포함되며 기존 볼륨은 자동 갱신되지 않습니다.

```bash
set -e
git switch develop
git pull --ff-only origin develop
backup="sagopalgo-before-016-$(date +%Y%m%d-%H%M%S).sql"
docker compose --env-file .env exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --routines --triggers "$MYSQL_DATABASE"' > "$backup"
test -s "$backup"
docker compose --env-file .env exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot "$MYSQL_DATABASE"' < Back/database/migrations/016_manual_order_commands.sql
docker compose --env-file .env exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot "$MYSQL_DATABASE" -e "SHOW CREATE TABLE manual_order_commands; SHOW CREATE TABLE manual_order_observations;"'
docker compose --env-file .env up -d --build --no-deps spring-api
```

016·017·019 저장소를 사용할 수 없으면 주문 화면은 `ORDER_STORAGE_UNAVAILABLE`(503)로 안내하고 전송을 막습니다. 준비 상태는 전송 단계/복구 감사를 포함한 여섯 주문 테이블 접근 가능 여부도 검사합니다. 공식 주문 URL은 `https://developer.kbsec.com:32484`, 토큰 경로는 `/oauth2/token`으로 제한합니다. IP/MAC 형식 충족만으로 KB 운영 승인을 받았다고 간주하지 않습니다. 계좌·사전검증·별도 실주문 스위치를 포함한 모든 설정이 충족되어야 `canSubmit=true`입니다.

016 적용을 마친 기존 DB는 아래처럼 **별도 백업 후 017**을 적용합니다. 위의 016 절차를 대체하지 않으며 실주문 스위치는 OFF로 유지합니다.

```bash
set -e
backup="sagopalgo-before-017-$(date +%Y%m%d-%H%M%S).sql"
docker compose --env-file .env exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --routines --triggers "$MYSQL_DATABASE"' > "$backup"
test -s "$backup"
docker compose --env-file .env exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot "$MYSQL_DATABASE"' < Back/database/migrations/017_manual_order_reconciliations.sql
docker compose --env-file .env exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot "$MYSQL_DATABASE" -e "SHOW CREATE TABLE manual_order_reconciliation_preparations; SHOW CREATE TABLE manual_order_reconciliations;"'
docker compose --env-file .env up -d --build --no-deps spring-api
```

새 EXE 경로는 `Front/app_version/build/windows/x64/runner/Release/SagoPalgo.exe`입니다. 현재 배포에는 DB 016·017·019·백엔드·새 EXE가 필요합니다. 시뮬레이터에는 별도 018이 필요합니다. 이번 작업은 운영 환경변수·실계좌 주문·운영 DB를 변경하지 않았습니다.

## 남은 검증

후속 백엔드 290건에는 실제 MySQL 8.4 통합 8건이 포함됩니다. 격리된 임시 DB에서 016·017 적용/재적용, 실제 MyBatis record 매핑·제약조건, 같은/다른 승인 동시 제출, 실제 가드 롤백·만료, 동시 확정의 단일 소비, KB 주문번호 재사용 실패 시 토큰 롤백을 검증했습니다. 외부 KB 응답과 화면 테스트는 모의 응답 기반입니다. 운영 DB에서의 경쟁 실행이나 실제 KB 결과 대조를 했다는 뜻은 아닙니다.

실제 소액 주문·체결·정정·취소는 사용자의 별도 승인 아래 검증해야 합니다. RETURNED가 없는 `SENDING`과 미체결/변경 주문의 미확정 대조, 미지원 변경 범위가 남아 있어 D 전체 완료나 E 자동매매 착수로 처리하지 않습니다.

## 격리 MySQL 통합 검증 재현

Docker Desktop Linux 엔진을 실행하고 프로젝트 루트에서 아래 PowerShell 명령을 사용합니다. 운영 `.env`·볼륨을 연결하지 않고 별도 프로젝트 `sagopalgo-order-tests`의 tmpfs MySQL만 만듭니다. 테스트는 고정 루프백 `127.0.0.1:33316/sagopalgo_order_test`와 전용 마커를 확인한 후에만 테스트 테이블을 초기화합니다. KB 클라이언트나 Spring 앱 서버는 생성하지 않습니다.

```powershell
docker compose -f Back/spring-server/compose.order-test.yml up -d --wait
Push-Location Back/spring-server
$env:SAGOPALGO_ORDER_MYSQL_TEST = 'true'
try {
    .\gradlew.bat test --rerun-tasks
} finally {
    Remove-Item Env:SAGOPALGO_ORDER_MYSQL_TEST
    Pop-Location
    docker compose -f Back/spring-server/compose.order-test.yml down
}
```

기본 테스트 실행에서는 MySQL 통합 테스트 묶음을 건너뜁니다. 위 플래그와 임시 DB를 준비하고 `--rerun-tasks`로 실행해야 실제 MySQL 검증을 포함합니다. 이후 [주문 시뮬레이터](order-simulation.md)의 018·가상 계좌·상태 전이 검증도 같은 격리 DB에서 실행합니다. 테스트 자격증명은 임시 DB 전용 고정값이며 운영 설정에 사용하지 않습니다.

## 후속 019: 저장 결과가 남은 SENDING 복구

[SENDING 기록/복구의 상세 기준·화면 확인·019 백업/적용](order-dispatch-recovery.md)을 따릅니다. 신규·정정·취소의 종료된 호출 결과를 별도 커밋하며, SENDING 카드의 `전송 기록 확인·복구`에서 유효한 RETURNED만 명시적 확인 후 반영합니다. 자동 재전송·가드 초기화는 없고 UNKNOWN은 차단을 유지합니다. 기존/진행 중/종료 기록 없는 SENDING을 해제하지 않습니다. 위의 전량 체결 대조는 계속 UNKNOWN 신규 주문에만 적용됩니다.

GET `/manual/{id}/dispatch`는 단계·반환 결과·복구 가능 여부를 조회하고, POST `/manual/{id}/dispatch/recover`는 `{acknowledged:true,confirmation:"저장된 전송 결과 복구"}`로 상태만 적용합니다. 두 경로 모두 KB를 호출하지 않습니다. 019가 없으면 새 백엔드는 주문 저장소 사용을 차단하므로 재배포 전에 별도 백업 후 적용합니다.

## 후속 020: SENDING 수동 진단 이력

[종료 결과 없는 SENDING 진단](sending-manual-diagnostics.md)에서 RESERVED/DISPATCHING/LEGACY_UNVERIFIED의 읽기 전용 관찰 절차와 020 배포를 확인합니다. 전송 기록 창의 `주문번호로 잠금 유지 진단`으로 진입하고, 이후 카드의 `저장된 진단 이력`에서 최근 20건을 조회합니다. 일치·빈 결과·전량 체결 관찰로도 원래 상태/가드를 해제하지 않습니다. 020 누락은 새 진단 기능에만 503을 반환하며 기존 016/017/019 준비 조건과 분리됩니다.
