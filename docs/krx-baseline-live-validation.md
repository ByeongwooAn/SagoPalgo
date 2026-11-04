# KRX 2023년 11월 1일 실제 종목군 기준표 검증

후속: [기간 전체 일별 목록·관찰 변화 이력](krx-universe-history.md)에서 이 시작일 자료를 재사용해 1,098개 날짜·두 시장으로 확장했습니다. 아래 시작일 검증 기록과 원본 V1/V2 해시는 유지합니다.

기준일: 2026-11-04. 사용자가 유가증권/코스닥 종목기본정보와 일별매매정보 4개 API 승인 화면 및 로컬 키 등록을 제공해 [승인 대기 중이던 기준일 수집](krx-historical-universe.md)을 재개했습니다. **시작 날짜 2023-11-01의 두 시장 기준표를 실제 확보**하고 다른 API·기존 공시와 대조했습니다. 전체 목표 기간의 일별 종목군 확보는 후속입니다.

## 확보 결과

| 시장 | 기준정보 원문 행 | 보통주 | 다른 종류 주식 | 거래량 0 보통주 |
|---|---:|---:|---:|---:|
| KOSPI | 952 | 838 | 114 | 17 |
| KOSDAQ | 1,682 | 1,679 | 3 | 66 |
| 합계 | **2,634** | **2,517** | **117** | **83** |

모두 `basDd=20231101`의 운영 API 응답입니다. 기존 공식 샘플 20행과 현재 법인 식별 목록 2,658개를 실제 기준표에 합산하지 않습니다. 숫자/영문 코드·선행 0·ISIN·시장·상장일·증권/주식 종류·현재 수집 시각과 원문 해시를 보존합니다. 기존 원주가 730건·삼성전자 공시 204건의 수집 범위를 늘린 것으로 계산하지 않습니다.

운영 조회는 기본정보 2회(시장별 1회)와 일별매매정보 2회(시장별 1회), **총 4회**입니다. 각각 별도 수집 계획의 2회 예산 안에서 완료했습니다. 캐시 감사·보완 분류·공시/일별매매 대조·재실행에는 추가 호출이 없었습니다. 키·계좌정보는 출력/저장하지 않았고 원문·보고서는 Git 제외 경로에 보관했습니다.

## 실제 응답의 분류 보완과 원본 보존

최초 V1 파서는 샘플에 없던 세 유형 때문에 95행을 미검토로 남겼습니다. 이를 원문 값에 따라 보완했습니다.

| 원문 값 | 건수 | V2 처리 |
|---|---:|---|
| 주권 / 구형우선주 | 81 | 다른 종류 주식 |
| 주권 / 종류주권 | 13 | 다른 종류 주식 |
| 선박투자회사 / 보통주 | 1 | 보통주 |

최종 미검토는 0건입니다. 기존 V1 원문·수신 영수증·보고서·파서 기본 동작은 보존합니다. `reviewed-v2.json`에는 `KRX_COMMON_SHARE_CLASSIFICATION_2`, 원본 보고서 해시, 변경된 95개 코드/분류를 기록합니다. 원본 V1의 미검토 95건을 덮어쓰거나 기존 해시를 바꾸지 않았습니다. 알 수 없는 다른 유형이 나오면 계속 미검토로 남습니다.

## 공시와 대조

감사한 [기존 대표 사례](multi-company-reference-cases.md)와 [이전상장·합병 사유 폐지](historical-universe-seed.md)의 대조 **5/5 통과**, 불일치/대기 0건입니다.

| 항목 | 실제 결과 |
|---|---|
| M83는 당시 신규상장 전 | KOSDAQ 목록에 없음 |
| 유진스팩7호는 당시 상장 중·이후 폐지 | KOSDAQ 보통주에 있음 |
| 엘앤에프는 이전상장 전 KOSDAQ 소속 | KOSDAQ 보통주에 있음 |
| 같은 엘앤에프의 KOSPI 편입은 이후 | KOSPI 목록에 없음 |
| 한국스팩11호는 합병 사유 폐지 전 | KOSDAQ 보통주에 있음 |

이후에 확보한 공시로 과거 응답을 사후 대조한 결과입니다. 공시가 과거 전략 시점에 알려져 있었다고 간주하지 않습니다. `knownAt`은 실제 현재 수신 시각입니다.

## 일별매매정보 교차 대조

공식 [유가증권 일별매매정보](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=JvJFzlAENzZlPBDNGAWC), [코스닥 일별매매정보](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=hZjGpkllgCBCWqeTsYFj)의 명세를 확인하고 같은 기준일을 조회했습니다. 수집기는 기존 키/권한 검사·고정 HTTPS 주소·헤더 인증·응답 제한을 재사용합니다. 각각 `stk_bydd_trd`, `ksq_bydd_trd`이며 다른 날짜를 응답하면 거부합니다. KOSDAQ GLOBAL 표기는 KOSDAQ 시장으로 연결하되 원래 표기도 보존합니다.

