# 5-08 재상장·이전상장 편입 확인과 V7 원장

최신 후속: [전체 기간 달력·특수 세션 확대](market-calendar-session-coverage.md)에서 1,098일 개장 여부와 날짜 충돌의 휴장 문맥을 대조했습니다. 개별 공시 576/577건·폐지일 충돌 1건은 유지하며 아래는 V7 작업 기록입니다.

기준일: 2026-11-05. [V6 상장폐지 대조](delisting-disclosure-coverage.md)의 후속입니다. 현황 일치 단계에 남았던 **17건을 모두 수집·대조해 16건 확인, 폐지일 충돌 1건 유지**로 기록했습니다. 편입/제외 관련 개별 공시 확인은 **560 → 576/577건·99.8%**, 현황 일치 단계는 **17 → 1건**입니다. 99.8%는 해당 관찰의 개별 공시 확인율이며 전체 5-08 완료율이 아닙니다.

## 이번 결과

| 대상 | 확인 결과 | 근거 범위 |
|---|---|---|
| 재상장 9건 | 9건 확인: KOSDAQ `70779` 2·KOSPI `68156` 7 | 전체 코드·ISIN·보통주·대상 시장·재상장일과 실제 편입 구간 일치 |
| 이전상장 현황 7건 | 코스닥 `70760` 7건 확인 | 대상 시장 편입일만 확인. 범위 밖 시장 이력·양 시장 전체 이전 쌍은 미확인 |
| 폐지일 충돌 1건 | 위지윅스튜디오 `299900` 검토 유지 | 공시 2026-08-14와 KRX 현황/종목군 제외 2026-08-18 충돌 |

재상장 대상은 폰드그룹 `472850`, SK이터닉스 `475150`, HS효성 `487570`, 한화인더스트리얼솔루션즈 `489790`, GS피앤엘 `499790`, 삼양바이오팜 `0120G0`, 삼성에피스홀딩스 `0126Z0`, 네오뷰 `0218L0`, 한화머시너리앤서비스홀딩스 `0220W0`입니다. 이름은 해당 공시/관찰 시점의 표기이며 최신 사명이나 투자 추천 목록이 아닙니다. 영문자가 포함된 전체 종목코드도 원문 그대로 대조하며 현황의 짧은 발행회사 키에서 코드를 만들어내지 않습니다.

이전상장 현황 7건은 유투바이오 `221800`, 한중엔시에스 `107640`, 에이치엔에스하이텍 `044990`, 듀켐바이오 `176750`, 한국피아이엠 `448900`, 지에프씨생명과학 `388610`, 진코스텍 `250030`입니다. 현황은 `이전상장`, 개별 공시는 `신규상장`으로 구분해 보존합니다. 신규상장 공시는 코스닥 편입일의 근거로만 사용하며 최초 IPO나 이전 시장의 제외일까지 확인했다고 표시하지 않습니다.

## 검증 규칙과 주식 종류

V6의 파일 SHA-256과 원래 514건 목록, 정확한 미확인 관찰 집합을 고정합니다. 각 대상의 관찰 ID·전체 코드·ISIN·시장·관찰 구간·현황 날짜/사유/참조 ID가 일치해야 합니다. 기존 완료 행을 새 대상으로 편입하지 않습니다.

공식 검색 → 뷰어 → 문서 경로 → 본문을 모두 보존합니다. 검색은 관찰 직전 날짜의 45일 전부터 현황 날짜 이후 30일까지이며, 상한은 기존 기간 종료일 2026-11-02입니다. 후속 정정 검색을 위해 범위를 넓혔으나 부모 원장의 관찰 구간이나 적용일을 바꾸지 않습니다. 페이지·건수·후보 중복·공식 HTTPS 호스트·접수/문서번호·뷰어 전체 코드·문서 계보와 현재 `Y` 표시를 검사합니다. 이번에는 대상별 1개씩 총 17개 본문을 수집했습니다. 지원하지 않는 양식·정정 또는 불완전 검색 결과는 검토 상태로 남깁니다.

