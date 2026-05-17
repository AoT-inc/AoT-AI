# coding=utf-8
"""
env_control/effect_functions.py — 액추에이터별 EffectFn 구현체.

모든 함수는 R1 단위 규약을 준수한다:
  magnitude_native = 변수 native 단위 / 1 사이클 (cmd_pct=100 기준)

K_* 계수는 모듈 기본값. 실제 사용 시 apply_calibration()으로 장치별 오버라이드.

참조: docs/dev/integrated_env_control_design.md §3.3
"""

from .types import EffectResult, EnvContext

# ─────────────────────────────────────────────────────────────────────────────
# 보수적 기본 계수 (K_*) — Phase F 에서 자동 캘리브레이션으로 정밀화
# ─────────────────────────────────────────────────────────────────────────────
# 개구부: 외내부 온도차×개방률에 비례하는 경험적 배율
K_OPENING_T   = 0.08   # °C/cycle per (°C_delta × cmd_pct/100)
K_OPENING_RH  = 0.06   # %/cycle per (%_delta × cmd_pct/100)
K_OPENING_CO2 = 0.04   # ppm/cycle per (ppm_excess × cmd_pct/100)
# 냉방기
K_COOLER_T    = 2.5    # °C/cycle at 100%
K_COOLER_RH   = 0.8    # %/cycle at 100% (응결 가습)
# 포그·관수
K_FOG_RH      = 3.0    # %/cycle at 100%
K_FOG_T       = 0.5    # °C/cycle at 100% (증발냉각)
# 난방기
K_HEATER_T    = 2.0    # °C/cycle at 100%
K_HEATER_RH   = 1.5    # %/cycle at 100% (온도 상승 → 상대습도 하락)
# CO₂ 주입기
K_CO2_INJ     = 80.0   # ppm/cycle at 100%
# 차광막·보온커튼 (온도 영향만 — 복사 차단 비율)
K_SHADE_T     = 1.0    # °C/cycle at 100% (차광 → 온도 하락)

# 풍속 부스트 상한 (m/s)
WIND_BOOST_CAP = 8.0
WIND_BOOST_K   = 0.15  # 풍속 1m/s 당 효과 배율 증가

# G3: 면적·단열성능 가중 기준값 (참조용; 실측 캘리브레이션 시 조정)
REFERENCE_OPENING_AREA_M2 = 10.0   # 일반 온실 측창 1면 표준
REFERENCE_U_EFF           = 4.0    # vinyl_double 단층 기준 (W/m²K)


def _wind_boost(env: EnvContext) -> float:
    wind = min(env.get('wind', 0.0), WIND_BOOST_CAP)
    return 1.0 + WIND_BOOST_K * wind


def _gis_factor(profile, use_u: bool = True):
    """GIS 메타에서 (area_factor, u_factor) 산출.

    profile 또는 필드가 없으면 1.0 (효과 변동 없음).
    """
    af, uf = 1.0, 1.0
    if profile is None:
        return af, uf
    area_m2 = getattr(profile, 'area_m2', None)
    if area_m2 and area_m2 > 0:
        af = float(area_m2) / REFERENCE_OPENING_AREA_M2
    if use_u:
        cap_meta = getattr(profile, 'capacity_meta', None) or {}
        u_eff = cap_meta.get('u_effective')
        if u_eff and u_eff > 0:
            uf = REFERENCE_U_EFF / float(u_eff)
    return af, uf


# ─────────────────────────────────────────────────────────────────────────────
# 개구부 (opening)
# ─────────────────────────────────────────────────────────────────────────────

def opening_temp_effect(env: EnvContext, cmd_pct: float, profile=None) -> EffectResult:
    """외부 온도 방향으로 내부 온도를 끌어당긴다. 풍속·면적 보정.

    참고: 개구부가 열리면 envelope u_eff 는 우회되므로 u_factor 미적용.
    u_factor 는 curtain/외피 단열 변경 효과에서 의미가 있다.
    """
    delta = env.get('T_ext', 0.0) - env.get('T_int', 0.0)
    if abs(delta) < 0.5:
        return EffectResult('0', 0.0)
    direction = '↑' if delta > 0 else '↓'
    af, _u = _gis_factor(profile, use_u=False)
    magnitude = (abs(delta) * (cmd_pct / 100.0) * K_OPENING_T
                 * _wind_boost(env) * af)
    return EffectResult(direction, magnitude)


