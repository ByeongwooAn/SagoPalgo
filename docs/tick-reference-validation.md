# 실제 호가·체결 입력 규격과 기존 자료 대조

기준일: 2026-11-06. [5-08 조건 6](multi-company-reference-cases.md)과 5-09의 연결 작업입니다. 실제 틱 대조 완료가 아닌 **규격·오프라인 감사 도구·표본 계획과 확보된 일봉의 교차 대조**입니다. 전체 진행률 26/48·54%, 5번 7/18·39%, 5-08 진행 중을 유지합니다.

## 저장 필드 점검

기존 `MarketStreamEvent`, `KisStreamDecoder`, `StoredDatasetExportService` 및 Python `StoredExport`를 점검했습니다. 공급자의 새 외부 규격을 추정해 추가하지 않았습니다.

| 항목 | 현재 자료 | 검증 가능 범위 / 한계 |
|---|---|---|
| 체결 가격·수량·누적 수량 | 십진/정수 문자열 | 양수 가격·0수량·누적 역행/불연속 가능성·자연 체결 ID 검사. 누적 차이를 누락된 개별 체결로 복원하지 않음 |
| 매수·매도 호가·잔량 | 각 10단계 price/quantity; 과거 격리 fixture는 빈 호가 | 원래 레벨 유지, 부족한 레벨·빈 방향·정렬·잠금/교차 상태 표시. 빈 값은 체결 가격/수량 0으로 채우지 않음 |
| 공급자 시각 | `marketTime` / DB `marketAt` | 메타데이터 대조. 체결은 공급자 영업일, 호가는 수신 한국 날짜 추정 |
| 수신 시각 | `receivedAt` | 지연/역순 수신·미래 호가 차단. 나노초는 마이크로초로 미래 방향 올림 |
| 순서 | eventId, 체결 누적 수량 | 거래소 순번 없음. export 정렬 `market_at,event_id`를 공급자/도착 순서로 사용하지 않음 |
| 원문 | 정규화 payloadJson·SHA-256 | 원래 export 전체·행 해시 보존. 원래 WebSocket 프레임 전체는 저장되지 않음 |
| 당시 가용 시각 | DB 커밋/전략 가용 시각 없음 | `knownAt=exportedAt`로 보수적으로 제한. receivedAt을 실제 전략 가용 시각으로 승격하지 않음 |
| 시장·세션·권한 | 설정과 공급자 코드 | 시장·출처 분류·권한·세션 의미는 호출자의 근거 선언. 자동 확인으로 표시하지 않음 |
| 비용·호가 단위·계좌 체결 | 이 입력에 없음 | 수수료/세금/호가 단위·대기열·내 주문 체결 검증 불가 |

## 표본 계획과 실제 확보 상태

[고정 표본 계획](examples/tick-sample-plan.json)은 KOSPI 005930·KOSDAQ 247540의 2026-11-02 후보, 저거래량/누락 조건 후보, 2024-08-05 KOSPI CB 경계와 재개 단일가를 구분합니다. **저거래량/누락 후보가 실제 그 조건을 충족했다고 판정하지 않았습니다.** 조건 미충족이면 제외 사유를 남깁니다.

- 일반 후보: 한국 시간 09:00~09:05. 세션의 확정·전체 틱 확보는 별도입니다.
- CB 시작: 한국 시간 14:14:30. 14:14~14:16 표본 후보로 전/경계/후를 구분합니다.
- 재개 단일가: 14:34:30~14:44:30. 일반 연속 호가 체결 모형으로 단일가 가격·대기열을 추정하지 않습니다.
- 근거는 이전 불변 타임라인 SHA-256에 고정합니다. 시장 공지는 해당 종목의 실제 틱을 증명하지 않습니다. 기존 장중 엔진의 구간/미래 정보 차단 테스트와 새 입력 감사 도구는 별개이며 `audit-ticks`가 엔진 정책을 덮어쓰지 않습니다.
- 이번 예산은 **신규 외부 공급자 호출 0회, 구독 변경 0회**인 캐시 전용입니다. 향후 실제 틱 수집은 권한·공유 구독 예산·운영 025 저장소를 먼저 확인해야 합니다. 과거 CB 틱을 현재 실시간 구독으로 복원할 수 있다고 가정하지 않습니다.