코스닥 재상장 `70779`는 회사명·보통주 행·전체 코드·ISIN·0보다 큰 주식수·매매개시일을 검증합니다. 코스피 재상장 `68156`은 재상장/인적분할 표기·상장종목·전체 코드·ISIN·보통주·상장일을 검증합니다. 상장일은 현황 날짜와 정확히 같고 관찰 전후의 편입 구간 안에 있어야 합니다. `재상장-인적분할`이라는 원문 분류를 법적 회사분할 완료일이나 비율의 확인으로 바꾸지 않습니다.

한화머시너리앤서비스홀딩스 [재상장 공시](https://kind.krx.co.kr/external/2026/08/21/000488/20260821001579/68156.htm)에는 `(1) 보통주권`과 `(2) 종류주권(3우선주)`가 함께 있습니다. 보통주 구간의 `A0220W0`·`KR70220W0000`·상장일·보통주 수만 선택하고, 우선주 `A0220WL`·`KR70220WK021` 구간의 식별자와 원문 텍스트 해시는 제외 근거로 보존합니다. 두 구간을 합쳐 보통주 사실로 만들지 않습니다. 중복·뒤바뀐 구간이나 다른 식별자는 승인하지 않습니다.

실제 출처 예: [폰드그룹 재상장](https://kind.krx.co.kr/external/2024/01/31/001121/20240131002611/70779.htm), [SK이터닉스 재상장](https://kind.krx.co.kr/external/2024/03/27/001386/20240327004277/68156.htm), [삼양바이오팜 재상장](https://kind.krx.co.kr/external/2025/11/20/000726/20251120002095/68156.htm), [유투바이오 신규상장](https://kind.krx.co.kr/external/2023/10/31/000464/20231031000969/70760.htm).

위지윅스튜디오 [폐지 공시](https://kind.krx.co.kr/external/2026/08/14/002694/20260814009419/70769.htm)는 확장한 검색에서도 2026-08-14를 기재한 원문으로 확인됐습니다. KRX 현황 날짜 2026-08-18 및 08-17 존재/08-18 제외 경계와 다릅니다. 이 결과만으로 어느 날짜가 잘못됐는지 판단하거나 날짜를 수정하지 않습니다. V7은 기존 `STATUS_LIST_MATCH`와 이전 검토 기록을 보존하고 새 원문·확보 시각·충돌 날짜를 추가합니다. 이번 검색 범위에서 일치 근거를 확보하지 못했다는 뜻이며, 모든 출처에 정정이 없다는 단정이 아닙니다.

## 원장 보존과 검증 체크리스트

- [x] 남은 17건의 정확한 대상·V6/목록 해시 고정과 제한 수집
- [x] 재상장 9건·대상 시장 편입 7건의 개별 공시 확인
- [x] 보통주/우선주 혼합 문서 1건의 구간·식별자 분리
- [x] 폐지일 충돌 1건과 이전 검토 기록 보존
- [x] 원래 관찰 868개·대상 밖 851행·V1~V6·이름 관찰 결과 보존
- [x] 실제 종목군 편입/제외 전후 34/34개 경계 일치
- [x] 기존 파일 7,246개와 새 원문/계획/보고서 72개 해시 보존
- [x] 네트워크 차단 전체 원장 재감사·완료 캐시 재사용 추가 요청 0회
- [x] 전체 AI 서버 834건 통과: 기존 777 + 신규 57, 실패/오류/건너뛰기 0. Java 저장 내보내기 fixture 포함, 기존 Starlette/AnyIO 경고 1건 유지
- [ ] 폐지일 충돌의 추가 공식 근거 또는 명시적인 적용 범위 제외 판단
- [ ] 전체 법적 사건/발행회사 관계/독립 총수·범위 밖 시장 이력·달력/세션·기업행사·과거 공개 시점·실제 가격 검증

새 사실과 새 검토 사유 모두 실제 원문·KRX 문맥·부모 행의 확보 시각 이후에만 조회합니다. 접수일이나 상장일을 과거 최초 공개 시각으로 추정하지 않습니다. 전체 관찰 분류의 미해결 수 0건과 개별 공시의 날짜 충돌 1건을 구분하며, 전체 종목군/법적 사건 완전성·학습/거래 사용 가능 플래그는 올리지 않습니다.

## 실행과 요청 예산

실행 위치는 `AI/ai-server`입니다. 최대 160회는 금액이 아닌 공개 HTTP 요청 상한입니다. 실제 **68/160회**로 검색·뷰어·경로·본문 각 17회를 사용했습니다. 최소 시작 간격 1초, 단계당 최대 3회, 실패/중단 예약의 명시적 `--retry-failed`, 성공 캐시 재사용 정책을 유지합니다. 규격 탐색·KRX 인증 API·KB·KIS·DART 추가 호출은 없습니다.

실측 최소 요청 시작 간격은 **1.000230초**이며, 네트워크 차단 재감사와 완료 캐시 재사용 중 추가 요청은 0회입니다.

```powershell
.\.venv\Scripts\python.exe -m app.replay.remaining_membership_disclosures plan `
  --job research-artifacts/remaining-membership-20261105/job `
  --parent research-artifacts/delisting-coverage-20261104/reconciled-v6.json `
  --inventory research-artifacts/listing-coverage-20261104/inventory.json --max-requests 160
.\.venv\Scripts\python.exe -m app.replay.remaining_membership_disclosures collect `
  --job research-artifacts/remaining-membership-20261105/job --max-new-requests 160
.\.venv\Scripts\python.exe -m app.replay.remaining_membership_disclosures audit `
  --job research-artifacts/remaining-membership-20261105/job
```

`plan`은 새 폴더에 한 번만 실행합니다. [V6 실행 예제](delisting-disclosure-coverage.md)의 `$coverageArguments`에서 `--facts-output`·`--output`을 이번 경로로 바꾸고 다음 인자를 추가합니다.

```powershell
  '--parent-v6', 'research-artifacts/delisting-coverage-20261104/reconciled-v6.json',
  '--remaining-job', 'research-artifacts/remaining-membership-20261105/job',
  '--facts-output', 'research-artifacts/remaining-membership-20261105/facts.json',
  '--output', 'research-artifacts/remaining-membership-20261105/reconciled-v7.json'
```

```powershell
.\.venv\Scripts\python.exe -m app.replay.remaining_membership_reconciliation build @coverageArguments
.\.venv\Scripts\python.exe -m app.replay.remaining_membership_reconciliation audit @coverageArguments
.\.venv\Scripts\python.exe -m app.replay.remaining_membership_reconciliation as-of @coverageArguments `
  --at 2025-11-24T09:00:00+09:00 --symbol 0120G0
```

`build/audit/as-of`는 기존 KRX 원문/파생·V1~V6를 재계산하고 새 수집의 요청·원문·대상 집합·확보 시각을 감사합니다. 실제 원문·계획·보고서는 Git 제외 경로 `AI/ai-server/research-artifacts/remaining-membership-20261105`의 `job/`, `facts.json`, `reconciled-v7.json`, `boundaries.json`, `validation.json`에 보관합니다. 기존 계획과 보고서를 다른 결과로 덮어쓰지 않습니다.

| 보고서 | SHA-256 |
|---|---|
| 보존한 V6 | `961913e8e972195fc138b026df339886ee033ad06c96f61e152c31c23151b555` |
| 원래 514건 목록 | `f452566ef88bbd5ddb3cc57909982d82704261ee21d87bd5575768aed0fe75ef` |
| 이번 개별 공시 사실 | `8da3334e0ac5a54b7a9fa9825ef2c3204ded2232b3b9975de124eace3c1ae921` |
| 신규 V7 | `99ed9386ee14991816a7e9907fcec8b214c714f52a4af470a49b262fe4d0bdbc` |

이번 작업은 고정 완료 조건 ① 과거 종목군·⑤ 정정/시점·⑥ 경계·⑦ 감사를 보강했습니다. **5-08 진행 중, 5번 7/18·39%, 1~5번 26/48·54%**를 유지합니다. 다음은 남은 날짜 충돌 근거 확인과 거래일 달력/세션 등 전체 기준정보 검증입니다. 학습·실주문·배포·DB·EXE 변경은 없습니다.