def opening_humid_effect(env: EnvContext, cmd_pct: float, profile=None) -> EffectResult:
    """외부 습도 방향으로 내부 RH를 끌어당긴다. 풍속·면적 보정."""
    delta = env.get('RH_ext', 0.0) - env.get('RH_int', 0.0)
    if abs(delta) < 1.0:
        return EffectResult('0', 0.0)
    direction = '↑' if delta > 0 else '↓'
    af, _u = _gis_factor(profile, use_u=False)
    magnitude = (abs(delta) * (cmd_pct / 100.0) * K_OPENING_RH
                 * _wind_boost(env) * af)
    return EffectResult(direction, magnitude)


def opening_co2_effect(env: EnvContext, cmd_pct: float, profile=None) -> EffectResult:
    """외부 CO₂(~400ppm)로 수렴. 내부가 더 높을 때만 희석 방향."""
    co2_ext = env.get('CO2_ext', 400.0)
    excess = env.get('CO2_int', 400.0) - co2_ext
    if excess <= 20:
        return EffectResult('0', 0.0)
    af, _ = _gis_factor(profile, use_u=False)   # CO₂ 희석은 면적만 영향
    magnitude = excess * (cmd_pct / 100.0) * K_OPENING_CO2 * af
    return EffectResult('↓', magnitude)


# 개구부 effect_model 묶음
OPENING_EFFECT_MODEL = {
    'temperature': opening_temp_effect,
    'humidity':    opening_humid_effect,
    'co2':         opening_co2_effect,
}


# ─────────────────────────────────────────────────────────────────────────────
# 냉방기 (cooler)
# ─────────────────────────────────────────────────────────────────────────────

def cooler_temp_effect(env: EnvContext, cmd_pct: float, profile=None) -> EffectResult:
    """항상 냉각. 외부 조건 무관. (실내기 — 면적·u_eff 가중 미적용)"""
    return EffectResult('↓', K_COOLER_T * (cmd_pct / 100.0))


def cooler_humid_effect(env: EnvContext, cmd_pct: float, profile=None) -> EffectResult:
    """응결로 RH 약간 상승 경향."""
    return EffectResult('↑', K_COOLER_RH * (cmd_pct / 100.0))


COOLER_EFFECT_MODEL = {
    'temperature': cooler_temp_effect,
    'humidity':    cooler_humid_effect,
}


# ─────────────────────────────────────────────────────────────────────────────
# 포그·관수 가습기 (fogger)
# ─────────────────────────────────────────────────────────────────────────────

def fogger_humid_effect(env: EnvContext, cmd_pct: float, profile=None) -> EffectResult:
    return EffectResult('↑', K_FOG_RH * (cmd_pct / 100.0))


def fogger_temp_effect(env: EnvContext, cmd_pct: float, profile=None) -> EffectResult:
    """증발냉각으로 온도 하락."""
    return EffectResult('↓', K_FOG_T * (cmd_pct / 100.0))


FOGGER_EFFECT_MODEL = {
    'temperature': fogger_temp_effect,
    'humidity':    fogger_humid_effect,
}


# ─────────────────────────────────────────────────────────────────────────────
# 난방기 (heater)
# ─────────────────────────────────────────────────────────────────────────────

def heater_temp_effect(env: EnvContext, cmd_pct: float, profile=None) -> EffectResult:
    return EffectResult('↑', K_HEATER_T * (cmd_pct / 100.0))


def heater_humid_effect(env: EnvContext, cmd_pct: float, profile=None) -> EffectResult:
    """온도 상승 → 같은 절대습도에서 RH 하락."""
    return EffectResult('↓', K_HEATER_RH * (cmd_pct / 100.0))


HEATER_EFFECT_MODEL = {
    'temperature': heater_temp_effect,
    'humidity':    heater_humid_effect,
}


