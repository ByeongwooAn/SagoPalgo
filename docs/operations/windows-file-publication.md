# Windows 파일 게시 잠금 복구와 전체 회귀 정상화

기준일: 2026-11-06. PR #112의 전체 회귀를 막던 요청 일지·JSONL 교체와 완성 번들 폴더 게시 실패를 수정했습니다. **기존 1,062개 테스트 + 신규 17개 = 전체 1,079개 통과**, 실패/오류/제외 0개입니다. 기존 Starlette/AnyIO 경고 1개는 유지합니다. 이전 실패 로그와 원문·요청 기록은 보존합니다.

## 원인 분리와 재현

이전 전체 실행은 `history.atomic_json`의 `os.replace`, 데이터셋 게시의 `os.rename` 등에서 `PermissionError: WinError 5`가 발생했습니다. KIS·DART 일지·파생 JSONL·데이터셋·저장 자료 변환은 즉시 실패했고, KRX 체크포인트에만 별도 제한 재시도가 있었습니다. 같은 파일 게시 조건을 공통으로 처리하도록 수정했습니다.

사용자가 소유한 **별도 진단 경로**에서 Win32 `CreateFileW`의 읽기 핸들을 열고 읽기/쓰기 공유만 허용해 삭제/이름 변경 공유를 차단했습니다. 권한·백신·시스템 설정은 바꾸지 않았습니다.

| 검사 | 파일 교체 | 폴더 게시 |
|---|---|---|
| 같은 경로에서 쓰기·flush·fsync | 성공 | 성공 |
| 공유를 차단한 핸들이 열린 동안 | WinError 5 | WinError 32 |
| 실패 시 이전 파일/준비 폴더 바이트 | 보존 | 보존 |
| 핸들을 닫고 같은 연산 재실행 | 성공 | 성공 |

이 재현은 **일시적으로 열린 핸들도 접근 거부/공유 위반을 만들 수 있음**을 확인합니다. 과거 실패에서 실제 핸들을 소유했던 외부 프로세스까지 특정한 것은 아니며, 백신이나 특정 프로그램을 원인으로 단정하지 않습니다. 영구 ACL 문제도 코드 5가 될 수 있으므로 무조건 성공 처리하지 않습니다.

