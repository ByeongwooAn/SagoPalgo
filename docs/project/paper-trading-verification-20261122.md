# 1차 학습 프로토타입 4단계 수동 모의매매 검증 · 2026-11-22

**검증 진행 중.** 별도 MySQL 8.4에서 네 종목의 모의 체결 8건을 API와 KRW·USD 원장에 대조했습니다. 운영 DB에 028을 적용하고 Windows 앱의 USD 모의 현황을 복구했습니다. 주문 단계의 만료·시세 지연·KRW 재전송과 정규장 앱 체결 대조가 남았습니다. [4단계 완료 기준](learning-prototype.md#4단계-앱에서-수동-모의매매-검증)

## 운영 신호와 Windows 앱

11월 22일 21:03~21:06 KST에 로컬 운영 API에서 11월 20일 일봉에 기반한 신호를 조회했습니다. 두 시장 모두 주말이어서 운영 모의 주문은 제출하지 않았습니다.

| 종목 | 장 마감 모델 | 상승 확률 | 만료(KST) | 주문 경로 관찰 |
| --- | --- | ---: | --- | --- |
| 삼성전자 `005930` | 관망 | 34.34% | 11-23 15:30 | 저장 추천 `HOLD` |
| SK하이닉스 `000660` | 매수 관찰 | 60.81% | 11-23 15:30 | 저장 추천 `HOLD`, Windows 모의매수 비활성 |
| 애플 `AAPL` | 관망 | 47.04% | 11-24 06:00 | USD 주문 요청은 티커·거래소·매수/매도·수량·요청 ID를 받음 |
| 엔비디아 `NVDA` | 관망 | 85.79% | 11-24 06:00 | USD 주문 요청은 애플과 같은 계약 사용 |

KRW 모의 현황은 HTTP 200이었습니다. Windows 앱에서 SK하이닉스는 **보유 유지**로 표시됐고 **AI 신호로 모의매수** 버튼은 비활성이었습니다. 주문 경로는 장 마감 모델의 `BUY_WATCH`와 별도로 저장 추천의 `BUY`를 요구합니다.

028 적용 전 Windows 앱에서 **모의 → 미국주식 모의매매 (USD)**를 열었을 때 서버 내부 오류가 표시됐습니다. 해당 API는 HTTP 500 `INTERNAL_ERROR`를 반환했습니다. 운영 MySQL의 스키마 조회에서 `trade_records`가 있었고 `paper_us_accounts`와 `paper_us_trades`는 조회되지 않았습니다. 서버 로그에서 `paper_us_accounts` 부재로 초기 자금 조회가 실패한 것을 확인했습니다. [028 마이그레이션](../../Back/database/migrations/028_us_paper_trading.sql) · [모의매매 API](../contracts/api-spec.md#14-모의매매-api)

애플·엔비디아의 주말 KB 시세 응답에는 가격과 서버 수신 시각 `receivedAt`이 있었습니다. 응답에는 거래소 체결 시각이나 지연 여부가 없었습니다. 이후 장중 검증에서는 공급자 체결 시각과 서버 수신 및 가상 체결 시각을 각각 확인해야 합니다.

## 운영 DB 028 적용과 USD 화면 복구

11월 22일 21시대 KST에 로컬 운영 MySQL의 전체 논리 백업을 사용자 프로필의 접근 제한 폴더에 저장했습니다. gzip 검사를 통과했고 컨테이너 원본과 호스트 백업의 SHA-256이 일치했습니다. 검증된 백업을 확보한 뒤 028 SQL을 운영 DB에 적용했습니다. [백업·마이그레이션 절차](../architecture/docker-architecture.md#기존-ubuntu-db의-kb-점검-이력-테이블)

| 확인 항목 | 결과 |
| --- | --- |
| USD 스키마 | `paper_us_accounts`·`paper_us_trades`, 외래 키 2개, `(user_id, request_id)` 고유 키 확인 |
| 기존 KRW 원장 | `trade_records` 덤프의 적용 전후 SHA-256과 API 체결 목록 일치 |
| USD 현황 API | HTTP 200, 통화 `USD`, 미개설 계좌의 포지션과 체결 목록 0건 |
| Windows 앱 | **미국주식 가상 계좌** 진입 및 **USD 시작 자금 설정** 버튼 표시 |
| USD 모의계좌 개설 | 사용자 요청액을 직전 거래일 기준환율로 환산해 앱에서 개설. 앱과 API의 시작 자금·현금이 DB와 일치했고 체결 0건 확인 |

## 격리 MySQL 원장 대조

Spring 모의매매 컨트롤러를 테스트 요청으로 실행하고 MyBatis가 MySQL에 저장한 원장을 대조했습니다. KRW 매수 경로에는 유효한 저장 `BUY` 추천과 장 마감 모델 증거를 테스트 입력으로 넣었습니다. 네 종목의 시세는 지정 가격을 사용했습니다. USD 테스트 주문은 현재의 티커 기반 경로를 실행했습니다. Flutter 테스트에서는 앱의 주문 입력·통화별 경로와 USD 응답 유실 재시도를 확인했습니다. [Spring 통합 테스트](../../Back/spring-server/src/test/java/com/sagopalgo/api/papertrading/service/UsPaperTradingMysqlIntegrationTest.java) · [Flutter 화면 테스트](../../Front/app_version/test/paper_trading_screen_test.dart)

| 원장 | 종목 | 매수 단가 × 주 | 매도 단가 × 주 | 매도 실현손익 |
| --- | --- | ---: | ---: | ---: |
| KRW | 삼성전자 | 70,000 × 2 | 71,200 × 1 | +1,200 |
| KRW | SK하이닉스 | 188,000 × 1 | 184,000 × 1 | −4,000 |
| USD | 애플 | 180.1250 × 2 | 182.5000 × 1 | +2.37 |
| USD | 엔비디아 | 120.1250 × 1 | 119.1150 × 1 | −1.01 |

체결 8건의 단가·수량·손익·체결 ID·서버 체결 시각이 API와 DB에서 일치했습니다. DB 체결 시각은 실제 테스트 요청 구간 안에 있었으며 저장 정밀도는 KRW 초, USD 마이크로초입니다. 원장 4행씩을 독립적으로 대조했습니다. KRW는 현금 927,200원, 실현손익 −2,800원, 평가손익 +1,200원이었습니다. USD는 현금 821.24달러, 실현손익 +1.36달러, 평가손익 +2.38달러였습니다. USD는 체결 금액과 매도 원가를 센트 단위로 반올림하므로, 애플 부분 매도의 매도 원가 180.13달러와 남은 원가 180.12달러가 합계 360.25달러를 이룹니다.

## 예외 처리

| 조건 | 확인 결과 |
| --- | --- |
| KRW·USD 현금 부족, 보유 수량 초과 | 네 요청 모두 HTTP 400으로 거절. 기존 행과 기록된 수량을 보존 |
| USD 동일 요청 ID 및 동일 주문 | HTTP 200, 기존 체결 1행과 현금 유지. 앱의 응답 유실 재시도는 같은 ID 전송 |
| USD 동일 요청 ID 및 다른 수량 | HTTP 409 `DUPLICATE_RESOURCE`, 추가 체결 0행 |
| KRW 만료된 장 마감 모델을 담은 저장 `BUY` | 만료 1분 뒤 해당 추천을 보내면 HTTP 200, 체결 1행 추가 |
| KRW·USD 지연 시세 입력 | 테스트 시세의 서버 수신 시각을 15분 전으로 지정했을 때 각각 HTTP 200, 체결 1행씩 추가 |
| KRW 동일 추천·수량 재전송 | 같은 요청을 다시 보내면 HTTP 200, 체결 1행 추가. 원래 체결과 합계 2행 |

만료·지연·KRW 재전송은 동일한 격리 DB에서 별도의 진단 요청으로 재현했습니다. 장 마감 모델 카드의 만료 표시와 주문 서버의 만료 판정은 서로 다른 경로입니다. 지연 시험은 오래된 수신 시각을 제어한 결과이며, 공급자의 실제 지연 시간 측정에는 거래소 시각이 필요합니다.

## 원장 대조 재실행

Spring 전체 테스트 826건 중 672건 통과, 154건 건너뜀, 실패 0건이었습니다. 3건의 격리 MySQL 통합 테스트는 모두 실행했습니다. 모의매매 화면·API 저장소·장 마감 모델 카드의 Flutter 테스트 10건도 통과했습니다.

`Back/spring-server`에서 새 MySQL 컨테이너를 사용합니다. 테스트는 DB 이름을 확인하고 스키마를 생성한 후 테스트 사용자별 원장을 구성합니다.

```powershell
docker run --rm -d --name sagopalgo-stage-four-mysql -p 127.0.0.1:33428:3306 -e MYSQL_ROOT_PASSWORD=us-paper-test-only -e MYSQL_DATABASE=sagopalgo_us_paper_test mysql:8.4
docker exec -e MYSQL_PWD=us-paper-test-only sagopalgo-stage-four-mysql mysql -h 127.0.0.1 -uroot sagopalgo_us_paper_test -e "SELECT 1"
$env:SAGOPALGO_US_PAPER_MYSQL_PORT = '33428'
.\gradlew.bat test --tests '*UsPaperTradingMysqlIntegrationTest'
docker stop sagopalgo-stage-four-mysql
```

## 4단계에서 남은 검증

1. 장 마감 모델과 주문 요청의 연결 기준을 정하고, 만료·지연 시세·KRW 재전송에서 추가 체결이나 잔고 변화가 없음을 API와 DB에서 재검증합니다. 장 마감 모델이 매수 관찰을 반환한 경우의 KRW 저장 추천 처리와 USD 주문에 대응 신호를 남기는 범위도 확인합니다.
2. 두 시장의 정규장에서 Windows 앱으로 수동 모의 주문을 실행합니다. 네 종목의 신호, 공급자 시세·시각, 수량, 손익, 통화별 원장을 대조합니다. 관망 신호는 실제 모델 결과를 기록하고 주문 경로는 테스트 입력으로 확인합니다. 다음 정규장 기준은 KOSPI 11월 23일 09:00~15:30 KST, NASDAQ 11월 23일 23:30~11월 24일 06:00 KST입니다. [KRX 정규장](https://global.krx.co.kr/contents/GLB/06/0602/0602020204/GLB0602020204T1.jsp) · [NASDAQ 정규장과 휴장일](https://www.nasdaq.com/market-activity/stock-market-holiday-schedule)

4단계 완료와 5단계 착수는 위 확인을 마친 뒤 진행합니다. [단계별 실행 순서](learning-prototype.md#실행-순서와-완료-기준)
