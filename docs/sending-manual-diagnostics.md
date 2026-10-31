# 종료 결과 없는 SENDING: 잠금 유지 진단

2026-11-01 D(10) 후속입니다. RESERVED·DISPATCHING·LEGACY_UNVERIFIED 상태에서 KB 앱으로 확인한 주문번호의 읽기 전용 관찰을 기록합니다. 기존 RETURNED 저장 결과 복구와는 별도입니다. 진단은 주문 상태·전송 단계·제출 가드·정정/취소 원주문 가드·보유분·자본금을 변경하지 않습니다.

## 화면 확인 순서

먼저 실주문 스위치 OFF 상태의 `모의 → 주문 시뮬레이션`에서 시험합니다. 실제 KB 모의투자 서버가 아닌 내부 가상 증권사입니다.

1. 새 가상 세션에서 `전송 예약 직후 중단`을 선택해 승인·최종 확인을 진행합니다. SENDING/RESERVED, 전송 0회 상태가 남습니다.
2. `가상 주문번호로 잠금 유지 진단`을 열어 `0000000001`을 입력합니다. 체크박스 확인 전에는 `조회·진단 기록`을 누를 수 없습니다.
3. 진단 후 **조회 결과 없음 · 미접수 확정 아님**을 확인합니다. SENDING·신규 전송 차단·전송 0회는 그대로여야 합니다.
4. 별도 새 세션에서 `접수 후 반환 기록 실패`를 진행합니다. SENDING/DISPATCHING, 전송 1회와 가상 증권사 주문번호를 확인합니다.
5. 같은 진단 화면에 실제 표시된 가상 주문번호를 입력합니다. 기본 신규 주문은 **주문 항목 일치 · 전송 종료 확정 아님**으로 표시됩니다. 진단 전후 전송 1회·가상 현금/보유·SENDING·차단 유지가 기준입니다.
6. 화면을 다시 열거나 세션을 재조회해 `저장된 진단 이력`의 결과·조회 시각·전송 단계가 보존되는지 확인합니다. 이력 GET은 증권사 조회나 주문 전송을 하지 않습니다.

실제 기록은 `보유 → KB 수동 주문 → SENDING 카드의 전송 기록 확인·복구 → 주문번호로 잠금 유지 진단`으로 들어갑니다. KB 앱에서 확인한 숫자 10자리 번호를 입력합니다. 진단 화면에서 체크 후 명시적으로 요청할 때만 KB 읽기 전용 조회를 합니다. 현재 계좌 지문이 승인 당시와 다르면 조회 전에 거절합니다. 실주문 스위치를 켤 필요는 없습니다. 운영에 테스트용 주문을 만들거나 실제 주문 장애를 유발하지 않습니다.

RETURNED가 있으면 새 진단 대신 기존 기록 복구를 사용합니다. 모든 준비 완료 이후의 수동 주문 카드에서는 `저장된 진단 이력`을 읽을 수 있습니다. 저장 이력은 당시 관찰이며 현재 계좌 권한·주문 상태를 보증하지 않습니다.

## 결과 의미와 제한

| 결과 | 의미 |
|---|---|
| FIELDS_MATCH | 조회 범위·단일 행·신규 주문·번호/종목/방향/가격/수량·시각·수량 합계·거절 사유 없음 확인. 원주문 연결/전송 종료/접수 확정은 아님 |
| NOT_FOUND | 전체 조회 결과에 번호 없음. 미접수/실패 확정 근거로 쓰지 않음 |
| INCOMPLETE | 전체 페이지 확인 실패. 최대 10페이지의 기존 KB 조회 제한 적용 |
| AMBIGUOUS | 중복 또는 불명확한 조회 행 |
| MISMATCH | 요청 범위 또는 주문 항목이 맞지 않음 |
| LOOKUP_FAILED | 조회 실패. 민감한 예외/KB 원문을 저장하지 않음 |
| ACCOUNT_CHANGED | 조회 도중 계좌 지문 변경. 조회 행·검증 항목은 저장 결과에서 제외 |
| CHANGE_REQUIRES_REVIEW | 정정/취소 번호의 관찰. 신규 주문과 같은 항목만으로 변경 결과를 판정하지 않음 |

시각은 명령 생성 시각 -2초~+300초 범위로만 비교합니다. 전체 페이지·단일 행을 확인한 경우에만 제한된 숫자 관찰을 보관합니다. 원문 종목명·거절 사유·응답 메시지·계좌 지문·실행 UUID·토큰 해시는 응답/진단 JSON에 넣지 않습니다. 잘못된 시각·누락 가격·수량 불일치는 참조 항목 실패로 표시합니다.

동일 조건의 다른 주문이 존재하거나, 원래 실행자가 나중에 전송을 계속할 수 있습니다. 전량 체결처럼 보이는 조회도 SENDING을 UNKNOWN/ACCEPTED로 바꾸거나 기존 UNKNOWN 전량 체결 대조에 자동 연결하지 않습니다. 경과 시간으로 잠금을 해제하지 않습니다.

## 요청 저장·중복·응답 유실

실제 진단은 다음 순서입니다.

