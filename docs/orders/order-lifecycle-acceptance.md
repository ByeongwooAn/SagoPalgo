# 주문 흐름 통합 검증

기준일: 2026-11-02. 문의 답변 대기 중 진행할 작업으로 합의한 **주문 화면 → 실제 테스트 API → MySQL → 백엔드/앱 재시작** 검증입니다. 제품의 OrderSimulationScreen/ManualOrdersScreen을 실제 Windows 엔진에서 실행하며 HTTP·DB를 모의 응답으로 대체하지 않습니다. 이 작업은 KB의 실계좌/실제 모의투자 서버에 접속하지 않습니다.

## 고정한 완료 범위

1. 가상 매수·부분/전량 체결·매도의 자원 일치
2. 일부 변경·추가 정정·선택 예약금 재사용
3. 11개 접수/실패 시나리오, 복구·예약 중단·진단·관찰·가상 종결과 중복 전송 방지
4. 실제 JVM과 Windows 테스트 앱을 종료/재실행한 뒤 기록·차단 상태 유지
5. 실주문 OFF 화면의 승인/전송 차단 및 비시뮬레이터 테이블 보존

위 범위에서 통과하면 이번 통합 검증 묶음은 완료입니다. KB 공식 답변이 필요한 실제 주문 종결·추가 변경/예약금 처리와 별도 승인된 실거래 검증은 후속으로 보류합니다. 뉴스/AI/알림의 외부 Provider 성공, 장기 운영·Windows 배율 전체 검증을 이 결과로 대체하지 않습니다.

## 환경과 재현

프로젝트 루트 PowerShell에서 Docker Desktop의 Linux 엔진과 Flutter Windows 빌드 도구를 준비한 뒤 실행합니다. 테스트용 Windows 창이 자동으로 열리고 닫힙니다.

```powershell
./scripts/run-order-acceptance.ps1 -Flutter C:/flutter/bin/flutter.bat
```

- 전용 Compose 프로젝트는 sagopalgo-order-acceptance, 호스트 접속은 127.0.0.1:18082입니다. 운영 Compose 및 .env 대신 별도의 빈 테스트 env 파일을 명시합니다.
- Spring API와 MySQL은 internal 네트워크에만 연결합니다. Windows가 접속하는 nginx 프록시만 별도 ingress에 연결하며 전달 대상은 테스트 API로 고정합니다. API의 네트워크 개수와 internal 설정을 실행 시 확인합니다.
- DB는 sagopalgo_acceptance_test, 임시 메모리 저장소와 전용 환경 표식을 사용합니다. 운영 볼륨·계좌·인증값을 마운트하지 않습니다. 모든 Provider/자동 분석·수집·실주문 스위치는 명시적으로 OFF입니다.
- 앱 테스트의 HTTP 클라이언트는 고정 loopback의 시뮬레이터 경로와 수동 주문 GET/readiness만 허용합니다. 리다이렉트 및 다른 주소/실주문 POST를 거절합니다. 실제 제품 repository가 요청을 직렬화하고 서버 응답을 파싱합니다.
- 기존 테스트 컨테이너 또는 사용 중인 포트가 있으면 실행을 거절합니다. 실행기가 만든 컨테이너/네트워크만 finally에서 정리하며 결과 로그는 build 디렉터리에 보존합니다.
- integration_test는 Flutter SDK 의존성입니다. 일반 flutter test는 기존 test/ 회귀 검증을 실행합니다. 전용 integration_test 파일도 명시적 실행 플래그가 없으면 주문 시험을 건너뜁니다.

## 검증 항목

