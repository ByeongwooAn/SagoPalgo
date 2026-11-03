# R1 실제 계좌 읽기 관찰 점검

기준일: 2026-11-03 · 결과: 관찰 저장/재조회 및 보유·현금 대조 확인, 지정일 주문 조회는 미확인입니다. 전체 SUCCESS·자동 수집 운영 완료로 올리지 않습니다.

후속 [자동 수집 제한 운영 검증](account-collection-operations.md)에서 자동 1주기의 부분 실패 중단·재시작 보존·OFF 재개를 확인했습니다. 현재 수집은 OFF·IDLE이며 이력은 아래 수동 1건과 후속 자동 1건입니다. 아래 수집 미활성화/NOT_STARTED는 최초 수동 점검 당시의 기록입니다.

## 실행 범위와 확인 결과

현재 Windows PC의 로컬 Docker 배포 API에서 한국 날짜 `20261103`으로 관찰 저장 POST를 **1회** 실행했습니다. 요청 ID·날짜·대상 서버를 로컬 파일에 먼저 기록하고 디스크에 flush한 뒤 전송했습니다. 이후 상세와 최근 이력 확인은 같은 ID의 GET을 사용했습니다. 백엔드/DB/앱 코드는 재배포하지 않았으며 수집/주문 설정을 변경하지 않았습니다.

| 확인 대상 | 결과 | 해석 범위 |
|---|---|---|
| 저장 POST·상세 GET | HTTP 200·no-store, COMPLETED | 결과 저장과 조회 성공. KB 전체 조회 성공과 다름 |
| 저장된 전체 관찰 | PARTIAL, atomic=false, usableForTrading=false | 주문/원장 판단에 사용하지 않음 |
| SSQM1801 보유 | SUCCESS·COMPLETE·1페이지·종목 행 0건·문제 0건 | 사용자가 KB 앱의 동일 연결 계좌에 보유 종목이 없음을 확인 |
| SSQM2932 결제기준 잔고 | SUCCESS·COMPLETE·1페이지·종목 행 0건·문제 0건 | 현금은 별도 요약 필드에 수신됨. 종목 행 0건이 현금 0원을 뜻하지 않음 |
| SSQM2952 체결기준 잔고 | SUCCESS·COMPLETE·1페이지·종목 행 0건·문제 0건 | 결제/체결 기준을 합산하거나 같은 기준의 전체 자산으로 해석하지 않음 |
| 현금 대조 | 예수금·주문가능현금·체결기준 당일예수금의 표시 금액 일치, 사용자 KB 앱 확인 | 이 관찰 시점의 사용자 확인. 입출금/체결이 있는 계좌 전체 정합성 검증과 다름 |
| SSQM2341 지정일 주문 | FAILED·UNKNOWN·정상 봉투 0페이지·LOOKUP_FAILED | 주문 0건이나 미체결 없음으로 확정하지 않음 |
| 최근 이력 GET | 같은 요청 ID가 1건 포함됨 | 새 관찰/재전송 없이 조회 |
| 자동 수집 | OFF·NOT_STARTED·900초 | 수동 관찰이 수집 실행 상태를 만들거나 활성화하지 않음 |
| 주문 사전검증·실주문 스위치 | 모두 OFF | 주문·정정·취소·승인·가드 해제 실행 없음 |

실행 중인 Windows 앱의 설정 화면에서 보유/현금 표시를 확인하고, `계좌 관찰 이력·비교`에서 수집 OFF·시작 기록 없음과 실제 저장 이력의 `저장 완료 · 일부만 확인` 표시를 확인했습니다. KB 앱은 이 PC의 제어 가능한 앱 목록에 없어 대조 결과는 사용자가 KB 앱에서 확인한 답변을 근거로 기록했습니다. 실제 잔고 금액·계좌번호·인증값·외부 응답 전문·화면 캡처는 저장소에 추가하지 않습니다.

## 지정일 주문 조회 진단

실패 구간의 원인을 구분하기 위해 기존 읽기 API `GET /api/v1/orders/kb/executions?orderDate=20261103&classification=0`을 별도로 1회 호출했습니다. 주문 전송 API가 아닙니다. HTTP 502·EXTERNAL_DATA_ERROR이며, 서버가 전달한 KB 실패 메시지가 조회 내역 없음에 해당함을 원문 출력 없이 확인했습니다. 최초 관찰에도 해당 실패가 포함되지만 실패 메시지 전문은 관찰 계약에 저장되지 않습니다.

