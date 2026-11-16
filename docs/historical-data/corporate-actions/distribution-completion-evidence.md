# 5-08 배당·소각 원문과 취득결과 보고 연결

후속: [삼성전자 외 3개 기업의 실제 기준정보 사례와 5-08 완료 조건](../replay/multi-company-reference-cases.md)을 추가했습니다. 아래 기록은 배당·소각 작업 당시의 검증 결과를 보존합니다.

기준일: 2026-11-03. [기존 원문 사실 추출](corporate-action-facts.md)에 거래소 배당·소각 양식과 명시적으로 연결된 자기주식 취득결과보고서를 추가했습니다. 배당/소각 계획과 회사가 보고한 취득 결과를 구분합니다. 소각 완료·배당 지급 확정은 남아 있으며 고정 체크리스트는 **7/18·39% 유지**, 5-08 진행 중입니다.

## 원문 형식과 대상 검증

공식 [공시서류원본파일 API](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019003)에서 받은 배당/소각 ZIP의 `.xml` 파일에는 실제로 거래소 XForms HTML 표가 들어 있었습니다. 기존 DART XML을 임의로 바꾸지 않고 별도 [distribution_facts.py](../../../AI/ai-server/app/replay/distribution_facts.py)로 분기합니다. 기존 XML 결과와 보관 파일은 유지됩니다.

- 원본 ZIP·공시 목록·법인/종목 해시를 먼저 감사합니다. HTML의 회사/보고서 제목/공시 날짜는 목록과 감사된 기업개황의 이름에 맞아야 합니다. 이름 변경을 임의 추정하지 않습니다.
- 검토한 메인 표 ID와 행 제목·주식 종류·rowspan·셀 수를 확인합니다. 종류주식 상세 표·주석·정정 전후 표를 최종 메인 표와 혼용하지 않습니다. 정정/철회 표시가 있는 새 HTML 양식은 미지원으로 남깁니다.
- HTML은 8 MiB·노드 50,000개·깊이 제한과 닫힘 구조를 검사합니다. script/style은 값으로 읽지 않고, 선언·외부 엔티티를 거절합니다. 링크·스크립트·외부 스키마를 실행하지 않습니다.
- 실제 파일은 UTF-8로 읽을 수 있지만 HTML 메타의 charset은 euc-kr였습니다. 메타 선언만으로 재인코딩하지 않고 검증된 실제 디코딩 방식을 기록합니다. 다른 인코딩이나 모호한 양식은 값을 채우지 않고 오류로 남깁니다.
- 숫자 문자열은 정확한 쉼표·소수점 형식을 검사하고 단위를 보존합니다. 주수는 정수, 배당금/배당률은 지원 정밀도의 소수를 허용하며 반올림하지 않습니다.

## 배당과 소각의 날짜 역할

| 양식 | 이번 추출 | 미확인으로 남기는 범위 |
|---|---|---|
| 현금·현물 배당 결정 중 현금배당 | 주식 종류별 주당 금액·시가배당률·총액, 기준일·지급 예정일·총회 예정일·결정일 | 배당락일·실제 지급일, 미정인 예정일 |
| 주식 소각 결정 | 종류별 소각 예정 수량·보고된 발행주식 수, 주당 가액·예정 금액, 취득 예정 기간·소각 예정일·결정일 | 실제 소각일·변경상장/자본 변경 완료 |

배당기준일이 결정일보다 앞선 실제 사례를 허용하며, 기준일을 배당락일로 바꾸지 않습니다. `-`는 null이며 지급일을 계산해서 만들지 않습니다. 소각의 발행주식 수는 공시된 수치 그대로이고, 차감해서 소각 후 주식 수를 확정하지 않습니다. 기타주식의 종목코드도 보통주에서 추측하지 않습니다.

## 명시적 관련 원문

