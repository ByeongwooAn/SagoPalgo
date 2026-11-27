"""Publish reports from the committed paper ledger, including data coverage."""

from decimal import Decimal as D


def money(value):
    return '미확정' if value is None else f'{D(value):,.2f}원'


def number(value):
    return '—' if value is None else f'{D(value).normalize():f}'


def stats(day, daily, state, costs):
    mark = daily['close']
    held, cash, basis = (D(mark[key]) for key in ('quantity', 'cash', 'cost'))
    hold = state['hold']
    verified = mark['price'] is not None and not (hold and day >= hold['day'])
    value = costs.proceeds(held * D(mark['price'])) if held and verified else (None if held else D(0))
    fills = [event for event in daily['events'] if event['kind'] == '체결']
    return dict(equity=None if value is None else cash + value,
                unrealized=None if value is None else value - basis,
                realized=sum((D(event['realized']) for event in fills), D(0)),
                buy=sum(event['side'] == 'BUY' for event in fills),
                sell=sum(event['side'] == 'SELL' for event in fills))


def daily_report(config, day, daily, totals, change, state):
    mark = daily['close']
    status = {True: '정규장', False: '휴장', None: '개장 확인 대기'}[daily['open']]
    info = [f"# {config['name']} 모의매매 {day}", '',
        f"- 실행 `{config['id']}` · KST · {status}",
        f"- 최초 기동 `{state['started']}` · 직전 정규장 종가 {money(daily['prior'])}",
        f"- 장중 수신 {daily['observations']:,}건 · 최초 `{daily['first'] or '없음'}` · 마지막 `{daily['last'] or '없음'}`",
        f"- 정규장 종가 {money(mark['price'])} · 수신 `{mark['asof'] or '대기'}`",
        f"- 체결 매수 {totals['buy']}건 · 매도 {totals['sell']}건",
        f"- 마감 현금 {money(mark['cash'])} · 보유 {number(mark['quantity'])}주 · 남은 매입원가 {money(mark['cost'])}",
        f"- **일일 순손익 {money(change)}** · 당일 실현손익 {money(totals['realized'])} · 마감 미실현손익 {money(totals['unrealized'])}",
        f"- 마감 순자산 {money(totals['equity'])} · 누적 실현손익 {money(mark['realized'])}",
        '', '일일 순손익은 이전 마감 순자산 대비 증감입니다. 첫날은 가상 시작 현금과 비교합니다. '
        '마감 순자산은 가상 현금과 보유분 예상 순매도대금의 합입니다.', '', '## 주문과 체결', '']
    if not daily['events']:
        info += ['기록된 주문과 체결이 없습니다.', '']
    for event in daily['events']:
        side = '매수' if event['side'] == 'BUY' else '매도'
        info += [f"### 주문 {event['id']} {side} {event['kind']}", '', f"- KIS 체결 관측 또는 상태 변경 시각 `{event['at']}`"]
        if event['kind'] in {'신호', '체결'}:
            info += [f"- 근거 {event['rule']} · 기준 {money(event['basis'])} · 조건 경계 {money(event['threshold'])} · 관측값 {money(event['observed'])}"]
        if event['kind'] == '체결':
            info += [f"- 결과 {money(event['price'])} × {number(event['quantity'])}주 · 총거래대금 {money(event['gross'])} · 수수료 {money(event['fee'])} · 매도 비용 {money(event['tax'])}",
                f"- 원장 반영 {money(event['change'])} · 실현손익 {money(event['realized'])} · 잔고 {money(event['cash'])} 및 {number(event['held'])}주"]
        if event['remaining'] is not None:
            info += [f"- 미체결 잔량 {number(event['remaining'])}주"]
        info += ['']
    info += ['## 시세 공백과 보류', '']
    if daily['open'] is not False:
        info += [f'- 30초 초과 관측 공백 {len(daily["gaps"])}건']
        info += [f'- `{start}` ~ `{end}`' for start, end in daily['gaps']]
    info += [f'- {issue} ({count}회)' for issue, count in daily['issues'].items()]
    if state['hold'] and day >= state['hold']['day']:
        hold = state['hold']
        info += [f"- 기준가 대조 중지 · {hold['day']} 직전 종가 {money(hold['prior'])}, KRX 기준가 {money(hold['base'])}"]
    return '\n'.join(info).rstrip() + '\n'


def publish(folder, state, config, costs, finished, write):
    def update(path, body):
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            write(path, body)

    start = D(config['cash'])
    previous = start
    summaries = []
    for day, daily in sorted(state['days'].items()):
        if daily['close'] is None:
            continue
        totals = stats(day, daily, state, costs)
        value = totals['equity']
        change = None if previous is None or value is None else value - previous
        update(folder / 'daily' / f'{day}.md', daily_report(config, day, daily, totals, change, state))
        previous = value
        summaries.append((day, daily, totals, change))
    if not finished:
        return

    last_day, last, totals, _ = summaries[-1]
    profit = None if previous is None else previous - start
    returns = '미확정' if profit is None else f'{profit / start:.2%}'
    coverage_count = sum(daily['observations'] > 0 for _, daily, _, _ in summaries)
    buy_count = sum(values['buy'] for _, _, values, _ in summaries)
    sell_count = sum(values['sell'] for _, _, values, _ in summaries)
    total_cost = sum((D(event['fee']) + D(event['tax']) for _, daily, _, _ in summaries
                      for event in daily['events'] if event['kind'] == '체결'), D(0))
    missing_mark = any(daily['open'] is not False and daily['close']['price'] is None
                       for _, daily, _, _ in summaries)
    status = '종가 자료 대기' if missing_mark else '마감 집계'
    if state['hold']:
        status += ' · 기준가 확인 필요'
    lines = [f"# {config['name']} 모의매매 최종 보고서", '',
        f"- 실행 `{config['id']}` · {summaries[0][0]} ~ {last_day} KST · {status}",
        f"- 가상 시작 현금 {money(start)} · 장중 시세 관측일 {coverage_count}/{len(summaries)}일",
        f"- **최종 순손익 {money(profit)} · 수익률 {returns}** · 마감 순자산 {money(previous)}",
        f"- 누적 실현손익 {money(last['close']['realized'])} · 마감 미실현손익 {money(totals['unrealized'])}",
        f"- 누적 매수 체결 {buy_count}건 · 매도 체결 {sell_count}건 · 체결 비용 {money(total_cost)}",
        f"- 마감 현금 {money(last['close']['cash'])} · 잔여 {number(last['close']['quantity'])}주",
        f"- 최대 보유 매입원가 {money(state['max_invested'])} · 관측 기준 최대 낙폭 {D(state['drawdown']):.2%}",
        f"- 비용 가정 편도 수수료 {config['fee_bps']}bps · 매도 추가 비용 {config['sell_tax_bps']}bps", '',
        '최대 낙폭은 확인된 장중 시세와 마감 평가에서 구한 값입니다. 관측 공백과 체결 모형은 일별 보고서와 전략 문서에서 확인할 수 있습니다.', '',
        '## 일별 결과', '', '| 거래일 | 시세 관측 | 매수 체결 | 매도 체결 | 일일 순손익 | 마감 순자산 |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for day, daily, values, change in summaries:
        lines += [f"| [{day}](daily/{day}.md) | {daily['observations']:,} | {values['buy']} | {values['sell']} | {money(change)} | {money(values['equity'])} |"]
    update(folder / 'final.md', '\n'.join(lines) + '\n')
