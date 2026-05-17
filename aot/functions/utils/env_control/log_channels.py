# coding=utf-8
"""
env_control/log_channels.py — 의사결정 로깅 채널 표준.

매 사이클의 결정을 InfluxDB 에 기록하는 채널 번호 상수와
write_decision_log() 헬퍼를 제공한다.

채널 레이아웃 (§10):
  0~9   : L1 goal_target_<var>
  10~19 : L1 goal_priority_<var>
  20~29 : L2 situation_deviation_<var>
  30    : L2 limiting_factor
  31    : L2 mode
  40+   : L3 액추에이터 명령  (actuator_idx × 2 + 40)
  50+   : L3 액추에이터 근거  (actuator_idx × 2 + 41, 위 채널과 쌍)
  60+   : L3 적분 누적 (debug)
  70    : Gate 활성 비트마스크

참조: docs/dev/integrated_env_control_design.md §10
"""

from typing import Dict, Optional

from aot.utils.influx import write_influxdb_value

# ─────────────────────────────────────────────────────────────────────────────
# 변수 인덱스 — 채널 계산 기준
# ─────────────────────────────────────────────────────────────────────────────
VAR_INDEX = {
    'temperature': 0,
    'humidity':    1,
    'co2':         2,
    'vpd':         3,
}

# ─────────────────────────────────────────────────────────────────────────────
# 채널 오프셋 상수
# ─────────────────────────────────────────────────────────────────────────────
CH_GOAL_TARGET_BASE      = 0    # + VAR_INDEX[var]
CH_GOAL_PRIORITY_BASE    = 10   # + VAR_INDEX[var]
CH_SITUATION_DEV_BASE    = 20   # + VAR_INDEX[var]
CH_SITUATION_LIMIT       = 30
CH_SITUATION_MODE        = 31
CH_COORD_CMD_BASE        = 40   # + actuator_idx × 2
CH_COORD_REASON_BASE     = 41   # + actuator_idx × 2
CH_INTEGRAL_BASE         = 60   # + VAR_INDEX[var]
CH_SAFETY_GATE           = 70
CH_DISPATCH_FAIL         = 71   # 한 사이클에서 dispatch 실패한 액추에이터 수
CH_RUNTIME_STATE_FAIL    = 72   # runtime state DB 저장 실패 누적 카운트

# ─────────────────────────────────────────────────────────────────────────────
# 근거 코드 (§10.1)
# ─────────────────────────────────────────────────────────────────────────────
REASON_IDLE             = 0    # 모든 변수 허용 범위 내
REASON_PRIMARY          = 1    # 효과 방향 일치, 비용 최저
REASON_SECONDARY        = 2    # 효과 방향 일치, 보조
REASON_WRONG_DIRECTION  = 10   # 효과 방향 불일치 — 제외
REASON_SIDE_EFFECT      = 11   # 부작용 충돌 — 제외
REASON_SAFETY_PRE_GATE  = 12   # 안전 Pre-Gate 강제 명령
REASON_UNAVAILABLE      = 13   # Output unavailable (통신 실패)
REASON_SAFETY_POST_GATE = 14   # 안전 Post-Gate 보정
REASON_NO_GRADIENT      = 15   # 구동력 없음 — 내외부 차이 부족으로 효과 없음
REASON_MANUAL_OVERRIDE  = 20   # 수동 오버라이드 — 락 활성

# 안전 게이트 비트마스크 (CH_SAFETY_GATE)
GATE_BIT_RAIN    = 1 << 0
GATE_BIT_WIND    = 1 << 1
GATE_BIT_EXT_EXP = 1 << 2
GATE_BIT_INT_EXP = 1 << 3
GATE_BIT_HEAT    = 1 << 4
GATE_BIT_COLD    = 1 << 5

# 운전 모드 → 정수 코드 (CH_SITUATION_MODE)
MODE_CODES = {
    'cooling':      1,
    'heating':      2,
    'humidify':     3,
    'dehumidify':   4,
    'co2_enrich':   5,
    'conservation': 0,
    'emergency':    99,
}

# 제한 인자 → 정수 코드 (CH_SITUATION_LIMIT)
LIMIT_CODES = {
    'light':       1,
    'co2':         2,
    'temperature': 3,
    'water':       4,
}

# ─────────────────────────────────────────────────────────────────────────────
# 채널 번호 계산 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def ch_goal_target(var: str) -> int:
    return CH_GOAL_TARGET_BASE + VAR_INDEX.get(var, 9)


def ch_goal_priority(var: str) -> int:
    return CH_GOAL_PRIORITY_BASE + VAR_INDEX.get(var, 9)


def ch_situation_deviation(var: str) -> int:
    return CH_SITUATION_DEV_BASE + VAR_INDEX.get(var, 9)


def ch_coord_cmd(actuator_idx: int) -> int:
    return CH_COORD_CMD_BASE + actuator_idx * 2


