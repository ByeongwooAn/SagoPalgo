# SagoPalgo AI Analysis Server

최신 U04: [결제일 기준 비용·세금 팩](../../docs/actual-cost-tax-rules.md)의 `python -m app.replay.cost_rules`를 추가했습니다. 공개 KB 요율과 실제 계좌 프로필을 분리하고 미확인 비용 합계는 null/차단합니다. 반올림은 명시적 연구 시나리오이며 기존 호가 엔진의 가정값을 자동 교체하지 않습니다. 전체 AI 1,271건 통과·실제 징수액 대조는 대기입니다.

U03 후속: [과거 공식 호가 단위·엔진 연결](../../docs/historical-tick-rules.md). `quote-scenario --tick-rules <팩>`은 가격별 단위를 검사하고, 기본 주문 판단 시각보다 나중에 확보한 근거는 차단합니다. 명시적 `--rules-known-at` 사후 대조는 거래/전략 검증과 구분합니다. 전체 1,233건 통과입니다.

최신 후속은 [U02 연구용 입력 수신·시계 연결](../../docs/strategy-input-receipts.md)입니다. `python -m app.replay.input_receipts --base-url http://127.0.0.1:18081 --config tick-config.json --output research-artifacts/새-영수증`으로 명시적 로컬 수신·해시 검증·시계 연결·영수증 게시를 수행합니다. 기존 `app.replay` CLI는 오프라인으로 유지합니다. 실제 123건 수신·프로세스 재시작, 최종 전체 1,196건 통과이며 모델 실행·전역 UTC 판단과 구분합니다.

최신 후속은 [커밋 이후 로컬 입력 공개 시각](../../docs/committed-input-availability.md)입니다. V1/V2 입력 검증, 오프라인 `snapshot-inputs`, 명시적 `INPUT_PUBLICATION_OBSERVED` 호가 모드를 추가했습니다. 같은 JVM 도메인의 안정 관측만 사용하며 UTC 동기화·실제 AI 수신과 구분합니다. 전체 회귀 1,164건 통과입니다. [다음/잔여 실행 단위](../../docs/remaining-development-units.md)를 따릅니다.

[세션·시각 품질·호가 체결 추정](../../docs/quote-execution-quality.md)은 `profile-ticks`·`quote-scenario` CLI입니다. 공식 코드 0은 장중 의미만 연결하고 추정 날짜/가용 시각을 승격하지 않습니다. 기본 가용 시각 모드는 보류하며, 명시적 연구 가정에서 시장가·지정가 IOC/자원/잔량·비용 가정과 기존 장중 제한을 검사합니다. 실제 고유 이벤트 1,199개·호가 가정 프로브 28개, 전체 AI 1,150개 테스트 통과이며 독립 비용·계좌 체결과 장기 운영은 남습니다.

[실제 틱 수집 장애 복구](../../docs/public-tick-collection-recovery.md)에서 025/026 적용 후 체결 946·호가 135행을 확보해 기존 `audit-ticks`로 입력 대조했습니다. 실제 원문은 Git 제외 경로에 보존하며 세션 코드·시각 품질·실제 주문 체결 검증은 남습니다. 운영 공개 저장소 점검은 루트 `scripts/check_public_tick_readiness.py`입니다.

[틱 입력·실제 기준 자료 대조](../../docs/tick-reference-validation.md)는 `python -m app.replay audit-ticks`와 `python -m app.replay.daily_reference`로 실행합니다. 원본/해시·추정 날짜·수신/가용 시각·중복/누락을 구분하며 공개 체결 일치를 계좌 체결 증명으로 표시하지 않습니다. 실제 KIS 730일 재감사·KRX 1일 OHLCV 대조와 합성 4행 감사를 분리하며, 실제 틱/호가 확보는 남습니다.

