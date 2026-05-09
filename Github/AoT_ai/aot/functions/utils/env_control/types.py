# coding=utf-8
"""
env_control/types.py — 통합 환경 제어 시스템 핵심 타입 정의.

참조: docs/dev/integrated_env_control_design.md §3
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

# ─────────────────────────────────────────────────────────────────────────────
# 단위 규약 R1 (§3.2)
#
# EffectResult.magnitude_native 단위 = 변수 native 단위 / 1 사이클
#   T:   °C/cycle
#   RH:  %/cycle
#   CO2: ppm/cycle
#
# accumulated, residual, tolerance 도 모두 native 단위 사용.
# 우선순위 정렬 시에만 정규화 (|deviation| / tolerance × priority).
# 정규화 값은 비교용 일시값이며 accumulated 에 들어가지 않는다.
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# 기본 자료형
# ─────────────────────────────────────────────────────────────────────────────

EnvContext = Dict  # 아래 키 집합을 포함하는 dict:
# 내부 상태
#   T_int, RH_int, CO2_int, VPD_int
# 외부 상태
#   T_ext, RH_ext, CO2_ext, wind, rain, solar, dewpoint
# 메타
#   now_ts (epoch float), cycle_sec (float)


@dataclass
class EffectResult:
    """EffectFn 반환값. 단위 규약 R1 준수."""
    direction: str          # '↑' | '↓' | '0'
    magnitude_native: float  # native 단위 / 사이클 (R1)


# EffectFn: (env_context, cmd_pct, profile=None) -> EffectResult
# profile 인자는 G3 도입. 모든 구현체는 profile=None 기본값을 가져 후방 호환됨.
EffectFn = Callable[..., EffectResult]

# CostFn: (env_context, cmd_pct) -> float  (낮을수록 우선)
CostFn = Callable[[EnvContext, float], float]


# ─────────────────────────────────────────────────────────────────────────────
# 수동 락 상태 (§3.6)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ManualLockState:
    locked: bool = False
    until_ts: float = 0.0         # 락 해제 epoch (0 = 영구 락 없음)
    manual_value: float = 0.0     # 사용자가 설정한 값
    reason: str = ''              # 'user_ui' | 'maintenance' | 'pre_gate'

    def is_active(self) -> bool:
        """현재 시각 기준으로 락이 유효한지 확인."""
        if not self.locked:
            return False
        if self.until_ts > 0 and time.time() > self.until_ts:
            self.locked = False
            return False
        return True


MANUAL_LOCK_DEFAULT = ManualLockState()


# ─────────────────────────────────────────────────────────────────────────────
# 명령 제약 조건 (§3.1, §4.1)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CmdConstraints:
    slew_per_cycle: float = 20.0   # 사이클당 최대 명령 변화 (%)
    min_on_pct: float = 5.0        # 미만이면 0으로 스냅
    min_dwell_sec: float = 30.0    # 명령 유지 최소 시간


# ─────────────────────────────────────────────────────────────────────────────
# ActuatorProfile (§3.1)
# ─────────────────────────────────────────────────────────────────────────────

# 지원 kind 목록
ACTUATOR_KINDS = frozenset({
    'opening',       # 개구부 (측창·천창)
    'cooler',        # 냉방기
    'heater',        # 난방기
    'fogger',        # 포그·관수 가습기
    'co2_injector',  # CO₂ 주입기
    'shade',         # 차광막 (외부)
    'curtain',       # 보온 커튼 (내부)
    'lighting',      # 보광등 (LED 등) — R2 secondary primary, optional
})


@dataclass
class ActuatorProfile:
    """Output 플러그인이 자기 자신을 신고하는 메타데이터."""
    actuator_id: str                          # AoT Output unique_id
    kind: str                                 # ACTUATOR_KINDS 중 하나
    capabilities: list = field(default_factory=list)
    cost_fn: CostFn = field(default_factory=lambda: (lambda env, pct: 3.0))
    response_sec: float = 60.0                # 명령 후 효과 발현까지 (초)
    safe_default: float = 0.0                 # 명령 없을 때 안전 위치
    manual_lock: ManualLockState = field(default_factory=ManualLockState)
    effect_model: Dict[str, EffectFn] = field(default_factory=dict)
    cmd_constraints: CmdConstraints = field(default_factory=CmdConstraints)
    gains: Dict[str, float] = field(default_factory=lambda: {'kp': 1.0, 'ki': 0.05})

    # ─── Facility / GIS metadata (optional, populated when linked to GeoFacility) ───
    geo_facility_id: Optional[str] = None     # GeoFacility.unique_id (None = unlinked)
    slot_key: Optional[str] = None            # 'outer_side_vent_motor' 등 (facility 슬롯 식별자)
    azimuth_deg: Optional[float] = None       # 외향 법선 방위각 (0=N, 90=E, 180=S, 270=W)
    area_m2: Optional[float] = None           # 개구부/장치 유효 면적
    capacity_meta: Dict[str, float] = field(default_factory=dict)  # u_eff, volume_m3 등 캐시

    # L3 가 매 사이클 채우는 필드 (Profile 원본에는 없음)
    live_effect: Dict[str, EffectResult] = field(default_factory=dict, repr=False)


# ─────────────────────────────────────────────────────────────────────────────
# 캘리브레이션 머지 규칙 R2 (§3.5)
# ─────────────────────────────────────────────────────────────────────────────

def apply_calibration(profile: dict, custom_options: dict) -> dict:
    """
    K_* 캘리브레이션 계수를 custom_options(DB)로 오버라이드한다.

    머지 규칙 R2:
      1. DB(custom_options)에 사용자가 입력한 값이 있으면 우선
      2. DB 값이 None / '' 이면 모듈 기본값 fallback
      3. 0 은 '비어있음'으로 간주 — 진짜 비활성화는 enabled 플래그 사용
    """
    result = dict(profile)
    k_keys = [k for k in profile if k.startswith('K_')]
    for key in k_keys:
        db_val = custom_options.get(key)
        if db_val is not None and db_val != '' and db_val != 0:
            result[key] = float(db_val)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# L1 출력: EnvTarget (§5.3)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TargetVar:
    value: float
    tolerance: float
    priority: float = 1.0
    unit: str = ''


EnvTarget = Dict[str, TargetVar]
# 키: 'temperature', 'humidity', 'co2', 'vpd', '_vpd_diag'(분해 후)


# ─────────────────────────────────────────────────────────────────────────────
# L2 출력: SituationReport (§2, §5.5)
# ─────────────────────────────────────────────────────────────────────────────

# 운전 모드 상수 (§5.7)
MODE_COOLING      = 'cooling'
MODE_HEATING      = 'heating'
MODE_HUMIDIFY     = 'humidify'
MODE_DEHUMIDIFY   = 'dehumidify'
MODE_CO2_ENRICH   = 'co2_enrich'
MODE_CONSERVATION = 'conservation'
MODE_EMERGENCY    = 'emergency'


@dataclass
class SituationReport:
    context: EnvContext                      # 내부+외부+추세+now_ts+cycle_sec
    target: EnvTarget                        # L1 목표 (VPD 분해 후)
    deviation_native: Dict[str, float]       # 변수별 편차 (native 단위, R1)
    limiting_factor: Optional[str] = None   # 'light'|'co2'|'temperature'|'water'
    modes: list = field(default_factory=list)  # 복합 모드 리스트
