# R1 자동 수집 운영 검증

기준일: 2026-11-03. [수집 계약](account-observation-collection.md)과 [실제 읽기 관찰 결과](account-observation-live-validation.md)를 이어서 검증합니다. 정상 연속 수집의 검증과 부분 실패 시 중단·복구 검증을 구분합니다.

**목차**

- [범위](#범위) · [실제 1주기 검증 결과](#실제-1주기-검증-결과) · [격리 검증](#격리-검증)
- [읽기 전용 운영 상태 점검 도구](#읽기-전용-운영-상태-점검-도구) · [도구 검증과 재현](#도구-검증과-재현) · [연속 운용 전에 남은 조건](#연속-운용-전에-남은-조건)

## 범위

KB-07의 지정일 주문 ‘조회 내역 없음’ 처리 조건이 미확정이므로 정상 SUCCESS의 장기 반복 수집을 완료로 판정하지 않습니다. 이번 실환경 시험은 기존 배포 이미지의 수집기를 일시적으로 켜 자동 관찰 1회와 부분 실패 중단을 확인하고, 다시 OFF로 돌린 뒤 재시작 보존·명시적 재개를 확인하는 범위입니다. 주문 스위치는 OFF를 유지합니다.

시험 전 조건은 현재 수집 OFF·NOT_STARTED, 간격 900초, 기존 수동 관찰 1건, 개인용/계좌 조회/연결 설정 활성, 주문 사전검증·실주문 스위치 OFF입니다. 현재 Windows PC의 로컬 Docker 배포를 대상으로 하며 Ubuntu 서버 검증과 구분합니다.

기본 간격 900초를 바꾸지 않고 일시 활성화 구간을 그보다 짧게 제한합니다. 정상 결과가 나오더라도 다음 정상 주기 전에 OFF로 복귀하도록 하며, 예상한 부분 실패를 관찰하면 PAUSED 상태에서 다음 60초 스케줄러 확인을 넘겨 새 관찰이 생기지 않는지 확인합니다. 예외 경로에서도 환경 설정 원복과 OFF 배포 확인을 시도합니다. ACTIVE/PENDING을 시간 경과로 강제 해제하지 않습니다.

## 실제 1주기 검증 결과

2026-11-03 한국 시간 10:11~10:15에 실제 배포된 수집기의 제한 시험을 완료했습니다. 운영 자료는 Git 제외 경로 `Back/spring-server/build-codex-collection-operations/`의 작업 기록·상태 보고서·이벤트 기록에 보관합니다. 해당 경로의 일회 실행 스크립트는 이 환경의 원복 제어용 로컬 산출물이며 일반 배포 도구로 커밋하지 않습니다.

| 단계 | 확인 결과 |
|---|---|
| 기준 상태 | OFF·NOT_STARTED, 수동 관찰 1건, 간격 900초, 주문 스위치 OFF |
| 일시 활성화 | 기존 Spring 이미지 그대로 API 컨테이너만 재생성. 간격/계좌/주문 설정은 유지 |
| 첫 스케줄 실행 | 수동 저장 POST 없이 자동 관찰 1건 생성·COMPLETED/PARTIAL 저장, PAUSED/SNAPSHOT_PARTIAL |
| 중단 유지 | PAUSED 확인 후 65초를 더 관찰해 다음 스케줄러 tick 이후에도 동일 요청·이력 2건 유지 |
| OFF 원복과 재시작 | 원래 환경 파일 내용을 바이트 단위로 복구하고 API 컨테이너 재생성. OFF에서도 같은 PAUSED 요청 보존 |
| 명시적 재개 | 마지막 요청 ID를 기록한 뒤 재개 POST 1회. GET으로 OFF·IDLE, 기존 COMPLETED/PARTIAL 유지와 다음 실행 가능 시각 확인 |
| OFF 안정성 | 재개 후 65초를 더 관찰해 IDLE·OFF·같은 요청·이력 2건 유지 |
| 최종 확인 | GET 점검 통과. 수집 OFF, IDLE, 진행 요청 없음, 주문 스위치 모두 OFF |

Spring API 컨테이너만 두 번 재생성했고, Nginx는 새 upstream 주소를 반영하기 위해 설정 reload만 수행했습니다. MySQL·AI·프록시 컨테이너 ID는 유지됐습니다. 이미지 재빌드·앱 변경·DB 마이그레이션·주문·정정·취소·강제 상태 해제는 수행하지 않았습니다. 시험용 격리 MySQL/네트워크는 검증 후 정리했습니다.

상태 전이는 `OFF/NOT_STARTED → ON/PAUSED → OFF/PAUSED → OFF/IDLE`입니다. ACTIVE가 API 관측 사이에 빠르게 지나갈 수 있으므로 이번 실환경에서 ACTIVE 순간을 직접 관측했다고 주장하지 않습니다. 예약/전송 전 커밋과 ACTIVE/PENDING 보호는 격리 검증 근거를 따릅니다.

최종 IDLE은 다음 주기를 허용한 저장 상태이며 설정 OFF이므로 실행되지 않습니다. 기존 PARTIAL 관찰이 SUCCESS로 바뀐 것이 아닙니다. 수동 1건과 자동 1건이 남아 있으며 반복 재개·새 수동 저장으로 실패를 우회하지 않았습니다. 이 결과는 부분 실패 중단·상태 보존·OFF 재개를 검증한 것이고, 정상 실계좌의 연속 수집이나 호출 예산 확정은 아래 후속 조건으로 남습니다.

## 격리 검증

전용 MySQL Compose의 루프백 `33317`, DB 이름 `sagopalgo_account_observation_test`, 전용 마커를 확인한 환경에서 기존 `AccountObservationCollection*` 테스트를 실행했습니다. 관찰기는 mock이고 실제 KB 키·운영 DB를 사용하지 않습니다.

- 설정 테스트 7건: 기본 OFF·900초, 활성화 시 스케줄러 등록과 초기 무호출, 간격 경계.
- 서비스 테스트 25건: 정상 주기·부분 실패·명시적 재개·잘못된 범위/설정/저장 결과의 차단.
- MySQL 통합 테스트 14건: 8개 독립 실행기의 단일 소유권, 외부 조회 전 예약 커밋, 재생성 후 cooldown과 종료 결과 대조, orphan/PENDING 보존, 갱신 롤백, 손상 결과 차단, HTTP 상태/재개 경로.

총 46건 통과, 실패·오류·제외 0건입니다. 기존 서비스/Mapper 재생성 검증은 프로세스 재시작 검증과 구분합니다. 실환경의 서버 재생성 검증은 별도 결과로 기록합니다.

## 읽기 전용 운영 상태 점검 도구

[check-account-collection.ps1](../../scripts/check-account-collection.ps1)은 GET만 사용합니다. 수집 설정을 바꾸거나 재개 POST를 보내지 않으며 KB 조회를 직접 실행하지 않습니다. 별도의 영수증/행·금액을 저장하지 않고 현재 설정·실행 상태·마지막 종료 기록·최근 이력 ID만 보고합니다.

```powershell
New-Item -ItemType Directory -Path 'Back/spring-server/build-codex-collection-operations' -Force | Out-Null
./scripts/check-account-collection.ps1 `
  -ApiBaseUrl 'http://192.168.0.2:8081' `
  -ReportPath 'Back/spring-server/build-codex-collection-operations/status.json' `
  -ExpectedEnabled OFF -ExpectedState IDLE
```

상태를 명시하지 않으면 현재 상태의 계약을 검사합니다. `ExpectedEnabled`의 기본은 OFF이고 ON은 ON 상태를 기대한다는 검사 조건일 뿐 설정 변경이 아닙니다. 다음을 확인합니다.

1. 응답의 no-store·readOnly·usableForTrading, 설정의 boolean 타입, 간격과 상태 enum, 요청 UUID·고정 실패 코드.
2. 주문 사전검증·실주문 스위치 OFF. 주문 준비 API는 설정/저장소만 읽으며 KB를 호출하지 않습니다.
3. PAUSED/IDLE의 마지막 요청을 상세 GET으로 대조해 종료 상태·마지막 관찰 결과와 읽기 계약 일치를 확인합니다. IDLE의 마지막 결과가 이전 PARTIAL일 수도 있으며 재개가 그 관찰을 수정하지 않습니다.
4. ACTIVE는 실행 중 또는 결과 미확정으로 종료 코드 1을 반환하고 해제·재개·자동 만료시키지 않습니다. PENDING·404·손상/불일치 기록 역시 확인 성공으로 올리지 않습니다.
5. 최근 최대 100개 관찰의 ID와 마지막 요청 포함 여부. 최근 목록 밖의 기록이나 다른 계좌/키 범위로 바뀐 경우 전체 이력의 부재를 추정하지 않고 점검 실패로 남깁니다.

이전 보고서와 변화가 없어야 하는 구간은 다음과 같이 확인합니다. 보고서 경로를 서로 다르게 지정하며 이전 파일은 덮어쓰지 않습니다.

```powershell
./scripts/check-account-collection.ps1 `
  -ApiBaseUrl 'http://192.168.0.2:8081' `
  -ReportPath 'Back/spring-server/build-codex-collection-operations/recheck.json' `
  -ExpectedState IDLE `
  -PreviousReport 'Back/spring-server/build-codex-collection-operations/status.json' `
  -RequireUnchanged
```

설정·상태·마지막/진행 요청·고정 사유·최근 요청 목록이 다르면 종료 코드 1입니다. 같은 서버 주소의 다른 연결 범위나 수동 관찰 추가도 변화로 탐지할 수 있으며 원인을 자동 판정하지 않습니다. 이력 변화 없음은 다른 화면/기존 API의 모든 KB 호출이 없었다는 증거가 아닙니다.

정상 종료 코드 0·CHECK_PASSED는 관측 시점의 상태 검사 통과입니다. 장기 운용 승인·호출 한도 확정·KB-07 해결·완전한 계좌 대조를 뜻하지 않습니다. 보고서는 `build-codex*` 아래 등 Git 제외 경로에 보관하며 실제 환경 파일과 함께 커밋하지 않습니다.

## 도구 검증과 재현

```powershell
python -m unittest discover -s scripts/tests -p test_account_collection_check.py -v
```

로컬 모의 HTTP 테스트 7건이 모두 GET임을 확인하고 OFF 초기 상태, PAUSED 종료 대조, 이전 PARTIAL을 보존한 IDLE, ACTIVE 미확정 차단, PENDING/불일치/거래 가능 플래그 차단, 기준 보고서 비교·원본 보존, 설정·HTTP·캐시·계약 오류 비노출을 검증합니다. 실제 KB나 배포 DB를 사용하지 않습니다.

격리 MySQL 실행/정리 절차는 [관찰 이력 테스트](account-observation-history.md#5-격리-검증과-재현)를 따릅니다. 테스트 필터는 `--tests '*AccountObservationCollection*'`입니다. 해당 테스트는 명시적 `SAGOPALGO_ACCOUNT_OBSERVATION_MYSQL_TEST=true`에서만 전용 DB 통합 검증을 포함합니다. 운영 Compose나 운영 DB에서 fixture 정리를 실행하지 않습니다.

## 연속 운용 전에 남은 조건

- KB-07의 정상 빈 주문 응답과 업무 실패를 분리할 공식 코드·건수·다음키·조회일 조건. 실패 메시지만으로 SUCCESS로 바꾸지 않습니다.
- 키/계좌/API별 호출 예산과 다른 앱·수동 조회·페이지·OAuth 요청을 합친 예산. 관찰의 상한은 보유 최대 10페이지 + 잔고 2회 + 주문 최대 10페이지로 최대 22개 조회이며 토큰 호출은 별도입니다. 이 코드 상한이 KB의 승인된 한도라는 뜻은 아닙니다.
- 보유 종목·소수점 수량이 있는 실제 사례, 장중 입출금/체결 중 시점 차이, 장기간 장애·종료 미확정의 운영 해결 절차.
- 이번 부분 실패 중단/복구 결과와 별개인 정상 실계좌의 다음 주기 반복 수집·장시간 재시작 검증. 이번 시험으로 연속 운용이나 주문을 켜지 않습니다.