[장중 거래구간·재현 엔진 연결](../../docs/intraday-session-replay.md)은 `app.replay.intraday` build/audit와 `app.replay replay --intraday-timeline --timeline-sha256 --market --order-class`로 실행합니다. CB 17쌍·프로그램 정지 100개를 제한 구간 134개로 연결하고 당시 미확인·부분 근거 및 단일가 체결을 보류합니다. 명시적 적용 보고서는 R5_FOUNDATION_3, 기존 무타임라인 보고서는 바이트를 보존합니다. [Windows 게시 복구](../../docs/windows-file-publication.md)로 일지/JSONL/준비 폴더의 잠금 복구를 통일했으며 전체 **1,079건 통과·실패/오류/제외 0건**입니다. 과거 실패 로그는 보존합니다.

[추가 양식·발표 경계·정정과 세션 판단](../../docs/session-coverage-boundary-review.md)은 `app.replay.session_coverage_review`의 plan/extend/collect/build/audit/review/audit-review/decide/audit-decision/as-of로 실행합니다. 170개 검색·176페이지·고유 본문 235개, CB 18쌍과 원본/정정 본문 차이를 대조합니다. 1,448개 일반 후보에 날짜별 규정·보류 사유를 기록하고 기존 ReferencePack은 보존합니다. 검토 명세는 `session-boundary-review.json`, `session-category-review.json`이며 전체 회귀 1,018건 통과입니다.

[임시 거래시간 변경 공지 목록·본문 검토](../../docs/session-exception-notice-inventory.md)는 `app.replay.session_notice_inventory`의 plan/extend/collect/status/build/audit와 `app.replay.session_notice_review`의 build/audit/as-of로 실행합니다. 16개 검색·40페이지·공시 2,622건·본문 75개를 검토하고 기존 특수 세션 12개를 대조했습니다. 검토 명세는 `docs/examples/session-notice-review.json`입니다. 8개 구간의 선택 범위 검토이며 전체 공지/정정 계보 완성은 아닙니다. 일반 후보 1,448개와 기존 ReferencePack을 보존합니다. 회귀 984건 통과, 상세 재현·예산·한계는 연결 문서를 따릅니다.

[코스닥 과거 전문·위임 시행일과 규정 V2](../../docs/kosdaq-rule-effective-evidence.md)는 `app.replay.rule_effective_evidence`의 capture/build/audit/as-of로 실행합니다. `docs/examples/kosdaq-rule-effective-evidence.json`에 V1 해시·세 원문 식별을 고정하고 과거 전문과 위임 부칙을 연결합니다. 제2280호의 2025-03-04 시행일·15/15개 규정 연결을 확인하되 이전 불일치·자리표시자와 실제 세션 미확인 상태를 보존합니다. 임시 변경 검토 8구간은 대기 상태입니다.

[과거 일반 정규장 규정 판본 검증](../../docs/historical-ordinary-session-rules.md)은 `app.replay.historical_session_rules`의 capture/build/audit/as-of로 실행합니다. `docs/examples/historical-session-rules.json`에 판본과 이전 달력 해시를 고정합니다. 15개 중 14개 일치·코스닥 제53차 본문 불일치 1건을 보존하며, KOSPI 규정 7구간 확인과 실제 세션 확정을 구분합니다. 일반 후보는 실제 세션에서 계속 제외합니다.

[전체 기간 달력·시장별 특수 세션](../../docs/market-calendar-session-coverage.md)은 `app.replay.krx_calendar_sources`의 plan/collect/audit와 `app.replay.market_calendar_evidence`의 capture/build/audit/as-of로 실행합니다. 검토 출처는 `docs/examples/market-calendar-sources.json`입니다. 두 시장의 1,098일 개장 여부를 재구성하고 시장별 특수 세션 6일을 확인하며, 일반 시간 후보 724일씩과 미확인 플래그를 유지합니다. 기존 V7·가격·원문은 보존하며 아래는 당시 기록입니다.

[남은 이름·약명 3건과 V4 원장](../../docs/name-alias-evidence.md)은 `app.replay.name_alias_evidence`의 plan/collect/audit, `app.replay.name_alias_facts`의 약명/양언어 필드 대조, `app.replay.name_alias_reconciliation`의 build/audit/as-of로 실행합니다. V3와 고정 사례 설정을 감사하고 미해결 이름 관찰 3건만 보강합니다. 이름 관찰 291건의 설명/대조 완료와 전체 법적 사건/개별 공시 완전성을 구분합니다. 아래 V3 후속 수치는 해당 작업 당시 기록입니다.

