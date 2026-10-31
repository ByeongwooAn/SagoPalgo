# UNKNOWN 미체결·부분체결·정정·취소 대조 관찰

2026-11-01, 남은 작업 3번의 대조 범위 확장입니다. 기존 017의 신규 주문 전량 체결 확정에 더해, UNKNOWN 신규 주문의 미체결·부분체결과 변경 주문의 원주문 연결 근거를 90초 준비/재조회/사용자 확인으로 저장합니다. 새 관찰 이력은 차단 해제나 주문번호 연결 확정의 근거로 사용하지 않습니다.

## 범위와 완료 기준

| 대상 | 지원하는 대조 | 저장 후 상태 |
|---|---|---|
| UNKNOWN 신규, 미체결 | 전체 조회·단일 행·일자/번호/종목/방향/가격/수량/시각, 체결 0·잔량=주문량 | OPEN 관찰 저장, UNKNOWN·차단 유지 |
| UNKNOWN 신규, 부분체결 | 같은 항목 및 체결+잔량=주문량·정수 수량 확인 | PARTIAL 관찰 저장, UNKNOWN·차단 유지 |
| UNKNOWN 정정·취소 | 같은 항목, 알려진 당일 원주문과 예약된 자식 명령·계좌·원주문번호·변경 구분 필드 확인 | CHANGE_REFERENCE 관찰 저장, 변경 완료를 추정하지 않음. 원주문 사용 가드·UNKNOWN·차단 유지 |
| UNKNOWN 신규, 전량 체결 | 기존 `KB 주문번호로 전량 체결 대조` 사용 | 기존 017 확정 기준에 따름. 새 관찰 API에서는 해당 경로로 안내 |
| SENDING·빈/중복/불완전·불일치·거절 근거 | 새 대조 준비 거절 | 기존 진단 사용 또는 KB 앱 확인, 차단 유지 |

이번 작업은 미체결·부분체결의 결과를 확인/보관할 수 있도록 확장합니다. 정정·취소도 연결 근거와 수량을 확인할 수 있지만, 최종 성공·실패·취소 완료 판정과 그에 따른 차단 해제는 지원하지 않습니다. 새 대조 관찰을 저장했다고 신규 주문/추가 정정 버튼이 열리면 안 됩니다.

## 공식 명세 확인과 해석 경계

