# SagoPalgo 문서

## 개발 현황과 학습

- 네 종목의 학습·앱 연결·수동 모의매매 순서와 단계별 완료 조건을 확인합니다. [1차 학습 프로토타입](project/learning-prototype.md#실행-순서와-완료-기준)
- 완료율과 작업별 검증 근거를 확인합니다. [번호별 체크리스트](project/numbered-work-progress.md#현재-개발-진척도) · [개발 진척도](project/development-progress.md)
- 착수할 수 있는 일과 보류 항목의 재개 조건을 찾습니다. [남은 실행 단위](project/remaining-development-units.md) · [보류 작업](project/deferred-work.md)
- 전체 개발 목표와 단계별 의존성을 확인합니다. [실시간 자동매매 로드맵](project/realtime-trading-roadmap.md) · [미국주식 학습·자동매매 로드맵](project/us-equity-ai-trading-roadmap.md)
- 모델을 재현하거나 학습 결과를 비교합니다. [학습 보고서 작성 기준](project/ai-model-reporting.md) · [삼성전자·SK하이닉스 독립 평가](project/daily-learning-evaluation.md) · [애플·엔비디아 독립 평가](project/us-daily-learning-evaluation.md)

## 설치, 테스트, 시스템 구조

- 백엔드 설치·업데이트, 네트워크와 민감정보 설정을 확인합니다. [Docker 배포 구조](architecture/docker-architecture.md)
- Spring 서버의 Java4Shell 영향과 운영 패치·접근 점검 순서를 확인합니다. [Java4Shell 운영 영향 평가](operations/java4shell-security-assessment-20261120.md)
- 서버를 실행하고 API, Flutter 화면, 주문 상태를 점검합니다. [수동 테스트 가이드](operations/manual-test-guide.md)
- 실시간 수집부터 학습·주문까지의 목표 흐름과 초기 설계 이력을 확인합니다. [목표 시스템 구조](architecture/target-system-architecture.md) · [기존 설계·구현 이력](architecture/personal-windows-investment-assistant.md)
- 파일 게시 중 Windows 잠금이 발생했을 때의 재시도와 실패 처리를 확인합니다. [Windows 파일 게시 복구](operations/windows-file-publication.md)

## API, 계좌, 주문

- 서버 요청·응답과 저장 구조를 확인합니다. [API 명세](contracts/api-spec.md) · [DB 스키마](contracts/database-schema.md)
- 증권사별 지원 범위와 확인이 필요한 KB 계약을 찾습니다. [지원·계약 매트릭스](contracts/trading-api-contract-matrix.md) · [KB 계약 보류·재개 조건](contracts/kb-contract-blockers.md)
- KB 계좌의 관찰·저장·대조·화면과 자동 수집을 확인합니다. [계좌 관찰 계약](accounts/account-snapshot-contract.md) · [자동 수집 운영 검증](accounts/account-collection-operations.md) · [계좌 문서 전체](accounts/)
- 신규·정정·취소, 전송 복구와 주문 대조를 확인합니다. [KB 수동 주문](orders/kb-manual-orders.md) · [주문 흐름 통합 검증](orders/order-lifecycle-acceptance.md) · [주문 문서 전체](orders/)

## 실시간 수집과 체결 연구

- 시세 수집·저장·내보내기, 입력 수신과 소켓 복구를 확인합니다. [실시간 수집 구조](market-data/realtime-data-pipeline.md) · [시장 데이터 문서 전체](market-data/)
- 호가 단위, 체결 추정·대조, 거래 비용·세금의 근거를 찾습니다. [과거 호가 단위](execution-research/historical-tick-rules.md) · [체결 품질 검증](execution-research/quote-execution-quality.md) · [체결 연구 문서 전체](execution-research/)
- 종목별 가상 매매 규칙, Docker 테스트와 일별·최종 보고서를 확인합니다. [모의매매 테스트](paper-trading/README.md)

## 과거 데이터와 재현

| 찾는 내용 | 시작 문서 | 전체 문서 |
| --- | --- | --- |
| 종목군, 상장·폐지·편입, 종목명과 식별자 | [KRX 종목 목록과 변화 이력](historical-data/universe/krx-universe-history.md) | [종목군](historical-data/universe/) |
| 거래 달력, 결제일, 정규장과 예외 세션 | [개장일 재구성과 특수 세션](historical-data/sessions/market-calendar-session-coverage.md) | [거래 세션](historical-data/sessions/) |
| 배당·소각·합병·분할과 종목별 거래소 조치 | [기업행사 결과 감사](historical-data/corporate-actions/historical-corporate-action-outcome-census.md) · [배당 지급 대조](historical-data/corporate-actions/historical-dividend-payments.md) | [기업행사](historical-data/corporate-actions/) |
| 과거 가격 수집, 기준정보 검증, 시점 재현 | [과거 데이터 재현 구조](historical-data/replay/historical-data-replay.md) · [가격 수집](historical-data/replay/historical-price-acquisition.md) | [재현](historical-data/replay/) |

## 자료 폴더

- [프로젝트 문서 전체](project/) · [아키텍처 문서 전체](architecture/) · [계약 문서 전체](contracts/) · [운영 문서 전체](operations/)
- [예제·스키마·검증 자료](examples/) · [시스템 구조도](images/)