[이름 변경 관찰 검토와 V3 원장](../../docs/name-change-evidence.md)은 `app.replay.name_disclosures`의 plan/collect/audit, `app.replay.name_facts`의 검토 양식 추출과 `app.replay.name_reconciliation`의 build/audit/as-of로 실행합니다. 관찰 291건 중 공시 일치 285건·이전상장 표기 변화 3건·추가 검토 3건을 구분하며 정식명/명시된 약명·거래소 적용일·현재 확보 시점을 보존합니다.

[미해결 57건의 개별 공시 확인과 V2 원장](../../docs/unresolved-membership-evidence.md)은 `app.replay.kind_membership_evidence`의 plan/collect/audit, `app.replay.membership_corrections`의 plan/collect/audit, `app.replay.membership_reconciliation`의 build/audit/as-of로 실행합니다. `app.replay.membership_evidence_facts`가 검토 양식의 사실을 추출합니다. 기존 원장을 보존하고 전체 코드·KDR 문맥·정정 전후를 대조하며 현황 일치와 개별 공시 확인을 구분합니다.

[KIND 현황·공시 대조 원장](../../docs/universe-event-reconciliation.md)은 `app.replay.kind_membership_status`의 plan/capture/audit와 `app.replay.universe_reconciliation`의 build/audit/as-of로 실행합니다. 전체 관찰을 공식 현황·공시와 대조하고 식별 관계·날짜·근거 누락을 구분하며 기존 관찰과 과거 정보 시점을 보존합니다.

[KRX 기간 전체 종목 목록·관찰 변화 수집](../../docs/krx-universe-history.md)은 `app.replay.krx_universe_history`의 plan/status/collect/build/audit/as-of/check-events로 실행합니다. 일별 원문·호출 예산·중단 재개·사건 경계 대조를 관리하며 거래일 달력·전체 기업행사·학습 가능 여부는 별도로 검증합니다.

[KRX 실제 시작일 기준표·매매정보 교차 검증](../../docs/krx-baseline-live-validation.md)에서 2023-11-01 두 시장 2,634행·보통주 2,517개를 확보했습니다. `app.replay.krx_baseline_validation`은 원본 V1을 보존하는 V2 분류·일별매매 대조를 실행하며 전체 기간 확보 상태와 구분합니다.

[KRX 과거 기준일 종목군 수집](../../docs/krx-historical-universe.md)은 `python -m app.replay.krx_universe`의 plan/status/collect/audit/check로 실행합니다. KRX 인증키와 유가증권/코스닥 종목기본정보 이용 승인 후 명시적으로 수집하며 샘플과 실제 기준표 확보를 구분합니다.

[이전상장·합병 폐지와 종목군 식별 목록](../../docs/historical-universe-seed.md)은 `app.replay.universe_events`와 `app.replay.kind_registry`로 실행합니다. 시장별 편입/제외를 구분하고 현재 법인 목록·과거 사례를 연결하며 현재 명단을 과거 전체 종목군으로 소급하지 않습니다.

[여러 기업의 실제 기준정보 사례](../../docs/multi-company-reference-cases.md)는 `python -m app.replay.kind_cases`의 capture/build/audit/as-of로 실행합니다. 신규상장·폐지·분할·정지/해제 5개 대표 사례를 원문과 연결하며, 5-08 전체 완료 조건과 시장·기간 누락을 별도로 관리합니다.

[배당·소각 및 취득결과 연결](../../docs/distribution-completion-evidence.md)은 거래소 HTML 원문을 지원합니다. 관련공시 원문은 `app.replay.related_documents`, 취득 결과/합계·계획 대조는 `app.replay.treasury_outcomes`로 실행하며 취득 보고와 실제 소각 완료를 구분합니다.

[공시 원문 사실 추출](../../docs/corporate-action-facts.md)은 `python -m app.replay.corporate_facts`로 실행합니다. 자기주식 취득·해외 상장폐지의 예정 날짜/수량/금액과 정정 전후를 원본에 연결하고 실제 완료·가격 조정과 구분합니다.

