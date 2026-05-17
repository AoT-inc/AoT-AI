# coding=utf-8
"""
facility_sensors.py — GeoFacility 센서 바인딩 읽기 및 집계 유틸리티.

facility.sensors 배열에서 센서 목록을 로드하고, 각 센서의 최신 측정값을
InfluxDB에서 읽어 role별로 가중 평균을 계산한다.

지원 역할(role):
    indoor_temp       → indoor.temp_c         (°C)
    indoor_humidity   → indoor.humidity_pct   (%)
    indoor_co2        → indoor.co2_ppm        (ppm)
    outdoor_temp      → outdoor.temp_c        (°C)
    outdoor_humidity  → outdoor.humidity_pct  (%)
    outdoor_wind      → outdoor.wind_ms       (m/s)
    outdoor_wind_dir  → outdoor.wind_deg      (°)
    outdoor_solar     → outdoor.solar_wm2     (W/m²)

복수 센서(동일 role): weight 기반 가중 평균. 유효하지 않은 센서는 제외.
센서 유효 조건: max_age 이내의 InfluxDB 데이터 존재.

Update handling:
    1. 센서 목록 변경 → facility.sensors 수정. 런타임 엔드포인트 다음 폴링에서 즉시 반영.
    2. 측정값 갱신   → get_last_measurement가 매 호출마다 최신값 조회. max_age 초과 시 자동 제외.
    3. 장치 제거     → device_id/measurement_id 미존재 시 [None, None] 반환 → 자동 제외.
                      valid_count < total_count이면 결과에 degraded=True 플래그.
"""

import logging
from typing import Dict, List, Optional, Tuple

from aot.utils.influx import get_last_measurement  # module-level — patchable in tests

logger = logging.getLogger(__name__)

# 기본 측정값 유효 수명 (초). runtime endpoint의 폴링 주기보다 충분히 길게 설정.
DEFAULT_MAX_AGE_S: int = 300

# role → (섹션, 필드) 매핑
_ROLE_MAP: Dict[str, Tuple[str, str]] = {
    'indoor_temp':      ('indoor',  'temp_c'),
    'indoor_humidity':  ('indoor',  'humidity_pct'),
    'indoor_co2':       ('indoor',  'co2_ppm'),
    'outdoor_temp':     ('outdoor', 'temp_c'),
    'outdoor_humidity': ('outdoor', 'humidity_pct'),
    'outdoor_wind':     ('outdoor', 'wind_ms'),
    'outdoor_wind_dir': ('outdoor', 'wind_deg'),
    'outdoor_solar':    ('outdoor', 'solar_wm2'),
}

KNOWN_ROLES = set(_ROLE_MAP.keys())