[KB 공개 SSQM2341 상세 정의](https://openapi.kbsec.com/api/apis/catalog/66998ea3-85f3-4060-bf6d-f88a163eee35/tr-list)를 같은 날 확인했습니다. 정의에는 resultCode `200` 성공/`9999` 실패, processFlag `A` 성공/`B` 실패, processCode `0000` 성공이 기재되어 있습니다. 이번에 확인한 정의만으로 ‘조회 내역 없음’ 실패를 완전한 정상 0건으로 변환할 별도 코드·종료 조건은 확정하지 못했습니다.

따라서 문자열 메시지 일치로 빈 배열을 만들어 SUCCESS로 바꾸거나 날짜를 바꿔 자동 재조회하지 않습니다. 미확인 응답을 주문 없음·미체결 종결·예약금 반환 근거로 사용하지 않습니다. 정확한 원본 처리 코드와 적용 조건 확보는 [KB-07 보류 항목](kb-contract-blockers.md)에 기록합니다. 자동 수집을 켜면 같은 종류의 부분 실패에서 PAUSED가 될 수 있으므로 이 결과를 정상 반복 수집 검증으로 해석하지 않습니다.

## 점검 스크립트

[check-account-observation.ps1](../scripts/check-account-observation.ps1)은 개인용 API의 기본 OFF 환경에서 명시적인 읽기 관찰 점검과 기존 요청 확인을 구분합니다. 기본 실행은 저장된 요청의 GET만 수행하며 새 외부 조회를 만들지 않습니다. JWT가 필요한 배포는 이 스크립트의 현재 지원 범위가 아닙니다.

영수증 폴더를 먼저 만들고, 다음과 같이 새 요청을 실행합니다. `-Capture`는 실제 KB 읽기 조회와 DB 관찰 저장을 실행하므로 단순 상태 점검에 붙이지 않습니다. 같은 영수증 파일이 이미 있으면 POST 전에 중단합니다.

```powershell
New-Item -ItemType Directory -Path 'Front/app_version/build-codex-account-observation-live' -Force | Out-Null
./scripts/check-account-observation.ps1 `
  -ApiBaseUrl 'http://192.168.0.2:8081' `
  -ReceiptPath 'Front/app_version/build-codex-account-observation-live/manual-20261103.json' `
  -OrderDate '20261103' -Capture
```

위 경로는 이번 실제 요청 영수증이 있는 경로입니다. 새 점검을 위한 빈 파일 경로는 별도로 지정해야 하며, 재확인을 위해 기존 영수증을 삭제하거나 다른 파일명으로 자동 우회하지 않습니다. 주소는 각 배포 환경에 맞춥니다.

이번 요청의 결과를 다시 확인하려면 `-Capture`를 빼고 실행합니다.

```powershell
./scripts/check-account-observation.ps1 `
  -ApiBaseUrl 'http://192.168.0.2:8081' `
  -ReceiptPath 'Front/app_version/build-codex-account-observation-live/manual-20261103.json'
```

- 새 요청 전에 수집 OFF·개인용/계좌 조회/연결 설정·주문 스위치 OFF·공식 운영 서버 설정·이력 저장소 접근을 확인합니다. 주문용 계좌번호 유무는 B2C 읽기 조회의 차단 조건으로 추가하지 않습니다.
- 요청 파일은 CreateNew로 만들고 flush합니다. 파일 쓰기 실패나 기존 파일은 새 POST를 차단합니다. POST는 한 번이며 타임아웃/유실 이후에는 같은 ID의 상세 GET만 수행합니다.
- 응답 UUID·조회일·읽기 계약·4개 구간·문자열/null 필드와 최근 이력 포함을 검사합니다. 전체 SUCCESS·모든 구간 COMPLETE·문제 0건일 때만 종료 코드 0입니다. PARTIAL은 저장 검증에 성공해도 종료 코드 1입니다. 실행 결과와 실패 원인은 JSON으로 표시합니다.
- `<영수증 경로>.report.json`은 최근 검사 보고서이며 재확인 때 갱신됩니다. 영수증에는 요청 ID·날짜·서버·생성 시각만, 보고서에는 상태·개수·고정 문제 코드만 기록합니다. 금액·종목 행·키·오류 원문은 보관하지 않습니다. 스크립트는 KB 앱 대조를 자동 수행하지 않으므로 `kbAppComparison=NOT_PERFORMED`이고 사용자 확인은 이 문서에 별도 기록합니다.
- 이 스크립트의 API/저장 성공은 계좌 전체 검증·주문 준비 완료를 뜻하지 않습니다. PENDING·404·계약 오류에서도 새 UUID를 만들거나 POST로 복구하지 않습니다.

모의 서버 검증은 다음 명령으로 실행합니다. 실제 KB·배포 DB를 사용하지 않으며 PowerShell 실행 파일이 필요합니다.

```powershell
python -m unittest discover -s scripts/tests -p test_account_observation_check.py -v
```

9개 테스트가 선행 파일 기록·단일 POST·응답 유실 후 GET 복구·기존 영수증 차단·부분 결과·PENDING·요청 불일치·설정/저장소/파일 오류·잘못된 날짜를 검증합니다. 테스트 실행에 사용할 PowerShell은 선택적으로 `SAGOPALGO_TEST_POWERSHELL`에 지정할 수 있습니다.

## 다음 확인

1. KB-07의 정상 빈 주문 결과와 업무 실패를 구분할 공식 처리 코드·응답 예제·다음키/건수/조회일 종료 조건을 확보합니다. 메시지 문자열만으로 성공 처리하지 않습니다.
2. 근거가 확보되면 모의 계약 테스트와 전용 DB/앱 검증을 추가하고 해당 읽기 구간을 별도로 재확인합니다. 원래 PARTIAL 관찰은 수정하지 않습니다.
3. 승인된 호출 예산과 부분 실패/중단/재개 조건이 정리된 뒤 자동 수집의 운영 점검을 진행합니다. 이번에 자동 수집이나 실주문을 활성화하지 않았습니다.
