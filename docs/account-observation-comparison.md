# R1 저장된 계좌 관찰 비교

기준일: 2026-11-02 · 계약: `KB_ACCOUNT_COMPARISON_V1` · 상태: 백엔드 구현·격리 MySQL 검증. 앱 구현은 [후속 문서](account-observation-ui.md)에 연결합니다. 운영 배포·실계좌 대조는 후속입니다.

[관찰 저장·이력](account-observation-history.md)의 두 기록을 읽어 **관찰된 필드의 변화**를 반환합니다. 같은 연결에서 관측한 수량·잔고·주문 필드가 달라졌는지 확인하는 R1 진단 단계입니다. 입출금·매수/매도·체결·주문 종결·수익을 판정하거나 원장·예약·보유분을 갱신하지 않습니다.

## 1. API와 요청

```text
GET /api/v1/kb/accounts/primary/observations/comparison
    ?beforeRequestId=<이전 관찰의 요청 UUID>
    &afterRequestId=<이후 관찰의 요청 UUID>
```

- 두 요청 ID는 필수이며 서로 달라야 합니다. UUID 표준 형식을 검사하고 소문자로 정규화합니다. 대소문자만 다른 같은 ID도 400입니다. 입력 오류는 저장 이력을 읽기 전에 거절합니다.
- 서버의 로컬 사용자와 현재 KB 연결 범위로 각각 상세를 조회합니다. 다른 사용자·다른 연결·없는 기록은 404이며, 저장 본문의 체크섬/계약 불일치는 503 `OBSERVATION_STORAGE_UNAVAILABLE`입니다.
- 두 기록을 읽는 사이 또는 비교 중 연결이 바뀌면 409입니다. 첫 기록을 읽은 연결과 두 번째 기록의 연결이 섞인 결과를 반환하지 않습니다.
- 외부 KB 조회·토큰 발급·DB INSERT/UPDATE는 없습니다. 기존 상세 경로 `/{requestId}`와 공존하며 `comparison`은 고정 경로입니다.
- 정상 응답은 공통 `ApiResponse`와 `Cache-Control: no-store`, `readOnly=true`, `usableForTrading=false`입니다. HTTP 200/공통 `success=true`는 비교 가능한 구간이 있다는 보장이 아닙니다.