[자료 목록 보고서](examples/tick-inventory-20261106.json)의 점검 범위는 기존 KIS 일봉 작업, KRX 일별매매 캐시, Java/MySQL 격리 export, 운영 공개 시세 테이블 존재와 로컬 GET입니다. 전체 디스크/시장 자료의 완전 탐색 결과는 아닙니다.

| 구분 | 결과 |
|---|---|
| 실제 KIS 일봉 | 005930, 2023-11-01~2026-11-02, 730행; 기존 원문/일지 재감사 |
| 독립 공급자 비교 | 기존 KRX 2023-11-01 캐시와 공통 1행·OHLCV 5필드 일치 |
| 실제 틱/호가 | 점검 범위 안에서 확보 0행; **판정 불가** |
| 격리 Java/MySQL export | 합성 체결 3·호가 1행. 역순 수신 1·추정 날짜/빈 호가 검출. 합성 주문 주장 3개 모두 NOT_ASSESSABLE |
| 로컬 읽기 전용 API | 192.168.0.2:8081 / 루프백 8080 경로 합계 4회 시도, 502. 원문 오류는 저장/출력하지 않음 |
| 운영 DB | information_schema에서 `market_stream_events` 이름만 조회, 테이블 없음. 마이그레이션/수집 활성화는 수행하지 않음 |
| 운영 수집 설정 | 활성화·권한 확인이 true가 아니며 승인 구독 예산이 양수가 아님. 비밀값 없이 세 조건만 조회 |

[실제 일봉 결과 요약](examples/daily-reference-20261106.json)은 시가·고가·저가·종가·거래량 5필드의 판정과 해시만 포함하며, 실제 가격·수량 값과 상세 결과는 Git 제외 로컬 파일에 보존합니다. KIS/KRX 서로 다른 공급자의 날짜 단위 사후 대조이며 **틱·호가·내 주문 체결·장중 가용 시점·다른 729일의 독립 가격 대조를 증명하지 않습니다.**

## 입력과 판정 계약

- `app.replay.ticks`: 기존 export V1을 엄격 검증하고 `SAGOPALGO_PUBLIC_TICK_V1`로 정규화합니다. 원문 해시/타입/종목/시각/자연 ID 불일치·중복 eventId·미허용 필드는 전체 실패입니다. 행을 조용히 삭제하거나 고치지 않습니다.
- `TickAuditConfig`: 출처·시장·종목·최대 24시간 `[startAt,endAt)`·권한/출처 분류·세션 코드·호가 최대 나이를 명시합니다. 입력 export 범위와 정확히 일치해야 합니다.
- `ExecutionClaim`: claimId, referenceTradeId, BUY/SELL, 판단/체결 시각, 가격/수량입니다. 같은 claimId와 범위 밖/역전 시각을 거부합니다. 계좌 식별자는 받지 않습니다.
- JSON Schema: [설정](examples/tick-audit-config.schema.json), [저장 공개 payload](examples/public-tick-payload.schema.json), [비교 주장](examples/execution-claim.schema.json). 수치 문자열/리스트 상한 등의 구조 검증과 모델의 시각/해시/숫자 관계 검증을 함께 적용합니다.
- `MATCH`: 허용·관측 선언과 정상 근거 아래 참조 공개 체결 ID/시각/가격 일치 및 주장 수량 ≤ 해당 공개 체결량. **내 주문이 그 가격에 체결됐다는 판정이 아닙니다.**
- `MISMATCH`: 해당 공개 체결의 시각·가격·수량과 모순됩니다. 실제 틱이 없을 때 불일치 0건을 성공으로 표시하지 않습니다.
- `NOT_ASSESSABLE`: 참조 없음·합성·권한 미확인·추정 날짜·미확인 세션·0수량/시계 이상 등입니다. 실제 계좌 체결 판정은 항상 `NOT_PROVEN`입니다.
- 호가 선택은 시장 시각과 수신 시각이 모두 판단 시각 이하인 마지막 호가만 후보로 사용합니다. 추정 날짜·오래된 호가·역전/빈 호가·과거 가용 시점 미확인 사유를 남기며 실제 사용 가능으로 승격하지 않습니다.
- 같은 시장 시각에 여러 호가가 있고 거래소 순번이 없으면 해시 순서로 마지막 호가를 단정하지 않고 `AMBIGUOUS_QUOTE_ORDER`로 보류합니다.
- 수수료·세금·호가 단위·단일가 대기열은 미지원 사유에 남깁니다. 데이터셋/기존 엔진·수집·계좌·주문 상태는 바꾸지 않습니다.

