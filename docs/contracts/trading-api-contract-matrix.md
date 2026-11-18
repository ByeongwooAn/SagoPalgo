# R0 API 지원·계약 매트릭스

확인일: 2026-11-02 · 작업 브랜치: `feature/trading-contract-matrix` · 상태: 문서 기반 조사 완료, R0 전체는 진행 중.

[최신 로드맵](../project/realtime-trading-roadmap.md)의 R0 산출물입니다. [KB 계약 보류 목록](kb-contract-blockers.md), [초기 운용·측정 기준 초안](../project/initial-trading-policy.md)과 함께 사용합니다. 실제 KB 문의 답변은 아직 대기 중이라는 사용자 설명을 반영했습니다. 이 조사에서는 공개 문서와 저장소 코드만 확인했으며 인증된 계좌/주문 API, 운영 DB, 주문 스위치를 조작하지 않았습니다.

## 1. 지원 여부를 판정하는 기준

다음은 서로 독립적인 확인 축입니다. API 이름이 존재한다고 주문 완료 해석·계좌 권한·호출 성공·실운영 준비가 모두 확인되는 것은 아닙니다.

| 축 | 기록할 값 | 필요한 근거 |
|---|---|---|
| 공식 계약 | 목록 확인 / 필드 확인 / 의미 미확정 / 미확인 | 공식 URL·필드·확인일·상품/시장 |
| 현재 코드 | 조회 구현 / 제한적 전송 구현 / 부분 구현 / 미착수 | 어댑터·서비스·기존 계약 테스트 |
| 실환경 | 기존 문서의 개별 기록 / 이번 미검증 / 운영 확인 | 계좌·권한·범위를 식별하되 민감값을 제거한 대조 기록 |
| 허용할 후속 작업 | 설계/격리 검증 / 읽기 연결 검증 / 계약 확인 후 확장 | 선행 계약과 기존 차단 유지 여부 |

이 표는 런타임의 지원 플래그가 아닙니다. 코드 구현 여부는 공개 API 전체 능력과 다를 수 있습니다. 기존 실환경 증거는 [개발 진척도](../project/development-progress.md)와 각 주문 문서의 범위로만 인정하며 이번 조사로 확대하지 않습니다.

## 2. 계좌·시세·시장 탐색

| ID | 기능과 API | 공식 계약 확인 | 현재 코드와 한계 | 다음 단계 / 허용 범위 |
|---|---|---|---|---|
| A01 | KB 보유주식 `SSQM1801` | 공개 목록·POST 경로 확인 [E01] | 조회·수동 미리보기 가져오기 구현. 지속 동기화·전체 페이지 완전성은 별도 | R1 계좌 스냅샷/완전성 설계·격리 검증 가능 |
| A02 | KB 결제/체결 기준 잔고 `SSQM2932`, `SSQM2952` | 공개 목록·POST 경로 확인 [E01] | 두 조회 구현. 현금/평가 시점·동일 스냅샷·예약 중복 차감 확인 필요 | R1 각 잔고의 기준시점과 출처 보존부터 진행 |
| A03 | KB 매수주문가능금액 `SSQM1802` | 공개 목록·POST 경로 확인 [E01] | 현재 사전검증은 `SSQM2932`의 주문가능현금 사용. `SSQM1802` 전용 어댑터는 미구현 | 응답의 종목/계좌 기준과 예약 반영을 확인한 후 배분 계약에 반영 |
| A04 | KB 체결·미체결 `SSQM2341` | 필드 정의 확인, 변경 완료 의미 미확정 [E02] | 페이지·다음키·주문번호 대조와 관찰 구현. 최대 10페이지/날짜 스캔 200행은 앱의 보호 상한 | R1 읽기 결과 보관·완전성 검사 가능. KB-01~04 관련 자동 종결은 보류 |
| A05 | KB 계좌 목록·관심목록 | 기본 계좌 목록 경로는 비어 있음. 이번 공개 목록의 이름 검색에서 관심 API 미확인 [E01] | 계좌 목록은 경로 설정 필요. 실제 환경의 설정값은 이번 미조회. 앱 관심목록은 자체 DB 관리 | 목록 부재를 API 미지원 확정으로 해석하지 않음. 앱 목록 사용, KB-06 확인 |
| M01 | KB 현재가 `IVU10140` | 공개 시세 목록 [E01] | REST 조회 구현. 호출 시 스냅샷이며 구독 아님 | R2 기준 스냅샷·출처/거래소 일치 검증에 재사용 |
| M02 | KB 통합차트 `IVS11560` | 공개 목록·POST 경로 확인 [E01] | 앱은 DAILY/WEEKLY/MONTHLY만 허용. `MINUTE` enum이 있어도 서비스가 거절 | API 전체의 분봉 미지원으로 단정하지 않음. R2 스트리밍 분봉, R5 과거 해상도 별도 확인 |
| M03 | KIS 국내 현재가·기간별 시세 | 공식 REST/실시간 예제 [E07] | `inquire-price`, `inquire-daily-itemchartprice` 구현. 장 마감 모델 입력은 `inquire-daily-price`로 기준일 원주가를 대조 | R2 읽기 전용 Provider로 확장. 장 마감 모델은 두 종목의 오프라인 대조 완료, 실환경 확인 대기. [확정 기준과 검증](../project/daily-inference-integration.md) |
| M04 | KIS 체결·호가 WebSocket | 공식 인증·구독 예제 확인 [E07] | 서버/앱 구현·025/026 적용·1종목/2구독 실키 수신 확인 | [실제 제한 표본](../market-data/public-tick-collection-recovery.md). 운영 기본 OFF, 더 큰 공유 한도·장기 운용·수급·세션 의미/시각 대조는 후속 |
| M05 | KB 실시간 구독 | 이번 조사에서 스트리밍 계약 미확인 | KB REST 시세만 구현 | 미확인을 미지원으로 확정하지 않음. KIS 기반 수집을 먼저 설계하고 KB-06으로 확인 |
| M06 | Toss 현재가·종목·캔들 | 이번 작업은 공식 최신 명세 재검증 범위에서 제외 | 기존 REST Provider 있음. 설정 기본 경로가 공식 지원 증거는 아님 | 기존 읽기 fallback 유지. 신규 연결/확대 전에 현재 계약·권한 검증 |
| M07 | KB 투자자별 동향 `IVU10430` | 공개 목록·POST 경로 확인 [E01] | 기관/외국인/개인 수급 어댑터 미구현 | R2 응답 시각·추정/확정·단위·갱신 주기 확인 전 실시간 확정 수급으로 사용하지 않음 |
| M08 | KB 거래대금/거래량 상위 `IVU10210`, `IVU10280` | 공개 목록·POST 경로 확인 [E01] | 시장 전체 탐색 미구현 | R4 후보 입력 계약·가상 응답 테스트 가능. 랭킹의 거래소·세션·페이지·한도 확인 필요 |

