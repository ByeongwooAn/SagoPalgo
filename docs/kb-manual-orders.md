# KB 수동 주문: 구현 범위와 배포 확인

2026-10-31 D(10) 제한 범위 구현입니다. 실제 주문·운영 DB 적용은 실행하지 않았습니다. 자동매매는 포함하지 않습니다.

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

앱도 응답이 끊긴 뒤에는 기록이 아직 조회되지 않더라도 새 주문을 차단하고 GET으로만 결과를 재조회합니다. `주문 기록 새로고침`은 주문을 보내지 않습니다. 서버 재시작으로 `SENDING/UNKNOWN`이 풀리지 않습니다. 이 상태는 KB 앱에서 원주문을 확인한 뒤 별도 운영 복구가 필요하며 앱의 잠금 해제 기능은 아직 없습니다. 빈 조회 결과나 날짜별 비슷한 주문을 성공·미접수 근거로 자동 사용하지 않습니다.

`KB 체결 조회`는 알려진 주문번호를 최대 10페이지 조회합니다. 전체 조회, 단일 행, 종목·방향·단가·수량이 모두 맞을 때만 `OPEN/PARTIAL/FILLED`로 표시합니다. 미일치·빈 결과·중복 행·불완전 페이지는 `UNKNOWN`입니다. 조회 결과는 별도 이력으로 저장하고 원래 접수 기록은 보존합니다. 앱 보유분·자본금·모의매매 원장은 자동 변경하지 않습니다.

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

016을 사용할 수 없으면 주문 화면은 `ORDER_STORAGE_UNAVAILABLE`(503)로 안내하고 전송을 막습니다. 준비 상태는 두 테이블 접근 가능 여부도 검사합니다. 공식 주문 URL은 `https://developer.kbsec.com:32484`, 토큰 경로는 `/oauth2/token`으로 제한합니다. IP/MAC 형식 충족만으로 KB 운영 승인을 받았다고 간주하지 않습니다. 계좌·사전검증·별도 실주문 스위치를 포함한 모든 설정이 충족되어야 `canSubmit=true`입니다.

새 EXE 경로는 `Front/app_version/build/windows/x64/runner/Release/SagoPalgo.exe`입니다. 이 배포에는 DB 016·백엔드·새 EXE가 모두 필요합니다. 이번 작업은 운영 환경변수·실계좌 주문·운영 DB를 변경하지 않았습니다.

## 남은 검증

백엔드 253건·Flutter 기존 전체 129건과 추가 취소 화면 1건 자동 테스트는 모의 응답/Mapper 기반입니다. Dart 정적 분석 이슈 없음, Windows Release 빌드 성공을 확인했습니다. DB 예약의 독립 트랜잭션 커밋·실패 롤백 순서를 프록시로 검증했고, 타임아웃·중복 요청·만료·잘못된 계좌·부분체결·불완전 페이지·변경 직전 상태 변화·최종 확인 취소를 검증했습니다. 실제 MySQL 8.4 DDL/동시 갱신, KB 체결 응답의 종목/방향 표기, 운영 IP/MAC·주문 권한은 별도 검증이 필요합니다. 로컬 Docker Linux 엔진이 실행되지 않아 MySQL 실행 검증은 하지 못했습니다.

실제 소액 주문·체결·정정·취소는 사용자의 별도 승인 아래 검증해야 합니다. 미확정 전송 복구와 미지원 변경 범위가 남아 있어 D 전체 완료나 E 자동매매 착수로 처리하지 않습니다.
