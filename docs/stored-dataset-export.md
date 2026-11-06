# R2·R3 저장 자료 → R5 데이터셋 연결

2026-11-06 후속: 기존 V1을 유지하고 [선택적 커밋/로컬 공개 관측 V2](committed-input-availability.md)를 추가했습니다. `GET /api/v1/research/dataset-export/availability`는 027 관측을 함께 반환하며, 없으면 null입니다. 실제 UTC 동기화·외부 전략 수신을 주장하지 않습니다. Python은 V1/V2를 지원하고 기본 변환의 보수적 가용 시각은 유지합니다. 아래는 V1의 원래 계약과 당시 검증 기록입니다.

후속 [틱 감사·대조 계약](tick-reference-validation.md)은 export V1의 체결/호가를 별도 감사 폴더로 보존합니다. 기존 BAR 변환이나 엔진 정책은 변경하지 않으며, 빈 호가·추정 날짜·거래소 순번/과거 가용 시각 부재를 표시합니다.

기준일: 2026-11-03. [R5](historical-data-replay.md) 후속이며 [고정 체크리스트](numbered-work-progress.md)의 5-05/5-06입니다. 제품 코드·격리 검증 단계입니다. 운영 025/026 적용·배포·실제 자료 수집/대조는 후속이며 수집 OFF·주문 설정·Windows 앱은 유지했습니다.

## 읽기 전용 API

`GET /api/v1/research/dataset-export?stockCode=005930&from=2025-11-03T00:00:00Z&to=2025-11-03T00:02:00Z`

- ApiResponse.data의 형식은 `SAGOPALGO_STORED_EXPORT_V1`, no-store·readOnly=true·usableForTrading=false입니다. 외부 Provider·계좌·주문·구독을 호출/변경하지 않고 수집 OFF에서도 기록된 자료만 읽습니다.
- 종목 6자리·분 단위 `[from,to)` 최대 24시간·종료된 구간입니다. `market_stream_events`는 시장 시각으로 읽어 현재 DB 스냅샷에 있는 늦은 수신도 포함합니다. 최종 분봉 테이블은 사용하지 않습니다.
- `research_versions`는 observed_at < to인 **과거 버전 전체**입니다. from 이전도 포함해 revision 1과 정정 이력을 유지합니다. 최신 자료만 기간 필터로 내보내지 않습니다.
- readOnly·REPEATABLE_READ 트랜잭션에서 용량 검사와 두 자료를 읽습니다. 중간 동시 저장이 앞뒤 조회를 서로 다른 스냅샷으로 만들지 않습니다. exportedAt은 DB UTC 내보내기 시각입니다.
- 종류별 최대 10,000행·합계 원문 32MiB를 payload 로드 전에 확인합니다. 초과하면 일부 결과를 완료로 반환하지 않습니다. 저널이 10,000행을 넘으면 from을 줄여도 과거 전체 버전 상한이 풀리지 않으며 안정적 분할/페이지 내보내기는 후속입니다.
- 타입·식별자·DB 메타데이터·연구 원문 해시를 대조합니다. 미허용 필드·손상 자료·저장소 오류는 원문 없는 고정 오류입니다. 누락 테이블을 자동 생성하거나 마이그레이션을 적용하지 않습니다.

streamEvents는 eventId·종목·종류·시장/수신 시각·payloadJson·해시, researchVersions는 changeId·공급자·자료 키·revision·관측 시각·origin·payloadJson·해시입니다. 원문은 공개 자료 타입의 필드만 허용합니다. 시세 수신 시각은 DB 커밋 시각이 아니며 이 결과는 거래소 자료의 완전성을 보장하지 않습니다.

## 변환과 원본 보존

`python -m app.replay convert-stored --input export.json --config conversion.json --output converted`는 ApiResponse 전체 또는 data 객체 파일을 읽습니다. 네트워크를 호출하지 않고 기존 출력 경로를 덮어쓰지 않습니다.

| 파일 | 내용 |
|---|---|
| source-export.json | 원본 바이트 전체. 제외된 호가·날짜 공시도 보존 |
| spec.json | 출처·권한 선언·생성 경위·원본 SHA-256 참조·시각 정책 |
| records.jsonl | 지원하는 R5 자료만 정규화 |
| conversion.json | 설정·입력/출력 수·제외 사유·파일별 해시 |

변환 폴더와 별도 R5 번들을 함께 보존해야 서버 내보내기까지 대조할 수 있습니다. 번들의 raw.jsonl은 변환된 records.jsonl 원본이며 전체 서버 내보내기와 동일하지 않습니다.

### 체결 → 관측 분봉

