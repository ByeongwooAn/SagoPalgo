"""Deterministic, cash-only strategy evaluated against sampled KRX trades."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN


D = Decimal
ZERO = D(0)
UNIT = D('0.0001')
CUT = D('0.95')
TARGET = D('1.05')
SMA_CUT = D('0.98')
SMA_RULE = '직전 5거래일 종가 평균의 98%와 전일 종가 중 낮은 가격 이하'
PREVIOUS_CLOSE_RULE = '직전 정규장 종가 × 0.95'


@dataclass(frozen=True)
class Tick:
    at: datetime
    price: Decimal
    volume: Decimal


@dataclass(frozen=True)
class Costs:
    fee_bps: Decimal
    sell_tax_bps: Decimal

    def fee(self, gross):
        return (gross * self.fee_bps / 10000).to_integral_value(rounding=ROUND_CEILING)

    def tax(self, gross):
        return (gross * self.sell_tax_bps / 10000).to_integral_value(rounding=ROUND_CEILING)

    def proceeds(self, gross):
        return gross - self.fee(gross) - self.tax(gross)

    def affordable(self, budget, price):
        # Find the largest 0.0001-share lot whose rounded fee fits the cash budget.
        low, high = 0, int(budget / (price * UNIT))
        while low < high:
            middle = (low + high + 1) // 2
            gross = middle * UNIT * price
            if gross + self.fee(gross) <= budget:
                low = middle
            else:
                high = middle - 1
        return low * UNIT


def initial_state(cash, started):
    return dict(started=started.isoformat(), cash=str(cash), quantity='0', cost='0',
                realized='0', last_buy=None, last_sale=None, liquidation=None, pending=None,
                next_id=1, peak=str(cash), drawdown='0', max_invested='0', days={}, hold=None)


def day_state(state, day):
    return state['days'].setdefault(str(day), dict(open=None, prior=None, first=None, last=None,
        observations=0, gaps=[], issues={}, events=[], close=None))


def equity(state, price, costs):
    return D(state['cash']) + costs.proceeds(D(state['quantity']) * price)


def mark_risk(state, price, costs):
    value = equity(state, price, costs)
    peak = max(D(state['peak']), value)
    state['peak'] = str(peak)
    state['drawdown'] = str(max(D(state['drawdown']), (peak - value) / peak))


def condition(state, prior, tick, costs, entry_average=None):
    held = D(state['quantity'])
    if held:
        selling = state['liquidation']
        base = D(selling['cost'] if selling else state['cost'])
        estimate = costs.proceeds(held * tick.price) + (D(selling['net']) if selling else ZERO)
        if estimate >= base * TARGET:
            return dict(side='SELL', rule='청산 순수령액 ≥ 총매입원가 × 1.05',
                        basis=str(base), threshold=str(base * TARGET), observed=str(estimate))
        if selling:
            return None
        rule, base = '직전 매수 평균 체결가 × 0.95', D(state['last_buy'])
    elif state['last_sale'] is not None:
        rule, base = '직전 청산 평균 체결가 × 0.95', D(state['last_sale'])
    elif entry_average is not None:
        threshold = min(entry_average * SMA_CUT, prior)
        if tick.price <= threshold:
            return dict(side='BUY', rule=SMA_RULE, basis=str(entry_average),
                        threshold=str(threshold), observed=str(tick.price))
        return None
    else:
        rule, base = PREVIOUS_CLOSE_RULE, prior
    if tick.price <= base * CUT:
        return dict(side='BUY', rule=rule, basis=str(base), threshold=str(base * CUT),
                    observed=str(tick.price))
    return None


def finish_order(state, day, at, reason):
    order = state['pending']
    if order is None:
        return
    if order['side'] == 'BUY' and D(order['filled']) > 0:
        state['last_buy'] = str(D(order['gross']) / D(order['filled']))
    day['events'].append(dict(kind=reason, id=order['id'], at=at.isoformat(), side=order['side'],
                              remaining=order['remaining']))
    state['pending'] = None


def apply_tick(state, day, tick, costs, amount):
    order = state['pending']
    if order is not None and order['side'] == 'BUY':
        evidence = None
        if tick.price <= D(order['threshold']):
            evidence = {key: order[key] for key in ('side', 'rule', 'basis', 'threshold')}
            evidence['observed'] = str(tick.price)
    else:
        average = day.get('entry_average')
        evidence = condition(state, D(day['prior']), tick, costs, D(average) if average is not None else None)
    if order is None:
        if evidence is None:
            return
        budget = min(amount, D(state['cash']))
        if evidence['side'] == 'BUY' and not costs.affordable(budget, tick.price):
            day['issues']['가상 현금으로 최소 수량 매수 불가'] = 1
            return
        order = dict(**evidence, id=state['next_id'], at=tick.at.isoformat(),
                     price=str(tick.price), budget=str(budget), remaining=None,
                     filled='0', gross='0', spent='0')
        state['next_id'] += 1
        state['pending'] = order
        day['events'].append(dict(kind='신호', **order))
        return

    if tick.at <= datetime.fromisoformat(order['at']):
        return
    if evidence is None or evidence['side'] != order['side']:
        finish_order(state, day, tick.at, '조건 이탈로 잔량 취소')
        return

    buying = order['side'] == 'BUY'
    if buying:
        available = D(order['budget']) - D(order['spent'])
        affordable = costs.affordable(available, tick.price)
        remaining = affordable if order['remaining'] is None else min(D(order['remaining']), affordable)
    else:
        remaining = D(state['quantity'])
    qty = min(remaining, tick.volume.quantize(UNIT, rounding=ROUND_DOWN))
    if not qty:
        finish_order(state, day, tick.at, '수량 또는 가상 현금 부족으로 잔량 취소')
        return

    gross = qty * tick.price
    fee = costs.fee(gross)
    tax = ZERO if buying else costs.tax(gross)
    cash, held, cost = (D(state[key]) for key in ('cash', 'quantity', 'cost'))
    realized = ZERO
    if buying:
        change = -(gross + fee)
        held += qty
        cost -= change
        order['spent'] = str(D(order['spent']) - change)
        state['max_invested'] = str(max(D(state['max_invested']), cost))
    else:
        change = gross - fee - tax
        liquidation = state['liquidation'] or dict(cost=str(cost), qty='0', gross='0', net='0')
        for key, value in [('qty', qty), ('gross', gross), ('net', change)]:
            liquidation[key] = str(D(liquidation[key]) + value)
        allocated = cost if qty == held else cost * qty / held
        realized = change - allocated
        cost -= allocated
        held -= qty
        state['realized'] = str(D(state['realized']) + realized)
        state['liquidation'] = liquidation if held else None
        if not held:
            state['last_sale'] = str(D(liquidation['gross']) / D(liquidation['qty']))

    state.update(cash=str(cash + change), quantity=str(held), cost=str(cost))
    order['remaining'] = str(remaining - qty)
    order['filled'] = str(D(order['filled']) + qty)
    order['gross'] = str(D(order['gross']) + gross)
    day['events'].append(dict(kind='체결', **evidence, id=order['id'], at=tick.at.isoformat(),
        price=str(tick.price), quantity=str(qty), gross=str(gross), fee=str(fee), tax=str(tax),
        change=str(change), realized=str(realized), cash=state['cash'], held=state['quantity'],
        remaining=order['remaining']))
    if qty == remaining:
        finish_order(state, day, tick.at, '주문 완료')