# ─────────────────────────────────────────────────────────────────────────────
def read_facility_sensors(
    sensor_bindings: List[dict],
    max_age: int = DEFAULT_MAX_AGE_S,
) -> dict:
    """sensor_bindings 목록을 읽어 indoor/outdoor 환경 값을 반환한다.

    Args:
        sensor_bindings: facility.sensors JSON 배열
            각 항목: {role, device_id, measurement_id, name, weight(optional)}
        max_age: 측정값 최대 유효 수명 (초). 초과 시 해당 센서 제외.

    Returns:
        {
            'indoor':  {temp_c, humidity_pct, co2_ppm},
            'outdoor': {temp_c, humidity_pct, wind_ms, wind_deg, solar_wm2},
            'sensors': [  # 센서별 상세 (디버깅/UI용)
                {role, name, value, unit, ts, valid, stale, degraded_reason}
            ],
            'degraded': bool,   # 하나 이상의 센서가 유효하지 않음
            'valid_count': int,
            'total_count': int,
        }
    """
    # 섹션별 집계 버킷: role → [(value, weight)]
    buckets: Dict[str, List[Tuple[float, float]]] = {}
    sensor_details: list = []
    total_count = 0
    valid_count = 0

    for binding in (sensor_bindings or []):
        role          = (binding.get('role') or '').strip()
        device_id     = (binding.get('device_id') or '').strip()
        measurement_id = (binding.get('measurement_id') or '').strip()
        name          = binding.get('name') or role
        weight        = float(binding.get('weight') or 1.0)

        if not role or not device_id or not measurement_id:
            continue
        if role not in KNOWN_ROLES:
            logger.debug('[FacilitySensors] 알 수 없는 role 무시: %s', role)
            continue

        total_count += 1
        detail: dict = {
            'role':   role,
            'name':   name,
            'value':  None,
            'ts':     None,
            'valid':  False,
            'stale':  False,
            'degraded_reason': None,
        }

        try:
            ts, value = get_last_measurement(device_id, measurement_id, max_age=max_age)
        except Exception as exc:
            logger.warning('[FacilitySensors] %s(%s) 조회 실패: %s', name, role, exc)
            detail['degraded_reason'] = f'query_error: {exc}'
            sensor_details.append(detail)
            continue

        if ts is None or value is None:
            # max_age 초과 여부 판단: max_age 없이 재조회하여 데이터 존재 자체를 확인
            try:
                ts_any, val_any = get_last_measurement(device_id, measurement_id, max_age=None)
                if ts_any is not None:
                    detail['stale'] = True
                    detail['degraded_reason'] = 'stale'
                else:
                    detail['degraded_reason'] = 'no_data'
            except Exception:
                detail['degraded_reason'] = 'no_data'
            sensor_details.append(detail)
            continue

        # 유효한 측정값
        detail['value'] = value
        detail['ts']    = ts
        detail['valid'] = True
        valid_count += 1

        buckets.setdefault(role, []).append((float(value), weight))
        sensor_details.append(detail)

    # ── role별 가중 평균 계산 ──────────────────────────────────────────────
    averaged: Dict[str, Optional[float]] = {}
    for role, readings in buckets.items():
        total_w = sum(w for _, w in readings)
        averaged[role] = sum(v * w for v, w in readings) / total_w if total_w > 0 else None

    def _get(role: str) -> Optional[float]:
        return averaged.get(role)

    indoor = {
        'temp_c':       _get('indoor_temp'),
        'humidity_pct': _get('indoor_humidity'),
        'co2_ppm':      _get('indoor_co2'),
    }
    outdoor = {
        'temp_c':       _get('outdoor_temp'),
        'humidity_pct': _get('outdoor_humidity'),
        'wind_ms':      _get('outdoor_wind'),
        'wind_deg':     _get('outdoor_wind_dir'),
        'solar_wm2':    _get('outdoor_solar'),
    }

    return {
        'indoor':      indoor,
        'outdoor':     outdoor,
        'sensors':     sensor_details,
        'degraded':    valid_count < total_count,
        'valid_count': valid_count,
        'total_count': total_count,
    }


# ─────────────────────────────────────────────────────────────────────────────
HOTSPOT_DELTA_T  = 3.0   # °C: 평균 대비 이 값 이상 차이나면 핫스팟
HOTSPOT_DELTA_RH = 10.0  # %RH

# 측정값 measurement 필드 → 내부 환경 키 매핑 (DeviceMeasurements.measurement 값)
_MEAS_T_NAMES  = {'temperature', 'temp', 'temp_c'}
_MEAS_RH_NAMES = {'humidity', 'humidity_pct', 'relative_humidity'}


