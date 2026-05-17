# coding=utf-8
"""
calibration.py — P3-3: 효과계수 자동 캘리브레이션 (Recursive Least Squares).

알고리즘: 망각 RLS (λ=0.95)
  K̂(t+1) = K̂(t) + P(t)·x(t)·e(t) / (λ + P(t)·x(t)²)
  P(t+1) = (P(t) - P(t)·x(t)²·P(t) / (λ + P(t)·x(t)²)) / λ
  where x = cmd_pct/100, e = ΔY_obs - K̂·x

사용 조건:
  - Δcmd > 5%  (유의미한 변화만)
  - 외란 없음  (rain=0, wind < 5 m/s)
  - 수렴 보호: K_learned ∈ [K_default × 0.1, K_default × 5]

API:
  rls = RLSCalibrator(k_default=2.0, lambda_=0.95, bounds_factor=(0.1, 5.0))
  rls.update(cmd_pct_prev, cmd_pct_now, delta_obs, disturbed)
  k = rls.k_hat
  state = rls.state_dict()   # DB 저장용
  rls2 = RLSCalibrator.from_state(state)
"""

import math


class RLSCalibrator:
    """단일 효과계수 K의 Recursive Least Squares 추정기."""

    def __init__(self, k_default: float, lambda_: float = 0.95,
                 bounds_factor: tuple = (0.1, 5.0)):
        self.k_default = float(k_default)
        self.lambda_   = float(lambda_)
        self.k_min     = self.k_default * bounds_factor[0]
        self.k_max     = self.k_default * bounds_factor[1]

        self.k_hat  = self.k_default  # 현재 추정값
        self._P     = 1.0             # 추정 분산 (초기 불확실성 크게)
        self.n_updates = 0

    # ── RLS 갱신 ─────────────────────────────────────────────────────────────

    def update(self, cmd_pct_prev: float, cmd_pct_now: float,
               delta_obs: float, disturbed: bool = False) -> bool:
        """관측 ΔY 를 이용해 K 추정값 갱신.

        Args:
            cmd_pct_prev: 이전 사이클 명령 (0~100)
            cmd_pct_now:  현재 사이클 명령 (0~100)
            delta_obs:    관측된 변수 변화량 (native 단위)
            disturbed:    외란 여부 (True 면 갱신 스킵)

        Returns:
            True if update was applied.
        """
        if disturbed:
            return False

        delta_cmd = abs(cmd_pct_now - cmd_pct_prev)
        if delta_cmd < 5.0:
            return False

        # 현재 적용된 명령이 응답을 만들므로 cmd_pct_now 를 리그레서로 사용
        x = cmd_pct_now / 100.0
        if abs(x) < 1e-6:
            return False

        lam = self.lambda_
        P   = self._P

        # 칼만 이득
        denom = lam + P * x * x
        gain  = P * x / denom

        # 예측 오차
        e = delta_obs - self.k_hat * x

        # 갱신
        self.k_hat = self.k_hat + gain * e
        self._P    = (P - gain * x * P) / lam

        # 수렴 보호
        self.k_hat = max(self.k_min, min(self.k_max, self.k_hat))
        self.n_updates += 1
        return True

    # ── 상태 직렬화 ───────────────────────────────────────────────────────────

    def state_dict(self) -> dict:
        return {
            'k_hat':      self.k_hat,
            'P':          self._P,
            'n_updates':  self.n_updates,
            'k_default':  self.k_default,
            'lambda_':    self.lambda_,
            'k_min':      self.k_min,
            'k_max':      self.k_max,
        }

    @classmethod
    def from_state(cls, state: dict) -> 'RLSCalibrator':
        obj = cls.__new__(cls)
        obj.k_default  = state['k_default']
        obj.lambda_    = state.get('lambda_', 0.95)
        obj.k_min      = state.get('k_min', obj.k_default * 0.1)
        obj.k_max      = state.get('k_max', obj.k_default * 5.0)
        obj.k_hat      = state.get('k_hat', obj.k_default)
        obj._P         = state.get('P', 1.0)
        obj.n_updates  = state.get('n_updates', 0)
        return obj

    @property
    def variance(self) -> float:
        return self._P

    def is_converged(self, threshold: float = 0.01) -> bool:
        """분산이 threshold 이하이면 수렴으로 판단."""
        return self._P < threshold


class ActuatorCalibrator:
    """단일 액추에이터의 (temperature, humidity, co2) 각 효과계수 RLS 추정."""

    _DEFAULT_K = {
        'opening':         {'temperature': 0.08, 'humidity': 0.06, 'co2': 0.04},
        'cooler':          {'temperature': 2.5,  'humidity': 0.8},
        'heater':          {'temperature': 2.0,  'humidity': 1.5},
        'fogger':          {'humidity': 3.0,     'temperature': 0.5},
        'co2_injector':    {'co2': 80.0},
        'shade':           {'temperature': 1.0},
        'curtain':         {'temperature': 2.0},
        'circulation_fan': {'temperature': 0.3,  'humidity': 0.5},
        'exhaust_fan':     {'temperature': 0.5,  'humidity': 0.5,  'co2': 0.3},
        'intake_fan':      {'temperature': 0.5,  'humidity': 0.5},
    }

    def __init__(self, actuator_id: str, kind: str, enabled: bool = False):
        self.actuator_id = actuator_id
        self.kind        = kind
        self.enabled     = enabled
        defaults = self._DEFAULT_K.get(kind, {})
        self._rls: dict[str, RLSCalibrator] = {
            var: RLSCalibrator(k_def)
            for var, k_def in defaults.items()
        }

    def update(self, var: str, cmd_pct_prev: float, cmd_pct_now: float,
               delta_obs: float, disturbed: bool = False) -> bool:
        if not self.enabled:
            return False
        rls = self._rls.get(var)
        if rls is None:
            return False
        return rls.update(cmd_pct_prev, cmd_pct_now, delta_obs, disturbed)

    def k_hat(self, var: str) -> float:
        rls = self._rls.get(var)
        return rls.k_hat if rls else 0.0

    def state_dict(self) -> dict:
        return {
            'actuator_id': self.actuator_id,
            'kind':        self.kind,
            'enabled':     self.enabled,
            'rls':         {var: rls.state_dict() for var, rls in self._rls.items()},
        }

    @classmethod
    def from_state(cls, state: dict) -> 'ActuatorCalibrator':
        obj = cls.__new__(cls)
        obj.actuator_id = state['actuator_id']
        obj.kind        = state['kind']
        obj.enabled     = state.get('enabled', False)
        obj._rls = {
            var: RLSCalibrator.from_state(rls_state)
            for var, rls_state in state.get('rls', {}).items()
        }
        return obj


def is_disturbed(ext_ctx: dict, wind_threshold: float = 5.0) -> bool:
    """외란 여부 판단 — 강우 또는 강풍 시 True."""
    rain = ext_ctx.get('rain', 0.0) or 0.0
    wind = ext_ctx.get('wind', 0.0) or 0.0
    return rain > 0 or wind > wind_threshold
