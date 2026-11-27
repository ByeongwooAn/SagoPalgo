from datetime import date, datetime, timedelta
from decimal import Decimal as D
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market import DataError, KST, KisMarket
from strategy import Costs, Tick, apply_tick, day_state, initial_state
from worker import Trial


DAY = date(2026, 11, 27)
START = datetime(2026, 11, 27, 9, tzinfo=KST)
COSTS = Costs(D(5), D(20))
AMOUNT = D(100000)


class Strategy(unittest.TestCase):
    def setUp(self):
        self.state = initial_state(D(1000000), START)
        self.day = day_state(self.state, DAY)
        self.day['prior'] = '1000000'
        self.clock = START

    def tick(self, price, volume='100'):
        self.clock += timedelta(seconds=10)
        apply_tick(self.state, self.day, Tick(self.clock, D(price), D(volume)), COSTS, AMOUNT)

    def fills(self):
        return [event for event in self.day['events'] if event['kind'] == '체결']

    def test_threshold_and_gap_use_a_new_observation_and_one_order(self):
        self.tick('950001')
        self.assertFalse(self.day['events'])
        self.tick('950000')
        self.assertIsNotNone(self.state['pending'])
        apply_tick(self.state, self.day, Tick(self.clock, D(880000), D(1)), COSTS, AMOUNT)
        self.assertFalse(self.fills())
        self.tick('880000')
        self.assertEqual(self.state['last_buy'], '880000')
        self.assertEqual(len(self.fills()), 1)
        self.tick('836001')
        self.assertIsNone(self.state['pending'])
        self.tick('836000')
        self.tick('810000')
        self.assertEqual(len(self.fills()), 2)
        self.assertEqual(self.state['last_buy'], '810000')

    def test_cash_is_the_only_limit_and_residual_cash_participates(self):
        self.state['cash'] = '163000'
        self.tick('940000')
        self.tick('940000')
        self.tick('880000')
        self.tick('880000')
        self.assertEqual(len(self.fills()), 2)
        self.assertLess(D(self.state['cash']), D(100))
        self.assertGreaterEqual(D(self.state['cash']), D(0))
        self.state = initial_state(D(1000000), START)
        self.day = day_state(self.state, DAY)
        self.day['prior'] = '1000000'
        price = D(940000)
        for _ in range(12):
            self.tick(price)
            self.tick(price)
            price = (price * D('.94')).to_integral_value()
        self.assertGreater(len(self.fills()), 5)
        self.assertGreaterEqual(D(self.state['cash']), D(0))
        self.assertGreater(D(self.state['max_invested']), D(950000))

    def test_sma_entry_requires_both_bounds_and_does_not_change_add_on(self):
        self.day.update(prior='1053000', entry_average='1087800')
        self.tick('1053001')
        self.assertIsNone(self.state['pending'])
        self.tick('1053000')
        self.assertEqual(D(self.state['pending']['threshold']), D('1053000'))
        self.tick('1053001')
        self.assertFalse(self.fills())
        self.day['entry_average'] = '1000000'
        self.tick('980001')
        self.assertIsNone(self.state['pending'])
        self.tick('980000')
        self.tick('980000')
        self.tick('931001')
        self.assertIsNone(self.state['pending'])
        self.tick('931000')
        self.assertEqual(D(self.state['pending']['threshold']), D('931000'))

    def test_partial_buy_preserves_order_basis_and_budget(self):
        self.tick('900000')
        self.tick('880000', '.05')
        self.assertEqual(D(self.state['quantity']), D('.05'))
        self.tick('880000')
        self.assertIsNone(self.state['pending'])
        self.assertEqual(self.state['last_buy'], '880000')
        self.assertGreaterEqual(D(self.state['cash']), D(900000))
        self.assertEqual({event['id'] for event in self.fills()}, {1})

    def test_partial_sale_then_reentry_uses_entire_liquidation(self):
        self.tick('90000')
        self.tick('90000')
        held = D(self.state['quantity'])
        self.tick('100000')
        self.tick('100000', '.4')
        self.tick('80000')
        self.tick('80000')
        self.assertIsNotNone(self.state['liquidation'])
        self.assertIsNone(self.state['pending'])
        self.tick('101000')
        self.tick('101000')
        average = (D(100000) * D('.4') + D(101000) * (held - D('.4'))) / held
        self.assertEqual(D(self.state['last_sale']), average)
        self.assertEqual(D(self.state['quantity']), D(0))
        self.tick(average * D('.95'))
        self.assertEqual(self.state['pending']['rule'], '직전 청산 평균 체결가 × 0.95')

    def test_profit_target_applies_costs_before_emitting_sell_signal(self):
        self.tick('90000')
        self.tick('90000')
        self.tick('94500')
        self.assertIsNone(self.state['pending'])
        self.tick('94850')
        self.assertEqual(self.state['pending']['side'], 'SELL')
        self.tick('94500')
        self.assertIsNone(self.state['pending'])
        self.assertEqual(len(self.fills()), 1)


