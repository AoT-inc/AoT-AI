# coding=utf-8
"""
env_control/authority.py — Control Authority 자동 도출 (P5-2).

등록된 액추에이터 종류(kind)로부터 각 환경 변수에 대한 제어 권한
(ACTIVE / PASSIVE / NATURAL)을 자동으로 결정한다.

등급 정의:
  ACTIVE  — 능동 제어 가능 (해당 변수에 직접 영향을 주는 액추에이터 보유)
  PASSIVE — 간접/외부 의존 제어 (환기·차광 등, 외기 조건에 의존)
  NATURAL — 자연 의존, 제어 불가 (영향 액추에이터 없음)

참조: docs/env_control_enhancement_design.md §3.17
"""

from __future__ import annotations

from typing import Dict, List

# ─────────────────────────────────────────────────────────────────────────────
# 권한 등급 순위 (높을수록 강한 제어)
# ─────────────────────────────────────────────────────────────────────────────

LEVEL_NATURAL = 'NATURAL'
LEVEL_PASSIVE = 'PASSIVE'
LEVEL_ACTIVE  = 'ACTIVE'

_RANK: Dict[str, int] = {
    LEVEL_NATURAL: 0,
    LEVEL_PASSIVE:  1,
    LEVEL_ACTIVE:   2,
}

# 권한 키 집합 (변수명_방향)
AUTHORITY_KEYS = (
    'T_up', 'T_down',
    'RH_up', 'RH_down',
    'CO2_up', 'CO2_down',
    'Light_up', 'Light_down',
)


def _upgrade(current: str, candidate: str) -> str:
    """후보가 현재보다 높은 등급이면 교체, 아니면 유지."""
    return candidate if _RANK.get(candidate, 0) > _RANK.get(current, 0) else current


# ─────────────────────────────────────────────────────────────────────────────
# kind → authority 영향 매핑
# ─────────────────────────────────────────────────────────────────────────────