[KB 공식 SSQM2341 명세](https://openapi.kbsec.com/apidoc_b2c#O_5e895db9-9f4c-4c98-aeb1-efc9c57df6f8#G_domestic#A_66998ea3-85f3-4060-bf6d-f88a163eee35)와 공개 [상세 필드 정의](https://openapi.kbsec.com/api/apis/catalog/66998ea3-85f3-4060-bf6d-f88a163eee35/tr-list)를 확인했습니다. `orgn_ordr_no`, `crct_cncl_ccd`, `crct_q`, `sor_cncl_q`를 읽기 전용 항목에 추가합니다. 누락된 선택 수량은 null로 보존하고, 있으면 0 이상 정수 문자열만 허용합니다. 명시적으로 반환한 `ordr_dt`가 요청일과 다르면 조회를 거절합니다.

확인한 명세의 `crct_cncl_ccd`에는 값별 의미가 기재되지 않았습니다. 숫자 1/2 또는 임의 문자열을 정정/취소 성공으로 매핑하지 않습니다. SOR 취소 수량을 KRX 전체 취소 수량으로 대체하지 않습니다. 원주문번호·필드 존재만으로 변경 완료를 확정하지 않습니다. 실계좌의 실제 반환 값과 공식 코드 의미 확인은 남아 있습니다. 시뮬레이터의 SIM_AMEND/SIM_CANCEL은 가상 표식이며 KB 코드가 아닙니다.

기존 전량 체결 확정도 명시적인 원주문 연결·정정 수량·SOR 취소 수량이 있으면 신규 전량 체결로 오인하지 않도록 차단합니다. 선택 필드가 없는 기존 응답과 클라이언트는 호환됩니다.

## 앱 확인

### 실제 기록 화면

`보유 → KB 수동 주문`의 UNKNOWN 카드에서 신규는 `미체결·부분체결 대조`, 정정/취소는 `정정·취소 주문 대조`를 선택합니다. 실주문 스위치를 켤 필요는 없지만 승인 당시 계좌 지문이 현재와 같아야 합니다.

1. KB 앱에서 확인한 숫자 10자리 주문번호로 `읽기 전용 대조 준비`를 누릅니다. 준비 과정은 KB 읽기 전용 조회만 수행합니다.
2. 체결/잔량·주문일·시각·번호·가격·원주문번호·구분 원문·정정/SOR 취소 수량을 확인합니다. 신규는 일치하는 정수 잔량, 변경은 알려진 원주문과 별도 변경 번호가 필요합니다. 가격이 없거나 맞지 않으면 대체 가격을 만들지 않습니다.
3. 관찰 내용과 차단 유지 확인을 체크한 뒤 90초 안에 `대조 관찰 저장`을 누릅니다. 준비 취소는 확인 API를 호출하지 않습니다.
4. 서버가 다시 조회합니다. 체결·잔량·시각·번호·변경 근거가 준비 때와 달라지면 저장을 거절하므로 새로 준비해야 합니다. 두 조회 사이의 진행을 성공/실패로 자동 바꾸지 않습니다.
5. 저장 후 UNKNOWN과 신규 전송 차단이 유지되는지 확인합니다. `저장된 대조 관찰`은 현재 사용자 최근 20건 이력만 읽고 KB를 재조회하지 않습니다.

확인 응답이 끊기면 자동 POST 대신 이력 GET으로 동일 reviewId를 확인합니다. 화면은 확인 토큰을 다시 전송하지 않습니다. 같은 ID·정확한 토큰의 서버 재요청은 이미 저장된 결과만 반환합니다. 이력에서 확인할 수 없으면 화면을 다시 열어 새로 준비할 수 있지만, 이전 준비는 새 토큰으로 대체되어 무효화됩니다.

### 시뮬레이터에서 먼저 확인

`모의 → 주문 시뮬레이션`에 2개 시나리오를 추가해 총 11개입니다. 기본 가정 시세 75,000원·2주를 사용합니다. 실계좌·실제 KB 모의투자 서버를 호출하지 않습니다.

1. **미체결 접수 후 응답 유실:** 새 세션에서 신규 매수를 진행합니다. UNKNOWN·OPEN·전송 1회·잔량 2주를 확인하고 `미체결·변경 주문 대조`에서 표시된 가상 번호를 준비/확인합니다. 저장 뒤 상태·차단·전송 횟수·가상 자원은 유지됩니다.
2. **부분체결 후 응답 유실:** 별도 새 세션에서 신규 매수를 진행합니다. UNKNOWN·PARTIAL·체결 1주/잔량 1주를 대조합니다. 확인 전 수동 가상 체결로 잔량을 바꾸면 저장이 거절되어야 합니다.
3. **정정:** 별도 새 세션에서 대기 신규 주문 접수 → 지정가 인하 → 기존 `접수 후 응답 유실`로 정정합니다. 자식 UNKNOWN 카드에서 새 가상 번호를 대조해 원주문 번호·SIM_AMEND를 확인합니다. 저장 후 부모 사용 가드와 UNKNOWN은 유지됩니다.
4. **취소:** 별도 새 세션에서 대기 신규 주문 접수 → `접수 후 응답 유실`로 전부 취소합니다. 자식 번호·원주문 번호·SIM_CANCEL 관찰을 저장해도 취소 완료 판정/차단 해제를 하지 않습니다. 취소에는 새 미체결/부분체결 응답 유실 시나리오를 지정하지 않습니다.
5. 저장 이력과 세션 재진입을 확인합니다. 이전 JSON에 새 필드가 없으면 빈 이력으로 읽습니다. 시뮬레이터는 명령당 최대 20건을 보관하며 내부 준비/확인 토큰 해시는 API 상태에서 제외합니다.

## 저장과 동시성

021의 준비 테이블은 명령당 최신 한 건입니다. 토큰은 해시로 저장하며, 준비가 바뀌면 이전 reviewId/토큰은 사용할 수 없습니다. 정규화한 관찰 해시를 함께 저장해 최종 재조회가 같은 관찰인지 검사합니다. 마이너스·소수 주식 수량과 합계 불일치·불완전 조회는 준비하지 않습니다. 시간 범위는 기존처럼 생성 시각 -2초~+300초입니다.

조회 중에는 DB 잠금을 유지하지 않습니다. 저장 직전 사용자·명령을 잠그고 UNKNOWN·현재 계좌·원주문 예약·만료·토큰/관찰 해시를 확인합니다. 토큰 소비와 관찰 이력 저장을 같은 트랜잭션으로 처리하고, 저장 실패는 소비도 롤백합니다. 실제 소비 시각으로 만료를 다시 검사합니다. 같은 확인의 동시 실행은 감사 기록을 한 번만 저장합니다.

원래 주문·전송 결과·제출 가드·원주문 변경 가드·보유/자본금은 수정하지 않습니다. 017의 전량 체결 확정 테이블에도 쓰지 않으며 pending 집계 조건을 바꾸지 않습니다. 원문 종목명/거절 사유/예외·계좌 지문·토큰/관찰 해시는 준비/이력 응답에 노출하지 않습니다.

## API와 배포

| 메서드/경로 | 동작 |
|---|---|
| POST `/api/v1/orders/manual/{id}/reviews/prepare` | `{orderNo}` → `{reviewId,token,expiresAt,evidence,message}` |
| POST `/api/v1/orders/manual/{id}/reviews/confirm` | `{reviewId,token,acknowledged:true,confirmation:"잠금 유지 대조 저장"}` → 저장된 관찰 |
| GET `/api/v1/orders/manual/{id}/reviews` | 최근 20건 관찰. KB 호출 없음 |
| POST `/api/v1/orders/simulations/{sessionId}/commands/{id}/reviews/prepare` | 같은 번호 본문으로 가상 대조 준비 |
| POST `/api/v1/orders/simulations/{sessionId}/commands/{id}/reviews/confirm` | 같은 확인 본문으로 저장 후 가상 세션 상태 반환 |

evidence는 `kind,observation,orderDate,orderNo,orderTime,stockCode,side,price,quantity,filledQuantity,openQuantity,originalOrderNo,changeCode,correctedQuantity,sorCancelledQuantity,parentObservation`입니다. 선택적 parentObservation은 아래 후속 범위를 따릅니다. 저장 응답은 여기에 `reviewId,commandId,confirmedAt,lockMaintained:true,message`를 제공합니다. 시뮬레이터 저장 상태에는 공개 reviews 목록을 추가하고 내부 reviewPreparation/토큰 해시는 반환하지 않습니다.

021 미적용은 새 관찰 API에서 `REVIEW_STORAGE_UNAVAILABLE`(503)로 안내합니다. 기존 전량 체결 확정과 수동 주문 준비 조건에는 021을 추가하지 않습니다. 016은 사용자가 운영 적용을 확인했고, 017~021 적용 완료는 아직 확인받지 않았습니다. PR 병합 후 Ubuntu 프로젝트 루트에서 기존 DB를 백업하고 적용합니다. 실제 주문 스위치는 OFF로 유지합니다.

```bash
set -e
git switch develop
git pull --ff-only origin develop
backup="sagopalgo-before-021-$(date +%Y%m%d-%H%M%S).sql"
docker compose --env-file .env exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --routines --triggers "$MYSQL_DATABASE"' > "$backup"
test -s "$backup"
docker compose --env-file .env exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot "$MYSQL_DATABASE"' < Back/database/migrations/021_unknown_order_reviews.sql
docker compose --env-file .env exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot "$MYSQL_DATABASE" -e "SHOW CREATE TABLE manual_order_review_preparations; SHOW CREATE TABLE manual_order_reviews;"'
docker compose --env-file .env up -d --build --no-deps spring-api
```

실행 파일은 기존 `Front/app_version/build/windows/x64/runner/Release/SagoPalgo.exe` 경로이며 새 Flutter 번들까지 함께 사용합니다. 실제 KB 조회/주문·운영 DB 변경은 이번 작업에서 수행하지 않았습니다.

## 남은 범위

변경 구분 코드의 공식 값/실제 응답과 최종 정정·취소 결과 검증, 잔량 주문의 종결·차단 해제, 종료 증거 없는 SENDING 종결, 가격 증액·일부 수량 변경·추가 정정, 실제 계좌 검증 및 11번 자동매매는 남았습니다. 이번 관찰 저장을 해당 범위의 완료로 계산하지 않습니다.

자동 검증은 백엔드 410건(실제 격리 MySQL 통합 71건), Flutter 176건 통과, Dart 분석 이슈 없음, Windows Release 빌드 성공입니다. 새 대조·레거시 전량 체결 오인 차단·조회 일자·토큰 교체/만료·재조회 변경·동시 확인·저장 실패 롤백·가상 자원 보존을 검증했습니다. 테스트 컨테이너·네트워크는 정리했습니다.

## 후속: 원주문 관찰과 가상 종결의 분리 (2026-11-01)

정정/취소는 자식 조회 이후 저장된 원주문번호로 원주문도 별도 조회합니다. `parentObservation`은 `orderNo,orderTime,price,quantity,filledQuantity,openQuantity,correctedQuantity,sorCancelledQuantity,verification`이며 검증된 항목만 담습니다. verification은 REFERENCE_MATCH/LOOKUP_FAILED/SCOPE_MISMATCH/INCOMPLETE/ROW_NOT_UNIQUE/IDENTITY_MISMATCH/QUANTITY_INVALID입니다. 참조 일치는 정정·취소 완료가 아닙니다. 실패는 원문 없이 보관하며, 부모 관찰만 달라져도 확인 시 재준비를 요구합니다. 계좌 변경은 거절하고 실제 상태·차단·가드는 유지합니다.

이전 이력의 누락 필드는 null로 읽고 원주문 미조회로 표시합니다. 021 JSON 확장이므로 추가 마이그레이션은 없습니다. 배포 전 발급한 90초 준비는 해시가 달라질 수 있어 다시 준비합니다. KB 공개 자료 조사에서는 완료 코드값 근거를 찾지 못했습니다. [공식 출처·조회 한계·후속 확인](order-completion-evidence.md)을 참고합니다.

시뮬레이터에는 별도의 `가상 주문 종결 대조`를 추가했습니다. 가상 증권사의 엄격한 소유권/종결 근거와 별도 동의가 있는 명령만 가상 차단 집계에서 제외합니다. 이 문서의 reviews 저장은 계속 잠금을 유지하며, 실제 주문 종결/해제 API는 추가하지 않았습니다. 후속 전체 자동 검증은 백엔드 462건(MySQL 87건)·Flutter 182건입니다.
