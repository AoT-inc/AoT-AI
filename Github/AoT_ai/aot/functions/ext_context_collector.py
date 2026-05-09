# coding=utf-8
"""
ext_context_collector.py — 외부 환경 컨텍스트 수집기 Function (Phase A4).

시설 외부의 환경값(온도·습도·풍속·강우·일사량·이슬점·CO₂)을
한 번에 수집해 시스템 단일 진실원으로 제공한다.

책임:
  - 각 외부 센서 측정값을 get_last_measurement 로 조회
  - age 검사 → 단계별 fallback (§8.2)
  - InfluxDB 에 수집 결과 기록
  - 다른 Function 이 get_context() 를 통해 최신 컨텍스트를 가져갈 수 있도록 공유

Fallback 정책 (§8.2):
  정상 수집 → 캐시 갱신 + last_ts 업데이트
  age > 60s   → 경고 로그
  age > 5분   → 만료 — Pre-Gate 신호용 last_ext_ts 가 오래됨
  age > 30분  → 시스템 알림 (로그 ERROR)

참조: docs/dev/integrated_env_control_design.md §8
"""

import time
from statistics import median

from flask_babel import lazy_gettext

from aot.databases.models import CustomController
from aot.functions.base_function import AbstractFunction
from aot.utils.constraints_pass import constraints_pass_positive_value
from aot.utils.database import db_retrieve_table_daemon
from aot.utils.influx import write_influxdb_value

# ─────────────────────────────────────────────────────────────────────────────
# 수집 채널 — InfluxDB measurement 이름
# ─────────────────────────────────────────────────────────────────────────────
MEAS_EXT_T        = 'ext_context_temperature'
MEAS_EXT_RH       = 'ext_context_humidity'
MEAS_EXT_WIND     = 'ext_context_wind'
MEAS_EXT_RAIN     = 'ext_context_rain'
MEAS_EXT_SOLAR    = 'ext_context_solar'
MEAS_EXT_DEWPOINT = 'ext_context_dewpoint'
MEAS_EXT_CO2      = 'ext_context_co2'
MEAS_EXT_AGE      = 'ext_context_age'         # 가장 오래된 센서의 age (초)
MEAS_EXT_VALID    = 'ext_context_valid'        # 1=정상, 0=만료

# ─────────────────────────────────────────────────────────────────────────────
# 시스템 공유 컨텍스트 캐시 (같은 프로세스 내 모듈 수준 공유)
# ─────────────────────────────────────────────────────────────────────────────
_shared_context: dict = {}
_shared_context_ts: float = 0.0


def get_shared_context() -> dict:
    """최신 외부 환경 컨텍스트를 반환. 다른 Function 이 호출."""
    return dict(_shared_context)


def get_shared_context_ts() -> float:
    return _shared_context_ts


# ─────────────────────────────────────────────────────────────────────────────
# FUNCTION_INFORMATION
# ─────────────────────────────────────────────────────────────────────────────