[related_documents.py](../../../AI/ai-server/app/replay/related_documents.py)는 감사된 소각 원문의 관련공시 행에 있는 링크만 사용합니다. 출처 문서의 회사·제목·날짜·표를 먼저 검증한 후 고정 KIND 호스트/경로·허용 쿼리·DART 접수번호·표시 날짜·보고서 역할을 검사합니다.

거래소의 접수번호 `acptno`와 DART 접수번호 `rcpno`를 구분하고, 원문 요청에는 확인된 `rcpno`만 사용합니다. HTML 링크를 따라 HTTP 요청을 보내지 않고 기존 고정 HTTPS OpenDART 경로로 지정한 원문 1건만 조회합니다. 임의 공시나 다른 호스트는 요청 전에 거절합니다.

원문별 최대 조회 횟수는 1회이며 사전 예약·실패 상태·ZIP 검사·캐시 재검사를 유지합니다. 원문·출처 원문·목록 해시와 명시된 관계를 함께 보관합니다. 목록에 없던 결과보고서를 원래 204건 목록에 소급 삽입하지 않습니다. 관련공시 연결은 정정의 직접 부모 확정과 다른 관계이며 기존 정정 부모 후보 2개는 그대로 남습니다.

## 회사가 보고한 취득 결과 대조

[treasury_outcomes.py](../../../AI/ai-server/app/replay/treasury_outcomes.py)는 검토한 자기주식취득결과보고서 00681/6.0 양식을 해석합니다. 회사 고유번호·보고서 유형·실제 취득 기간을 확인하고, 각 행의 일자·주식 종류·주문수량·취득수량·취득금액·증권사 고유번호를 구분합니다.

- 같은 날 같은 주식 종류의 여러 증권사 내역을 임의로 중복 제거하지 않습니다. 행을 모두 보존하고 종류별로 합산합니다.
- 주문수량을 취득수량으로 사용하지 않습니다. 반올림된 주당 취득가액을 곱해 금액을 다시 만들지 않고 공시된 금액을 합산합니다.
- 행별 취득수량은 주문수량 이하여야 하고 일자는 보고 기간 안이어야 합니다. 수량/금액 합계는 본문의 합계 필드 3개와 일치해야 합니다.
- 명시적 링크가 가리키는 기존 취득 결정·취득 결과·소각 계획을 연결합니다. 실제 보고 기간은 계획 기간 안에 있어야 하며, 종류별 소각 예정 수량 ≤ 보고 취득수량 ≤ 취득 예정 수량을 검사합니다. 계획 금액과 실제 금액을 같다고 강제하지 않습니다.

결과는 `REPORTED_OUTCOME`, `actualAcquisitionReported=true`입니다. 회사의 취득 결과 보고와 합계를 확인한 것이며 소각 완료를 확인한 것은 아닙니다. 소각 계획은 계속 `DECLARED_PLAN`, 대조 결과의 `cancellationCompletionReported=false`입니다. 실제 소각일·개인 계좌 보유 수량·주가 조정을 자동 생성하지 않습니다.

## 실제 결과

| 항목 | 결과 |
|---|---|
| 새 원문 | 배당 20240131800043, 소각 20250218800029, 명시적 링크의 취득결과 20250217001961 |
| 이번 조회 | 원문별 최대 1회 / 각각 GET 1회, 총 3회 |
| 배당 사실 | 수치 5필드·날짜 4필드, 지급/총회 예정일 2개 미정 유지 |
| 소각 사실 | 수치 6필드·날짜 4필드, 취득 예정 기간 2개 미확인 유지 |
| 취득결과 | 내역 110행, 실제 취득 기간·종류별 합계와 본문 합계 3개 일치 |
| 3문서 관계 | 소각의 두 명시적 링크로 기존 취득 결정·취득결과 연결 |
| 주식 종류별 수량 | 보통주/기타주식 모두 계획 취득수량과 보고 취득수량 일치, 소각 계획과 대조 |
| 반영 범위 | 취득 결과 보고 근거 1건 연결, 소각 완료·배당 지급 확정은 미완료 |
| 재검사 | 기존/새 원문·기존 사실·일봉 해시 보존, 통신 금지 재사용/감사 통과 |

