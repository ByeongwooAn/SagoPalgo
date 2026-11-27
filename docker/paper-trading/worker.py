"""Run one paper trial and publish crash-recoverable local reports."""

import argparse
from datetime import date, datetime, time, timedelta
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import re
from time import sleep

from market import DataError, KST, KisMarket, now
from reports import publish
from strategy import Costs, D, apply_tick, day_state, finish_order, initial_state, mark_risk


POLL_SECONDS = 10
GAP_SECONDS = 30
LOG = logging.getLogger('paper-trial')


def atomic_write(path, string, durable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    with temp.open('w', encoding='utf-8', newline='\n') as file:
        file.write(string)
        file.flush()
        os.fsync(file.fileno())
    temp.replace(path)
    if durable:
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


class Trial:
    def __init__(self, config_path, storage, reports, market_factory=KisMarket, clock=now):
        raw = config_path.read_bytes()
        self.config = json.loads(raw)
        cfg = self.config
        trial_id = cfg['id']
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', trial_id):
            raise ValueError('잘못된 모의실험 식별자입니다.')
        self.fingerprint = hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()
        self.start_cash = D(cfg['cash'])
        self.order_amount = D(cfg['order_amount'])
        self.costs = Costs(D(cfg['fee_bps']), D(cfg['sell_tax_bps']))
        self.sessions = {}
        for key, times in cfg['sessions'].items():
            day = date.fromisoformat(key)
            opening, closing = (datetime.combine(day, time.fromisoformat(t), KST) for t in times)
            if opening >= closing:
                raise ValueError('잘못된 모의실험 세션입니다.')
            self.sessions[day] = (opening, closing)
        if not self.sessions or min(self.start_cash, self.order_amount) <= 0 or min(
                self.costs.fee_bps, self.costs.sell_tax_bps) < 0 or self.costs.fee_bps + self.costs.sell_tax_bps >= 10000:
            raise ValueError('잘못된 모의실험 비용 또는 세션 설정입니다.')
        self.finish_at = self.sessions[max(self.sessions)][1] + timedelta(minutes=2)
        self.clock = clock
        self.folder = storage / trial_id
        self.folder.mkdir(parents=True, exist_ok=True)
        self.report_path = reports / trial_id
        self.state_path = self.folder / 'ledger.json'
        self.lock = (self.folder / 'worker.lock').open('a')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if self.state_path.exists():
            self.state = json.loads(self.state_path.read_text(encoding='utf-8'))
            if self.state.get('config_sha256') != self.fingerprint:
                raise ValueError('기존 가상 원장의 실행 설정이 다릅니다. 새 실행 식별자가 필요합니다.')
        else:
            self.state = initial_state(self.start_cash, self.clock())
            self.state['config_sha256'] = self.fingerprint
            self.save()
        self.market = market_factory(cfg['symbol'], storage / 'kis-token.json')
        self.last_close_attempt = {}
        self.last_issue = None
        self.last_status = None

    def save(self):
        atomic_write(self.state_path, json.dumps(self.state, ensure_ascii=False, indent=2) + '\n', durable=True)

    def add_issue(self, daily, issue):
        daily['issues'][issue] = daily['issues'].get(issue, 0) + 1
        if issue != self.last_issue:
            LOG.warning('%s', issue)
            self.last_issue = issue

    def verify_session(self, day, daily):
        if daily['open'] is None:
            daily['open'] = self.market.is_open(day)
        return daily['open']

    def monitor(self, day, opening, closing):
        daily = day_state(self.state, day)
        try:
            if not self.verify_session(day, daily):
                return
            if self.state['hold']:
                raise DataError('기준가 변경 확인 필요로 전략 중지')
            if daily['prior'] is None:
                prior_date, price = self.market.previous_close(day)
                daily['prior'] = str(price)
                daily['prior_date'] = prior_date.isoformat()
            base, tick = self.market.live(day, opening, closing)
            if base != D(daily['prior']):
                self.state['hold'] = dict(day=str(day), prior=daily['prior'], base=str(base))
                raise DataError('기준가 변경 확인 필요로 전략 중지')
        except DataError as exc:
            self.add_issue(daily, str(exc))
            self.save()
            return

        if daily['last'] is not None and tick.at <= datetime.fromisoformat(daily['last']):
            return
        start = datetime.fromisoformat(self.state['started']).replace(microsecond=0)
        if tick.at < start:
            return
        previous = datetime.fromisoformat(daily['last']) if daily['last'] else max(start, opening)
        if tick.at - previous > timedelta(seconds=GAP_SECONDS):
            daily['gaps'].append([previous.isoformat(), tick.at.isoformat()])
        if daily['first'] is None:
            daily['first'] = tick.at.isoformat()
            LOG.info('%s 첫 시세 확인 KIS KRX %s원 공급자 %s', day, tick.price, tick.at.isoformat())
        if self.last_issue:
            LOG.info('KRX 정규장 시세 수신 재개')
            self.last_issue = None
        daily['last'] = tick.at.isoformat()
        daily['observations'] += 1
        before = len(daily['events'])
        mark_risk(self.state, tick.price, self.costs)
        apply_tick(self.state, daily, tick, self.costs, self.order_amount)
        mark_risk(self.state, tick.price, self.costs)
        self.save()
        for event in daily['events'][before:]:
            LOG.info('%s 주문 %s %s %s', day, event['id'], event['side'], event['kind'])

    def capture_close(self, day, opening, closing, at):
        daily = day_state(self.state, day)
        if daily['close'] is None:
            finish_order(self.state, daily, closing, '정규장 종료로 잔량 취소')
            start = datetime.fromisoformat(self.state['started'])
            last = datetime.fromisoformat(daily['last']) if daily['last'] else max(start, opening)
            if closing - last > timedelta(seconds=GAP_SECONDS):
                daily['gaps'].append([last.isoformat(), closing.isoformat()])
            daily['close'] = {key: self.state[key] for key in ('cash', 'quantity', 'cost', 'realized')}
            daily['close'].update(price=None, asof=None)
            self.save()
        mark = daily['close']
        if daily['open'] is False or mark['price'] is not None:
            return
        if day in self.last_close_attempt and at - self.last_close_attempt[day] < timedelta(minutes=1):
            return
        self.last_close_attempt[day] = at
        try:
            if self.verify_session(day, daily):
                price = self.market.close(day)
                if price is None:
                    raise DataError('날짜가 일치하는 KRX 일봉 종가 미수신')
                mark.update(price=str(price), asof=self.clock().isoformat())
                if day == at.date() and not self.state['hold']:
                    mark_risk(self.state, price, self.costs)
                LOG.info('%s 정규장 종가 확인 %s원', day, price)
        except DataError as exc:
            self.add_issue(daily, str(exc))
        self.save()

    def step(self):
        at = self.clock()
        for day, (opening, closing) in sorted(self.sessions.items()):
            if at >= closing + timedelta(minutes=2):
                self.capture_close(day, opening, closing, at)
        status = '대기'
        if at >= self.finish_at:
            status = '종료'
        elif at.date() in self.sessions:
            opening, closing = self.sessions[at.date()]
            if opening <= at < closing:
                self.monitor(at.date(), opening, closing)
                if self.state['hold']:
                    status = '기준가 확인 필요'
                else:
                    status = '시세 확인 대기' if self.last_issue else '정규장 관측'
            elif closing <= at < closing + timedelta(minutes=2):
                status = '장 마감 자료 대기'
        day = self.state['days'].get(str(at.date()), {})
        current = dict(status=status, asof=at.isoformat(), last_market_at=day.get('last'),
                       observed=day.get('observations', 0), last_issue=self.last_issue,
                       pending=self.state['pending'] is not None, hold=self.state['hold'])
        atomic_write(self.report_path / 'status.json', json.dumps(current, ensure_ascii=False, indent=2) + '\n')
        self.last_status = status
        publish(self.report_path, self.state, self.config, self.costs, at >= self.finish_at, atomic_write)
        return status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--storage', type=Path, default=Path('/state'))
    parser.add_argument('--reports', type=Path, default=Path('/reports'))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    trial = Trial(args.config, args.storage, args.reports)
    LOG.info('%s 가상 원장 준비 (최초 기동 %s, 종료 %s)',
             trial.config['id'], trial.state['started'], trial.finish_at.isoformat())
    while True:
        try:
            prior = trial.last_status
            status = trial.step()
            if status != prior:
                LOG.info('실행 상태 %s', status)
        except OSError as exc:
            LOG.error('원장 또는 보고서 저장 실패 (errno=%s). 재시작하여 원장을 복구합니다.', exc.errno)
            raise SystemExit(1) from None
        if trial.last_status == '종료':
            sleep(60)
        else:
            sleep(POLL_SECONDS if trial.last_status in {'정규장 관측', '시세 확인 대기'} else 20)


if __name__ == '__main__':
    main()