def ch_coord_reason(actuator_idx: int) -> int:
    return CH_COORD_REASON_BASE + actuator_idx * 2


def ch_integral(var: str) -> int:
    return CH_INTEGRAL_BASE + VAR_INDEX.get(var, 9)


# ─────────────────────────────────────────────────────────────────────────────
# write_decision_log — 의사결정 InfluxDB 기록 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def write_decision_log(unique_id: str, measurement: str, channel: int, value: float):
    """의사결정 로그를 InfluxDB 에 기록.

    Args:
        unique_id:   AoT Function unique_id (기록 주체)
        measurement: 측정값 이름 (예: 'goal_target_temperature')
        channel:     채널 번호 (위 상수 사용)
        value:       기록할 값
    """
    write_influxdb_value(unique_id, measurement, value=value, channel=channel)


# ─────────────────────────────────────────────────────────────────────────────
# P1-3: 사이클 메트릭 일괄 기록 (설계 §3.3)
# ─────────────────────────────────────────────────────────────────────────────

# InfluxDB measurement 이름 (태그: function_id, facility_id)
_MEASUREMENT_ENV = 'env_control'


def write_cycle_metrics(
    unique_id: str,
    ctx: Dict,
    target: Dict,
    deviation: Dict,
    commands: Dict,
    limiting_factor: Optional[str],
    modes: list,
    facility_id: Optional[str] = None,
):
    """
    매 사이클 종료 시 환경 제어 메트릭을 InfluxDB 에 일괄 기록한다. (P1-3)

    저장 채널 규약 (설계 §3.3):
      CH 0~5   : 내부 센서 실측 (T, RH, VPD, CO2, Light, —)
      CH 10~14 : 외부 환경 (T_ext, RH_ext, wind, wind_dir, rain)
      CH 20~24 : 목표값 (VPD, T_aux, RH_aux, CO2, Light)
      CH 30~33 : 편차 residual (temperature, humidity, co2, vpd_diag)
      CH 40+   : 액추에이터 명령 (기존 ch_coord_cmd 채널과 동일)
      CH 70    : 제한 인자 코드 (기존 CH_SAFETY_GATE 와 별도)
      CH 71    : 운전 모드 코드 (첫 번째 모드)

    Args:
        unique_id:       Function unique_id (InfluxDB tag)
        ctx:             EnvContext (내부+외부 센서)
        target:          EnvTarget (VPD 분해 후 working_target)
        deviation:       deviation_native dict
        commands:        CoordResult {actuator_id: ActuatorCommand}
        limiting_factor: 제한 인자 문자열 또는 None
        modes:           운전 모드 리스트
        facility_id:     GeoFacility unique_id (extra tag, 선택적)
    """
    extra = {'facility_id': facility_id} if facility_id else None

    def _w(channel: int, value: float):
        write_influxdb_value(
            unique_id, _MEASUREMENT_ENV,
            value=value, channel=channel,
            extra_tags=extra,
        )

    # ── 내부 센서 실측 ─────────────────────────────────────────────────────
    _w(0, ctx.get('T_int',   0.0))
    _w(1, ctx.get('RH_int',  0.0))
    _w(2, ctx.get('VPD_int', 0.0))
    _w(3, ctx.get('CO2_int', 0.0))

    # ── 외부 환경 ─────────────────────────────────────────────────────────
    _w(10, ctx.get('T_ext',    0.0))
    _w(11, ctx.get('RH_ext',   0.0))
    _w(12, ctx.get('wind',     0.0))
    _w(13, ctx.get('wind_dir', 0.0))
    _w(14, ctx.get('rain',     0.0))

    # ── 목표값 ────────────────────────────────────────────────────────────
    vpd_diag = target.get('_vpd_diag')
    _w(20, vpd_diag.value if vpd_diag else 0.0)
    t_tv = target.get('temperature')
    _w(21, t_tv.value if t_tv else 0.0)
    rh_tv = target.get('humidity')
    _w(22, rh_tv.value if rh_tv else 0.0)
    co2_tv = target.get('co2')
    _w(23, co2_tv.value if co2_tv else 0.0)

    # ── 편차 ──────────────────────────────────────────────────────────────
    _w(30, deviation.get('temperature', 0.0))
    _w(31, deviation.get('humidity',    0.0))
    _w(32, deviation.get('co2',         0.0))

    # ── 액추에이터 명령 (순서 보장을 위해 정렬) ───────────────────────────
    for idx, (aid, cmd) in enumerate(sorted(commands.items())):
        _w(ch_coord_cmd(idx),    cmd.value)
        _w(ch_coord_reason(idx), float(cmd.reason))

    # ── 제한 인자 + 운전 모드 ────────────────────────────────────────────
    _w(71, float(LIMIT_CODES.get(limiting_factor, 0)))
    primary_mode = modes[0] if modes else 'conservation'
    _w(72, float(MODE_CODES.get(primary_mode, 0)))
