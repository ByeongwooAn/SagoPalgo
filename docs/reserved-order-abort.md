# 전송 시작 전 예약 중단

2026-11-01, D(10)의 SENDING 후속 기능입니다. 전송 시작 전에 남은 로컬 예약을 별도 동의로 중단합니다. KB 주문 취소나 증권사 미접수 판정이 아닙니다.

| 단계 | 처리 |
|---|---|
| RESERVED | SENDING·현재 계좌·실행 소유권과 시작/반환 결과 부재를 확인한 경우만 중단 가능 |
| ABORTED | 중단 감사가 일치하면 해당 명령만 신규 전송 차단 집계에서 제외 |
| DISPATCHING / LEGACY_UNVERIFIED | 시작 이후 또는 증거 누락으로 중단 불가, 기존 차단 유지 |
| RETURNED / UNKNOWN | 기존 저장 결과 복구·대조 정책 적용, 이 기능으로 해제하지 않음 |

중단은 사용자 → 명령 → 전송 기록 순서로 잠그고 RESERVED→ABORTED와 감사 저장을 한 트랜잭션에서 수행합니다. 전송 시작은 같은 행의 RESERVED→DISPATCHING 조건부 갱신을 먼저 커밋해야 외부 전송에 진입할 수 있습니다. 두 경로 중 하나만 성공하므로 중단이 먼저 확정되면 지연된 실행자도 전송을 시작할 수 없습니다. 전송 시작이 먼저 확정되면 중단을 거절합니다. 중단 감사 저장 실패는 단계 변경도 롤백합니다.

`manual_order_reservation_aborts`에 실행 키·계좌 지문·시각을 저장하고 원본 명령 SENDING·승인 제출 가드·원주문 변경 가드를 보존합니다. 감사의 사용자/키/계좌/시각과 시작·반환 필드 부재가 모두 일치할 때만 차단 집계에서 제외합니다. 다른 SENDING/미종결 UNKNOWN은 계속 차단합니다. 같은 승인이나 자식 변경을 재전송할 수 없으며 새 승인은 기존 안전 조건을 다시 통과해야 합니다. 늦은 결과 콜백은 검증된 중단을 덮어쓰지 않습니다.

## 화면 확인

백엔드와 Windows 앱을 함께 갱신합니다. 먼저 `모의 → 주문 시뮬레이션`의 새 세션에서 확인합니다.

1. `전송 예약 직후 중단` 시나리오를 선택해 별도 승인·가상 전송을 진행합니다. SENDING/RESERVED·모의 전송 0회와 신규 전송 차단을 확인합니다.
2. `전송 전 가상 예약 중단`을 열고 동의하지 않은 채 취소합니다. 단계·차단·전송 횟수가 유지되어야 합니다.
3. 다시 열어 확인 체크 후 중단합니다. ABORTED·원본 SENDING 보존·전송 0회·중단 시각, 현금/보유 불변과 새 주문 진입 가능을 확인합니다.
4. 새로고침·재진입 후에도 유지되어야 합니다. 중단 응답 유실은 자동 POST 없이 GET만 재조회합니다. 같은 명령의 저장된 중단 출처를 확인한 경우만 화면 대기를 해소합니다.
5. 별도 세션의 `접수 후 반환 기록 실패`는 DISPATCHING·전송 1회·차단을 유지하고 중단 버튼이 없어야 합니다. UNKNOWN도 이 기능으로 해제되지 않아야 합니다.

실제 기록은 `보유 → KB 수동 주문 → SENDING → 전송 기록 확인·복구`에서 서버가 `abortable=true`인 경우에만 별도 체크와 `전송 전 예약 중단` 버튼을 제공합니다. 실주문 스위치가 OFF여도 가능하지만 현재 계좌 지문은 일치해야 합니다. 검증을 위해 운영에 가짜 SENDING을 만들거나 실제 장애를 유발하지 않습니다.

## API

- POST `/api/v1/orders/manual/{id}/dispatch/abort-reservation`
- POST `/api/v1/orders/simulations/{sessionId}/commands/{id}/abort-reservation`

본문은 `{acknowledged:true,confirmation:"전송 전 예약 중단"}`입니다. 실제 GET dispatch 응답에 `abortable,reservationAbort`가 추가됩니다. 실제 주문 이력에도 `reservationAbort={source:"LOCAL_BEFORE_DISPATCH",abortedAt}`가 추가되며 실행 키·계좌 지문은 공개하지 않습니다. ABORTED에는 증권사 반환 receipt를 만들어 넣지 않습니다.