# 각 actuator kind가 올릴 수 있는 변수×방향 권한.
# 값: ACTIVE 또는 PASSIVE (NATURAL은 기본값 — 목록 미포함 = 영향 없음)
_KIND_AUTHORITY: Dict[str, Dict[str, str]] = {
    'heater': {
        'T_up': LEVEL_ACTIVE,
    },
    'cooler': {
        'T_down': LEVEL_ACTIVE,
    },
    'fogger': {
        'RH_up':  LEVEL_ACTIVE,
        'T_down': LEVEL_PASSIVE,   # 증발 냉각 부수효과
    },
    'co2_injector': {
        'CO2_up': LEVEL_ACTIVE,
    },
    'shade': {
        'Light_down': LEVEL_PASSIVE,
        'T_down':     LEVEL_PASSIVE,   # 차광 → 복사열 감소
    },
    'curtain': {
        'T_up': LEVEL_PASSIVE,         # 보온 커튼 → 열 보존
    },
    'lighting': {
        'Light_up': LEVEL_ACTIVE,
    },
    'opening': {
        'T_down':   LEVEL_PASSIVE,
        'RH_down':  LEVEL_PASSIVE,
        'CO2_down': LEVEL_PASSIVE,
    },
    'circulation_fan': {
        'T_down':  LEVEL_PASSIVE,
        'RH_down': LEVEL_PASSIVE,
    },
    'exhaust_fan': {
        'T_down':   LEVEL_PASSIVE,
        'RH_down':  LEVEL_PASSIVE,
        'CO2_down': LEVEL_PASSIVE,
    },
    'intake_fan': {
        'T_down': LEVEL_PASSIVE,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────────────────────────────────────

def derive_authority(profiles) -> Dict[str, str]:
    """등록된 액추에이터 목록으로부터 변수별 제어 권한을 도출한다.

    Args:
        profiles: List[ActuatorProfile] — 등록된 액추에이터 프로파일 목록

    Returns:
        {var_key: level} — 예: {'T_up': 'ACTIVE', 'T_down': 'PASSIVE', ...}
        미등록 kind는 NATURAL 유지.
    """
    result: Dict[str, str] = {k: LEVEL_NATURAL for k in AUTHORITY_KEYS}

    for p in profiles:
        kind_map = _KIND_AUTHORITY.get(p.kind, {})
        for var_key, level in kind_map.items():
            result[var_key] = _upgrade(result[var_key], level)

    return result


def authority_summary(authority: Dict[str, str]) -> str:
    """로깅용 한줄 요약 문자열."""
    parts = []
    for k in AUTHORITY_KEYS:
        v = authority.get(k, LEVEL_NATURAL)
        if v != LEVEL_NATURAL:
            parts.append(f'{k}={v[0]}')  # A/P 첫 글자만
    return ', '.join(parts) if parts else 'all NATURAL'


def is_all_natural(authority: Dict[str, str]) -> bool:
    """모든 변수가 NATURAL이면 True (외기 추적 전용 모드)."""
    return all(v == LEVEL_NATURAL for v in authority.values())


def is_natural_var(authority: Dict[str, str], var: str) -> bool:
    """특정 변수의 상승·하강 모두 NATURAL이면 True."""
    up_key   = f'{_VAR_TO_KEY.get(var, var)}_up'
    down_key = f'{_VAR_TO_KEY.get(var, var)}_down'
    return (authority.get(up_key, LEVEL_NATURAL) == LEVEL_NATURAL and
            authority.get(down_key, LEVEL_NATURAL) == LEVEL_NATURAL)


# 내부: EnvTarget 변수명 → authority 키 접두사
_VAR_TO_KEY: Dict[str, str] = {
    'temperature': 'T',
    'humidity':    'RH',
    'co2':         'CO2',
    'light':       'Light',
    'vpd':         'T',    # VPD는 T/RH 복합 — T 권한으로 근사
}


# ─────────────────────────────────────────────────────────────────────────────
# P5-3: 목표 자동 완화 (degrade_target)
# ─────────────────────────────────────────────────────────────────────────────

def degrade_target(env_target, authority: Dict[str, str], external: Dict) -> None:
    """NATURAL 권한 변수의 목표를 외기 조건에 맞게 완화한다 (in-place).

    완화 정책:
      - 변수가 NATURAL(양방향 모두)이면 목표값을 외기 측정값으로 교체.
      - 외기 측정값이 없으면 완화 생략 (원래 목표 유지).
      - 완화된 TargetVar는 degraded=True 로 표시.

    Args:
        env_target: EnvTarget dict (in-place 수정)
        authority:  derive_authority() 결과
        external:   외부 센서 dict {'T_ext', 'RH_ext', 'CO2_ext', ...}
    """
    _VAR_EXT_KEY = {
        'temperature': 'T_ext',
        'humidity':    'RH_ext',
        'co2':         'CO2_ext',
    }

    for var, tv in env_target.items():
        if var.startswith('_'):
            continue
        if not is_natural_var(authority, var):
            continue

        ext_key = _VAR_EXT_KEY.get(var)
        ext_val = external.get(ext_key) if ext_key else None
        if ext_val is None:
            continue

        tv.value    = float(ext_val)
        tv.degraded = True


def detect_unattainable(
    env_target,
    deviation_native: Dict[str, float],
    authority: Dict[str, str],
    unattainable_state: Dict[str, int],
    threshold_cycles: int = 5,
) -> List[str]:
    """목표 달성 불가 변수 목록을 반환하고 카운터를 갱신한다.

    조건: 변수가 ACTIVE이면서 편차가 tolerance × 2 초과인 상태가
    threshold_cycles 사이클 이상 지속되면 unattainable로 판정.

    Args:
        env_target:           EnvTarget
        deviation_native:     편차 dict (situation.deviation_native)
        authority:            derive_authority() 결과
        unattainable_state:   {var: 연속 초과 사이클 수} (in-place 갱신)
        threshold_cycles:     판정 임계 사이클 수

    Returns:
        현재 unattainable 판정된 변수명 목록
    """
    unattainable_vars: List[str] = []

    for var, tv in env_target.items():
        if var.startswith('_'):
            continue
        dev = deviation_native.get(var, 0.0)
        # ACTIVE이면서 편차가 2×tolerance 이상인 경우만 카운트
        if (not is_natural_var(authority, var) and
                abs(dev) > tv.tolerance * 2.0):
            unattainable_state[var] = unattainable_state.get(var, 0) + 1
        else:
            unattainable_state[var] = 0

        if unattainable_state.get(var, 0) >= threshold_cycles:
            unattainable_vars.append(var)

    return unattainable_vars