class FakeMarket:
    def __init__(self, clock):
        self.clock = clock
        self.base = D(1000000)
        self.price = D(900000)
        self.close_price = None

    def is_open(self, day):
        return True

    def previous_close(self, day):
        return day - timedelta(days=1), D(1000000)

    def recent_closes(self, day, count):
        return [(day - timedelta(days=offset), D(1000000)) for offset in range(count, 0, -1)]

    def live(self, day, opening, closing):
        return self.base, Tick(self.clock[0], self.price, D(10))

    def close(self, day):
        return self.close_price


class Integration(unittest.TestCase):
    def test_restart_retains_pending_and_emits_daily_and_final_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'test.json'
            config.write_text(json.dumps(dict(id='test-trial', symbol='000660', name='SK하이닉스',
                cash='1000000', order_amount='100000', fee_bps='5', sell_tax_bps='20',
                sessions={str(DAY): ['09:00', '15:30']}), indent=2), encoding='utf-8')
            clock = [START]
            market = FakeMarket(clock)
            arguments = (config, root / 'state', root / 'reports', lambda *_: market, lambda: clock[0])
            first = Trial(*arguments)
            self.assertEqual(first.step(), '정규장 관측')
            self.assertTrue(first.state['pending'])
            first.lock.close()
            config.write_bytes(config.read_bytes().replace(b'\n', b'\r\n'))

            trial = Trial(*arguments)
            self.addCleanup(trial.lock.close)
            trial.step()
            self.assertEqual(trial.state['cash'], '1000000')
            clock[0] += timedelta(minutes=2)
            trial.step()
            self.assertLess(D(trial.state['cash']), D(1000000))
            clock[0] = START.replace(hour=15, minute=32)
            self.assertEqual(trial.step(), '종료')
            daily = root / 'reports/test-trial/daily/2026-11-27.md'
            final = root / 'reports/test-trial/final.md'
            self.assertIn('종가 자료 대기', final.read_text(encoding='utf-8'))
            self.assertIn('일일 순손익 미확정', daily.read_text(encoding='utf-8'))
            market.close_price = D(920000)
            clock[0] += timedelta(minutes=1)
            trial.step()
            report = daily.read_text(encoding='utf-8')
            self.assertIn('최초', report)
            self.assertIn('순손익 1,913.00원', report)
            self.assertEqual(report.count('매수 체결\n'), 1)
            self.assertIn('관측 공백 2건', report)
            self.assertIn('최종 순손익 1,913.00원', final.read_text(encoding='utf-8'))
            dashboard = json.loads((root / 'reports/test-trial/dashboard.json').read_text(encoding='utf-8'))
            self.assertEqual(dashboard['fillCount'], 1)
            self.assertEqual(D(dashboard['portfolio']['netAsset']), D('1001913'))
            self.assertEqual(D(dashboard['closedDays'][0]['profit']), D('1913'))
            self.assertIsNone(trial.state['pending'])
            trial.lock.close()

    def test_new_rule_waits_for_complete_history_and_publishes_basis(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'test.json'
            config.write_text(json.dumps(dict(id='test-trial', symbol='000660', name='SK하이닉스',
                cash='1000000', order_amount='100000', fee_bps='5', sell_tax_bps='20',
                sessions={str(DAY): ['09:00', '15:30']})), encoding='utf-8')
            clock = [START]
            market = FakeMarket(clock)
            market.price = D(970000)
            trial = Trial(config, root / 'state', root / 'reports', lambda *_: market,
                          lambda: clock[0], sma_start=DAY)
            self.addCleanup(trial.lock.close)
            with patch.object(market, 'recent_closes', side_effect=DataError('종가 누락')):
                self.assertEqual(trial.step(), '시세 확인 대기')
            self.assertIsNone(trial.state['pending'])
            clock[0] += timedelta(seconds=10)
            self.assertEqual(trial.step(), '정규장 관측')
            self.assertIsNotNone(trial.state['pending'])
            data = root / 'reports/test-trial/dashboard.json'
            entry = json.loads(data.read_text(encoding='utf-8'))['entry']
            self.assertEqual(D(entry['averageClose']), D(1000000))
            self.assertEqual(D(entry['threshold']), D(980000))
            self.assertEqual(entry['effectiveFrom'], str(DAY))

    def test_rejects_stale_and_halted_quotes(self):
        market = object.__new__(KisMarket)
        fresh = {'stck_cntg_hour': '090003', 'stck_prpr': '930000', 'cnqn': '4'}
        market.domestic = lambda endpoint, *_args, **_kwargs: (
            {'output': {'stck_sdpr': '1000000', 'temp_stop_yn': 'N'}}
            if endpoint == 'inquire-price' else {'output2': [fresh]})
        with patch('market.now', return_value=START + timedelta(seconds=10)):
            self.assertEqual(market.live(DAY, START, START.replace(hour=15))[1].price, D(930000))
        with patch('market.now', return_value=START + timedelta(seconds=19)):
            with self.assertRaises(DataError):
                market.live(DAY, START, START.replace(hour=15))
        market.domestic = lambda *_args, **_kwargs: {'output': {'stck_sdpr': '1000000', 'temp_stop_yn': 'Y'}}
        with self.assertRaisesRegex(DataError, '거래정지'):
            market.live(DAY, START, START.replace(hour=15))