- 일별매매 응답도 KOSPI 952/KOSDAQ 1,682행으로 **기준정보와 전체 코드 집합 일치**
- 기준정보에만 있거나 매매정보에만 있는 코드 **0개**
- 코드별 상장주식수 불일치 **0건**
- 거래량 0인 보통주 **83개 유지**, 양수 거래량 조건으로 종목군을 구성하지 않음
- 원문 4개 모두 해시 감사 통과, 실제 날짜·시장·중복 검사 통과

`CROSS_ENDPOINT_MATCH`, `crossEndpointTotalsVerified=true`입니다. 이는 **같은 KRX 공급자의 서로 다른 API 간 대조**입니다. 별도 독립 자료로 절대 총수를 증명하거나 거래량 0을 모두 거래정지로 판정한 결과가 아닙니다. `sameProviderCrossCheck=true`, `independentTotalVerified=false`, `tradingHaltCoverageVerified=false`를 구분해 보존합니다. 모든 정지 공시·변경 이력의 완전성 검증은 남습니다.

## 재실행과 파일

`AI/ai-server`에서 실행합니다. 다음 명령은 이미 받은 캐시를 읽습니다. 기본정보 `collect`도 완성된 같은 작업을 다시 읽으면 키·네트워크 없이 결과를 재사용합니다.

```powershell
# 원본 V1 감사: 원문과 기존 보고서 불변 확인
.\.venv\Scripts\python.exe -m app.replay.krx_universe audit --job research-artifacts/krx-universe-20231101-20261104/job

# V2 보완 분류 재계산/감사
.\.venv\Scripts\python.exe -m app.replay.krx_baseline_validation audit-review --job research-artifacts/krx-universe-20231101-20261104/job --output research-artifacts/krx-universe-20231101-20261104/reviewed-v2.json

# 다른 API와 코드/상장주식수 대조 재현
.\.venv\Scripts\python.exe -m app.replay.krx_baseline_validation reconcile `
  --job research-artifacts/krx-universe-20231101-20261104/job `
  --reviewed research-artifacts/krx-universe-20231101-20261104/reviewed-v2.json `
  --daily research-artifacts/krx-daily-check-20231101-20261104 `
  --output research-artifacts/krx-universe-20231101-20261104/daily-reconciliation.json
```

최초 V2 생성은 `review --job <기본정보 작업> --output <새 결과>`이며 일별매매 최초 수집은 `capture-daily --job <기본정보 작업> --output <새 캐시> --env-file ../../.env`입니다. 일별매매 수집 계획도 기준정보의 날짜·출처·원본 보고서 해시에 묶이고 요청 예산 2회입니다. 실패/중단 예약은 자동 재시도하지 않습니다. 이미 받은 원문이 잘못됐거나 형식이 달라졌으면 캐시를 보존하고 오프라인으로 진단합니다.

기존 `krx_universe check` 명령에 `--reviewed research-artifacts/krx-universe-20231101-20261104/reviewed-v2.json`을 추가하면 V2를 감사한 뒤 공시와 대조합니다. 기존 `comparison-collected.json`은 V1 결과를 보존하며 V2는 `comparison-reviewed-v2.json`에 별도 저장했습니다. 실제 상태 조회는 운영 응답을 확인한 시장만 `serviceAccessObservedByMarket=true`로 표시하고, 가상 데이터로 서비스 승인 상태를 확인한 척하지 않습니다.

## 검증과 체크리스트

- [x] 사용자 4개 API 승인·로컬 키 등록 확인, 실제 기본정보/매매정보 호출 성공
- [x] 시작 날짜 두 시장 원문 2,634행·보통주 2,517개 확보
- [x] 분류 보완 95행·미검토 0건, 원본 V1과 별도 V2 해시 보존
- [x] 과거 신규상장/폐지/이전상장 대조 5/5 통과
- [x] 매매정보와 코드·상장주식수 불일치 0건, 거래량 0 보통주 83개 보존
- [x] 전체 AI 서버 **442건 통과, 실패/오류/건너뛰기 0건**(기존 423 + 신규 19), 기존 Starlette/AnyIO 경고 1건 유지. Java 저장 내보내기 fixture 포함
- [x] 실제 자료를 추가 통신 금지 상태로 재감사, 기존 가격/DART 파일 55개와 모든 수집 원문/영수증/원본 보고서 해시 유지
- [ ] 2023-11-01~2026-11-02 기간 전체의 일별 종목군과 상장/폐지/이전상장 이력 연결
- [ ] 별도 총수 자료·정지 상태/정정 계보·전체 세션/달력 완전성 검증
- [ ] 실제 호가/체결·가격 재현·특징/학습·실시간 판단 연결

**시작 날짜 기준표 확보는 완료**했습니다. 전체 5-08은 기간 전체 이력·달력/세션·기업행사가 남아 진행 중이며 고정 완료율 **7/18·39%를 유지**합니다. 다음 작업은 이 기준표를 바탕으로 기간 전체의 종목 편입/제외 변화를 수집·연결하는 것입니다. 이번 보고서의 `marketUniverseComplete`, `usableForTraining`, `usableForTrading`는 계속 false이며 자동 학습·실주문·운영 배포·DB·EXE 변경은 없습니다.