모든 새 사실과 대조 결과의 가용 시각은 현재 관측 시각입니다. 과거 시점에서는 보이지 않고 실제 knownAt 이후에만 보입니다. 기존 XML 사실 2건의 식별자/출력도 그대로 재감사했습니다. `automaticEffectAllowed=false`, `effectiveDate=null`, 기준정보 반영 이벤트/주가 조정 0건, 학습 사용 가능 false를 유지합니다.

Git 제외 산출물은 `AI/ai-server/research-artifacts/dart-history-20261103/` 아래 새 `original-20240131800043/`, `original-20250218800029/`, `related-20250217001961/`, 두 `facts-*.json`, `outcome-20250217001961.json`, `treasury-reconciliation.json`입니다. 실제 수량/금액/행별 취득 내역·원문·시세·인증정보는 PR에 넣지 않습니다.

## 실행

```powershell
# AI/ai-server. 배당/소각 원문은 기존 dart_documents capture로 각각 확보합니다.
.\.venv\Scripts\python.exe -m app.replay.corporate_facts extract --index research-artifacts/dart-job --capture research-artifacts/dividend-original --output research-artifacts/dividend-facts.json

# 감사된 소각 원문의 명시적 링크에 있을 때만 아래 결과보고서를 조회할 수 있습니다.
.\.venv\Scripts\python.exe -m app.replay.related_documents capture --index research-artifacts/dart-job --origin research-artifacts/cancellation-original --receipt 20250217001961 --output research-artifacts/acquisition-result
.\.venv\Scripts\python.exe -m app.replay.treasury_outcomes extract --index research-artifacts/dart-job --origin research-artifacts/cancellation-original --capture research-artifacts/acquisition-result --output research-artifacts/outcome.json
.\.venv\Scripts\python.exe -m app.replay.treasury_outcomes reconcile --index research-artifacts/dart-job --origin research-artifacts/cancellation-original --capture research-artifacts/acquisition-result --decision research-artifacts/acquisition-decision --output research-artifacts/reconciliation.json
```

related_documents의 audit, treasury_outcomes의 audit/audit-reconciliation/as-of는 원본을 다시 검사하고 네트워크 없이 실행합니다. output은 새 파일/전용 폴더이며 덮어쓰지 않습니다. 정상 종료값은 0, 입력/결합/파일/조회 오류는 고정 코드와 2입니다.

## 검증·체크리스트

전체 AI 서버 **322건 통과**, 실패·오류·제외 0건(기존 291 + 신규 31)입니다. HTML 회사/제목·표/rowspan·주식 종류·소수/날짜 역할·명시적 링크/접수번호·원문 결합·실패/재사용·취득 행/합계·3문서 수량/기간·과거 시점 조회를 검증했습니다. 기존 Starlette/AnyIO 경고 1건은 유지됩니다.

- [x] 실제 배당·소각 원문 양식과 날짜 역할 지원
- [x] 미정 지급일·취득 기간·배당락일을 만들어 넣지 않음
- [x] 명시적 관련공시 원문을 별도 해시/접수번호로 확보
- [x] 취득결과 110행과 합계·기존 취득 결정/소각 계획 대조
- [x] 기존 사실/원문 보존·현재 관측 시점 조회·무통신 감사
- [ ] 소각 완료일·변경상장 및 실제 배당 지급일/배당락일 근거 확보
- [ ] 분할·합병 등 다른 양식과 명시적 정정 계보·실제 효력 연결
- [ ] 전체 과거 상장/폐지 종목군·달력/세션 확보

다음은 실제 소각 완료/변경상장 및 배당 지급·배당락 근거 연결입니다. 5-08 전체는 미완료이며 모델 학습·실주문·운영 배포·EXE 재빌드는 수행하지 않았습니다.