## 오프라인 재실행

작업 디렉터리 `AI/ai-server`. 실제 자료가 없으므로 첫 명령의 입력은 **격리 합성 파일**이며 설정/주장은 Git 제외 검증 폴더에 있습니다.

```powershell
.\.venv\Scripts\python.exe -m app.replay audit-ticks --input ../../Back/spring-server/build-codex-dataset-export/bridge-fixture.json --config research-artifacts/trade-quote-20261106/synthetic-config.json --claims research-artifacts/trade-quote-20261106/synthetic-claims.json --output research-artifacts/trade-quote-20261106/synthetic-audit-new
.\.venv\Scripts\python.exe -m app.replay.daily_reference --kis-job research-artifacts/kis-daily-live-20261103-130145/job --krx-daily-job research-artifacts/krx-daily-check-20231101-20261104 --market KOSPI --output research-artifacts/trade-quote-20261106/daily-reference-new.json
```

틱 감사 폴더는 source-export.json·config.json·claims.json 원본 바이트, ticks.jsonl, audit.json 및 파일별 해시를 포함합니다. 기존 출력을 덮어쓰지 않으며 게시 실패 시 완성된 준비 폴더를 보존합니다. 일봉 도구도 출력 파일을 배타 생성합니다.

## 완료와 후속

- [x] 저장 필드·부족한 능력 목록화
- [x] 후보 종목/일시/상황·필요 근거·캐시 전용 예산 고정
- [x] 입력 검증·정규화·대조 보고서·보존 CLI
- [x] 기존 실제 일봉의 원문 재감사·독립 공급자 1일 OHLCV 대조
- [ ] 실제 틱/호가 표본 확보 및 주문 추정과 대조 — API 502·저장 테이블 없음/자료 부재. 합성으로 대체 완료하지 않음
- [ ] 실제 비용/호가 단위·단일가·부분 체결·미체결 대조 — 5-09 후속

## 검증 결과

- 신규 관련 테스트 **39개 통과**. 입력 누락/개인 필드·해시/ID/시각 불일치·중복·역순·누적량 불연속/역행·0수량·합성/권한 미확인·비교 일치/불일치·미래/늦은/동시각/오래된 호가·시각 경계·출력 보존·일봉 비교를 포함합니다. 네트워크를 차단한 CLI 시험도 포함합니다.
- 전체 AI 서버 **1,118개 통과·실패/오류/제외 0개**. 직전 1,079개 테스트 식별자를 모두 포함했는지 JUnit 대조했습니다. 기존 Starlette/AnyIO 폐기 예정 경고 1개입니다. 중간 실행은 1,117개였고 마지막 호가 순서 모호성 보완 후 전체를 다시 실행한 최종 결과입니다.
- 연구 자료 **11,228개 파일** 해시 유지. 통신 차단 재생성에서 합성 감사 보고서와 원본/설정/주장/정규화 파일 해시가 일치하고, 3개 입력 JSON Schema가 현재 모델과 일치합니다.
- 산출물은 Git 제외 `AI/ai-server/research-artifacts/trade-quote-20261106/`의 inventory.json, daily-reference.json, offline-final/, validation.json 및 preserved-before.json입니다. 전체 로그/JUnit은 `AI/ai-server/build-codex-replay/tick-full-final.log`, `tick-full-final.xml`입니다. 공개 요약은 위 examples에 포함합니다.
- 신규 외부 공급자 호출·실주문 0회. 운영 배포·DB·EXE·실시간 구독/설정·학습은 변경하지 않았습니다.

[개발 기간 추정](development-completion-estimate.md)은 구현율과 완료일의 차이를 구분합니다.
