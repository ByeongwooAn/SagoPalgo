# 모의매매 테스트

전략 문서와 실행 기간별 결과를 관리합니다. 이번 실행은 KIS의 SK하이닉스 실시간 시세를 읽고 별도 가상 원장으로 매매합니다.

| 실행 | 종목과 규칙 | 거래 기간 KST | 결과 경로 |
| --- | --- | --- | --- |
| `2026-11-27-000660` | [SK하이닉스 5% 매수·매도 전략](strategies/sk-hynix-five-percent.md) | 2026-11-27 기동 이후 ~ 2026-12-04 정규장 마감 | [일별 보고서 폴더](reports/2026-11-27-000660/daily/) · [최종 보고서](reports/2026-11-27-000660/final.md) |

## 결과 파일

- `reports/<실행 ID>/status.json`에 최근 기동 상태, 수신 건수, 마지막 거래소 시각과 보류 이유를 기록합니다.
- `reports/<실행 ID>/daily/<거래일>.md`에 주문·체결별 근거와 결과, 마감 가상 현금과 보유 수량, 일일 순손익과 실현·미실현손익을 기록합니다. 주문이 없는 거래일에도 보고서를 저장합니다.
- `reports/<실행 ID>/final.md`에 거래일별 요약, 총손익·수익률, 최대 보유 매입원가, 관측 기준 최대 낙폭, 잔여 보유를 기록합니다. 예정 시각은 종료일 장 마감 2분 후입니다. 가격 조회 실패 시 자료 대기로 표시하고 복구 후 갱신합니다.
- 보고서는 Windows 작업 폴더에 남는 로컬 실행 결과입니다. Docker 볼륨에는 실행별 원장과 KIS 시세 조회용 토큰 캐시가 별도로 저장됩니다.

## Docker 실행과 재개

초기 등록 및 이후 Docker Desktop을 시작한 뒤 상태를 확인할 때 저장소 루트에서 실행합니다. 개발용 Compose 프로젝트와 모의매매용 Compose 프로젝트는 분리되어 있습니다.

```powershell
docker compose -f compose.paper-trading.yml up -d --build
docker compose -f compose.paper-trading.yml ps
docker compose -f compose.paper-trading.yml logs --tail 30 trial
```

초기 등록 이후에는 Docker Desktop이 컨테이너를 다시 시작하면 기존 원장을 읽어 자동 재개합니다. Docker가 꺼진 구간에는 체결을 소급 생성하지 않고 일별 보고서에 관측 공백을 남깁니다. 마감 시점에 Docker가 꺼져 있으면 다시 켰을 때 날짜가 일치하는 종가를 조회해 보고서를 생성합니다. 컨테이너를 직접 중지하거나 제거했다면 위의 `up`으로 다시 등록합니다. 기존 원장을 이어가려면 `trial-state` 볼륨을 보존해야 합니다.

후속 테스트는 `docker/paper-trading/trials/`에 새 실행 ID와 세션 일정을 추가하고 `SAGOPALGO_PAPER_TRIAL_ID`로 선택합니다. 실행 ID는 `YYYY-MM-DD-종목코드`를 기본으로 하고 같은 날의 반복 실행에는 영문 또는 숫자 접미사를 붙입니다. 실행 ID마다 원장과 보고서가 생성됩니다.