1. 현재 사용자 소유 명령·SENDING·RETURNED 없음·현재 계좌 지문을 검사합니다.
2. 진단 ID와 번호·시작 전송 단계를 REQUESTED로 독립 커밋합니다.
3. DB 잠금 없이 KB 읽기 전용 조회를 한 차례 수행합니다. 한 조회는 최대 10페이지를 읽을 수 있습니다.
4. 현재 명령·전송 단계를 다시 읽고 결과를 COMPLETED로 별도 커밋합니다. 원래 실행자가 이 사이에 완료해도 진단이 상태를 덮어쓰지 않습니다.

같은 사용자·진단 UUID는 같은 명령/주문번호에만 사용할 수 있습니다. 같은 ID가 동시 요청되거나 다시 들어와도 이미 저장된 REQUESTED/COMPLETED를 반환하며 KB 조회를 반복하지 않습니다. 기존 REQUESTED가 남으면 조회 진행·프로세스 중단·최종 진단 저장 실패를 구분할 수 없으므로 자동 재시도하지 않습니다. 새 진단은 사용자가 명시적으로 별도 ID로 요청하는 읽기 작업입니다. 어떤 진단도 주문을 전송하지 않습니다.

화면도 응답 유실 시 POST를 반복하지 않습니다. `진단 이력 새로고침`으로 저장 결과를 읽고, 같은 ID의 COMPLETED가 확인될 때만 화면 대기 표시를 정리합니다. 이력은 실주문 최근 20건, 시뮬레이터는 명령별 최대 20건입니다. 시뮬레이터는 조회와 저장을 단일 세션 트랜잭션에서 실행하며 실제 KB 호출이 없습니다. 이전 JSON에 진단 목록이 없으면 빈 목록으로 조회합니다.

## API

| 메서드/경로 | 동작 |
|---|---|
| GET `/api/v1/orders/manual/{id}/diagnostics` | 사용자 소유 최근 20건 저장 이력. KB 호출 없음 |
| POST `/api/v1/orders/manual/{id}/diagnostics` | `{diagnosticId:"UUID",orderNo:"숫자10자리",acknowledged:true,confirmation:"잠금 유지 진단"}` |
| POST `/api/v1/orders/simulations/{sessionId}/commands/{id}/diagnostics` | 같은 확인 본문으로 가상 관찰 기록. 실제 KB 호출 없음 |

응답은 `diagnosticId,commandId,orderNo,phaseBefore,state,report,createdAt,completedAt`입니다. report는 `assessment,checks,observation,completeScan,pagesScanned,phaseAfter,commandStatusAfter,message`이며 REQUESTED는 report/완료 시각이 없습니다. 시뮬레이터 저장 상태의 각 명령에는 `diagnostics`가 추가됩니다.

020 접근 실패는 `DIAGNOSTIC_STORAGE_UNAVAILABLE`(503)로 구분하고 KB 조회 전에 차단합니다. 기존 수동 주문 저장소·준비 상태는 020을 참조하지 않으므로 진단 기능의 마이그레이션 누락이 기존 이력/전송까지 별도로 막지는 않습니다. 기존 016·017·019 저장소 점검은 계속 적용됩니다.

## 020 백업·적용과 배포

PR 병합 후 Ubuntu 프로젝트 루트에서 실행합니다. 기존 017/018/019의 운영 적용 완료는 별도로 확인해야 합니다. 실제 주문 스위치는 OFF로 유지합니다. 새 DB는 초기 schema.sql에 포함되며 기존 볼륨에는 자동 반영되지 않습니다.

```bash
set -e
git switch develop
git pull --ff-only origin develop
backup="sagopalgo-before-020-$(date +%Y%m%d-%H%M%S).sql"
docker compose --env-file .env exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --routines --triggers "$MYSQL_DATABASE"' > "$backup"
test -s "$backup"
docker compose --env-file .env exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot "$MYSQL_DATABASE"' < Back/database/migrations/020_manual_order_diagnostics.sql
docker compose --env-file .env exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot "$MYSQL_DATABASE" -e "SHOW CREATE TABLE manual_order_diagnostics;"'
docker compose --env-file .env up -d --build --no-deps spring-api
```

새 EXE 경로는 `Front/app_version/build/windows/x64/runner/Release/SagoPalgo.exe`로 동일합니다. 운영 DB·실주문 스위치·실제 주문은 이번 작업에서 변경/실행하지 않았습니다.

## 남은 작업

종료 결과가 없는 SENDING을 실제로 종결·해제하는 절차는 아직 없습니다. 이 작업은 운영 진단과 관찰 기록을 추가합니다. UNKNOWN 부분체결·미체결·정정/취소의 대조와 추가 정정, 실제 계좌 검증, 11번 자동매매는 남아 있습니다.

자동 검증은 백엔드 전체 362건(실제 격리 MySQL 8.4 통합 55건)과 Flutter 전체 164건 통과, Dart 정적 분석 이슈 없음과 Windows Release 빌드 성공입니다. 진단 요청/결과 저장 실패·동시 같은 ID·정상 실행자 완료 경쟁·계좌 변경·재시작 후 REQUESTED·020 누락을 포함합니다.

전용 테스트 MySQL 컨테이너·네트워크는 검증 후 정리했습니다. 운영 환경의 수동 화면 대조와 실제 KB 응답 확인은 별도입니다.