[OpenDART 과거 기업·공시 이력](../../docs/dart-historical-disclosures.md)은 `python -m app.replay.dart_history`로 일봉에 연결한 계획·제한 수집·감사를 실행합니다. 선택 원문은 `python -m app.replay.dart_documents`로 확보하며 현재 법인 연결·검토 후보와 실제 상장/기업행사 효력을 구분합니다.

개인용 이용 범위·캘린더/세션/상장/기업행사 대조는 [기준정보 검증](../../docs/historical-reference-validation.md)의 `python -m app.replay.reference_cli`로 실행합니다. 기존 수집 기록을 바꾸지 않고 새 범위를 자료 해시에 연결하며, 모르는 달력/이력을 생성하지 않습니다.

실제 특수 거래시간은 [KIND 공지 확보·시장별 대조](../../docs/historical-session-evidence.md)의 `session-fetch`와 `check --market`으로 검사합니다. 코스피/코스닥/코넥스 세션과 현재 확보 시각을 구분합니다.

[KB 공식 연말·연초 공지](../../docs/kb-historical-market-evidence.md)는 `kb-notice-capture`로 확보하고 `kb-notice-import`로 오프라인 변환합니다. 기본 현재 관측과 선택적 공급자 공개 시각 가정, 달력의 미확인 플래그를 구분합니다.

과거 원주가 수집은 별도 [KIS 수집 도구](../../docs/historical-price-acquisition.md)의 `python -m app.replay.history`를 사용합니다. plan/audit는 오프라인이며 collect만 제한된 인증·공개 시세 조회를 수행합니다. 실제 데이터의 학습 활용권·날짜 정밀도·가격 기준을 구분합니다.

R2/R3 저장 자료는 [읽기 전용 내보내기·변환](../../docs/stored-dataset-export.md)의 `convert-stored`로 연결합니다. 원본·제외 사유를 보존하며 기본 가용 시각과 선택적 수신 기반 추정을 구분합니다.

과거 자료 연구용 오프라인 도구는 [R5 데이터셋·시점 재현 문서](../../docs/historical-data-replay.md)를 따릅니다. `python -m app.replay --help`로 버전 데이터셋·시점 조회·명시적 주문안의 비용 추정·시간 구간 분리를 실행합니다. 기존 분석 API와 분리되어 있으며 실제 계좌·자동 주문·학습 모델을 활성화하지 않습니다. [가상 예제](examples/replay)는 실측 시세/성과가 아닙니다.

가격 추세, 뉴스 핵심어, 공시 사건 유형과 보유 종목의 손익·매입 원금 비중 신호를 조합해 설명 가능한 투자 참고 점수를 만드는 로컬 FastAPI 서비스입니다. `analysisType=WATCHLIST`에서는 보유 손익·비중 신호를 사용하지 않습니다. 외부 생성형 AI나 유료 API를 호출하지 않으며 주문을 실행하지 않습니다.

## 로컬 실행

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

상태 확인:

```powershell
Invoke-RestMethod -Uri 'http://localhost:8000/health'
```

테스트:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Spring Boot는 `POST /internal/ai/analyze-investment`를 호출합니다. 모델 버전 `WEIGHTED_SIGNAL_V1`과 추천 유형, 상태, 0~100 점수, 요약, 개별 점수 근거를 반환합니다.

관심 종목 분석은 `analysisType=WATCHLIST`와 실제 현재가를 보내고, 매수가·수익률·손절·익절 필드는 생략하거나 `null`로 둡니다. 기본 `HOLDING` 분석은 해당 보유 손익 필드를 모두 요구합니다. 관심 종목의 낮은 점수는 보유 주식 매도가 아니라 신규 진입 보류로 해석합니다.

보유 종목 요청의 선택적 `portfolioWeightRate`, `capitalWeightRate`, `maxCapitalWeightRate`는 Spring이 동일 종목의 여러 보유 건을 합산한 **매입 원금 기준**으로 계산합니다. 자본금 미설정 시 한도 판정은 하지 않습니다. 설정 자본금 대비 원금 비중이 권장 한도를 넘으면 신규 매수만 보류하며, 손절·익절 신호는 우선합니다. 실계좌 평가 비중이나 주문 가능 금액을 뜻하지 않습니다.
