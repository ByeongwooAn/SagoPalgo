# SENDING 전송 결과 기록과 수동 복구

2026-10-31, D(10)의 일부 복구 범위입니다. 종료된 호출의 결과를 별도 트랜잭션으로 저장하고, 최종 주문 상태 저장이 실패했을 때 그 결과만 다시 적용합니다. 실제 증권사에 재전송하거나 체결·미접수를 추정하는 기능이 아닙니다.

## 단계와 복구 기준

| 기록 단계 | 의미 | 수동 복구 |
|---|---|---|
| RESERVED | 주문 예약·제출 가드와 같은 트랜잭션에서 기록 | 불가. 실행자가 뒤늦게 전송을 진행할 수 있음 |
| DISPATCHING | 외부 호출 직전에 시작 기록을 독립 커밋 | 불가. 호출 진행 중·프로세스 종료·반환 기록 실패를 구분할 수 없음 |
| RETURNED | 호출 종료 후 정규화된 결과를 독립 커밋 | 주문이 SENDING이고 결과·현재 계좌 지문이 유효한 경우만 가능 |
| LEGACY_UNVERIFIED | 이전 기록에 전송 단계 증거가 없음 | 불가. 기존 SENDING을 자동 이관하거나 해제하지 않음 |

호출 순서는 `예약/RESERVED 커밋 → DISPATCHING 커밋 → 단일 외부 호출 → RETURNED 커밋 → 주문 상태 반영 커밋`입니다. 마지막 커밋이 실패해도 반환 결과는 남습니다. 전송 실행별 내부 UUID로 다른 실행자가 결과를 덮어쓰지 못하게 하고, RETURNED 결과는 불변으로 유지합니다. 시작 전 검증 실패도 종료 결과는 UNKNOWN으로만 기록합니다.

복구는 저장된 ACCEPTED/REJECTED/UNKNOWN을 그대로 적용합니다. ACCEPTED는 접수 응답이며 체결 완료를 뜻하지 않습니다. UNKNOWN은 주문번호를 만들어내지 않고 신규 전송 차단을 유지합니다. 예약 당시 제출 가드와 정정/취소 원주문 사용 가드는 초기화하지 않습니다. 신규·정정·취소의 저장 결과를 적용할 수 있지만, 정정/취소 UNKNOWN의 KB 체결 대조를 새로 지원하는 것은 아닙니다.

사용자·명령 행 잠금과 SENDING 조건 갱신으로 정상 완료·동시 복구를 직렬화합니다. 복구가 실제 상태를 변경할 때만 감사 기록을 같은 트랜잭션에 저장합니다. 감사 기록 실패는 상태 변경도 롤백하며 RETURNED는 보존됩니다. 동일 결과가 이미 반영된 요청은 추가 변경 없이 반환합니다. 경과 시간·빈 조회 결과로 잠금을 해제하지 않습니다.

## 화면에서 확인

### 먼저 시뮬레이터로 확인

`모의 → 주문 시뮬레이션 · 실패/체결 시나리오 시험`에서 새 가상 세션을 만들고 기본 종목·가정 시세·2주로 각각 시험합니다. 실제 주문 스위치는 켤 필요가 없습니다.

1. **접수 후 결과 저장 실패:** 승인 기록·별도 최종 확인 후 의도적 오류가 표시됩니다. 카드에 SENDING, RETURNED, 저장 결과 ACCEPTED, 모의 전송 1회를 확인합니다.
2. `기록으로 결과 복구` → 추가 전송 없이 저장 결과를 적용함을 체크 → 같은 이름의 확인 버튼을 누릅니다. ACCEPTED로 변경되고 신규 모의 전송 차단이 해소되어야 합니다. 전송 횟수 1회·현금·보유·가상 증권사 상태는 그대로입니다.
3. 새로고침·화면 재진입 후에도 결과와 복구 시각을 확인합니다. 결과 유실 메시지가 남아 있더라도 GET으로 일치하는 ACCEPTED/REJECTED를 확인하면 화면의 대기 표식을 해소합니다. 자동 POST는 없습니다.
4. **전송 예약 직후 중단:** 별도 새 세션에서 SENDING/RESERVED·전송 0회·차단 유지·복구 버튼 없음 확인.
5. **접수 후 반환 기록 실패:** 별도 새 세션에서 SENDING/DISPATCHING·전송 1회·가상 증권사 접수·차단 유지·복구 버튼 없음 확인.
6. **접수 전/후 응답 유실:** UNKNOWN·차단 유지 확인. 가상 증권사에 정답 데이터가 보여도 자동으로 성공 처리하지 않습니다.

시뮬레이터의 가상 증권사·체결 단계는 실계좌나 실제 KB 모의투자 서버를 호출하지 않습니다. 이전 버전의 SENDING 세션은 증거를 새로 만들지 않으므로 LEGACY_UNVERIFIED로 남습니다. 새 시나리오는 새 세션에서 시험합니다.

### 수동 주문 기록 화면

`보유 → KB 수동 주문`의 SENDING 카드에서 `전송 기록 확인·복구`를 엽니다. 단계·시작/종료 시각·저장 결과·차단 이유를 확인합니다. 복구 가능한 경우에만 체크박스와 `기록으로 결과 복구` 버튼이 나타납니다. 복구 후 주문 이력을 다시 읽습니다. 이후 카드의 `전송 기록`에서 반환 결과와 수동 복구 시각을 다시 확인할 수 있습니다. 실주문 스위치가 OFF여도 조회/복구는 가능하지만 현재 계좌 지문이 달라지면 복구할 수 없습니다.