가상 명령은 `abortable,reservationAbort={source:"SIMULATION_BEFORE_DISPATCH",abortedAt}`를 제공합니다. 가상 전송 0회·시작/반환/주문번호 부재·소유권 검증을 통과해야 합니다. 실제/가상 출처를 서로 대체할 수 없으며 이전 JSON의 누락·잘못된 근거를 추정해서 보충하지 않습니다. 반복 요청은 감사 한 건을 유지합니다.

## 022 백업·적용과 배포

사용자가 메인 PC 구동 테스트 완료를 확인했습니다. 앞선 메인 PC DB 점검은 021까지였으며 **022는 아직 적용하지 않았습니다**. Ubuntu의 별도 DB 상태나 실제 주문·계좌 대조 완료를 뜻하지 않습니다. 새 초기 DB는 schema.sql에 포함되며 기존 DB는 백업 후 022를 적용해야 합니다. 미적용 시 수동 주문 저장소를 안전하게 차단하고 016·017·019·022 확인 안내를 반환합니다. 가상 중단은 기존 018 JSON을 사용합니다.

PR 병합·최신 코드 반영 후 프로젝트 루트 PowerShell에서 실행합니다. 실제 주문 스위치는 기존 OFF 상태를 유지합니다. 아래 명령은 백업/SQL을 컨테이너 내부에서 처리해 PowerShell 리다이렉션 인코딩을 피합니다.

```powershell
$backup = "sagopalgo-before-022-$(Get-Date -Format yyyyMMdd-HHmmss).sql"
docker compose --env-file .env exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --routines --triggers "$MYSQL_DATABASE" > /tmp/sagopalgo-before-022.sql'
if ($LASTEXITCODE -ne 0) { throw '백업 생성 실패' }
docker compose --env-file .env cp mysql:/tmp/sagopalgo-before-022.sql $backup
if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $backup) -or (Get-Item -LiteralPath $backup).Length -eq 0) { throw '로컬 백업 확인 실패' }
docker compose --env-file .env cp Back/database/migrations/022_reserved_order_aborts.sql mysql:/tmp/022_reserved_order_aborts.sql
if ($LASTEXITCODE -ne 0) { throw '마이그레이션 복사 실패' }
docker compose --env-file .env exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot "$MYSQL_DATABASE" < /tmp/022_reserved_order_aborts.sql'
if ($LASTEXITCODE -ne 0) { throw '022 적용 실패' }
docker compose --env-file .env exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot "$MYSQL_DATABASE" -e "SHOW CREATE TABLE manual_order_reservation_aborts; SHOW CREATE TABLE manual_order_dispatches;"'
```

중단 테이블의 PK/FK와 전송 단계 CHECK의 ABORTED 포함 여부를 확인한 뒤 새 백엔드와 EXE를 배포합니다. 022는 기존 명령·가드·전송 단계를 자동 변경하지 않습니다. ABORTED 기록이 존재하는 상태에서 CHECK나 감사 테이블만 제거하면 기존 증거와 차단 판단이 깨지므로 임의로 되돌리지 않습니다.

## 검증 범위와 남은 작업

백엔드 530건(실제 격리 MySQL 138건), Flutter 197건이 통과했습니다. 전송 시작/중단 경쟁, 지연 실행자의 외부 전송 0회, 동시 중단 감사 한 건, 감사 실패 롤백, 계좌/소유권/동의/변조 검증, 마이그레이션 반복 적용·누락 차단, 원본/가드 보존, 응답 유실과 실제/가상 출처 분리를 검증했습니다. 실제 앱 소스·테스트 Dart 분석 이슈 없음. 전체 프로젝트 분석에서는 기존 build/desktop-preview 임시 파일의 불필요 import 안내 2건이 있었으며 제품 소스 이슈와 구분합니다.

`SAGOPALGO_API_BASE_URL=http://localhost:8080`으로 Windows Release 빌드를 완료했습니다. 실행 파일은 `Front/app_version/build/windows/x64/runner/Release/SagoPalgo.exe`이며 같은 폴더의 DLL/data를 포함한 번들로 사용합니다. 전용 테스트 MySQL 컨테이너·네트워크는 검증 후 정리했습니다.

실제 KB 호출·운영 DB/환경 스위치 변경은 수행하지 않았습니다. DISPATCHING/이전 기록의 SENDING 종결, 실제 UNKNOWN 잔량/변경 완료 계약·종결, 실제 추가 정정·예약금 재사용과 별도 승인된 제한 주문/장기 운영 검증은 남습니다. 10단계 71%·전체 약 87.0%·11단계 0% 추정치를 유지합니다.