코드 근거:

- [KB HTTP 클라이언트](../../Back/spring-server/src/main/java/com/sagopalgo/api/kb/client/KbSecuritiesAccountClient.java), [KB 계좌 서비스](../../Back/spring-server/src/main/java/com/sagopalgo/api/kb/service/KbAccountService.java), [KB 가져오기](../../Back/spring-server/src/main/java/com/sagopalgo/api/kb/service/KbPortfolioImportService.java).
- [주문 사전검증](../../Back/spring-server/src/main/java/com/sagopalgo/api/order/service/OrderPrecheckService.java), [체결/미체결 페이지 대조](../../Back/spring-server/src/main/java/com/sagopalgo/api/order/service/KbOrderExecutionService.java).
- [캔들 서비스](../../Back/spring-server/src/main/java/com/sagopalgo/api/market/service/MarketCandleService.java), [KIS REST 클라이언트](../../Back/spring-server/src/main/java/com/sagopalgo/api/market/client/KisMarketPriceClient.java), [Toss Provider](../../Back/spring-server/src/main/java/com/sagopalgo/api/market/client/TossMarketDataProvider.java).

## 3. 뉴스·공시·과거 자료

| ID | 기능과 API | 공식 계약 확인 | 현재 코드와 한계 | 다음 단계 / 허용 범위 |
|---|---|---|---|---|
| D01 | NAVER API HUB 뉴스 검색 `GET /search/v1/news` | 검색·날짜순 정렬·페이지 범위와 하루 25,000회 안내 확인 [E08] | 수집·저장 구현. 현재 Provider는 `sort=date`; 전체 페이지 순회·전 종목 누락 없는 수집은 미구현 | R3 중복/정정·체크포인트·호출 예산 설계 가능. 검색 결과를 전체 뉴스 원문 피드로 간주하지 않음 |
| D02 | OpenDART 공시 검색 `GET /api/list.json` | 회사/기간·페이지 검색 계약 확인 [E09] | 현재 종목별 첫 페이지 조회, 회사 코드 매핑·저장 구현 | R3 모든 페이지·수집 지연·정정 계보 검증. 요청 제한 오류와 키별 정책을 확인하고 무제한 폴링 금지 |
| D03 | 공시/기사 원문 사건 추출 | 공시 검색과 원문 제공은 별도 계약. 기사 원문 저장/활용 권한은 미확인 | 현재는 제목·요약·링크 중심, AI는 키워드 계산 | 허용된 원문만 R3에서 별도 수집. 제목만 있을 때 원문 분석으로 표시하지 않음 |
| D04 | 다년간 분봉·틱·호가·수급 | 필요한 기간/해상도·호출당 범위·활용권 미확정 | 앱의 최대 100개 캔들은 과거 데이터 확보 범위가 아님 | R5 자료 가용성 표부터 작성. 없는 호가를 합성해 실측 체결 검증으로 사용하지 않음 |