이 화면을 시험하기 위해 운영 DB에 가짜 SENDING을 만들거나 실제 주문 장애를 유발하지 않습니다. 이번 자동 검증은 격리 DB와 모의 응답에서만 수행했습니다. 실제 KB 주문·운영 DB 적용은 수행하지 않았습니다.

## API

| 메서드/경로 | 동작 |
|---|---|
| GET `/api/v1/orders/manual/{id}/dispatch` | 사용자 소유 전송 기록 조회. KB 호출 없음 |
| POST `/api/v1/orders/manual/{id}/dispatch/recover` | `{acknowledged:true,confirmation:"저장된 전송 결과 복구"}` 결과 반영. KB 호출 없음 |
| POST `/api/v1/orders/simulations/{sessionId}/commands/{id}/recover` | 동일한 확인 본문으로 가상 결과 반영. 외부 호출 없음 |

수동 기록 응답은 `commandId,commandStatus,phase,receipt,reservedAt,startedAt,returnedAt,recoveredAt,recoverable,message`입니다. `receipt`는 `status,orderNo,resultCode,processCode`만 포함합니다. 계좌 지문·실행 UUID·토큰 해시·증권사 원문 메시지를 반환하지 않습니다. 시뮬레이터 카드에는 `dispatchPhase,receipt,startedAt,returnedAt,recoveredAt,recoverable`이 추가됩니다. 이전 JSON은 필드가 없어도 조회할 수 있으며 복구 근거를 생성하지 않습니다.

복구 API는 운영 스위치를 켜지 않고 새 승인/주문을 만들지 않습니다. 요청 응답이 끊겨도 자동 반복하지 않고 GET으로 상태를 확인합니다. 미소유 명령·확인 문구 불일치·유효한 반환 기록 없음·계좌 변경은 거절합니다.

## 019 백업·적용과 배포

016은 사용자가 운영 적용을 확인했습니다. 017·018의 운영 적용 완료는 아직 전달받지 않았습니다. [수동 주문 017](kb-manual-orders.md#기존-db-적용과-배포)과 [시뮬레이터 018](order-simulation.md#db와-배포)을 먼저 확인합니다. 019는 기존 테이블·잠금을 초기화하지 않고 `manual_order_dispatches`, `manual_order_dispatch_recoveries`만 추가합니다. 새 DB의 `schema.sql`에도 포함됩니다.

PR 병합 후 Ubuntu 프로젝트 루트에서 실행합니다. 실제 주문 스위치는 OFF로 유지합니다.

```bash
set -e
git switch develop
git pull --ff-only origin develop
backup="sagopalgo-before-019-$(date +%Y%m%d-%H%M%S).sql"
docker compose --env-file .env exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --routines --triggers "$MYSQL_DATABASE"' > "$backup"
test -s "$backup"
docker compose --env-file .env exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot "$MYSQL_DATABASE"' < Back/database/migrations/019_manual_order_dispatch_journal.sql
docker compose --env-file .env exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot "$MYSQL_DATABASE" -e "SHOW CREATE TABLE manual_order_dispatches; SHOW CREATE TABLE manual_order_dispatch_recoveries;"'
docker compose --env-file .env up -d --build --no-deps spring-api
```

019가 없으면 실주문 준비/이력은 `ORDER_STORAGE_UNAVAILABLE`(503)로 차단합니다. 실행 파일 경로는 `Front/app_version/build/windows/x64/runner/Release/SagoPalgo.exe`로 동일합니다. 실행 폴더의 새 Flutter 번들까지 함께 사용해야 합니다. 시뮬레이션 저장소는 기존 018 JSON 테이블이며 019 테이블과 연결하지 않습니다.

## 검증과 남은 범위

격리 MySQL에서 019 신규 적용/재적용, 실제 MyBatis 매핑, 예약 기록 실패의 가드/명령 롤백, 최종 상태 갱신 실패 후 반환 기록 보존과 서비스 재생성 복구, 잘못된 실행 UUID·계좌·사용자·확인 차단, 결과 불변성, 동시 복구/정상 완료, 감사 기록 실패 롤백, UNKNOWN 차단 유지 및 정정/취소 원주문 가드 보존을 검증합니다. 시뮬레이터는 9개 시나리오, 이전 JSON 호환, 복구 전후 전송/가상 자원 유지와 정정/취소 재처리 금지를 검증합니다.

실제 주문/계좌 검증, RETURNED가 없는 SENDING의 확인·운영 대응, UNKNOWN 부분체결·변경 주문 대조와 추가 정정은 남았습니다. D(10) 전체 완료나 E(11) 자동매매 완료로 계산하지 않습니다.

최종 자동 검증은 백엔드 326건(격리 MySQL 40건), Flutter 155건 통과·Dart 분석 이슈 없음·Windows Release 빌드 성공입니다.

## 후속 020: 잠금 유지 진단

RETURNED가 없는 SENDING에는 [수동 진단 화면·이력](sending-manual-diagnostics.md)을 연결했습니다. 전송 기록 창에서 주문번호로 읽기 전용 관찰을 보관하며, FIELDS_MATCH·NOT_FOUND를 포함해 어떤 진단도 상태/잠금을 변경하지 않습니다. REQUESTED를 먼저 커밋해 같은 ID의 중복 KB 조회를 막습니다. 진단 이력에는 별도 020이 필요하며 기존 019 복구 기준은 유지합니다.
