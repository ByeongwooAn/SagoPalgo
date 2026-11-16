# 공개 시세 수집기의 운영 기록 영구 보존

기준일: 2026-11-06. U07 장기 관찰을 준비하는 **운영 기록 보존 기반**입니다. 연결 수명·고정 진단 코드·수신/저장 관찰 건수를 DB와 별도의 파일에 보존하고, 종료·부분 기록·재시작을 검증합니다. KIS 장중 실증(U06-B)과 세션 전체·장기 운영(U07)을 완료했다는 뜻은 아닙니다. 현재 운영 설정과 배포는 변경하지 않았습니다.

## 저장 방식과 재시작

- 기본 OFF입니다. 스트림과 저널을 함께 켠 경우에만 수집기 시작 시 새 `session-<UUID>.jsonl`을 만듭니다. 과거 파일에 이어 쓰거나 잘라내지 않습니다.
- 첫 START 기록의 `FileChannel.force(true)` 완료를 확인한 뒤 승인 요청/소켓 접속을 허용합니다. 같은 디렉터리의 `.writer.lock`을 보유한 작성자가 있으면 시작을 거절합니다.
- 상태 변경은 LIFECYCLE, 변경된 건수는 watchdog에서 COUNTERS, 정상 중지는 END로 기록합니다. 각 줄에는 스키마 버전·세션/시계 도메인·세션 내부 순번·연결 세대·로컬 단조 경과 시각·관찰 UTC 문자열과 이전 줄의 SHA-256이 있습니다.
- 별도 작성 스레드와 제한 큐를 사용합니다. **큐 수락은 디스크 보존 완료가 아닙니다.** 기록마다 강제 쓰기를 요청하고 완료 순번을 따로 관리합니다. 원문/가격/종목·계좌·키·승인키·외부 오류 문자열은 저널에 담지 않습니다.
- 재시작은 새 세션과 새 시계 도메인입니다. 이전 CONNECTED/LIVE 상태를 복구하거나 누락 시세를 만들어내지 않습니다. 세션 사이의 단조 시각/UTC 순서를 확정하지 않으며 `utcSynchronized=false`를 유지합니다.

[Java 17 FileChannel 공식 계약](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html)에 따라 `force(true)`와 `tryLock()`을 사용합니다. 로컬 저장 장치에 대한 계약이며 원격 파일시스템·디렉터리 메타데이터의 전원 장애 보존·장치 고장까지 검증한 결과는 아닙니다. 해시 연결은 무결성 점검이며 서명이나 작성자 인증이 아닙니다.

## 건수의 의미

| 필드 | 관찰하는 값 |
|---|---|
| receivedPublicFrames | 현재 세대에서 처리한 완성된 공개 프레임 수. ACK/PING 제외 |
| decodedEvents | 디코더가 반환한 이벤트 수 |
| storageInsertions | `hub.accept`가 true를 반환한 수 |
| nonInsertions | 같은 메서드가 false를 반환한 수. 중복 외에 퇴역 세대도 포함 가능 |
| storageFailures | 저장/공개 호출이 예외를 반환한 수 |
| retiredCompletions | 호출 완료 시 연결 세대가 이미 바뀐 수 |
| inFlightStorage | 스냅샷 시점에 반환되지 않은 저장 호출 수 |

이 값은 **메서드 관찰 스냅샷이며 DB 트랜잭션 원장이 아닙니다.** 커밋 뒤 공개 실패는 예외로 관찰될 수 있고, 중지 당시 진행 중인 호출은 END에 `inFlightStorage>0`으로 남을 수 있습니다. 중지 뒤 늦은 완료나 마지막 체크포인트 이후 강제 종료의 정확한 누락 건수는 이 파일만으로 확정하지 않습니다. 실제 DB 행·원문과의 대조는 후속 운영 상태 보고서에서 구분합니다.

## 실패·종료와 상한

