# 5-08 임시 거래시간 변경 공지 목록·본문 검토

기준일: 2026-11-06. [일반 규정 V2](kosdaq-rule-effective-evidence.md)의 두 시장·4개 연도 **8개 검토 구간**에 대해 KIND 공지 목록과 본문을 수집·검토했습니다. 5-08의 효력일 범위는 **2023-11-01~2026-11-02, KOSPI·KOSDAQ 보통주**로 유지합니다. 공지 검색 범위는 연초 개장 안내의 전년도 발표를 포함하도록 **2023-01-01~2026-11-05**로 고정했습니다. 검토일이 11월 6일이어도 수집 창을 자동 확장하지 않습니다.

## 완료한 범위

| 항목 | 결과 |
|---|---|
| 검색 | 시장·연도별 기타시장안내 8개 + 독립 거래시간 제목 검색 8개, 총 16개 |
| 목록 | 40페이지·고유 공시 2,622건. 제목 검색의 14개 행은 양식 검색과 중복 |
| 본문 검토 | 공지 75건·고유 본문 75개·뷰어 버전 참조 77개 |
| 종목별 목록 보존 | 2,547건은 시장 전체 세션 본문 검토에서 제외하고 목록 원문에 보존 |
| 정규 세션 변경 | 14개 본문: 범위 안 12개 시장/날짜 + 범위 밖 2개 |
| 구간 상태 | 8/8개 `SCOPED_INVENTORY_REVIEWED`. 검색 범위의 페이지·본문 검토 확인 |
| 실제 세션 | 기존 시장별 6일의 근거 보강. 일반 후보 1,448개 승격 0건 |

**8/8은 선택한 공지 양식과 검색 창의 검토 결과입니다. 전체 임시 변경 목록이나 5-08 전체 완료율이 아닙니다.** `scopedInventoryReviewComplete=true`와 `fullTemporaryChangeInventoryComplete=false`, `fullCorrectionLineageComplete=false`, `allHistoricalSessionsComplete=false`를 구분합니다. 기존 `ReferencePack`은 그대로 보존하며 학습·전략 검증·거래 사용은 모두 비활성입니다.

### 목록의 범위와 페이지 증명

