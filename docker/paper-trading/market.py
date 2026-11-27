"""Allowlisted, read-only KIS KRX data for the paper-trading worker."""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
from urllib import error, parse, request

from strategy import Tick


KST = timezone(timedelta(hours=9), 'KST')
BASE_URL = 'https://openapi.koreainvestment.com:9443'
QUOTATIONS = '/uapi/domestic-stock/v1/quotations/'
LIMIT = 1024 * 1024


class DataError(Exception):
    pass


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def now():
    return datetime.now(KST)


def positive(value):
    number = Decimal(value)
    if not number.is_finite() or number <= 0:
        raise ValueError('invalid positive market value')
    return number


class KisMarket:
    def __init__(self, symbol, token_path):
        self.symbol = symbol
        self.token_path = Path(token_path)
        self.token = None
        self.next_auth = None
        self.cache_checked = False
        self.key = os.environ['SAGOPALGO_KIS_APP_KEY']
        self.secret = os.environ['SAGOPALGO_KIS_APP_SECRET']
        self.base = os.environ['SAGOPALGO_KIS_BASE_URL'].rstrip('/')
        if self.base != BASE_URL or not self.key or not self.secret:
            raise ValueError('KIS 시세용 환경 설정이 필요합니다.')
        self.opener = request.build_opener(NoRedirect())

    def read(self, route, headers, data=None):
        req = request.Request(self.base + route, headers=headers, data=data)
        try:
            with self.opener.open(req, timeout=5) as response:
                body = response.read(LIMIT + 1)
            if len(body) > LIMIT:
                raise DataError('KIS 응답 크기 초과')
            value = json.loads(body)
            if not isinstance(value, dict):
                raise DataError('KIS 응답 형식 오류')
            return value
        except error.HTTPError as exc:
            status = exc.code
            exc.close()
            raise DataError(f'KIS HTTP {status}') from None
        except (OSError, ValueError):
            raise DataError('KIS 통신 또는 응답 형식 오류') from None

    def authenticate(self):
        current = now()
        if not self.cache_checked and self.token_path.exists():
            try:
                cached = json.loads(self.token_path.read_text(encoding='utf-8'))
                self.token = (cached['token'], datetime.fromisoformat(cached['expires']))
            except (OSError, ValueError, KeyError, TypeError):
                self.token = None
        self.cache_checked = True
        if self.token and current < self.token[1]:
            return self.token[0]
        if self.next_auth and current < self.next_auth:
            raise DataError('KIS 시세 토큰 발급 재시도 대기')
        self.next_auth = current + timedelta(seconds=65)
        value = self.read('/oauth2/tokenP', {'Content-Type': 'application/json'}, json.dumps(dict(
            grant_type='client_credentials', appkey=self.key, appsecret=self.secret)).encode())
        token = value.get('access_token')
        if not isinstance(token, str) or not token or any(c in token for c in '\r\n'):
            raise DataError('KIS 시세 토큰 발급 실패')
        expires = current + timedelta(seconds=int(value.get('expires_in', 82800)) - 120)
        self.token = (token, expires)
        temp = self.token_path.with_suffix('.tmp')
        with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w', encoding='utf-8') as file:
            json.dump(dict(token=token, expires=expires.isoformat()), file)
        temp.replace(self.token_path)
        return token

    def quotes(self, endpoint, tr_id, params):
        token = self.authenticate()
        try:
            payload = self.read(QUOTATIONS + endpoint + '?' + parse.urlencode(params), {
                'Authorization': 'Bearer ' + token, 'appkey': self.key, 'appsecret': self.secret,
                'tr_id': tr_id, 'custtype': 'P', 'Accept': 'application/json'})
        except DataError as exc:
            if str(exc) == 'KIS HTTP 401':
                self.token = None
            raise
        if payload.get('rt_cd') != '0':
            if payload.get('msg_cd') in {'EGW00123', 'EGW00121'}:
                self.token = None
            raise DataError('KIS 시세 요청 거부')
        return payload

    def domestic(self, endpoint, tr_id, **params):
        return self.quotes(endpoint, tr_id,
                           dict(FID_COND_MRKT_DIV_CODE='J', FID_INPUT_ISCD=self.symbol, **params))

    def is_open(self, day):
        key = day.strftime('%Y%m%d')
        payload = self.quotes('chk-holiday', 'CTCA0903R', dict(BASS_DT=key, CTX_AREA_NK='', CTX_AREA_FK=''))
        output = payload.get('output')
        if not isinstance(output, list):
            raise DataError('KIS 개장 응답 형식 오류')
        rows = [row for row in output if isinstance(row, dict) and row.get('bass_dt') == key]
        if len(rows) != 1 or rows[0].get('opnd_yn') not in {'Y', 'N'}:
            raise DataError('KIS 개장 날짜 미확인')
        return rows[0]['opnd_yn'] == 'Y'

    def bars(self, start, end):
        payload = self.domestic('inquire-daily-itemchartprice', 'FHKST03010100',
            FID_INPUT_DATE_1=start.strftime('%Y%m%d'), FID_INPUT_DATE_2=end.strftime('%Y%m%d'),
            FID_PERIOD_DIV_CODE='D', FID_ORG_ADJ_PRC='1')
        rows = {}
        try:
            for row in payload['output2']:
                if not isinstance(row, dict):
                    raise ValueError('invalid historical row')
                if Decimal(row.get('acml_vol') or '0') <= 0:
                    continue
                day = datetime.strptime(row['stck_bsop_date'], '%Y%m%d').date()
                if start <= day <= end:
                    if day in rows:
                        raise ValueError('duplicate daily row')
                    rows[day] = positive(row['stck_clpr'])
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise DataError('KIS KRX 종가 응답 형식 오류') from None
        return rows

    def previous_close(self, day):
        rows = self.bars(day - timedelta(days=14), day - timedelta(days=1))
        prior = max((date for date in rows if date < day), default=None)
        if prior is None or not self.is_open(prior):
            raise DataError('KIS 직전 정규장 종가 미확인')
        return prior, rows[prior]

    def close(self, day):
        return self.bars(day, day).get(day)

    def live(self, day, start, end):
        payload = self.domestic('inquire-price', 'FHKST01010100')
        quote = payload.get('output')
        try:
            base = positive(quote['stck_sdpr'])
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise DataError('KIS 당일 기준가 미확인') from None
        if quote.get('temp_stop_yn') != 'N':
            raise DataError('거래정지 또는 거래 가능 상태 미확인')
        queried = now()
        payload = self.domestic('inquire-time-itemconclusion', 'FHPST01060000',
                                FID_INPUT_HOUR_1=queried.strftime('%H%M%S'))
        received = now()
        candidates = []
        output = payload.get('output2')
        if not isinstance(output, list):
            raise DataError('KIS 당일 체결 응답 형식 오류')
        for row in output:
            if not isinstance(row, dict):
                continue
            try:
                market_time = time.fromisoformat(row['stck_cntg_hour'])
                at = datetime.combine(day, market_time, KST)
                if start <= at < end and timedelta(0) <= received - at <= timedelta(seconds=15):
                    candidates.append(Tick(at, positive(row.get('stck_prpr') or row['stck_pbpr']),
                                           positive(row['cnqn'])))
            except (KeyError, TypeError, ValueError, InvalidOperation):
                continue
        if not candidates or received >= end:
            raise DataError('15초 이내 KRX 정규장 체결 시세 없음')
        return base, max(candidates, key=lambda tick: tick.at)