| 항목 | 기본값 / 결과 |
|---|---|
| 대기 큐 | 256개, 포화 시 JOURNAL_QUEUE_FULL |
| 시작/개별 쓰기 대기 | 각각 2초, 시작 실패/쓰기 지연으로 처리 |
| 정상 종료 대기 | 최대 500ms, 미완료 시 JOURNAL_CLOSE_TIMEOUT |
| 세션/디렉터리 크기 | 16MiB / 256MiB, 초과 시 중단 |
| 파일 수 | 최대 1,024개 |
| 읽기 상한 | 파일 64MiB, 디렉터리 합계 1GiB, 파일 수 1,024개 |

시작할 수 없으면 공급자 접속 전에 `FAILED/OPERATIONS_JOURNAL_REQUIRED`, 실행 중 기록 실패·큐 포화·크기 초과·쓰기 지연이면 `FAILED/OPERATIONS_JOURNAL_FAILED`로 수집을 종결합니다. 쓰기 지연은 다음 상태 점검 시 감지하므로 2초가 장애 감지의 절대 상한은 아닙니다. 자동 재접속으로 기록 실패를 감추지 않습니다. 세부 저널 실패 코드는 로컬 상태에 보존하며 외부 오류 원문은 노출하지 않습니다.

END는 그 앞의 수락된 기록 뒤에 같은 큐로 들어갑니다. 종료 제한을 넘거나 쓰기에 실패하면 정상 보존을 인정하지 않습니다. 강제 종료로 사라진 큐 꼬리는 복원하지 않습니다. 이전 파일은 삭제·수정하지 않으며 자동 정리도 없습니다. 용량이 차면 백업·보관 정책을 검토하고 **수집기 중지 후** 별도로 관리해야 합니다.

## 설정과 Docker 보존

```dotenv
SAGOPALGO_MARKET_STREAM_JOURNAL_ENABLED=false
SAGOPALGO_MARKET_STREAM_JOURNAL_DIRECTORY=data/stream-operations
SAGOPALGO_MARKET_STREAM_JOURNAL_CAPACITY=256
SAGOPALGO_MARKET_STREAM_JOURNAL_MAX_SESSION_BYTES=16777216
SAGOPALGO_MARKET_STREAM_JOURNAL_MAX_DIRECTORY_BYTES=268435456
```

로컬 실행의 상대 경로는 서버 작업 디렉터리 기준입니다. Compose는 Spring 서비스에 `sagopalgo-stream-operations` named volume을 연결하고 경로를 `/app/data/stream-operations`로 고정합니다. 컨테이너 재생성 시 파일을 보존하도록 선언했으며 실제 운영 재배포·볼륨 복구 검증은 이번 범위가 아닙니다. 볼륨 삭제는 기록 삭제이므로 백업 없이 정리하지 않습니다. 파일 경로는 Git 제외 대상이며 운영 DB 마이그레이션은 없습니다.

## 읽기 전용 점검

Java 17, `Back/spring-server`에서 실행합니다. Spring 앱을 기동하거나 외부 API를 부르지 않는 별도 JavaExec 작업입니다. 출력 파일은 부모 디렉터리가 존재해야 하며 기존 파일을 덮어쓰지 않습니다.

```powershell
.\gradlew.bat inspectStreamOperationsJournal --args="--directory data/stream-operations --output inspection-new.json"
# 한 세션의 검증된 기록만 최대 100개 조회. UUID는 실제 보고서의 sessionId로 바꿉니다.
.\gradlew.bat inspectStreamOperationsJournal --args="--directory data/stream-operations --output inspection-page-new.json --session <UUID> --after-index 0 --limit 100"
```

세션 목록은 파일명 순서이며 시간순 보고서가 아닙니다. 페이지 범위와 별개로 해당 파일 전체의 연결·순번·시계 도메인·상태·건수 단조성을 점검합니다. 정상 실행 중 읽기와 비정상 종료는 이 읽기만으로 구분되지 않습니다.

