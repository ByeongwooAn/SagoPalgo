# U07-D KIS 전체 세션 관찰 · 2026-11-17~22

삼성전자 `005930`의 KIS KRX 공개 체결 `H0STCNT0`과 호가 `H0STASP0`을 한 연결에서 구독합니다. 구독 예산은 2입니다. Docker의 기존 서버는 장중 준비 실행 전 실시간 수집이 `DISABLED`임을 확인했습니다. 관찰 수집기는 별도 Docker 네트워크와 전용 MySQL의 공개 시세 테이블을 사용합니다. 매 실행 전과 실행 중 약 1분 간격으로 기존 서버 상태를 확인하며, 수집 OFF를 확인할 수 없으면 시작을 건너뛰거나 관찰 수집기를 중지합니다.

| 날짜(KST) | KRX 정규장 | 관찰 실행 |
|---|---|---|
| 11월 17일·18일·20일 | 09:00~15:30 | 08:45~15:45 |
| 11월 19일 수능일 | 10:00~16:30 | 09:45~16:45 |
| 11월 21일·22일 | 주말 휴장 | 수집기를 시작하지 않고 15:45에 미실행 기록 |

거래 일정은 [KRX 거래일 규정](https://regulation.krx.co.kr/contents/RGL/03/03010100/RGL03010100T1.jsp), [KRX 정규장 안내](https://global.krx.co.kr/contents/GLB/01/0109/0109000000/guide_to_trading_in_the_korean_stock_market.pdf), [수능일 거래시간 공지](https://www.hanwhawm.com/main/bbs/indexView.cmd?cc_gubun=1&mode=center&nn_id=69155&num=1975&pageVal=1&vc_bid=notice)를 근거로 작성했습니다.

관찰 실행과 자료는 Git 제외 경로 `Back/spring-server/build-codex-u07/capture-20261117/`에 있습니다. 11월 16일 장중 준비 검증의 `pilot-journal/`과 11월 17~22일 관찰용 `journal/`을 구분합니다. 일정과 실제 실행 여부는 `plan.json`과 `execution.log`를 대조합니다. 마지막 휴장일 체크포인트 뒤 `session-observation.json`과 `operations-status.json`을 생성합니다.

11월 16일 09:50:50~09:52:40 KST 준비 검증에서 `DATA_READY`를 확인했습니다. 저널 17개 레코드의 해시 체인과 `CLEAN_END`를 검증했고, 최종 삽입 기록 965건을 전용 MySQL의 체결 508건·호가 457건과 대조했습니다. 분봉은 3개, 저장 실패는 0건입니다. 준비 실행 종료 뒤 관찰 컨테이너가 11월 17일 개장 전 시작 시각을 기다리는 상태를 확인했습니다.

완료 판정에서는 거래일별 개장 전·정규장·마감 후 기록과 휴장일 미실행 기록을 확인합니다. 재접속 발생 여부, 자료 수신, 저장·중복·실패 건수, 정상 종료와 관찰 공백을 함께 검토합니다. Docker와 기존 서버가 관찰 기간 동안 가동돼야 합니다. 호스트 중단이나 시작 시각을 놓친 날은 별도로 기록하고 보완 여부를 판정합니다. [보고서 기준](stream-restart-session-observation.md#u07-d-관찰-계획과-보고서)