def compute_spatial_internal(
    sensors_resolved: List[dict],
    max_age: int = DEFAULT_MAX_AGE_S,
) -> dict:
    """sensors_resolved 목록에서 위치 인식 내부 환경값을 계산한다 (D2).

    `sensors_resolved` 는 ``get_facility_integration()`` 가 반환하는 배열로,
    각 항목에는 fitting 3D position과 연결된 Input device uuid가 포함된다.

    Position weighting: 현재 버전은 균일 가중(equal weight)이며 위치 정보는
    핫스팟 감지에 활용된다. 향후 베이별 분리 제어를 위한 확장 지점.

    Parameters
    ----------
    sensors_resolved : integration 응답의 sensors_resolved[]
    max_age          : 측정값 최대 유효 수명 (초)

    Returns
    -------
    {
        'T'          : float | None,  # 균일 가중 평균 온도 (°C)
        'RH'         : float | None,  # 균일 가중 평균 습도 (%RH)
        'detail'     : list,          # 센서별 상세 [{fitting_id, name, position, T, RH}]
        'hotspot_T'  : bool,          # 최대-최소 온도 > HOTSPOT_DELTA_T
        'hotspot_RH' : bool,
        'valid_count': int,
        'source'     : 'spatial',
    }
    """
    from aot.databases.models.measurement import DeviceMeasurements
    from aot.utils.database import db_retrieve_table_daemon
    from aot.utils.influx import get_last_measurement

    T_readings:  List[float] = []
    RH_readings: List[float] = []
    detail: List[dict] = []

    for s in (sensors_resolved or []):
        input_uuid = s.get('input_uuid')
        if not input_uuid:
            continue

        # 연결된 Input 의 DeviceMeasurements 채널 조회
        try:
            dm_rows = db_retrieve_table_daemon(DeviceMeasurements).filter(
                DeviceMeasurements.device_id == input_uuid
            ).all()
        except Exception:
            dm_rows = []

        t_val = rh_val = None
        for dm in dm_rows:
            meas_lower = (dm.measurement or '').lower()
            try:
                ts, val = get_last_measurement(input_uuid, dm.unique_id, max_age=max_age)
            except Exception:
                continue
            if ts is None or val is None:
                continue
            if meas_lower in _MEAS_T_NAMES and t_val is None:
                t_val = float(val)
            elif meas_lower in _MEAS_RH_NAMES and rh_val is None:
                rh_val = float(val)

        if t_val is not None:
            T_readings.append(t_val)
        if rh_val is not None:
            RH_readings.append(rh_val)

        detail.append({
            'fitting_id': s.get('fitting_id'),
            'name':       s.get('name') or input_uuid,
            'position':   s.get('position'),
            'T':          t_val,
            'RH':         rh_val,
        })

    T_mean  = sum(T_readings)  / len(T_readings)  if T_readings  else None
    RH_mean = sum(RH_readings) / len(RH_readings) if RH_readings else None

    hotspot_T  = (len(T_readings)  > 1 and (max(T_readings)  - min(T_readings))  > HOTSPOT_DELTA_T)
    hotspot_RH = (len(RH_readings) > 1 and (max(RH_readings) - min(RH_readings)) > HOTSPOT_DELTA_RH)

    valid = len([d for d in detail if d['T'] is not None or d['RH'] is not None])
    return {
        'T':           round(T_mean,  2) if T_mean  is not None else None,
        'RH':          round(RH_mean, 1) if RH_mean is not None else None,
        'detail':      detail,
        'hotspot_T':   hotspot_T,
        'hotspot_RH':  hotspot_RH,
        'valid_count': valid,
        'source':      'spatial',
    }


def validate_sensor_binding(binding: dict) -> Tuple[bool, str]:
    """센서 바인딩 항목의 필수 필드와 role 유효성을 검사한다.

    Returns:
        (ok: bool, reason: str)
    """
    for field in ('role', 'device_id', 'measurement_id'):
        if not (binding.get(field) or '').strip():
            return False, f'missing field: {field}'

    role = binding['role'].strip()
    if role not in KNOWN_ROLES:
        return False, f'unknown role: {role} (valid: {sorted(KNOWN_ROLES)})'

    weight = binding.get('weight')
    if weight is not None:
        try:
            w = float(weight)
            if w <= 0:
                return False, f'weight must be > 0, got {w}'
        except (TypeError, ValueError):
            return False, f'weight must be numeric, got {weight!r}'

    return True, 'ok'


def validate_sensor_bindings(bindings: list) -> Tuple[bool, List[str]]:
    """sensor_bindings 배열 전체를 검증한다.

    Returns:
        (all_ok: bool, errors: list[str])
    """
    if not isinstance(bindings, list):
        return False, ['sensors must be a list']
    errors = []
    for i, b in enumerate(bindings):
        ok, reason = validate_sensor_binding(b)
        if not ok:
            errors.append(f'sensors[{i}]: {reason}')
    return len(errors) == 0, errors