# ─────────────────────────────────────────────────────────────────────────────
# CO₂ 주입기 (co2_injector)
# ─────────────────────────────────────────────────────────────────────────────

def co2_injector_co2_effect(env: EnvContext, cmd_pct: float, profile=None) -> EffectResult:
    return EffectResult('↑', K_CO2_INJ * (cmd_pct / 100.0))


CO2_INJECTOR_EFFECT_MODEL = {
    'co2': co2_injector_co2_effect,
}


# ─────────────────────────────────────────────────────────────────────────────
# 차광막·보온커튼 (shade / curtain)
# ─────────────────────────────────────────────────────────────────────────────

def shade_temp_effect(env: EnvContext, cmd_pct: float, profile=None) -> EffectResult:
    """차광 → 일사 차단 → 온도 하락. 면적 가중 (단열 무관)."""
    af, _ = _gis_factor(profile, use_u=False)
    return EffectResult('↓', K_SHADE_T * (cmd_pct / 100.0) * af)


SHADE_EFFECT_MODEL = {
    'temperature': shade_temp_effect,
}

# 보온커튼은 외부 열 손실 차단 → 난방 효과. 단독 kind 로 등록.
CURTAIN_EFFECT_MODEL = {
    'temperature': heater_temp_effect,   # 같은 방향, 계수는 별도 캘리브레이션
}


# ─────────────────────────────────────────────────────────────────────────────
# 보광등 (lighting)
# ─────────────────────────────────────────────────────────────────────────────

K_LIGHT_PPFD = 200.0   # µmol/m²/s per cycle at 100%


def lighting_light_effect(env: EnvContext, cmd_pct: float, profile=None) -> EffectResult:
    return EffectResult('↑', K_LIGHT_PPFD * (cmd_pct / 100.0))


LIGHTING_EFFECT_MODEL = {
    'light': lighting_light_effect,
}


# ─────────────────────────────────────────────────────────────────────────────
# P3-1: fan 계열 효과 함수
# ─────────────────────────────────────────────────────────────────────────────
# 순환팬: 균질화 효과 (T/RH 구배 해소). 에너지 투입은 없음 — 효과 크기는 작음.
K_CIRC_FAN_T   = 0.3   # °C/cycle at 100% (T 불균일 완화)
K_CIRC_FAN_RH  = 0.5   # %/cycle at 100%

# 배기팬: ACH 기반. capacity_meta['rated_m3h'] (m³/h) + volume_m3 필요.
K_EXHAUST_FAN_FACTOR = 1.0   # 경험적 보정 계수 (추후 캘리브레이션)


def circulation_fan_temp_effect(env: EnvContext, cmd_pct: float, profile=None) -> EffectResult:
    """순환팬 → 내부 T 구배 완화 (미미한 효과)."""
    return EffectResult('~', K_CIRC_FAN_T * (cmd_pct / 100.0))


def circulation_fan_humid_effect(env: EnvContext, cmd_pct: float, profile=None) -> EffectResult:
    return EffectResult('~', K_CIRC_FAN_RH * (cmd_pct / 100.0))


CIRCULATION_FAN_EFFECT_MODEL = {
    'temperature': circulation_fan_temp_effect,
    'humidity':    circulation_fan_humid_effect,
}


def _exhaust_ach(cmd_pct: float, profile) -> float:
    """ACH (Air Changes per Hour) = rated_m3h × cmd/100 / volume_m3."""
    meta = getattr(profile, 'capacity_meta', {}) or {}
    rated = float(meta.get('rated_m3h', 0.0) or 0.0)
    volume = float(meta.get('volume_m3', 0.0) or 0.0)
    if rated <= 0 or volume <= 0:
        return 0.0
    return rated * (cmd_pct / 100.0) / volume