현재 수집 스케줄러의 기본 30분 간격은 앱 설정이며 공급자의 갱신 보장이 아닙니다. 기존 Provider가 한 페이지를 읽었다는 사실을 전체 검색 완료로 저장해서는 안 됩니다. 실시간 수집을 개발할 때는 페이지 잘림·지연 도착·같은 날짜의 정정도 검사합니다.

코드 근거: [뉴스 Provider](../../Back/spring-server/src/main/java/com/sagopalgo/api/research/client/NaverNewsProvider.java), [공시 Provider](../../Back/spring-server/src/main/java/com/sagopalgo/api/research/client/OpenDartDisclosureProvider.java), [관심종목 수집 스케줄러](../../Back/spring-server/src/main/java/com/sagopalgo/api/research/service/ResearchFeedScheduler.java).

## 4. 주문·소수점

| ID | 기능과 API | 공식 계약 확인 | 현재 코드와 한계 | 다음 단계 / 허용 범위 |
|---|---|---|---|---|
| O01 | KB 온주 매수/매도 `SSAM1802/1801` | 공개 목록·요청 계약 기반 [E01] | 국내 KOSPI/KOSDAQ·정수 수량/원화 지정가·KRX 정규장으로 제한한 수동 전송 | 현재 계약 테스트·시뮬레이터 유지. R8 자동 전송은 전체 선행 검증 전 보류 |
| O02 | KB 정정/취소 `SSAM1805/1806` | 요청 일부/전부 구분과 수량 확인 [E03, E04] | 당일 전량 미체결 NEW의 첫 일부/전량 변경만 지원. 요청량은 옮기거나 취소하는 수량 | 요청 지원과 완료 판정을 분리. 추가 정정·부분 체결 후 변경은 KB-01~03 확인 후 확장 |
| O03 | 증액 시 예약금 재사용 | 공개 요청 필드만으로 가용 현금/예약 반환 시점 미확정 | 현재 선택 수량의 새 가격×수량 전체를 별도 주문가능현금으로 검사 | 차액만 검사하거나 원주문 예약금을 합산하지 않음. KB-03 보류 |
| O04 | UNKNOWN·시작 이후 SENDING 종결 | 확인 가능한 완료/상관관계 계약 부족 [E02] | 읽기 관찰·진단 유지. 반환 기록이 있는 제한 복구/전량 체결 대조와 전송 전 RESERVED 중단은 별도 구현 | 기존 검증된 경로만 유지. 주문 없음 한 번 조회로 자동 실패/재전송/가드 해제 금지. KB-01~04 |
| F01 | 국내 소수점 매도/매수/취소/조회 `SSAM5762/5763/5764`, `SSQM5765` | 공개 목록 확인 [E01]. 일반 안내는 회차 처리·6자리 수량 [E06] | 별도 어댑터 미구현. 기존 전송 allowlist에 없음, 주요 수량 필드는 4자리 | R9 정밀도·금액/수량·배분 설계 가능. API 적용 체결/취소 조건은 KB-05 확인 |
| F02 | 해외 소수점 `SKAM2201/2202`, 주문가능금액 `SPQN5472` | 공개 목록 확인 [E01] | 해외 주문/소수점 어댑터 미구현 | 국내 계약을 재사용하지 않음. 통화·시간·금액/수량·매도·취소·배분을 별도 확인 |

코드·이력 근거: [온주 계약](../../Back/spring-server/src/main/java/com/sagopalgo/api/order/client/KbLimitOrderContract.java), [수동 주문 서비스](../../Back/spring-server/src/main/java/com/sagopalgo/api/order/service/ManualOrderService.java), [실제 첫 일부 수량 변경](../orders/manual-partial-order-changes.md), [지정가 증액 제한](../orders/order-price-amendment.md), [완료 근거 조사](../orders/order-completion-evidence.md), [수량 DB 정의](../../Back/database/schema.sql).

## 5. 2026-11-02 재확인한 핵심 차이

1. `SSAM1805/1806`의 요청 `crct_clsf`에 일부/전부 값 설명이 있지만, 이것을 `SSQM2341` 응답 `crct_cncl_ccd`의 완료 코드로 사용할 근거는 없습니다.
2. `SSQM2341` 상세 정의의 `crct_cncl_ccd`, `crct_q`, `sor_cncl_q`와 원주문/수량 필드는 존재하지만 이번 응답에서 description은 null입니다. 필드 존재만으로 누적 범위·완료 의미를 확정하지 않습니다.
3. 국내·해외 소수점 API는 공개 목록에 있습니다. API 지원과 즉시 체결 여부, 사용자 계좌 권한은 각각 확인해야 합니다.
4. 이번 공개 목록의 이름 검색에서 관심목록 API는 나오지 않았습니다. 숨겨진/다른 명칭의 계약 부재까지 입증하지 않으므로 미확인으로 유지합니다.
5. 현재 분봉 거절·조회 페이지 상한·허용 주문 경로는 앱의 구현 정책입니다. 외부 API의 전체 지원 능력으로 일반화하지 않습니다.