기존 023 테이블을 사용하므로 새 마이그레이션은 없습니다. 023이 없는 환경은 먼저 [저장 기능의 적용 절차](account-observation-history.md#4-db와-배포)를 따라야 합니다. 이번 작업은 운영 DB 적용·배포를 수행하지 않았습니다.

## 2. 비교 가능 조건

전체 응답의 `status`는 네 구간 모두 비교되면 `COMPARED`, 일부만 비교되면 `PARTIAL`, 모두 차단되면 `BLOCKED`입니다. 각 구간의 `status`는 `COMPARED` 또는 `BLOCKED`입니다. 차단된 구간에는 `reasons`만 반환하고 `summaryChanges`, `rowChanges`는 비웁니다.

먼저 두 저장 상태가 `COMPLETED`이고 관찰 본문이 있어야 합니다. `PENDING/FAILED` 기록을 정상적인 빈 계좌로 해석하지 않습니다. 이후 관찰의 서버 수신 시작 시각은 이전 관찰의 완료 시각과 같거나 뒤여야 합니다. 순서가 뒤집히거나 수신 구간이 겹치면 모든 구간을 차단합니다. 서버 수신 시각 비교이며 증권사 평가 기준 시각을 확정하지 않습니다.

네 구간은 각각 독립적으로 다음을 검사합니다.

1. 조회 범위 `scope`가 정확히 일치해야 합니다. 종목 필터·조회 분류·가격 기준이 바뀌면 해당 구간을 차단합니다. 주문 조회 날짜가 다르면 주문 구간만 차단할 수 있습니다.
2. 양쪽 모두 `status=SUCCESS`, `completeness=COMPLETE`, `issues=[]`여야 합니다. 전체 관찰 상태가 PARTIAL이어도 정상 구간은 비교할 수 있습니다.
3. 조회 페이지가 있고 수신 행 수가 보존된 행 수와 일치해야 합니다. 제공된 전체 건수도 행 수와 같아야 합니다.
4. 모든 행에 구간별 식별 필드가 있어야 하며 공백·중복 식별자를 허용하지 않습니다. V1에서 지원하지 않는 필드·잘못된 숫자가 있으면 구간 전체를 차단합니다.

| 구간 | 행 매칭 식별 필드 |
|---|---|
| SSQM1801 보유 | `is_no` |
| SSQM2932 결제기준 잔고 | `gds_typ`, `clsf`, `crncy_cd`, `is_cd`, `is_dtl_typ_cd`, `fnl_ccls_excg_cd` |
| SSQM2952 체결기준 잔고 | `clsf`, `crncy_cd`, `is_cd`, `is_dtl_typ_cd`, `fnl_ccls_excg_cd` |
| SSQM2341 지정일 주문 | 같은 날짜/범위의 `ordr_no`, `stnd_is_no` |

이름이나 응답 순서만으로 행을 맞추지 않습니다. 잔고의 통화·상품·거래소 중 하나라도 식별되지 않으면 비교를 차단하는 보수적인 정책입니다. 실제 계좌에서 해당 필드가 비어 있으면 그 구간은 비교할 수 없습니다. 이를 해소하려면 공식 필드 계약과 실환경 대조 증거가 필요하며 임의 기본값으로 채우지 않습니다.

## 3. 응답과 변화량

최상위 `before/after`는 요청 ID·조회 날짜·저장 상태·관찰 ID·관찰 상태·실패 코드·관찰 시작/완료 시각입니다. 각 `sections` 항목은 API 이름, 양쪽 범위와 상태·완전성·수신 시각·건수·문제 코드, 비교 상태·사유, 요약/행 차이를 담습니다. 인증값·연결 HMAC·사용자 ID·저장 본문/체크섬은 반환하지 않습니다.

행 차이의 `kind`는 다음 세 가지입니다.

| 값 | 의미 |
|---|---|
| `CHANGED` | 같은 식별자로 매칭된 행의 지원 필드가 달라짐 |
| `OBSERVED_ONLY_BEFORE` | 이전 관찰에서만 확인한 행 |
| `OBSERVED_ONLY_AFTER` | 이후 관찰에서만 확인한 행 |

한쪽에서만 보이는 행은 거래·종결 결과를 뜻하지 않습니다. 수량을 0으로 대입하거나 매수·매도로 이름 붙이지 않습니다. 식별자만 있고 다른 필드가 없는 한쪽 행도 차이로 남깁니다. 행 차이는 복합 식별 필드의 문자열 순서로 정렬해 입력 배열 순서에 영향을 받지 않습니다.

`summaryChanges`와 각 행의 `fields`에는 바뀐 필드만 들어갑니다. 필드 항목 예시입니다.

```json
{
  "field": "hld_q_p6",
  "beforePresent": true,
  "afterPresent": true,
  "beforeValue": "0.123456",
  "afterValue": "0.123457",
  "numericDelta": "0.000001"
}
```

- 원본 값은 문자열/null로 유지합니다. `beforePresent/afterPresent`로 필드 자체의 누락과 명시적 null을 구분합니다. 이 항목들의 null은 JSON에서 생략하지 않습니다.
- 알려진 숫자 필드만 BigDecimal로 비교합니다. `1`, `+001.000`처럼 수치가 같은 표현 변화는 보고하지 않습니다. 문자열 필드는 문자열 그대로 비교합니다.
- 양쪽에 숫자가 있을 때만 `이후 - 이전`을 계산합니다. 결과는 지수 표기 없는 십진 문자열입니다. 한쪽 값이 누락/null이거나 행이 없으면 `numericDelta=null`입니다.
- 일반 수량과 P6 수량을 서로 대체/환산하지 않으며 각 필드 이름의 관찰값을 비교합니다. 통화별 금액 합산·환산, 수익률/현금흐름/원장 계산은 하지 않습니다.
- 변화 항목이 없다는 것은 지원 필드의 관찰 차이가 없다는 뜻이며 두 수신 시각 사이에 거래가 없었다는 증거가 아닙니다.

## 4. 차단 사유

| `reasons` 코드 | 의미 |
|---|---|
| `STORAGE_NOT_COMPLETED` | 한쪽 이상이 저장 완료된 관찰이 아님 |
| `INTERVAL_NOT_FORWARD` | 서버 수신 구간이 겹치거나 이전/이후 순서가 역전됨 |
| `SCOPE_MISMATCH` | 조회 범위가 다름 |
| `SECTION_UNAVAILABLE` | 한쪽 이상 구간 상태가 SUCCESS가 아님 |
| `SECTION_INCOMPLETE` | 한쪽 이상 완전성이 COMPLETE가 아님 |
| `SECTION_HAS_ISSUES` | 구간에 문제 코드가 있음 |
| `INVALID_ROW_COUNT` | 페이지·수신/전체 건수와 보존된 행이 모순됨 |
| `INVALID_ROW_IDENTITY` | 행 식별 필드가 없거나 공백임 |
| `DUPLICATE_ROW_IDENTITY` | 복합 식별자가 중복됨 |
| `UNSUPPORTED_FIELDS` | V1 허용 목록 밖의 필드가 있음 |
| `INVALID_NUMBER` | 지원 숫자 필드가 정규화된 십진 문자열이 아님 |

## 5. 검증과 후속

[격리 MySQL 재현 절차](account-observation-history.md#5-격리-검증과-재현)를 그대로 사용합니다. KB 서비스는 mock이며 전용 DB 이름·마커·루프백 포트·tmpfs를 유지합니다. 비교 중 금융 기록·외부 조회 횟수가 바뀌지 않는지 검증합니다.

검증 범위는 정밀한 십진 계산·null/누락·행 재정렬·복합 식별·구간별 부분 차단·수신 순서·연결 변경·HTTP 경로 충돌 방지와 실제 저장 이력의 조회·무결성·사용자/연결 격리입니다. 실행 건수는 [개발 진척도](development-progress.md)에 기록합니다.

[앱 이력/비교 화면](account-observation-ui.md)을 후속 구현했습니다. 앱 연결 구현·모의 검증과 운영 배포·실계좌 대조는 구분합니다. 관찰 자동 수집과 일별 자산·입출금·체결 원장은 남아 있으며 관찰 비교를 원장 이벤트로 자동 변환하지 않습니다. KB 답변이 필요한 주문 완료·추가 정정·예약금 재사용은 [기존 보류 조건](kb-contract-blockers.md)을 유지합니다.