| 상태 | 의미 |
|---|---|
| CLEAN_END | 끝까지 검증되고 END로 끝남. 모든 DB 호출 완료·장기 운영 성공의 증명은 아님 |
| NO_END_MARKER | 검증된 접두부는 있으나 END 없음. 실행 중 또는 종료 중단 가능 |
| PARTIAL_TAIL | 끝에 줄바꿈 없는 부분 기록 존재. 앞의 검증된 기록만 보고 |
| CORRUPT | JSON·해시·순번·계보·상태/건수 규격 불일치. 처음 실패하기 전까지만 보고 |
| EMPTY | 빈 세션 파일 |

보고서는 `writerActivity=NOT_DETERMINED`, `crossSessionOrder=UNCONFIRMED`, `repairPerformed=false`, `durabilityAttestedByReader=false`, `usableForTrading=false`입니다. 검사 종료 코드 0은 보고서 생성 성공이며 모든 세션의 정상 종료를 뜻하지 않습니다. 입력/읽기/출력 실패는 고정 오류와 종료 코드 2입니다.

## 검증과 후속

검증 결과는 [요약 JSON](../examples/durable-stream-operations-validation.json)을 참조합니다. 합성 프레임의 실제 루프백 소켓에서 수집기 두 번 실행·기록 보존·새 자료 전 WAITING_DATA와 관찰 건수를 확인했습니다. 별도 소유 자식 JVM을 `Runtime.halt`로 종료해 END 없는 강제 쓰기 접두부를 검사하고 새 실행이 원본 바이트를 보존함을 확인했습니다. 실제 KIS 호출·주문은 없습니다.

Java 17 전체 백엔드 **819건 통과·실패/오류/제외 0건**입니다. 신규 저널 23건(파일/검사 20·루프백 소켓 3)을 포함합니다. 시장 자료·계좌 관찰·주문의 전용 MySQL 플래그 3개를 켰고 테스트 컨테이너만 종료했습니다. 기존 운영 컨테이너 4개는 유지됐습니다. 별도 자식 JVM 표본에 실제 `inspectStreamOperationsJournal` 작업을 실행해 `NO_END_MARKER`·검증된 2행·종료 코드 0을 확인했습니다. YAML의 미해석 설정 구조·문서 링크·Git 제외·차이 공백 검사도 통과했습니다.

- 저널 OFF 호환, 작성자 잠금, 시작/비동기 쓰기 실패, 부분 쓰기, 큐·세션·디렉터리 상한, 쓰기/종료 지연, 해시·중복 키·순번·END 이후 입력, 읽기 전용 페이지·출력 덮어쓰기 금지를 검사합니다.
- **현재 요청:** 운영 기록 보존 기반과 위 실패/재시작 검증까지 완료합니다. 운영 배포·장중 검증·장기 관찰은 포함하지 않습니다.
- **후속 U07-B:** 같은 검증기를 사용해 세션별 연결·복구 지연·관찰 건수·미확정 꼬리를 집계합니다. 사용법과 DB 대조 범위는 [운영 상태 보고서](stream-operations-status-report.md)에 기록했습니다.
- **U07-C:** 격리 DB 장애·프로세스 재시작을 묶어 기록과 원본·복구 지표를 대조합니다. 저널 자체의 파일 실패 테스트와 별개입니다.
- **U06-B/U07-D:** 장중 제한 KIS 단절/복구 실증, 이후 예산·기간을 고정한 세션 전체/장기 관찰을 수행합니다. 실제 장중 근거 확보 전 완료로 올리지 않습니다.
- U04 실제 비용·U05 독립/계좌 체결·U08 과거 CB/단일가 표본은 각각의 외부 근거가 필요합니다.

고정 완료율은 **전체 27/48·56%, 5번 7/18·39%, 5-08 진행 중**입니다. U07 기반을 추가한 것을 장기 운영이나 5-08 전체 완료로 환산하지 않습니다.