Microsoft의 [CreateFile 공유 모드 설명](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)은 삭제 접근이 이름 변경에도 사용됨을 설명하며, [오류 코드 정의](https://learn.microsoft.com/en-us/windows/win32/debug/system-error-codes--0-499-)는 5(접근 거부)·32(공유 위반)·33(잠금 위반)을 구분합니다.

## 수정한 계약

`app.replay.file_publish`에 파일 교체와 준비 폴더 게시를 모았습니다.

- Windows에서 실제 `winerror`가 **5·32·33**인 게시 실패에만 재시도합니다. 다른 오류와 비 Windows 환경의 오류는 즉시 전달합니다.
- 최초 시도 포함 **최대 8회**, 대기 간격 0.05/0.1/0.2/0.4/0.4/0.4/0.4초로 총 대기 상한은 **1.95초**입니다. 시스템 호출 자체의 실행 시간은 별도입니다.
- 재시도하는 것은 이미 준비된 파일/폴더의 `replace/rename`뿐입니다. JSON 직렬화·원문 다운로드·공급자 요청·요청 번호/예산 예약을 반복하지 않습니다.
- JSON은 기존처럼 임시 파일에 한 번 기록·flush·fsync하고 핸들을 닫은 뒤 원자 교체합니다. 기존 파일을 먼저 삭제하거나 직접 덮어쓰지 않습니다.
- 계속 실패하면 원래 오류를 전달합니다. 이전 JSON과 완성된 새 `.tmp` 바이트는 남습니다. 예약 기록의 게시가 끝내 실패하면 공급자 호출은 **0회**입니다.
- 데이터셋/저장 변환은 완성된 준비 폴더를 원자적으로 게시합니다. 게시가 끝내 실패하면 준비 폴더를 보존하며, 새 출력 경로에 일부 파일만 노출하지 않습니다. 준비 전 실패의 임시 폴더 정리는 유지합니다.
- 재시도 중 다른 출력이 생기면 기존 출력에 합치거나 덮어쓰지 않고 `FileExistsError`로 종료합니다. 원래의 작업 소유권·잠금 계약은 유지하며 동시 작성자를 임의로 허용하지 않습니다.

적용 위치는 KIS/DART 공통 JSON 일지, KIS `daily.jsonl`, DART `disclosures.jsonl`, KRX 공통 JSON, 데이터셋 번들 및 저장 자료 변환 폴더입니다. 자료 형식·파일 바이트·해시·주문 정책·재현 가격 계산은 바꾸지 않았습니다.

## 검증 결과

신규 17개 검증은 다음을 포함합니다.

- 코드 5/32/33의 일시 실패 뒤 같은 준비 바이트로 복구
- 영구 접근 실패의 8회 상한·이전/새 바이트 보존
- 다른 오류·비 Windows 오류의 즉시 전달
- KIS/DART 예약 게시 실패 시 공급자 호출 없음
- 일지/JSONL 교체 복구 중 공급자 호출 수와 요청 일지 수 일치
- 완성 번들의 게시 실패 시 준비 폴더·입력 원본 보존
- 대기 중 경쟁 출력이 생겨도 양쪽 자료 보존
- **실제 Windows 핸들**을 사용한 파일·폴더 잠금 해제 후 게시 성공 2개

관련 선행 검증은 195개 통과·저장 자료 교차 검증 fixture 미설정으로 1개 제외였습니다. 마무리 전체 실행은 그 fixture를 명시해 **1,079개 모두 실행·통과**, 실패/오류/제외 0개를 확인했습니다. 기존 1,062개 테스트의 식별자도 전체 결과에 모두 포함됐는지 대조합니다. 테스트를 건너뛰거나 테스트 실패를 재시도로 성공 처리한 결과가 아닙니다. 제한 재시도는 제품 코드의 파일 게시 경계에 적용합니다.

```powershell
# AI/ai-server에서 실행. bridge fixture가 준비된 환경 기준.
$previousFixture = $env:SAGOPALGO_STORED_EXPORT_FIXTURE
try {
    $env:SAGOPALGO_STORED_EXPORT_FIXTURE = (Resolve-Path '../../Back/spring-server/build-codex-dataset-export/bridge-fixture.json').Path
    .\.venv\Scripts\python.exe -m pytest -q --tb=short --basetemp=build-codex-replay/<새-임시-경로> -o cache_dir=build-codex-replay/pytest-cache
} finally {
    $env:SAGOPALGO_STORED_EXPORT_FIXTURE = $previousFixture
}
```

실행 로그는 `AI/ai-server/build-codex-replay/windows-publish-full.log`, JUnit은 `windows-publish-full.xml`입니다. 진단·보존 감사는 Git 제외 경로 `AI/ai-server/research-artifacts/windows-publish-20261106/`에 기록합니다. 감사 시 통신을 차단하고 이전 **11,082개 파일**의 해시를 보존했습니다. 타임라인 해시 `876f349993f30ce428041f08f1e9a5a4d5355e0dbe725f6f6d8e856860788875`, 기존 보고서 해시 `aa7d4e4c7b9393d404d00056829f1c9c599a1518e233b3a6f57ab5c952068177`, 실제 근거+합성 가격 재현 보고서 17개도 동일합니다. 신규 HTTP·계좌·주문 호출은 0회입니다.

## 완료 범위

- [x] 격리 경로에서 실제 Windows 잠금으로 오류 재현·해제 대조
- [x] 파일 게시에 한정한 재시도·영구 실패 전달·기존/준비 바이트 보존
- [x] 기존 1,062개와 신규 17개 전체 회귀 0실패 확인
- [x] PR #112의 검증 설명 갱신·리뷰 준비 상태 전환

이 작업은 PR의 파일 게시/회귀 장애를 해소한 것입니다. [장중 재현](../historical-data/replay/intraday-session-replay.md)의 실제 부분 근거·미확인 과거 가용 시점과 [5-08 고정 조건](../historical-data/replay/multi-company-reference-cases.md)은 유지합니다. **5-08 진행 중·5번 7/18·39%, 1~5번 26/48·54%**입니다. 운영 배포·DB·EXE·학습·실주문은 수행하지 않았습니다.
