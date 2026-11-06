# 커밋 이후 로컬 입력 공개 시각 기록

최신 후속 [U02 연구용 입력 수신·시계 연결](strategy-input-receipts.md)을 완료했습니다. 현재 수집 프로세스의 실제 123건을 Python 수신과 연결하고 Java/Python 재시작을 확인했습니다. 아래 U01 완료 당시의 외부 수신 미확인 기록과 구분합니다. 신뢰 UTC·실제 모델 소비는 여전히 후속입니다.

기준일: 2026-11-06. [세션·시각 품질 ①-06](quote-execution-quality.md)의 **DB 커밋 이후 로컬 입력 캐시 공개 기록**을 구현·실제 표본으로 검증했습니다. UTC 동기화와 외부 Python 전략의 실제 수신 확인은 [남은 실행 단위 U02](remaining-development-units.md)에 남깁니다. ①-06 전체 완료나 자동매매 준비 완료를 의미하지 않습니다.

## 원인과 변경

기존 `MarketStreamHub.accept`는 저장 메서드가 반환되면 캐시에 자료를 공개했습니다. 저장이 상위 트랜잭션에 참여하면 실제 커밋 전에 반환될 수 있어, 이후 롤백되는 입력을 캐시에서 볼 가능성이 있었습니다. 수신 시각을 커밋·전략 가용 시각으로 대체할 수도 없었습니다.

현재 순서는 다음과 같습니다.

1. 원본 이벤트·관측 분봉을 같은 트랜잭션에서 저장합니다.
2. 실제 상위 트랜잭션의 `afterCommit`에서 커밋 완료 관측 시각을 찍습니다.
3. 별도 `REQUIRES_NEW / READ_COMMITTED` 트랜잭션으로 원본이 커밋되어 읽히는지 다시 검사합니다. savepoint 롤백 후 남은 콜백도 원본이 없으면 공개하지 않습니다.
4. 연결 세대와 최신성 검사를 통과한 이벤트만 로컬 캐시에 공개합니다.
5. 캐시 모니터가 해제된 뒤 공개 완료 관측 시각을 찍고, 원문 해시와 함께 027 테이블에 불변 기록합니다.

Spring의 [트랜잭션 콜백 계약](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)에 따라 `afterCommit` 안의 후속 DB 작업은 새 트랜잭션을 사용합니다. 롤백·중복·오래된 이벤트·연결 세대가 바뀐 콜백에는 새 공개 기록을 만들지 않습니다. 기록 실패 시 원본 커밋은 보존하고 캐시를 비운 뒤 `AVAILABILITY_RECORD_FAILED`로 중단합니다. 로그를 켜지 않아도 커밋 이후 공개 보호는 적용됩니다.

이 기록은 **실제 DB 커밋 시각과 캐시 공개 시각의 관측 상한**입니다. DB 내부 커밋 타임스탬프, SSE 전달 완료, AI 모델이 실제 입력을 읽은 시각을 대신하지 않습니다. 관측 직전에 캐시가 이미 공개됐을 수 있으므로 재현에서는 관측 시각부터만 사용합니다.

## 시계와 저장 계약

[027 마이그레이션](../Back/database/migrations/027_market_input_availability.sql)은 `market_stream_availability`를 추가합니다. 기존 025 원본을 수정하거나 과거 행에 시각을 소급 생성하지 않습니다.

| 필드 | 의미 |
|---|---|
| event_id / content_hash | 저장된 공개 원문의 식별자·SHA-256 연결 |
| clock_domain | JVM 시작마다 새 UUID. 다른 프로세스·재시작 시각과 직접 비교하지 않음 |
| commit_observed_at | 원본 트랜잭션 커밋 후 콜백에서 관측한 시각 |
| input_published_at | 로컬 입력 캐시 공개 후 관측한 시각 |
| commit_elapsed_ns / published_elapsed_ns | 같은 프로세스 시작 기준 단조 시계 경과량 |
| clock_quality | MONOTONIC_STABLE 또는 CLOCK_STEP_DETECTED |

시계는 시작 UTC 표기값에 `System.nanoTime` 경과를 더하고 마이크로초로 미래 방향 올림합니다. 관측값은 엄격히 증가하며 시스템 벽시계와 250ms 넘게 달라지면 프로세스 종료까지 불안정으로 표시합니다. 시작 시각 자체의 UTC 오차는 검출·보정하지 못하므로 항상 `clockBasis=JVM_MONOTONIC_ANCHORED_UTC`, **`utcSynchronized=false`**입니다. OS 시간 설정은 변경하지 않았습니다.

기능 플래그 `SAGOPALGO_MARKET_AVAILABILITY_ENABLED`는 기본 **false**입니다. true 사용 전 027이 필요합니다. 기본 OFF와 기존 계좌·주문·자동 수집 설정을 유지했으며 이번 실제 수집은 별도 단기 컨테이너에서만 true로 실행했습니다.

## V1 호환과 명시적 V2 사용

기존 `GET /api/v1/research/dataset-export`와 V1 필드는 유지합니다. 새 읽기 전용 경로는 다음과 같습니다.

```text
GET /api/v1/research/dataset-export/availability?stockCode=005930&from=2026-11-06T06:42:00Z&to=2026-11-06T06:43:00Z
```

