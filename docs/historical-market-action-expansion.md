# H05 2023년 12월 거래소 조치 공지 원문 확대 대조

2023년 12월 게시분에서 기존 70건 표본에 없던 KOSPI 14건·KOSDAQ 79건을 모두 검토했습니다. 후보 모수는 기존 목록 4,033건입니다. 효력일은 H05 고정 범위인 2023-11-01~2026-11-02로 검사했습니다. [기존 표본](historical-actions-followup.md)

| 공지 원문 대조 결과 | 건수 |
| --- | ---: |
| 보통주 권리락 적용일·기준가 확인 | 5 |
| 보통주 배당락·권배락 적용일·기준가 확인 | 22 |
| 코스닥 보통주 거래정지 적용일 확인 | 17 |
| 코스닥 보통주 거래정지 해제 적용일 확인 | 5 |
| 코스닥 정지 기간 변경 전후 문구 확인 | 6 |
| 코스피 정지·해제 날짜 또는 시각 확인, 대상 주권 종류 미확인 | 5 |
| 본문 양식·종목 식별·대상 주권 등 미확인 | 30 |
| 공지 화면에 복수 버전 표시, 정정 이력 검토 대기 | 3 |

93건의 공지 화면과 90건의 본문 경로·본문을 확보해 응답 273개의 요청과 해시를 기록했습니다. 코스피 권배락 기준가격 양식(99302), 코스닥 권배락 표 양식(70768), 코스피 정지·해제 시각 양식(99808)을 추가로 대조했습니다. 코스피 시각 양식은 대상을 주권으로만 표시해 보통주 확정을 보류했습니다. 공지에 표시된 시각은 KST로 보존했습니다. 실제 첫 체결 시각과 당시 최초 공개 시각은 미확인입니다.

미확인 본문에는 공지 화면과 본문 회사명이 다른 사례, 우선주만 표시된 사례, 시장 전체 안내문이 포함됩니다. 복수 버전 공지 3건은 뷰어의 문서 번호를 보존했습니다. 이 중 2건은 같은 문서 번호 쌍을 가리킵니다. 버전별 본문 및 정정 적용 시점은 후속 대조 대상입니다.

## 로컬 재검증

AI 서버 디렉터리에서 실행합니다. [해시 고정 검토 명세](examples/historical-market-action-expansion.json)

~~~powershell
$job = 'research-artifacts/historical-market-action-expansion-20261113'
$options = @('--manifest', '../../docs/examples/historical-market-action-expansion.json',
             '--artifacts', 'research-artifacts', '--job', $job)
.\.venv\Scripts\python.exe -m app.replay.historical_market_action_expansion build @options
.\.venv\Scripts\python.exe -m app.replay.historical_market_action_expansion audit @options
~~~

보고서 SHA-256은 `8e229ae85fec4b35f5f39d56278344fb228708ce59ca1971bafff61e049e9d91`입니다. 기존 표본을 포함해 163건을 검토했으며 기존 후보 목록에 3,870건이 남았습니다. H05 전 기간 검토와 5-08은 진행 중입니다.