FUNCTION_INFORMATION = {
    'function_name_unique': 'ext_context_collector',
    'function_name': '외부 환경 컨텍스트 수집기',
    'function_name_short': 'Ext Context',

    'message': (
        '시설 외부의 온도·습도·풍속·강우·일사량·이슬점·CO₂를 수집합니다. '
        '통합 환경 제어 Function 이 이 수집기를 단일 진실원으로 사용합니다. '
        '각 항목에 해당하는 외부 센서를 선택하세요. '
        '없는 항목은 비워두면 fallback 기본값이 적용됩니다.'
    ),

    'options_enabled': ['custom_options'],
    'options_disabled': ['measurements_select', 'measurements_configure'],

    'custom_options': [
        {
            'id': 'update_period',
            'type': 'text',
            'class': 'aot-time-input',
            'default_value': 60,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': "{}: ({})".format(lazy_gettext('Update Period'), lazy_gettext('Seconds')),
            'phrase': '수집 주기 (초). 통합 제어 Function 의 사이클과 같거나 짧게 설정하세요.',
        },
        {
            'id': 'sensor_temperature',
            'type': 'select_measurement',
            'default_value': '',
            'required': False,
            'options_select': ['Input', 'Function'],
            'name': '외부 온도 센서',
            'phrase': '외부 기온 측정값을 선택하세요.',
        },
        {
            'id': 'sensor_humidity',
            'type': 'select_measurement',
            'default_value': '',
            'required': False,
            'options_select': ['Input', 'Function'],
            'name': '외부 습도 센서',
            'phrase': '외부 상대습도 측정값을 선택하세요.',
        },
        {
            'id': 'sensor_wind',
            'type': 'select_measurement',
            'default_value': '',
            'required': False,
            'options_select': ['Input', 'Function'],
            'name': '풍속 센서',
            'phrase': '풍속(m/s) 측정값을 선택하세요.',
        },
        {
            'id': 'sensor_rain',
            'type': 'select_measurement',
            'default_value': '',
            'required': False,
            'options_select': ['Input', 'Function'],
            'name': '강우 센서',
            'phrase': '강우량 또는 강우 감지 측정값을 선택하세요.',
        },
        {
            'id': 'sensor_solar',
            'type': 'select_measurement',
            'default_value': '',
            'required': False,
            'options_select': ['Input', 'Function'],
            'name': '일사량 센서',
            'phrase': '일사량(W/m²) 또는 조도 측정값을 선택하세요.',
        },
        {
            'id': 'sensor_dewpoint',
            'type': 'select_measurement',
            'default_value': '',
            'required': False,
            'options_select': ['Input', 'Function'],
            'name': '이슬점 센서',
            'phrase': '이슬점(°C) 측정값을 선택하세요. 없으면 온도·습도로 계산됩니다.',
        },
        {
            'id': 'sensor_co2',
            'type': 'select_measurement',
            'default_value': '',
            'required': False,
            'options_select': ['Input', 'Function'],
            'name': '외부 CO₂ 센서',
            'phrase': '외부 CO₂(ppm) 측정값을 선택하세요. 없으면 400ppm 기본값.',
        },
        {
            'id': 'sensor_max_age',
            'type': 'text',
            'class': 'aot-time-input',
            'default_value': 120,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': '센서 최대 허용 age (초)',
            'phrase': '이 시간보다 오래된 측정값은 fallback 기본값으로 대체됩니다.',
        },
        {
            'id': 'default_T_ext',
            'type': 'float',
            'default_value': 20.0,
            'required': False,
            'name': 'Fallback 외부 온도 (°C)',
            'phrase': '센서가 없거나 만료됐을 때 사용할 기본값.',
        },
        {
            'id': 'default_RH_ext',
            'type': 'float',
            'default_value': 60.0,
            'required': False,
            'name': 'Fallback 외부 습도 (%)',
            'phrase': '',
        },
        {
            'id': 'default_wind',
            'type': 'float',
            'default_value': 0.0,
            'required': False,
            'name': 'Fallback 풍속 (m/s)',
            'phrase': '',
        },
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# Function 클래스
# ─────────────────────────────────────────────────────────────────────────────

class CustomFunction(AbstractFunction):
    """외부 환경 컨텍스트 수집기."""

    def __init__(self, function, testing=False):
        super().__init__(function, testing=testing, name=__name__)

        self.update_period   = None
        self.sensor_max_age  = None
        self.default_T_ext   = None
        self.default_RH_ext  = None
        self.default_wind    = None

        # 센서 선택값 (device_id,channel_id 형태)
        self.sensor_temperature = None
        self.sensor_humidity    = None
        self.sensor_wind        = None
        self.sensor_rain        = None
        self.sensor_solar       = None
        self.sensor_dewpoint    = None
        self.sensor_co2         = None

        self.timer_loop = 0.0

        if not testing:
            self.setup_custom_options(
                FUNCTION_INFORMATION['custom_options'], function)
            self._log_startup()

    def _log_startup(self):
        self.logger.info(
            'ExtContextCollector started: period=%ss max_age=%ss',
            self.update_period, self.sensor_max_age)

    # ─────────────────────────────────────────────────────────────────────────
    # 메인 루프
    # ─────────────────────────────────────────────────────────────────────────

    def loop(self):
        if time.time() < self.timer_loop:
            return
        self.timer_loop = time.time() + (self.update_period or 60.0)
        self._collect_and_publish()

    # ─────────────────────────────────────────────────────────────────────────
    # 수집 + 발행
    # ─────────────────────────────────────────────────────────────────────────

    def _collect_and_publish(self):
        global _shared_context, _shared_context_ts

        max_age = self.sensor_max_age or 120.0
        now = time.time()
        oldest_age = 0.0

        def fetch(selector_val, fallback):
            """측정값 조회. 실패·만료 시 fallback 반환."""
            nonlocal oldest_age
            if not selector_val:
                return fallback, True
            try:
                dev_id, meas_id = selector_val.split(',')[:2]
                val = self.get_last_measurement(dev_id, meas_id, max_age=max_age)
                if val is None:
                    return fallback, False
                oldest_age = max(oldest_age, now - self._get_last_ts(dev_id, meas_id))
                return val, True
            except Exception:
                return fallback, False

        T_ext,    T_ok   = fetch(self.sensor_temperature, self.default_T_ext or 20.0)
        RH_ext,   RH_ok  = fetch(self.sensor_humidity,    self.default_RH_ext or 60.0)
        wind,     w_ok   = fetch(self.sensor_wind,        self.default_wind or 0.0)
        rain,     r_ok   = fetch(self.sensor_rain,        0.0)
        solar,    s_ok   = fetch(self.sensor_solar,       0.0)
        co2_ext,  c_ok   = fetch(self.sensor_co2,         400.0)
        dewpoint, d_ok   = fetch(self.sensor_dewpoint,    None)

        # 이슬점: 센서 없으면 Magnus 공식으로 계산
        if dewpoint is None:
            dewpoint = _calc_dewpoint(T_ext, RH_ext)

        # age 기반 valid 판정
        age_warn  = oldest_age > 60.0
        age_exp   = oldest_age > 300.0
        valid     = not age_exp

        if age_exp:
            self.logger.error(
                'ExtContext: sensors stale %.0fs — system alert!', oldest_age)
        elif age_warn:
            self.logger.warning(
                'ExtContext: sensors age %.0fs', oldest_age)

        ctx = {
            'T_ext':    T_ext,
            'RH_ext':   RH_ext,
            'wind':     wind,
            'rain':     rain,
            'solar':    solar,
            'dewpoint': dewpoint,
            'CO2_ext':  co2_ext,
            'last_ext_ts': now if valid else (_shared_context.get('last_ext_ts', 0)),
        }

        _shared_context    = ctx
        _shared_context_ts = now

        uid = self.unique_id
        write_influxdb_value(uid, MEAS_EXT_T,        value=T_ext,    channel=0)
        write_influxdb_value(uid, MEAS_EXT_RH,       value=RH_ext,   channel=0)
        write_influxdb_value(uid, MEAS_EXT_WIND,     value=wind,     channel=0)
        write_influxdb_value(uid, MEAS_EXT_RAIN,     value=rain,     channel=0)
        write_influxdb_value(uid, MEAS_EXT_SOLAR,    value=solar,    channel=0)
        write_influxdb_value(uid, MEAS_EXT_DEWPOINT, value=dewpoint, channel=0)
        write_influxdb_value(uid, MEAS_EXT_CO2,      value=co2_ext,  channel=0)
        write_influxdb_value(uid, MEAS_EXT_AGE,      value=oldest_age, channel=0)
        write_influxdb_value(uid, MEAS_EXT_VALID,    value=1.0 if valid else 0.0, channel=0)

    def _get_last_ts(self, dev_id: str, meas_id: str) -> float:
        """측정값의 실제 타임스탬프 조회 (age 계산용). 실패 시 현재 시각."""
        try:
            from aot.utils.influx import read_last_influxdb
            last = read_last_influxdb(dev_id, meas_id)
            if last:
                return last[0]
        except Exception:
            pass
        return time.time()


# ─────────────────────────────────────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────────────────────────────────────

def _calc_dewpoint(T: float, RH: float) -> float:
    """Magnus 공식으로 이슬점 계산 (°C)."""
    import math
    a, b = 17.27, 237.3
    alpha = (a * T) / (b + T) + math.log(max(RH, 0.1) / 100.0)
    return (b * alpha) / (a - alpha)
