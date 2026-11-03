# 5-08 실제 거래시간 공지 확보와 시장별 대조

기준일: 2026-11-03. [이전 기준정보 검증](historical-reference-validation.md) 다음 작업입니다. KIND 공개 공지 원문에서 실제 특수 거래시간을 추출하고 시장·확보 시각을 검사하는 경로를 추가했습니다. 고정 체크리스트는 **7/18·39% 유지**, 5-08은 진행 중입니다.

## 구현한 동작

[session_evidence.py](../AI/ai-server/app/replay/session_evidence.py)의 `session-fetch`는 지정한 한국거래소 KIND 공개 문서 1건을 GET으로 확보합니다. 인증·계좌·시세를 전송하지 않습니다.

- HTTPS의 `kind.krx.co.kr/external/.../...htm` 형식만 허용합니다. 다른 호스트·쿼리·경로 이동과 HTTP 리디렉션을 허용하지 않습니다.
- URL별 로컬 예약을 먼저 만들고 GET 1회, 20초 제한, 본문 512 KiB 제한을 적용합니다. 본문/영수증/파생 팩의 해시를 보존합니다.
- 완료된 캐시는 원문과 파생 팩을 재검사해 반환합니다. 실패·미해결 예약은 자동 재시도하지 않습니다. 페이지 목록 탐색이나 다른 URL의 자동 수집은 하지 않습니다.
- UTF-8/CP949 HTML에서 script/style을 제외하고 검토한 수능일·연초 개장일 양식만 해석합니다. 시장·시행일·정규장 시간 후보가 모호하거나 양식이 달라지면 고정 오류로 종료합니다.
- 수능일은 변경 전/후를 구분해 변경 후 정규장만 추출합니다. 연초는 공지에 적힌 개장·폐장 시각을 사용합니다. 시간외 거래·주말·일반 거래시간을 임의로 채우지 않습니다.
- `coverage`는 빈 목록입니다. 공지 1건으로 전체 기간 세션이나 휴장일 달력의 완전성을 선언하지 않습니다. 기업행사·과거 종목군도 생성하지 않습니다.

같은 URL은 이 캐시에서 하나의 불변 스냅샷입니다. 정정된 공지의 새 버전 수집·계보 관리나 전역 호출 예산 관리까지 구현한 것은 아닙니다.

## 시장과 시점 구분

[reference.py](../AI/ai-server/app/replay/reference.py)의 Session에 `market=KOSPI/KOSDAQ/KONEX/UNSPECIFIED`를 추가했습니다. 기존 파일의 생략값은 UNSPECIFIED로 유지합니다. 세션 식별자는 `(시장, 날짜)`이며 같은 시장·날짜의 상충 내용은 거절하고 다른 시장의 같은 날짜는 함께 보관합니다.

`check --market KOSPI`는 KOSPI 세션만 대조합니다. UNSPECIFIED나 다른 시장의 세션을 대체값으로 사용하지 않습니다. 세션 COMPLETE 선언도 해당 팩에 실제로 있는 대상 시장 날짜와 달력에서 휴장으로 확인된 날짜로 제한합니다. 미확인 날짜는 휴장으로 간주하지 않습니다. 달력이 아직 없는 날짜의 일봉도 `PRICE_SESSION_MISSING`으로 별도 집계합니다.

시장 인자는 검사 대상에 대한 호출자의 선언이며, 티커의 시장 이력을 독립 입증하지 않습니다. 보고서의 `sessionMarketBasis=CALLER_DECLARED`로 이를 표시합니다. 실제 자료에서 시장을 생략하면 `SESSION_MARKET_UNSPECIFIED`를 남겨 전체 기준정보 완료로 판정하지 않습니다. 과거 시장 이동·상장 이력 검증은 남아 있습니다.

이번 공지에는 검증된 과거 공개 시각이 없으므로 `knownAt=현재 capturedAt`, `knowledgeBasis=FETCH_TIME_ONLY`입니다. URL의 날짜나 문서에 적힌 시행일을 과거 공개 시각으로 바꾸지 않습니다. 과거 장 마감 시점 조회에서는 해당 세션이 보이지 않으며, 확보 시각 이후 같은 시장 조회에서만 보입니다. 과거 의사결정 재현에 쓰려면 당시 공개 시각/보존본 근거를 추가 확보해야 합니다.

## 실제 확보·검증 결과

다음 공식 공지를 각각 1회 읽었습니다. 원문은 Git 제외 로컬 저장소에만 보관합니다.