def exhaust_fan_temp_effect(env: EnvContext, cmd_pct: float, profile=None) -> EffectResult:
    """배기팬 → 외내부 온도차 × ACH 기반 T 변화."""
    ach = _exhaust_ach(cmd_pct, profile)
    if ach <= 0:
        # rated_m3h 없으면 근사값 사용
        return EffectResult('↓' if env.get('T_ext', 20) < env.get('T_int', 25) else '↑',
                            K_CIRC_FAN_T * 2 * (cmd_pct / 100.0))
    delta_T = env.get('T_ext', 20.0) - env.get('T_int', 25.0)
    mag = abs(delta_T) * ach * (1 / 60.0) * K_EXHAUST_FAN_FACTOR
    return EffectResult('↑' if delta_T > 0 else '↓', mag)


def exhaust_fan_humid_effect(env: EnvContext, cmd_pct: float, profile=None) -> EffectResult:
    """배기팬 → 외내부 RH 차 × ACH 기반 RH 변화."""
    ach = _exhaust_ach(cmd_pct, profile)
    if ach <= 0:
        return EffectResult('~', 0.0)
    delta_rh = env.get('RH_ext', 60.0) - env.get('RH_int', 70.0)
    mag = abs(delta_rh) * ach * (1 / 60.0) * K_EXHAUST_FAN_FACTOR
    return EffectResult('↑' if delta_rh > 0 else '↓', mag)


def exhaust_fan_co2_effect(env: EnvContext, cmd_pct: float, profile=None) -> EffectResult:
    """배기팬 → CO₂ 희석 (실내 CO₂ > 외부 가정)."""
    ach = _exhaust_ach(cmd_pct, profile)
    if ach <= 0:
        return EffectResult('~', 0.0)
    excess = max(0, env.get('CO2_int', 400) - env.get('CO2_ext', 400))
    mag = excess * ach * (1 / 60.0) * K_EXHAUST_FAN_FACTOR
    return EffectResult('↓', mag)


EXHAUST_FAN_EFFECT_MODEL = {
    'temperature': exhaust_fan_temp_effect,
    'humidity':    exhaust_fan_humid_effect,
    'co2':         exhaust_fan_co2_effect,
}

# 흡기팬: 배기팬과 동일 물리 모델 (보완 관계) — 별도 조율은 coordinator 에서 처리
INTAKE_FAN_EFFECT_MODEL = dict(EXHAUST_FAN_EFFECT_MODEL)


# ─────────────────────────────────────────────────────────────────────────────
# kind → 기본 effect_model 조회
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_EFFECT_MODELS = {
    'opening':          OPENING_EFFECT_MODEL,
    'cooler':           COOLER_EFFECT_MODEL,
    'heater':           HEATER_EFFECT_MODEL,
    'fogger':           FOGGER_EFFECT_MODEL,
    'co2_injector':     CO2_INJECTOR_EFFECT_MODEL,
    'shade':            SHADE_EFFECT_MODEL,
    'curtain':          CURTAIN_EFFECT_MODEL,
    'lighting':         LIGHTING_EFFECT_MODEL,
    'circulation_fan':  CIRCULATION_FAN_EFFECT_MODEL,
    'exhaust_fan':      EXHAUST_FAN_EFFECT_MODEL,
    'intake_fan':       INTAKE_FAN_EFFECT_MODEL,
}