| 항목 | 판정 기준 |
|---|---|
| 정상 매수/매도 | 100만원에서 75,000원×2주 예약 → 1주 체결 현금 925,000원/보유 1주 → 전량 체결 850,000원/2주 → 동일 가격 전량 매도 현금 100만원/보유 0 |
| 부분·추가 변경 | 375,000원·5주 전량 예약 → 2주를 74,000원으로 이동해 가용 2,000원 → 그중 1주를 76,000원으로 추가 정정해 가용 0원 → 원주문 1주 취소로 가용 75,000원. 체결 없는 현금/보유 보존 |
| WAIT / PARTIAL_FILL / FULL_FILL | ACCEPTED/RETURNED, 전송 1회, 체결/잔량별 자원 일치 |
| REJECT | REJECTED/RETURNED, 전송 1회, 새 전송 차단 해소 |
| TIMEOUT_BEFORE_ACCEPT | UNKNOWN/RETURNED·전송 1회, 차단 유지 |
| TIMEOUT_AFTER_ACCEPT | UNKNOWN/RETURNED·전송 1회. 별도 가상 종결 확인 뒤 원본 UNKNOWN·자원/전송 횟수를 보존하고 해당 차단만 해소 |
| SAVE_FAILURE | SENDING/RETURNED에서 별도 동의 복구 → ACCEPTED, 전송 횟수 유지 |
| STOP_BEFORE_SEND | SENDING/RESERVED·0회에서 별도 동의 중단 → ABORTED, 원본 SENDING·0회 보존 |
| JOURNAL_FAILURE | SENDING/DISPATCHING·1회. 주문번호 진단 이력을 저장해도 상태/차단 유지 |
| TIMEOUT_AFTER_OPEN | UNKNOWN·미체결·전송 1회, 차단 유지 |
| TIMEOUT_AFTER_PARTIAL | UNKNOWN·부분체결·전송 1회. 대조 관찰 이력을 저장해도 차단 유지 |
| HTTP 응답 유실 | 실제 서버 커밋까지 받은 submit 응답을 테스트 클라이언트가 버림. 제품 화면은 GET 기록으로 확인하고 submit은 1회만 발생 |
| 실주문 OFF | 실제 수동 주문 화면의 승인/전송 버튼 비활성, GET만 발생 |
| 재시작 | API 컨테이너 재시작 시각 변경, 새 Windows 앱 프로세스 실행. 14개 세션의 API 응답 일치와 선택한 정상/미확정/중단 세션의 화면 차단 상태 확인 |
| DB 보존 | 재시작/재조회 전후 session_id·revision·상태 JSON SHA-256 일치. 실제 주문/승인/가드/사전검증·기존 모의 원장·보유·자본금 테이블은 0건 유지 |

## 최종 결과와 검증 버전

**합의한 통합 검증 묶음 완료.** 2026-11-02 01:27 KST 실행에서 네이티브 Windows 검증 17건(재시작 전 16건·후 1건)이 통과했습니다. 두 단계는 별도 Windows 프로세스로 실행하며 해당 단계 밖의 테스트는 의도적으로 건너뜁니다. 14개 세션의 응답·DB 상태 JSON SHA-256·revision이 재시작 전후 일치했고 네 종류의 세션을 실제 화면에서 다시 선택해 정상/차단 상태를 확인했습니다. 비시뮬레이터 테이블 7종 합계 0건을 유지했습니다.

- 제품 코드 기준: develop `3300622247ed4fc4b940b2a5aaa387947a029d9d` (PR #72 반영). 이번 변경은 테스트·실행기·개발용 의존성과 문서이며 제품 런타임 코드 오류는 검증 대상 흐름에서 재현되지 않았습니다.
- 실제 기동한 API 이미지 ID: `sha256:2425df3b6fd9f6a7ac3a7cb73b87b7ef40b169b1d5e6dcdfeafcc7c27813ee45`.
- 기존 운영 Windows Release의 `data/app.so` SHA-256: `CCEACD2562D947B11ED12D72CCCF082BF877092CD5B8059E2A66C95FB9072C5F`. 네이티브 시험은 별도 Debug 테스트 앱을 사용했으며 실행 중인 일반 Release 앱/번들은 변경하지 않았습니다.
- 실행 증거: `Front/app_version/build/order-acceptance/20261101-162348/`의 report.json, before.log, after.log, before-restart.json, after-restart.json, database-before.txt, database-after.txt, api.log. 디렉터리 이름은 UTC이고 report.checkedAt은 KST입니다. 생성 파일은 Git에서 제외합니다.
- lib/test/integration_test 정적 분석 이슈 없음. 의존성 추가 후 기존 Flutter 회귀 206건도 통과했습니다. 백엔드 소스는 바꾸지 않았으며 이전 552건(MySQL 141건)의 회귀 결과를 이번 네이티브 17건과 합산하지 않습니다.
- 실행기에서 기존 테스트 스택을 거절하고 해당 컨테이너 ID들을 바꾸지 않는 동작을 별도로 확인했습니다. 완료·실패 실행의 임시 컨테이너/네트워크는 정리했습니다. Ctrl+C 등 프로세스 강제 종료로 finally가 실행되지 않으면 전용 Compose의 잔여 컨테이너를 먼저 확인해야 하며 실행기는 이를 임의로 재사용/삭제하지 않습니다.

이번 검증은 Windows 엔진에서 제품 주문 화면을 직접 진입시키는 통합 테스트입니다. 일반 앱 전체 탭 동선·테마·트레이/알림의 Windows 운영 검증과 KB 실계좌 주문 성공을 뜻하지 않습니다. 운영 DB·.env·스위치·기존 실행 중인 앱/서버를 변경하지 않았고 추가 마이그레이션이나 운영 재배포는 필요하지 않습니다.

가상 접수/체결 결과를 실제 KB의 정정·취소 완료 계약으로 사용하지 않습니다. 문의 답변이 필요한 실제 UNKNOWN/시작 이후 SENDING 종결·추가 변경·예약금 재사용 및 별도 승인된 실제 거래 대조는 보류입니다. 11단계 자동매매도 미착수로 유지합니다.