[KIND 상세검색](https://kind.krx.co.kr/disclosure/details.do?method=searchDetailsMain)의 시장 구분과 **기타시장안내 양식 KOSPI 99303 / KOSDAQ 70780**을 명시했습니다. 회사 필터를 비우고 최종보고서 전용 필터를 사용하지 않아 원본과 정정본을 함께 검색합니다. 별도로 양식 코드를 비운 `거래시간` 제목 검색을 수행해 알려진 시간 변경 공지의 누락을 대조합니다.

| 공지 연도 | KOSPI 양식 검색 | KOSDAQ 양식 검색 |
|---|---:|---:|
| 2023 | 14 | 564 |
| 2024 | 6 | 654 |
| 2025 | 10 | 702 |
| 2026~11-05 | 3 | 669 |
| 합계 | 33 | 2,589 |

양식 검색 32페이지와 제목 대조 8페이지를 수집했습니다. 페이지 크기 100으로 첫 페이지의 총수·페이지 수를 고정하고 모든 페이지의 총수, 연속 역순 행 번호, 접수번호 중복/누락, 검색 간 동일 공시의 제목·회사·제출인·접수 시각을 검증합니다. 원문·요청·영수증·계획의 해시를 연결합니다. 수집 중 총수가 바뀌면 완료로 계산하지 않습니다.

사전 탐색에서 보고서명만 지정한 넓은 2024년 검색은 ETF 등을 포함한 7,715건/78페이지를 반환했습니다. 별도 시장안내 게시판은 종목별 투자경고·이름 변경 등을 포함하면서 일반 시간 변경 안내를 빠뜨렸습니다. 두 방식 모두 이번 주 목록의 완전성 근거로 채택하지 않았습니다. 독립 제목 검색도 다른 제목의 모든 양식까지 포괄하는 증거는 아닙니다.

과거 공시의 회사 옆 시장 아이콘은 포스코DX처럼 현재 시장으로 표시될 수 있습니다. 이를 `issuerDisplayMarket`로 보존하고 과거 시장 필터·양식 식별을 덮어쓰지 않습니다. 일부 제목 장식 속성의 따옴표가 잘못된 HTML은 표시 텍스트로 읽되, 실제 뷰어 링크의 중복 `href`/`onclick`은 거부합니다.

### 본문 분류와 적용일

| 분류 | 고유 본문 | 처리 |
|---|---:|---|
| 정규 거래시간 변경 | 14 | 날짜·시장·변경 전후 시간을 원문에서 확인 |
| 시장조성 계약/정책 | 35 | 정규 세션 변경에 포함하지 않음 |
| 공매도 정책 | 21 | 정규 세션 변경에 포함하지 않음 |
| 의무보유 정책 | 2 | 정규 세션 변경에 포함하지 않음 |
| 특정 종목 거래정지/재개 | 3 | 해당 종목 사건으로 구분 |

범위 안에서는 아래 6개 날짜를 **각 시장에서** 확인했습니다. 수능일은 10:00~16:30, 연초 개장일은 10:00~15:30이며 모두 한국 시각입니다. [2024년 KOSPI 수능일 안내 원문](https://kind.krx.co.kr/external/2024/10/31/000086/20241031000185/99303.htm)처럼 공지 발표일과 실제 적용일을 구분합니다.

| 날짜 | 구분 | 결과 |
|---|---|---|
| 2023-11-16 | 수능일 | 두 시장 기존 세션 대조 일치 |
| 2024-01-02 | 연초 개장 | 두 시장 기존 세션 대조 일치 |
| 2024-11-14 | 수능일 | 두 시장 기존 세션 대조 일치 |
| 2025-01-02 | 연초 개장 | 두 시장 기존 세션 대조 일치 |
| 2025-11-13 | 수능일 | 두 시장 기존 세션 대조 일치 |
| 2026-01-02 | 연초 개장 | 두 시장 기존 세션 대조 일치 |

2026-11-19 수능 안내 2개는 발표일이 검색 창 안에 있지만 적용일이 고정 목표 범위 밖입니다. `outsideScopeSessions`에 남기고 기존 세션에 추가하지 않습니다. 새로 발견한 범위 안 특수 거래일은 없습니다.

회사 열이 빈 동양철관(008970) 안내 3개도 본문상 해당 종목의 12:05 정지·제목 정정·15:00 재개와 15:00~15:10 단일가 처리입니다. 이를 시장 전체 장중 정지나 정규장 시간 변경으로 해석하지 않습니다. 원본·정정 접수번호 두 뷰어가 같은 두 문서를 참조해 버전 참조는 77개, 고유 본문은 75개입니다. 뷰어에 보이는 연결은 보존하지만 전체 정정 계보 확인으로 올리지 않습니다.

## 구현·재현 계약

- `app.replay.session_notice_inventory`: `plan/extend/collect/status/build/audit`. 기존 규정 V2 해시와 8개 구간으로 검색 계획을 고정하고 목록→뷰어→문서 경로→본문을 수집합니다.
- `app.replay.session_notice_review`: `build/audit/as-of`. [검토 명세](examples/session-notice-review.json)의 목록 해시·시장·문서 식별자·본문 해시와 정확히 일치하는 75개 판단만 적용합니다. 누락·중복 판단, 미지원 시간/시장, 휴장일 충돌은 거부합니다.
- 공지 적용일은 본문에서 추출하며 발표 연도로 추정하지 않습니다. 수능일은 변경 전 09:00~15:30과 변경 후 10:00~16:30을 모두 확인하고, 기존 특수 세션과 충돌하면 실패합니다.
- 수집 시각 `sourceKnownAt`과 검토 시각 `knownAt`을 분리합니다. 이번 판단 시각은 **2026-11-06T00:10:41.059111+00:00**입니다. 과거 발표 시각을 당시 사용 가능 시각으로 소급하지 않으며 `as-of`도 검토 시각 이후에만 새 대조 결과를 반환합니다.
- 예약은 요청 전에 기록하고 실패/미확정 요청을 자동 재시도하지 않습니다. 요청 시작 간격은 최소 1초이며 같은 요청 키의 원문은 재사용합니다. `extend`는 기존 계획·일지·성공 원문을 변경하지 않고 후속 작업으로 복사하며 기존 사용량을 누적 계승합니다.

아래 명령은 `AI/ai-server`에서 실행합니다. `$py`는 프로젝트 가상환경 Python이며 원본 연구 캐시가 필요합니다. `audit/status/as-of`는 추가 수집 없이 실행할 수 있습니다.

```powershell
$py = '.\.venv\Scripts\python.exe'
$root = 'research-artifacts/session-inventory-20261105'
$parent = 'research-artifacts/kosdaq-rule-effective-20261105/report-v2.json'
$scope = '../../docs/examples/session-notice-review.json'

& $py -m app.replay.session_notice_inventory status --job "$root/job-complete"
& $py -m app.replay.session_notice_inventory audit --job "$root/job-complete" --parent $parent --output "$root/inventory.json"
& $py -m app.replay.session_notice_review audit --job "$root/job-complete" --parent $parent --inventory "$root/inventory.json" --review $scope --output "$root/review-report.json"
& $py -m app.replay.session_notice_review as-of --output "$root/review-report.json" --market KOSPI --at '2026-11-06T00:11:00Z'
```

새 수집 예시는 다음과 같습니다. **네트워크 호출을 수행하므로 재검증에는 실행하지 않습니다.** 새 작업은 신규 경로를 사용합니다. 실제 수집의 seed 재사용·시각·계획 계보까지 같은 결과를 얻으려면 원래 캐시와 선행 작업 경로를 함께 보존해야 합니다. 새 수집에는 새 해시·검토 명세가 필요하며 기존 명세/보고서를 덮어쓰지 않습니다.

```powershell
& $py -m app.replay.session_notice_inventory plan --job 'research-artifacts/new-session-inventory/job' --parent $parent --through 2026-11-05 --max-requests 256
& $py -m app.replay.session_notice_inventory collect --job 'research-artifacts/new-session-inventory/job' --max-new-requests 20
# 예산 변경이 필요할 때만: 새 300회가 아니라 앞선 사용량을 포함한 누적 상한
& $py -m app.replay.session_notice_inventory extend --from-job 'research-artifacts/new-session-inventory/job' --job 'research-artifacts/new-session-inventory/extended' --max-requests 300
& $py -m app.replay.session_notice_inventory collect --job 'research-artifacts/new-session-inventory/extended' --max-new-requests 20
& $py -m app.replay.session_notice_inventory build --job 'research-artifacts/new-session-inventory/extended' --parent $parent --output 'research-artifacts/new-session-inventory/inventory.json'
# 본문 검토 후 새 목록 해시에 맞춘 새 명세를 작성하고 review build 실행
& $py -m app.replay.session_notice_review build --job 'research-artifacts/new-session-inventory/extended' --parent $parent --inventory 'research-artifacts/new-session-inventory/inventory.json' --review 'research-artifacts/new-session-inventory/review.json' --output 'research-artifacts/new-session-inventory/review-report.json'
```

### 실제 요청 예산

| 단계 | 누적 상한 | 정식 신규 요청 누적 | 비고 |
|---|---:|---:|---|
| `job` | 256 | 256 | 사전 탐색의 첫 페이지 2개 seed 추가 재사용 |
| `job-final` | 257 | 257 | 뒤에 필요한 뷰어/경로/본문이 남아 대기 |
| `job-complete` | 300 | 263 | 후속 6회로 완료, 이전 요청 중복 호출 없음 |

최종 정식 증거는 **265개 요청 결과 = 목록 40 + 뷰어 75 + 경로 75 + 본문 75**입니다. 이 중 새 정식 요청은 263회, 나머지 2개는 사전 탐색 6회 안에서 가져온 seed입니다. 따라서 **새 공개 HTTP 총수는 263+6=269회**이며 seed를 다시 더하지 않습니다. 계승된 원문의 디스크 복사는 추가 호출이 아닙니다. 모든 호출은 인증 없는 KIND 공개 자료이며 계좌·KIS·OpenDART·KRX 인증 API를 추가 호출하지 않았습니다.

### 불변 보고서

연구 원문·캐시는 Git 제외 경로 `AI/ai-server/research-artifacts/session-inventory-20261105/`에 보관합니다. 검토 명세는 Git에 포함하며 `.gitattributes`로 LF를 고정해 바이트 해시를 유지합니다.

| 자료 | SHA-256 |
|---|---|
| 선행 규정 V2 | `e60174c567c80a07f5c7f2377342ba257316fa7fbcfed9134ceda8ebdb803715` |
| `inventory.json` | `2f705264ea03b085a25c24682aedbd061e35a8165e17a9244b17d53ad22b91ee` |
| `review-report.json` | `0193a6a016058d024073e60325c1657f0f514055b49b45bd74bee9655d59ecd4` |
| 검토 명세 | `d02d357c12b9f721ba2d4fdfd7bfb3d45d46b406da18951d063202a05fbc4aee` |

검토 명세의 바이트 해시는 `review-report.json.reviewScopeSha256` 및 `validation.json.reviewScopeSha256`으로 대조합니다. 범위·판단 수정은 기존 자료를 변경하지 않고 새 버전으로 진행합니다.

## 검증과 다음 완료 조건

전체 AI 서버 **984건 통과**(기존 948 + 신규 36), 실패/오류/제외 0건, 기존 Starlette/AnyIO 경고 1건입니다. 신규 검증은 페이지 누락/중복·잘못된 필터·현재 시장 아이콘·링크 변조·요청 실패/예약·예산 계승·원문/계획/일지 변조·검토 범위/해시·연도 경계·잘못된 시장/시간/휴장일과 실제 캐시 재사용을 포함합니다. 전체 감사 결과는 `validation.json`에 기록합니다.

통신을 차단한 전체 재계산 감사에서 기존 **7,581개 파일**과 신규 **803개 파일**의 해시를 보존했습니다. V1~V7 종목군 원장·달력·규정 V1/V2·새 목록/검토 보고서가 원래 결과와 일치하고 완성 캐시 재사용의 추가 요청은 0회입니다. 정식 신규 요청 263개의 키는 모두 고유하며 최소 시작 간격은 1.000042초입니다.

기존 일봉 730개 날짜·달력 1,098일과 `REFERENCE_GAPS`, 개별 공시 576/577건·폐지일 충돌 1건·관찰 868건은 그대로입니다. 이번 구현은 연구 CLI이며 운영 배포·DB·EXE·학습·주문 설정을 변경하지 않았습니다.

- [x] 16개 검색의 40페이지와 목록 2,622건 확보·해시 보존
- [x] 본문 75개 분류와 기존 특수 세션 12개 시장/날짜 대조
- [x] 범위 밖 적용일 2개·개별 종목 정지·뷰어 버전 연결 분리
- [x] 8개 구간의 선택 범위 페이지/본문 검토 및 예산 계승 구현
- [x] 새 테스트 36건과 전체 회귀 984건 통과
- [x] 전체 원장 재계산·기존 7,581개/신규 803개 파일 해시와 추가 통신 0회 확인
- [ ] 다른 공지 양식·제목을 포함한 임시 변경 목록의 검색 범위 보강
- [ ] 검색 창 밖에서 발표되어 목표 기간에 효력이 생기는 공지의 경계 검토
- [ ] 전체 정정/철회 계보·과거 최초 이용 가능 시각 확인
- [ ] 위 조건을 충족한 뒤 일반 후보 1,448개의 실제 세션 승격 판단
- [ ] [5-08 고정 완료 조건 7개](multi-company-reference-cases.md)의 나머지 종목군·달력 플래그·기업행사·가격/체결·전체 감사 완성

다음 작업은 **임시 변경 목록의 추가 양식·발표 경계·정정 계보 검증**입니다. 이번 결과로 “다른 변경이 전혀 없다”고 판단하지 않습니다. 5-08은 진행 중, **5번 7/18·39%, 1~5번 고정 목록 26/48·54%**를 유지합니다. 세부 증거 수집이 늘어난 정도를 전체 완료율로 환산하지 않습니다.