def build_effect_model(kind: str, k: dict) -> dict:
    """
    kind 와 캘리브레이션 계수 k 로 effect_model 딕셔너리를 생성.

    k 에 K_* 키가 있으면 모듈 기본값을 오버라이드한다 (R2).
    k 가 빈 dict 이면 모듈 기본값 그대로 반환.

    Args:
        kind: ACTUATOR_KINDS 중 하나 ('cooler', 'heater', ...)
        k:    캘리브레이션 계수 dict  {'K_COOLER_T': 3.0, ...}

    Returns:
        effect_model dict  {var: EffectFn, ...}
    """
    if not k:
        return dict(DEFAULT_EFFECT_MODELS.get(kind, {}))

    # 계수 오버라이드가 있는 경우 클로저로 새 함수 생성
    # 모든 람다는 (env, pct, profile=None) 시그니처. opening/shade 는 GIS 가중 적용.
    if kind == 'opening':
        k_t   = k.get('K_OPENING_T',   K_OPENING_T)
        k_rh  = k.get('K_OPENING_RH',  K_OPENING_RH)
        k_co2 = k.get('K_OPENING_CO2', K_OPENING_CO2)

        def _t(env, pct, profile=None, _k=k_t):
            d = env.get('T_ext', 0) - env.get('T_int', 0)
            if abs(d) < 0.5:
                return EffectResult('0', 0.0)
            af, _u = _gis_factor(profile, use_u=False)
            return EffectResult('↑' if d > 0 else '↓',
                                abs(d) * (pct/100) * _k * _wind_boost(env) * af)

        def _rh(env, pct, profile=None, _k=k_rh):
            d = env.get('RH_ext', 0) - env.get('RH_int', 0)
            if abs(d) < 1.0:
                return EffectResult('0', 0.0)
            af, _u = _gis_factor(profile, use_u=False)
            return EffectResult('↑' if d > 0 else '↓',
                                abs(d) * (pct/100) * _k * _wind_boost(env) * af)

        def _co2(env, pct, profile=None, _k=k_co2):
            ex = env.get('CO2_int', 400) - env.get('CO2_ext', 400)
            if ex <= 20:
                return EffectResult('0', 0.0)
            af, _u = _gis_factor(profile, use_u=False)
            return EffectResult('↓', ex * (pct/100) * _k * af)

        return {'temperature': _t, 'humidity': _rh, 'co2': _co2}

    elif kind == 'cooler':
        k_t  = k.get('K_COOLER_T',  K_COOLER_T)
        k_rh = k.get('K_COOLER_RH', K_COOLER_RH)
        return {
            'temperature': lambda env, pct, profile=None, _k=k_t:  EffectResult('↓', _k * (pct / 100)),
            'humidity':    lambda env, pct, profile=None, _k=k_rh: EffectResult('↑', _k * (pct / 100)),
        }
    elif kind == 'heater':
        k_t  = k.get('K_HEATER_T',  K_HEATER_T)
        k_rh = k.get('K_HEATER_RH', K_HEATER_RH)
        return {
            'temperature': lambda env, pct, profile=None, _k=k_t:  EffectResult('↑', _k * (pct / 100)),
            'humidity':    lambda env, pct, profile=None, _k=k_rh: EffectResult('↓', _k * (pct / 100)),
        }
    elif kind == 'fogger':
        k_rh = k.get('K_FOG_RH', K_FOG_RH)
        k_t  = k.get('K_FOG_T',  K_FOG_T)
        return {
            'humidity':    lambda env, pct, profile=None, _k=k_rh: EffectResult('↑', _k * (pct / 100)),
            'temperature': lambda env, pct, profile=None, _k=k_t:  EffectResult('↓', _k * (pct / 100)),
        }
    elif kind == 'co2_injector':
        k_co2 = k.get('K_CO2_INJ', K_CO2_INJ)
        return {
            'co2': lambda env, pct, profile=None, _k=k_co2: EffectResult('↑', _k * (pct / 100)),
        }
    elif kind == 'shade':
        k_t = k.get('K_SHADE_T', K_SHADE_T)

        def _shade_t(env, pct, profile=None, _k=k_t):
            af, _u = _gis_factor(profile, use_u=False)
            return EffectResult('↓', _k * (pct/100) * af)

        return {'temperature': _shade_t}
    elif kind == 'curtain':
        k_t = k.get('K_CURTAIN_T', K_HEATER_T)
        return {
            'temperature': lambda env, pct, profile=None, _k=k_t: EffectResult('↑', _k * (pct / 100)),
        }
    elif kind == 'lighting':
        k_ppfd = k.get('K_LIGHT_PPFD', K_LIGHT_PPFD)
        return {
            'light': lambda env, pct, profile=None, _k=k_ppfd: EffectResult('↑', _k * (pct / 100)),
        }
    elif kind in ('circulation_fan', 'exhaust_fan', 'intake_fan'):
        # fan 계열은 k_override 없으면 DEFAULT_EFFECT_MODELS 그대로 사용
        return dict(DEFAULT_EFFECT_MODELS.get(kind, {}))
    else:
        return {}
