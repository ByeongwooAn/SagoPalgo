# H05 거래소 조치 공지의 당시 보통주 식별자

2026-11-15 기준. [월별 대조 원장](../../examples/historical-market-action-monthly.jsonl)에서 본문 상호와 KIND 표시명이 달라 코드 연결을 보류한 **248개 접수, 250개 검토 행**을 대조했습니다. 두 접수가 같은 원본과 정정본을 가리키는 경우 접수번호와 문서번호를 함께 보존했습니다.

| 판정 근거 | 검토 행 |
| --- | ---: |
| 기준일 KRX 보통주 정식명·약명 일치 | 224 |
| 기검증 상호 변경·약명 공지와 기준일 KRX 목록 대조 | 11 |
| 게시일 상호 일치와 조치일까지 동일 코드·ISIN 확인 | 8 |
| 추가 KIND 상호·변경상장 공지와 기준일 KRX 목록 대조 | 4 |
| H05 고정 효력일 범위 밖 | 3 |

범위 내 **247행(245개 접수, 고유 단축코드 91개)**의 보통주 단축코드와 ISIN을 확인했습니다. 적용일을 표시한 행은 공지의 해당 날짜에서 확인했습니다. 별도 적용일이 기재되지 않은 정지기간 변경 65행의 식별 기준은 게시일입니다. 원본과 정정본의 화면 표시일은 접수 목록의 게시일과 함께 각각 보존했습니다. [접수·문서별 대조 결과](../../examples/historical-market-action-identity.json)

범위 밖 세 접수의 적용일은 이에이트 2026-11-04, 인지디스플레이 및 신한제12호스팩 2026-11-06입니다. H05의 기준정보 효력일 마감은 2026-11-02입니다. 세 접수의 조회 코드는 남겼으며 역사적 코드·ISIN 판정 필드는 공란입니다. [이에이트](https://kind.krx.co.kr/common/disclsviewer.do?acptno=20261103000413&method=search) · [인지디스플레이](https://kind.krx.co.kr/common/disclsviewer.do?acptno=20261105000681&method=search) · [신한제12호스팩](https://kind.krx.co.kr/common/disclsviewer.do?acptno=20261105000985&method=search)

## 상호 연결 사례

- **아모레퍼시픽그룹** 공지의 2025-03-27 KRX 보통주 표기는 아모레G였습니다. 변경상장 본문은 이전 거래소 종목명 아모레G와 이후 아모레퍼시픽홀딩스를 같은 보통주 `002790` / `KR7002790004`에 연결하며 변경상장일은 2025-04-25입니다. [KIND 변경상장](https://kind.krx.co.kr/external/2025/04/22/000309/20250422001001/68155.htm)
- **에이치엘비이노베이션**은 변경상장 본문에 상호와 보통주 코드 `024850`이 함께 표시됩니다. 2026-04-06과 2026-05-04의 KRX 목록에는 같은 코드와 `KR7024850000`이 있습니다. [KIND 변경상장](https://kind.krx.co.kr/external/2026/04/28/000988/20260428002985/70764.htm)
- **농업회사법인 엔에이치농우바이오**는 2025-05-02 변경상장 공시에서 정식명, 2026-05-11 약명 안내에서 NH농우바이오 표기를 확인했습니다. 2026-09-29 KRX 보통주는 `054050` / `KR7054050000`입니다. [KIND 변경상장](https://kind.krx.co.kr/external/2025/04/28/000726/20250428001828/70765.htm) · [KIND 약명 안내](https://kind.krx.co.kr/external/2026/05/06/000754/20260506001758/70792.htm)
- **피플바이오**는 2026-08-03 조치 기준일 목록에서 `304840` / `KR7304840002`로 확인했습니다. 상호변경안내의 주총일은 2026-07-20이며, 타임X AI 약명을 표시한 변경상장 공지의 상장일은 2026-11-03입니다. [KIND 상호변경안내](https://kind.krx.co.kr/external/2026/07/20/000325/20260719000016/70659.htm) · [KIND 변경상장](https://kind.krx.co.kr/common/disclsviewer.do?acptno=20261029000556&method=search)
- **스팩 5종목의 7개 접수**는 당일 KRX 정식명으로 식별자를 확인하고 신규상장 공지의 정식명·약명·보통주 단축코드·ISIN으로 보강했습니다. 예를 들어 에스케이증권제8호기업인수목적과 SK증권제8호스팩이 `435870` / `KR7435870001`에 연결됩니다. [KIND 신규상장 예시](https://kind.krx.co.kr/external/2022/10/04/000303/20221004000742/70760.htm) · [접수별 신규상장 증거](../../examples/historical-market-action-identity.json)

각 행에는 원문 접수·문서번호, 기준일, 종목 목록 원문·행 SHA-256, 관련 상호 공시의 링크·해시, 근거 확보 시각을 남겼습니다. 같은 코드가 표시돼도 게시일과 조치일의 ISIN이 다르면 게시일 이름 일치를 조치일에 적용할 수 없습니다. 법적 상호 변경 효력과 과거 최초 공개 시각은 별도 검증 범위입니다.

## 재검증

AI 서버에서 [입력 명세](../../examples/historical-market-action-identity-inputs.json)의 원장·자료 SHA-256을 확인한 뒤 결과를 다시 계산합니다. 원본 KRX 목록, 기존 이름 변경 보고서와 새 KIND 원문 영수증은 로컬 연구 자료에 있습니다.

~~~powershell
$identityOptions = @(
  '--manifest', '../../docs/examples/historical-market-action-identity-inputs.json',
  '--ledger', '../../docs/examples/historical-market-action-monthly.jsonl',
  '--artifacts', 'research-artifacts',
  '--job', 'research-artifacts/h05-symbol-identity',
  '--output', '../../docs/examples/historical-market-action-identity.json'
)
.\.venv\Scripts\python.exe -m app.replay.historical_market_action_identity audit @identityOptions
~~~

오프라인 감사에서 248개 접수·250행과 보통주 식별자 판정을 바이트 단위로 재현했습니다. 결과 파일의 SHA-256은 `1a2a48417e76b03b25f5e1085655b469eceede49427413414533cb42ee764799`입니다. AI 서버 회귀는 1,418건 통과이며 격리 Java/MySQL 내보내기 자료가 필요한 조건부 검사 1건을 건너뛰었습니다.