| 공식 근거 | 시장 | 적용일 | 정규장, 한국 시각 |
|---|---|---|---|
| [2023 수능일 안내](https://kind.krx.co.kr/external/2023/11/02/000075/20231101001384/70780.htm) | KOSDAQ | 2023-11-16 | 10:00~16:30 |
| [2024 수능일 안내](https://kind.krx.co.kr/external/2024/10/31/000080/20241031000019/32104.htm) | KONEX | 2024-11-14 | 10:00~16:30 |
| [2025 연초 개장 안내](https://kind.krx.co.kr/external/2024/12/17/000103/20241217000184/32104.htm) | KONEX | 2025-01-02 | 10:00~15:30 |

- 공개 문서 GET 총 3회입니다. 이후 캐시 검증은 네트워크를 호출하면 실패하도록 주입한 클라이언트로 3건 모두 성공했습니다. KIS 달력은 추가 호출하지 않았습니다.
- 기존 KIS 달력 원문/파생 해시도 오프라인에서 재확인했습니다. 기존 730건 일봉의 해시는 이전 보고서와 일치합니다.
- 기존 삼성전자 일봉 검사에 `--market KOSPI`를 선언해 실행한 결과, 위 세션 **3건 모두 제외**, 일치하는 세션 0건입니다. 다른 시장 자료로 미확보 세션을 채우지 않았습니다.
- 달력은 기존 24일·개장일 18일을 유지하며 확인된 개장일의 가격 불일치 0건입니다. 전체 1,098일 중 미확인 달력 1,074일, 가격에 대응하는 KOSPI 세션 미확보 730일을 그대로 표시합니다.
- 최종 상태는 `REFERENCE_GAPS`입니다. 학습·전략 검증·거래 사용 가능 표시는 모두 false를 유지합니다.

로컬 산출물: `AI/ai-server/research-artifacts/kind-session-cache/<URL 해시>/{body.html,receipt.json,reference.json}`, `AI/ai-server/research-artifacts/kis-daily-live-20261103-130145/reference-check-scoped-sessions-final.json`. 실제 공지 원문·개인 설정·시세는 PR에 포함하지 않습니다.

## 실행 예시

```powershell
# AI/ai-server에서 실행. 해당 공지 1건만 읽고 같은 URL은 캐시를 검증합니다.
.\.venv\Scripts\python.exe -m app.replay.reference_cli session-fetch --url https://kind.krx.co.kr/external/2023/11/02/000075/20231101001384/70780.htm --cache research-artifacts/kind-session-cache

# 오프라인 대조. 파일은 실제 확보한 경로를 지정하고 출력 파일은 새 이름으로 만듭니다.
.\.venv\Scripts\python.exe -m app.replay.reference_cli check --job research-artifacts/history-job --local-use research-artifacts/local-use.json --reference research-artifacts/calendar-reference.json research-artifacts/session-reference.json --market KOSPI --output research-artifacts/scoped-check.json
```

입력/파일/수집 오류는 종료값 2, 기준정보 부족은 1, 정상 확보/검사는 0입니다. 기존 수집 원본과 보고서를 덮어쓰지 않습니다. Python의 `references_as_of(..., market="KOSDAQ")`도 같은 시장/시각 필터를 사용합니다.

## 테스트와 다음 체크리스트

AI 서버 전체 **193건 통과**, 실패·오류·제외 0건입니다. 기존 163건에 신규 30건을 추가했습니다. 변경 전/후·연초 폐장 시각·문자 인코딩·모호한 날짜/시장/시각·URL·크기 제한·실패 예약·캐시 변조·시장별 식별·과거 시점 제외·휴장 근거와 COMPLETE 선언 제한·CLI를 검사했습니다. 기존 Starlette/AnyIO 경고 1건은 유지됩니다.

초기 테스트에서 샌드박스 임시 폴더 권한과 대용량 매개변수 식별자의 Windows 파일명 제한으로 실행 오류가 있었습니다. 정상 임시 폴더 권한으로 재실행하고 명시적 짧은 테스트 식별자를 적용한 최종 전체 결과가 위 193건입니다.

- [x] 공식 특수 거래시간 원문 확보·해시·캐시 재검사
- [x] 변경 전/후와 정규장/시간외 구분
- [x] 시장별 세션 분리와 실제 다른 시장 자료 제외
- [x] 확보 시각과 과거 공개 시각 구분·과거 조회 제외
- [ ] 대상 시장의 전체 기간 달력·일반/특수 세션과 당시 공개 근거 확보
- [ ] 실제 과거 상장/폐지·시장 이동 종목군과 기업행사 확보/대조

고정 항목 5-08 전체는 마지막 두 항목까지 확인한 후 완료 처리합니다. 이후 5-09 실제 체결/비용 대조, 5-10 후보 탐색, 5-11 특징/목표, 5-12 학습/평가 순서로 연결합니다. 이번 작업은 연구 코드와 문서이며 운영 배포·모델 학습·자동 주문·EXE 재빌드는 수행하지 않았습니다.
