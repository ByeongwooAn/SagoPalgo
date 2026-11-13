# H05 소각 상세 962행의 주권 종류 대조

2023-11-01~2026-11-02 KOSPI·KOSDAQ 기준정보 검토에서 주권 종류가 비어 있던 주식발행 상세 962행을 KIND 변경상장 공지 910건에 연결했습니다. 같은 시장·발행사의 변경상장일 전 14일 이내 공지를 후보로 삼고, 본문에서 확인한 상장일·소각 사유·감소 수량·변경 후 발행주식수가 일치할 때만 주권과 종목코드를 기록했습니다. 유가증권시장 공지에 명시된 경우 ISIN도 기록했습니다. [이전 소각 상세 감사](historical-corporate-action-outcome-census.md#소각과-거래소-조치)

| 변경상장 공지에서 확인한 주권 종류 | 상세 행 |
| --- | ---: |
| 보통주 | 905 |
| 우선주 | 51 |
| 기타 주권·주식예탁증서 | 6 |
| **합계** | **962** |

현대차처럼 공지 한 건에 여러 종류가 실리면 종류별 종목코드와 수량을 대조합니다. 정정 공지 묶음 4건에서는 원본과 정정본 양쪽에서 주권·수량이 동일한 항목을 확인했습니다. [현대차 변경상장](https://kind.krx.co.kr/external/2026/09/17/000117/20260917000264/68155.htm)

| 발행일·소각일 비교 | 행 |
| --- | ---: |
| 공지 날짜가 상세 발행일과 일치 | 839 |
| 공지 본문에 날짜 없음, 상세 발행일 보존 | 121 |
| 상세 발행일과 공지 날짜 불일치 | 1 |
| 원본·정정본의 날짜가 서로 다름 | 1 |

- 고려아연 보통주의 주식발행 상세에는 2025-09-30이 표시됐습니다. 변경상장 공지와 세이브로의 이익소각 기록은 모두 2025-09-11을 표시합니다. 보고서는 상세 발행일, 거래소 공지 날짜, 예탁결제원 날짜를 각각 보존합니다. [고려아연 변경상장](https://kind.krx.co.kr/external/2025/09/25/000078/20250925000078/68155.htm) · [세이브로 증권발행내역](https://seibro.or.kr/websquare/control.jsp?w2xPath=/IPORTAL/user/company/BIP_CNTS01012V.xml&menuNo=282)
- 셀트리온 보통주의 원본에는 2024-01-06, 정정본과 상세에는 2025-01-06이 표시됐습니다. 두 버전에서 일치한 주권·수량과 버전별 날짜를 보존했습니다. 같은 조건으로 확인한 세이브로 응답에는 연결되는 행이 없었습니다. [원본](https://kind.krx.co.kr/external/2025/01/13/000036/20250113000053/68155.htm) · [정정본](https://kind.krx.co.kr/external/2025/01/14/000318/20250114000927/68155.htm)
- 현대차 보통주 2025-05-21 변경상장의 예탁결제원 기록은 공지와 주권 종류·발행일이 일치했습니다. 예탁결제원 조회는 이 3개 선정 사례를 대상으로 했습니다. [세이브로 증권발행내역](https://seibro.or.kr/websquare/control.jsp?w2xPath=/IPORTAL/user/company/BIP_CNTS01012V.xml&menuNo=282)

## 재감사

AI 서버 디렉터리에서 실행합니다. 이번 로컬 원문 영수증 2,741개와 이전 두 보고서·이전 원문 명세를 해시로 고정했습니다. [검토 명세](examples/cancellation-share-class-census.json)

~~~powershell
$py = '.\.venv\Scripts\python.exe'
$h = @('--manifest', '../../docs/examples/cancellation-share-class-census.json',
       '--artifacts', 'research-artifacts', '--job', 'research-artifacts/cancellation-share-class-20261113')
& $py -m app.replay.cancellation_share_class_census build @h
& $py -m app.replay.cancellation_share_class_census audit @h
~~~

보고서 SHA-256은 `3ff4e9cec41dc63f4fdd6c2c50eb5991748a0dddabb3dae689844d681a584568`입니다.

상장일 경계 바깥의 소각 사건과 본문 날짜가 비어 있는 121행의 독립 소각일 근거가 남아 있습니다. 원문의 과거 최초 공개 시각은 별도 감사 대상이며, 보고서는 연구용입니다. [남은 작업](remaining-development-units.md)
