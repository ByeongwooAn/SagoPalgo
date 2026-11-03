# SagoPalgo AI Analysis Server

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