- 원문 해시·메타데이터·제공 영업일·자연 체결 식별자·수치 문자열을 검사합니다. 세션 대응은 코드와 근거를 설정으로 명시합니다. [KIS 공식 컬럼](https://github.com/koreainvestment/open-trading-api/blob/main/examples_user/domestic_stock/domestic_stock_functions_ws.py)의 HOUR_CLS_CODE 기록과 값별 정규 세션 의미 확인을 구분합니다.
- 제공 시각·누적 거래량 순서로 시가/종가를 정하고 관측한 체결량만 더합니다. 누락을 채우거나 완전 분봉으로 표시하지 않습니다.
- 기본 `EXPORT_OBSERVED`는 최종 관측 분봉 한 버전만 만들고 내보내기 시각부터 가용하다고 봅니다. 저장된 입력을 함께 확인한 시각보다 이전 계산/커밋 시각을 만들지 않습니다.
- 선택적 `RECEIPT_DERIVED`는 종료까지 받은 체결을 묶고 늦은 수신 그룹마다 revision을 만듭니다. publishedAt은 추정 계산 가능 시각, observedAt은 내보내기 시각입니다. 실제 계산·DB 커밋·전략 가용 시각의 증거가 아니므로 품질에 표시하고 재현에는 **allowDerivedAvailability=true**가 필요합니다. BAR에만 허용합니다.
- Java 나노초 수신 시각은 지원 마이크로초로 **미래 방향 올림**하며 일찍 알았던 것으로 잘라내지 않습니다. 같은 가용 시각 도착은 묶습니다.

### 뉴스·공시와 제외

- 시각이 확인되는 뉴스는 최초/정정/원복과 LEGACY_BASELINE의 실제 저널 관측 시각을 유지합니다. revision을 1로 재시작하지 않습니다. 계보 중 공개 시각 미상·관측보다 늦은 공개가 있으면 해당 뉴스 계보 전체를 제외하고 이유를 기록합니다.
- OpenDART 목록의 receiptDate는 날짜입니다. 임의 자정/개장 시각을 넣지 않고 `DATE_ONLY_DISCLOSURE`로 제외하되 원본은 남깁니다.
- 호가는 `QUOTE_NOT_A_BAR`, 추정 날짜 체결은 `UNCONFIRMED_BUSINESS_DATE`, 미확인 세션은 `UNMAPPED_SESSION` 등으로 구분합니다. 종목군·달력·정지 상태를 생성하지 않습니다. BAR의 TRADABLE은 관측 체결의 재현용 분류이며 시장 전체 거래 가능 판정을 대신하지 않습니다.

권한·출처·세션 대응은 입력자의 근거 선언이며 도구의 자동 계약 검증이 아닙니다. [가상 설정](../AI/ai-server/examples/replay/conversion.json)의 SYNTHETIC·PERMITTED·R은 테스트용으로 실제 계정에 복사하지 않습니다.

## 실행과 검증

제품 API는 새 백엔드와 025/026 적용 후 사용합니다. 이번 개발에서 운영 적용·실제 GET 다운로드는 하지 않았습니다. 아래는 가상 입력 파일이 준비된 경우이며 실제 자료는 별도의 근거 설정 파일을 지정합니다.

```powershell
# 작업 디렉터리 AI/ai-server
.\.venv\Scripts\python.exe -m app.replay convert-stored --input research-artifacts/export.json --config examples/replay/conversion.json --output research-artifacts/converted
.\.venv\Scripts\python.exe -m app.replay build --spec research-artifacts/converted/spec.json --input research-artifacts/converted/records.jsonl --output research-artifacts/stored-dataset
.\.venv\Scripts\python.exe -m app.replay inspect --dataset research-artifacts/stored-dataset
```

변환 기록이 없으면 명시적 빈 결과이며 build는 EMPTY_DATASET으로 중단합니다. 관측 자료로 과거 종목군을 만들지 않아 결과에 UNIVERSE는 없습니다. 재현에는 별도 검증한 당시 편입/제외 자료가 필요합니다. 실제 다년간 수집·계약/세션 확인·공시 시각/정정 계보·호가 체결 모델은 남습니다.

전용 MySQL 33318·고정 DB/마커/tmpfs에서 원본/버전 보존·손상 해시·상한·동시 커밋 격리를 검증했습니다. 여기서 출력한 가상 파일을 Python 변환→번들 생성→재로드까지 검증하며 `SAGOPALGO_STORED_EXPORT_FIXTURE`로 파일을 지정합니다. 운영 DB·실제 키는 사용하지 않습니다.

엔진은 R5_FOUNDATION_2이며 이전 R5_FOUNDATION_1 번들의 기존 품질 해시/형식을 읽습니다. 전체 검증 수는 [진척도](development-progress.md)를 따릅니다.