`SAGOPALGO_STORED_EXPORT_V2`는 기존 시세 행에 선택적 `availability`를 추가합니다. 기록이 없으면 null이며 수신 시각으로 대신하지 않습니다. 025/026/027, no-store·REPEATABLE_READ, 기존 분 단위 24시간/행/원문 용량 제한을 따릅니다. 원문 해시와 시각 순서를 검증하고 실제 Provider·계좌·주문을 호출하지 않습니다. [V2 스키마](examples/stored-export-v2.schema.json)를 함께 관리합니다.

Python의 기존 감사·BAR 변환은 V2를 읽어도 기본 `knownAt=exportedAt` 보수적 정책을 유지합니다. 관측 공개 시각은 다음 별도 조회에서만 사용합니다. 경로는 AI 서버 작업 폴더 기준 예시이며 실제 도메인은 V2에서 확인합니다.

```powershell
.\.venv\Scripts\python.exe -m app.replay snapshot-inputs --input actual-v2.json --config tick-config.json --at 2026-11-06T06:42:50Z --clock-domain <V2의-clockDomain> --output snapshot.json
```

`snapshot-inputs`는 같은 도메인·안정 시계·공개 시각 이하 자료만 반환합니다. 해당 뷰는 `knownAt=inputPublishedAt`, `exportObservedAt=기존 내보내기 시각`, `knownAtBasis=INPUT_PUBLICATION_SAME_CLOCK_DOMAIN`을 기록합니다. 도메인 불일치·관측 없음·시계 불안정은 대체 추정 없이 제외합니다. 출력은 덮어쓰지 않으며 네트워크를 사용하지 않습니다.

호가 연구 모형도 명시적 `availabilityMode=INPUT_PUBLICATION_OBSERVED`와 `decisionClockDomain`을 함께 지정한 경우에만 사용합니다. 날짜 앵커 체결 역시 자체 공개 관측이 필요합니다. 기존 `EXPORT_OBSERVED`·수신 기반 가정과 구분하며 **실제 Python 전략 판단 시각이 이 도메인에 연결됐다는 증거는 아직 없습니다.** 비용·세션·체결 가정과 `usableForStrategyValidation=false`는 유지합니다.

## 실제 자료와 보존 검증

전체 DB 백업을 압축 해제 검증한 뒤 메인 PC DB에 027만 추가 적용했습니다. 백업과 실제 원문·수집 영수증은 Git 제외 경로에 보존합니다. Ubuntu DB 적용이나 운영 백엔드 재배포 결과는 아닙니다.

- 백업: `Back/spring-server/build-codex-availability/before-027-20261106T064224Z.sql.gz`, SHA-256 `a7b833f868d0f1d7e614f016f1a263b8535994cc83a812a35371f7649cfb0fdb`.
- 삼성전자 1종목·체결/호가 2구독, 15:42:26~15:42:55 KST의 제한 수집에서 **체결 1·호가 4, 관측 5건**을 확보했습니다. 정규 연속매매 표본으로 분류하지 않습니다.
- 5건 모두 공개 1µs 전에는 해당 입력이 없고, 공개 시각에는 보입니다. 다른 도메인에는 0건입니다. 원본 V1 payload는 동일합니다.
- 이전 표본 1,081건은 V2에서도 관측이 없습니다. 전체 이전 이벤트 **1,199건 원문 해시 보존**, 추가 5건·관측 5건, 과거 이벤트 소급 관측 0건입니다.
- 이전 38개 테이블 중 스트림 원본/분봉을 제외한 **36개 테이블 불변**입니다. 원래 계좌·주문 자료를 포함합니다.
- 수집기와 읽기 전용 검증 서버는 종료·임시 환경 파일 제거했습니다. 신규 메인 운영 수집은 활성화하지 않았습니다.

공개 요약은 [가용 시각 검증 JSON](examples/committed-availability-validation-20261106.json)에 건수·해시·판정만 남깁니다. 5건의 짧은 마감 후 관측으로 장중 지연 분포·장기 안정성·실제 주문 체결을 일반화하지 않습니다.

## 회귀 결과와 남은 범위

- Java 전체 실행: **735건 중 602건 통과·133건 제외·실패/오류 0건**. 관련 실제 MySQL 통합 검증을 활성화했고, 다른 기능의 별도 외부 환경 조건 133건은 제외 상태를 숨기지 않습니다.
- AI 전체: **1,164건 통과·실패/오류/제외 0건**, 기존 Starlette 의존성 경고 1건.
- 수집 스크립트: **17건 통과**.
- 네트워크 차단 재검증: 기존 실제 호가 보고서 **28개 바이트 일치**, Java/MySQL V2→Python 2행 연결, 실제 5건 공개 경계 확인.
- 롤백/savepoint·커밋 전 비공개·동일 이벤트 재수신·재연결 세대·기록 실패·해시 불일치·과거 행 비소급·V1 호환을 검증했습니다.

이번 실행 단위 U01은 완료했습니다. ①-06은 UTC·외부 전략 수신 조건이 남아 미체크, ① 5/6·83%·② 7/8·88%·③ 5/6·83%를 유지합니다. 프로젝트 고정 합계 **27/48·56%, 5번 7/18·39%, 5-08 진행 중**도 유지합니다. 다음 작업과 이후 잔여 작업은 [실제 실행 단위 목록](remaining-development-units.md)으로 관리합니다.
