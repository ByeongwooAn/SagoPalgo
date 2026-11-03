# 5-08 KB 공식 공지의 대상 시장 세션·달력 연결

기준일: 2026-11-03. [시장별 특수 세션 검사](historical-session-evidence.md)의 다음 작업입니다. 이전 공지 3건은 KOSDAQ/KONEX 대상이었으며 기존 삼성전자 KOSPI 검사에서 모두 제외했습니다. 이번에는 KB 공식 [2025년 개장 공지](https://www.kbsec.com/go.able?idt=20241226&linkcd=s060901010000&seq=10007903)와 [2026년 개장 공지](https://www.kbsec.com/go.able?idt=20251222&linkcd=s060901010000&seq=10009341)를 확보해 KOSPI 거래시간과 명시된 개장/휴장 날짜를 연결했습니다. 5-08 전체는 진행 중이며 **7/18·39%**를 유지합니다.

후속: [OpenDART 실제 과거 공시 204건·선택 원문 1건](dart-historical-disclosures.md)을 확보했습니다. 현재 법인 연결과 해외 대상 표시·검토 후보를 구분하며 전체 상장/기업행사 효력 완료는 남습니다. 아래 229건은 당시 결과이며 최신 전체 검증은 266건입니다.

## 공개 원문 확보와 오프라인 변환

[kb_market_evidence.py](../AI/ai-server/app/replay/kb_market_evidence.py)에 다음 두 명령을 추가했습니다.

- `kb-notice-capture`: 공식 `https://www.kbsec.com/go.able` 공지의 날짜/목록/게시물 식별자만 허용합니다. 계좌·토큰 등 다른 쿼리, 다른 호스트, HTTP와 리디렉션은 거절합니다. GET 1회·20초·1 MiB 제한, URL 정규화, 사전 예약, 원문/영수증/해시 보관과 캐시 재검사를 수행합니다. 실패 예약은 자동 재시도하지 않습니다.
- `kb-notice-import`: 저장된 원문의 해시를 확인하고 검토한 연말·연초 양식만 변환합니다. 변환은 네트워크 없이 실행되며 결과를 덮어쓰지 않습니다. 파싱에 실패해도 성공한 원본 확보 이력은 보존하므로 오프라인 진단이 가능합니다.

공지의 유가증권/코스닥/코넥스 대상 구간과 변경 전후 표를 확인한 후 지정한 시장의 변경 후 정규장만 출력합니다. 2026년 양식은 KRX/NXT 구간과 거래시간/주문접수시간 열을 추가로 분리합니다. 파생상품·시간외·소수점 주문 회차·NXT 시간·주문접수시간을 KRX 정규장으로 사용하지 않습니다. 등록일·URL 날짜·연도·폐장/개장 순서·시각이나 표 경계가 모호하면 변환을 거절합니다.

인증·계좌 API·시세 전송은 없으며 KIS 달력은 추가 호출하지 않았습니다. 등록 시각과 현재 원문은 KB가 제공하는 공지 근거이며 독립된 당시 웹 보존본을 확보했다는 뜻은 아닙니다.

## 현재 관측과 공급자 공개 시각 가정

2025년 개장 공지는 등록일 `2024-12-26 13:44:42`, 2026년 개장 공지는 `2025-12-22 16:02:05`를 표시합니다(한국 시각). 현재 확보 시각과 별도 보존하고 두 방식의 결과를 비교했습니다.

| availability | knownAt | 용도/표시 |
|---|---|---|
| OBSERVED_AT, 기본값 | 실제 현재 확보 시각 | 과거 시점에서는 해당 세션이 보이지 않음 |
| PROVIDER_PUBLICATION_ASSUMED, 명시 옵션 | KB가 표시한 등록 시각, 한국 시각 | 공급자 등록 시각을 당시 공개 가능 시점으로 가정한 연구용 비교 |

두 방식 모두 팩의 `observedAt`은 현재 확보 시각을 유지합니다. 근거에는 원문 해시·선택 방식·등록 시각이 남습니다. 검사 보고서는 `providerPublicationAssumptions`에 가정한 근거를 표시합니다. 기본값을 바꾸거나 가정 결과를 독립 검증된 과거 관측으로 올리지 않습니다. 기존 KIS/이전 KIND 원문·팩·보고서도 소급 수정하지 않습니다.

이번 가정 결과는 과거 등록 시각 전 조회에서 세션을 제외하고, 등록 시각 이후 조회에서만 보입니다. 날짜에 장 개장 시각이나 자정을 임의로 붙인 것이 아닙니다. 시장 인자는 이전과 같이 `CALLER_DECLARED`이며 티커의 과거 시장 이력을 입증하지 않습니다.

## 명시된 사실만 달력에 연결

공지에서 다음을 직접 확인했습니다. 적용 시장 중 이번 산출물은 KOSPI로 한정했습니다.

| 날짜 | 연결한 사실 | 미확인으로 유지한 항목 |
|---|---|---|
| 2024-12-31 | 연말 휴장, 결제일 제외 | 영업일·공급자 거래일 플래그 |
| 2025-01-02 | 개장일, 정규장 10:00~15:30 | 영업일·공급자 거래일·결제일 플래그 |
| 2025-12-31 | 연말 휴장, 결제일 제외 | 영업일·공급자 거래일 플래그 |
| 2026-01-02 | 개장일, KRX 정규장 10:00~15:30 | 영업일·공급자 거래일·결제일 플래그 |

이를 위해 [기준정보 모델](../AI/ai-server/app/replay/reference.py)의 `businessDay/tradingDay/settlementDay`는 명시적 null을 허용합니다. `openDay`는 계속 필수 boolean입니다. 알 수 없는 플래그를 false로 바꾸지 않고 `calendarUnknownFlags`와 `CALENDAR_FLAGS_PARTIAL`에 표시합니다. 달력 완전성의 날짜 기준은 `calendarCompletenessBasis=OPEN_DAY`입니다. 다른 플래그까지 완전하다는 뜻은 아닙니다.

같은 날짜의 부분 플래그와 다른 출처의 확정 플래그는 양방향 같은 결과로 합칠 수 있습니다. 둘 다 알고 있는 값이 다르면 `REFERENCE_CONFLICT`로 중단합니다. 원본 팩과 입력 해시는 각각 보존합니다. `coverage`는 빈 목록이며 공지 1건을 전체 과거 달력·기업행사·종목군의 완전성으로 사용하지 않습니다.

## 실제 대조 결과

KB 공개 공지 GET 총 2회 후, 동일 URL 캐시와 기존 KIS/KIND 캐시는 네트워크 호출 시 실패하는 클라이언트로 재검사했습니다. 추가 네트워크 0회, 기존 730건 일봉 해시 일치를 확인했습니다. 두 시점 방식은 동일한 각 캡처에서 오프라인으로 파생했습니다.

| 항목 | 이전 | 이번 |
|---|---:|---:|
| 확인된 달력 날짜 | 24 | 28 |
| 확인된 개장일 | 18 | 20 |
| 대상 시장 일치 세션 | 0 | 2 |
| 일봉에 대응하는 세션 미확보 | 730 | 728 |
| 달력 미확인 날짜 | 1,074 | 1,070 |
| 확인된 개장일 가격 불일치 | 0 | 0 |

기존 다른 시장 세션 3건은 계속 제외합니다. 새 달력 4일의 영업일/거래일, 개장일 2일의 결제일은 미확인 상태입니다. 기본 OBSERVED_AT에서는 세션 지식 시각이 과거 장 마감 이후라는 사유 2건을 유지합니다. 공급자 공개 시각 가정에서는 그 사유가 없어지고 가정 2건을 명시합니다. 전체 상태는 두 방식 모두 `REFERENCE_GAPS`이며 학습/전략 검증/거래 사용 가능 표시는 false입니다.

로컬 산출물은 Git 제외 `AI/ai-server/research-artifacts/kb-market-notice-cache/<URL 해시>/{body.html,receipt.json}`, `kb-market-observed.json`, `kb-market-publication-assumed.json`, `kb-market-2026-observed.json`, `kb-market-2026-publication-assumed.json`, 기존 수집 폴더의 `reference-check-kb-years-OBSERVED_AT.json`/`reference-check-kb-years-PROVIDER_PUBLICATION_ASSUMED.json`입니다. 실제 원문·시세·개인 설정은 PR에 넣지 않았습니다.

## 실행

```powershell
# AI/ai-server에서 실행. capture만 지정한 공개 문서 1건을 읽습니다.
.\.venv\Scripts\python.exe -m app.replay.reference_cli kb-notice-capture --url 'https://www.kbsec.com/go.able?idt=20241226&linkcd=s060901010000&seq=10007903' --cache research-artifacts/kb-notice-cache

# 아래 capture 경로는 위 결과를 지정합니다. 기본 OBSERVED_AT 오프라인 변환입니다.
.\.venv\Scripts\python.exe -m app.replay.reference_cli kb-notice-import --capture research-artifacts/kb-notice-cache/캡처해시 --market KOSPI --output research-artifacts/kb-observed.json

# 공급자 공개 시각 가정은 별도 결과로 생성합니다.
.\.venv\Scripts\python.exe -m app.replay.reference_cli kb-notice-import --capture research-artifacts/kb-notice-cache/캡처해시 --market KOSPI --availability PROVIDER_PUBLICATION_ASSUMED --output research-artifacts/kb-publication-assumed.json
```

결과 팩은 기존 `check --market KOSPI --reference ...`에 추가합니다. 입력·파일·수집 오류는 종료값 2, 대조의 기준정보 부족은 1입니다. 원문 확보 성공과 변환/전체 기준정보 완성은 별도 상태입니다.

## 검증·체크리스트

AI 서버 전체 **229건 통과**, 실패·오류·제외 0건(기존 193 + 신규 36)입니다. 시장/시간 표 경계·KRX/NXT·주문접수시간 열·등록 시각·연도/날짜 충돌·URL·실패 예약·캐시 변조·확보/변환 분리·기본/가정 시점·달력 null·부분 플래그 합치기와 충돌을 검사했습니다. 기존 Starlette/AnyIO 경고 1건은 유지됩니다.

- [x] 대상 시장에 적용되는 실제 공지와 등록 시각 확보
- [x] KOSPI 특수 세션·개장/휴장 날짜의 원문 연결
- [x] 현재 관측/공급자 공개 시각 가정의 분리·과거 조회 검증
- [x] 미확인 달력 플래그 보존·일치 자료 보완·충돌 거절
- [x] 기존 730건과 실제 대조·무통신 재검사·전체 회귀 검증
- [ ] 대상 시장 전체 기간의 달력·일반/특수 세션 확보
- [ ] 실제 과거 상장/폐지·시장 이동 종목군과 기업행사 확보/대조

5-08 전체 완료 조건은 남아 있으며 고정 완료율은 올리지 않습니다. 다음은 과거 상장/기업행사 수집 경로와 전체 기간 기준정보 확대입니다. 이번 작업은 연구용 Python 코드와 문서로, 모델 학습·실주문·운영 배포·EXE 재빌드는 수행하지 않았습니다.