## 6. 다음 구현이 사용할 지원 능력 계약 초안

지원표를 코드로 옮길 때 Provider/상품/시장별로 아래 항목을 둡니다. 필드 이름은 설계 제안이며 이번 작업에 API·DB를 추가하지 않습니다.

- 기능: 계좌 조회, REST 시세, 체결/호가 스트림, 투자자별 자료, 주문·변경·체결 대조.
- 범위: 상품·거래소·통화·세션·계좌 권한, 금액/수량 기준·정밀도·최소 단위.
- 시점: 공개/시장/수신 시각의 정밀도, 추정/확정, 최대 관측 지연과 결측.
- 완전성: 조회 범위·페이지 종료 근거·다음키·잘림·부분 실패·최신 완료 시각.
- 근거: 공식 문서 버전·확인일, 코드 구현 버전, 실환경 검증 범위/일자, 연결된 보류 ID.
- 운영 제한: 호출/구독 예산, 저장·활용 범위, 불명확 주문/계좌 불일치 시 차단 조건.

`SUPPORTED=true` 하나로 모든 축을 합치지 않습니다. 예를 들어 분봉 코드 미구현과 공식 API 미지원, 호출 권한 없음, 데이터 일시 실패를 서로 다른 상태로 표현합니다.

## 7. 공식 근거 목록

아래 URL은 공개 문서 GET으로 확인했습니다. 금융 거래·계좌 조회용 POST를 실행하지 않았습니다.

| 근거 | 공식 자료 | 이번 확인 범위 |
|---|---|---|
| E01 | [KB 공개 API 목록](https://openapi.kbsec.com/apidoc_b2c) | 페이지의 API 메타데이터에서 이름·경로·메서드 확인 |
| E02 | [SSQM2341 상세 필드](https://openapi.kbsec.com/api/apis/catalog/66998ea3-85f3-4060-bf6d-f88a163eee35/tr-list) | 원주문·주문/체결/잔량·변경 코드/수량 필드와 설명 여부 |
| E03 | [SSAM1805 상세 필드](https://openapi.kbsec.com/api/apis/catalog/28577def-666f-4d77-b9dc-5904db58ba49/tr-list) | 요청 일부/전부·원주문번호·수량 |
| E04 | [SSAM1806 상세 필드](https://openapi.kbsec.com/api/apis/catalog/48815fb5-53fd-4b58-905b-c04431a1e882/tr-list) | 요청 일부/전부·원주문번호·수량 |
| E05 | [KB 개발 가이드](https://openapi.kbsec.com/guide_b2c) | 인증·권한·호출 제한과 주문 가능 조건의 별도 확인 필요 |
| E06 | [KB 국내 소수점 서비스 안내](https://fdata.kbsec.com/agree/notice50.pdf) | 일반 서비스의 회차·수량 정밀도. 개별 API 전체 계약으로 대체하지 않음 |
| E07 | [KIS 공식 예제](https://github.com/koreainvestment/open-trading-api) | REST/실시간 인증·체결/호가 구독 예제. 계정별 상한은 미확정 |
| E08 | [NAVER 뉴스 검색 규격](https://api.ncloud-docs.com/docs/naver-api-hub-search-news) | 검색·날짜순·페이지 범위·일 호출 한도 안내 |
| E09 | [OpenDART 공시 검색 규격](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001) | 공시 조건·페이지 조회. 계정의 실제 한도/지연은 미측정 |

## 8. R0 완료 체크

- [x] 공식 계약·코드·실환경 증거를 분리한 지원표 작성.
- [x] 기존 미확정 주문 계약을 보류 ID와 재개 조건에 연결.
- [x] 단기·중기·최종 목표 및 초기 운용/측정 초안 작성.
- [ ] KB 답변을 실제 필드·계보·완료 예제로 대조하고 계약 테스트로 고정.
- [ ] 계정별 권한·호출/구독 상한·과거 데이터 가용성·저장 조건 확인.
- [ ] 초안 운용 범위/한도와 측정 임계값 확정, 실제 읽기 연결·지연 측정.

R0 전체가 끝난 것으로 표시하지 않습니다. 읽기 전용/격리 개발의 상세 착수 범위는 [초기 실행 계획](../project/initial-trading-policy.md#6-답변-대기-중의-실행-순서)을 따릅니다.
