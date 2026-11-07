# U07-B 공개 시세 수집 운영 상태 보고서

수집기 실행마다 연결 시도와 재시도, 자료 준비, 저장 호출의 관찰 건수를 확인합니다. 보고서는 U07-A와 같은 검증기를 사용해 JSON 형식, 해시 연결, 순번과 시계 도메인이 유효한 구간만 읽습니다. 검증에 실패한 첫 줄 이후는 집계 범위에서 제외합니다. [운영 기록 보존과 검사 계약](durable-stream-operations-journal.md)

## 실행 방법

Java 17 환경의 `Back/spring-server`에서 실행합니다. 출력은 부모 디렉터리가 이미 있는 새 `.json` 파일로 지정합니다. 명령은 로컬 저널만 읽고 Spring과 DB를 기동하지 않습니다.

```powershell
.\gradlew.bat reportStreamOperationsStatus --args="--directory data/stream-operations --output operations-report-new.json"
.\gradlew.bat reportStreamOperationsStatus --args="--directory data/stream-operations --output operations-sample-new.json --session <UUID> --source SYNTHETIC"
```

`--session`은 선택 사항입니다. 생략하면 해당 디렉터리의 세션들을 파일명 순서로 나열합니다. `--source`는 합성 자료에 `SYNTHETIC`, 수집 자료에 `CAPTURE`를 지정하는 입력 출처 표시입니다. 기본값은 `UNSPECIFIED`입니다. 이 값은 선택한 입력 전체에 적용되는 실행자의 선언입니다. 출처가 섞였으면 기본값을 쓰거나 세션을 각각 선택합니다. 실제 출처의 독립 검증은 `sourceProvenanceVerified=false`로 표시합니다.

종료 코드 0은 보고서 파일 생성이 성공했다는 뜻입니다. 각 세션의 상태는 `integrityStatus`를 확인합니다. 잘못된 입력이나 읽기/출력 오류는 고정 코드 `JOURNAL_STATUS_REPORT_FAILED`와 종료 코드 2로 표시합니다. 기존 보고서와 저널 원본의 바이트를 보존합니다.

## 세션별 지표

| 필드 | 계산 방식과 해석 |
|---|---|
| `verifiedEntries`, `firstVerified`, `lastVerified` | 검증된 기록의 시작과 끝. 마지막 검증 행의 해시와 읽은 파일의 SHA-256으로 대조 범위를 식별 |
| `lifecycleCounts`, `diagnosticCounts` | 검증된 상태/진단 발생 건수. 재시도, ACK, 새 자료 준비, 실패, 중지를 구분 |
| `counterCheckpoints`, `latestCounters` | COUNTERS 기록 수와 마지막 검증 행의 누적 관찰 건수. 세션 내 스냅샷을 합산하지 않음. 검증 행 0건의 마지막 관찰값은 null |
| `attemptToAck`, `ackToDataReady` | 같은 연결 세대의 관찰 경계 사이 단조 시각 차이. 표본 수·최소·최대를 나노초로 표시. 짝을 찾지 못한 ACK/자료 준비는 별도 건수로 표시 |
| `recovery` | 첫 RECONNECTING으로 열린 복구 대기 구간을 같은 세션에서 더 새 연결 세대의 일치하는 DATA_READY가 닫음. 이어지는 재시도는 한 구간에 포함. FAILED, DISABLED, END는 자료 준비 전 종료로 기록 |
| `recentClosedWindows` | 최근 닫힌 복구 대기 구간 최대 16개의 기록 순번·세대·시간·결과. 전체 집계는 검증한 구간을 모두 포함하고 상세 표시에서 생략한 구간 수를 보고 |
| `unresolvedWindow` | 검증 범위 끝에 열려 있던 복구 구간. 종료 경계와 소요 시간은 null |

재접속 지표는 수집기가 상태를 관찰한 시점의 차이입니다. 초기 접속 실패도 복구 대기 구간이 될 수 있습니다. 실제 거래가 끊긴 시점, 미수신 체결 수, 거래소에서 수집기까지의 지연은 저널만으로 확정할 수 없습니다. 시각 문자열은 위치 확인에 쓰고 기간 계산은 세션별 단조 시각을 사용합니다. 서로 다른 세션의 순서와 복구 관계는 미확정으로 둡니다.

## 종료 경계와 DB 대조 범위

| `tail.assessment` | 판단 근거 |
|---|---|
| `END_MARKER_VERIFIED` | 검증된 END와 해당 시점의 진행 중 저장 호출 0건 |
| `END_WITH_IN_FLIGHT_STORAGE` | END 당시 반환되지 않은 저장 호출이 있음. 이후 완료 여부는 미확정 |
| `END_NOT_VERIFIED` | 검증 범위에 END가 없음. 작성 중인지 종료됐는지 판정할 근거가 부족 |
| `PARTIAL_LINE` / `INVALID_LINE` | 마지막 부분 줄 또는 검증 실패 줄을 제외한 범위만 집계 |
| `NO_RECORDS` | 파일이 비어 있음 |

`unobservedOperations`와 `missingProviderEvents`는 null입니다. `latestCounters`는 저장 메서드가 반환한 삽입·미삽입·예외 등의 관찰값입니다. 행 ID가 없고 커밋 후 공개 실패도 예외로 관찰될 수 있으므로 DB 행별 일치 여부는 `NOT_PERFORMED`로 표시합니다. U07-C에서는 격리 DB와 원본 이벤트 식별자를 별도로 확보해 같은 표본의 커밋 행·중복·미확정 구간을 대조합니다.

## 검증 결과

Java 17 전체 백엔드 828건이 통과했습니다. 실패·오류·제외는 0건입니다. 신규 보고서 9건에 반복 재시도, 벽시계 역전, 연결 세대 불일치, 부분/손상 기록, 세션 분리, 빈 파일, 1,000행 초과 집계와 출력 보존을 포함했습니다. 시장 자료·계좌 관찰·주문의 전용 MySQL 회귀도 실행했습니다.

두 Gradle 명령을 같은 합성 저널에 실행해 검증 행 수와 마지막 검증 해시의 일치를 확인했습니다. 입력 파일 두 개의 SHA-256도 실행 전후 동일했습니다.

| 합성 세션 | 무결성 | 검증 행 | 복구 결과 | 마지막 저장 관찰 |
|---|---|---:|---|---|
| 정상 종료 | CLEAN_END | 11 | 자료 준비까지 1회, 7초 | 삽입 2, 미삽입 1, 진행 중 0 |
| 부분 기록 | PARTIAL_TAIL | 6 | 종료 경계·소요 시간 미확정 | 진행 중 1 |

다음 작업은 **U07-C 격리 DB 장애·재시작 대조**입니다. 실제 KIS 복구는 장중 실증 U06-B, 세션 전체와 장기 관찰은 U07-D에서 검증합니다. [남은 실행 단위](remaining-development-units.md)
