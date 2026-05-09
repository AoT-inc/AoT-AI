# coding=utf-8
"""
env_control/coordinator.py — Layer 3 액추에이터 조율 알고리즘 (C2~C5).

설계 §4 의사코드를 구현한다:
  - C2: live_effect 평가 엔진
  - C3: 조율 알고리즘 (PI 명령, slew, hysteresis, anti-windup)
  - C4: 부작용 충돌 검출
  - C5: 의사결정 로깅 (caller 가 unique_id 전달)

단위 규약 R1:
  모든 deviation, accumulated, residual, magnitude 는 native 단위.
  우선순위 정렬에만 정규화 사용.

참조: docs/dev/integrated_env_control_design.md §4
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .log_channels import (
    write_decision_log,
    ch_coord_cmd, ch_coord_reason, ch_integral,
    REASON_IDLE, REASON_PRIMARY, REASON_SECONDARY,
    REASON_WRONG_DIRECTION, REASON_SIDE_EFFECT, REASON_MANUAL_OVERRIDE,
)
from .types import ActuatorProfile, SituationReport

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 조율 상태 (사이클 간 보존)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CoordinatorState:
    """매 사이클 result 로 반환, 다음 사이클에 prev 로 전달."""
    prev_commands: Dict[str, float] = field(default_factory=dict)
    integral:      Dict[str, float] = field(default_factory=dict)
    active_vars:   Dict[str, bool]  = field(default_factory=dict)  # hysteresis


# ─────────────────────────────────────────────────────────────────────────────
# 명령 결과
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ActuatorCommand:
    value: float
    reason: int
    var_source: Optional[str] = None  # 이 명령을 유발한 변수


CoordResult = Dict[str, ActuatorCommand]


# ─────────────────────────────────────────────────────────────────────────────
# 메인 진입점
# ─────────────────────────────────────────────────────────────────────────────

def coordinate(
    situation: SituationReport,
    profiles: List[ActuatorProfile],
    state: CoordinatorState,
    unique_id: str = '',
    actuator_index: Dict[str, int] = None,
) -> Tuple[CoordResult, CoordinatorState]:
    """
    L3 조율 알고리즘 실행.

    Args:
        situation:      L2 SituationReport
        profiles:       등록된 액추에이터 목록 (get_profile() 결과)
        state:          이전 사이클 상태 (첫 번째 사이클은 CoordinatorState() 전달)
        unique_id:      InfluxDB 기록용 Function unique_id
        actuator_index: {actuator_id: idx} — 로깅 채널 계산용

    Returns:
        (commands dict, 업데이트된 CoordinatorState)
    """
    commands: CoordResult = {}
    accumulated: Dict[str, float] = {
        var: 0.0 for var in situation.deviation_native
    }
    new_state = CoordinatorState(
        prev_commands=dict(state.prev_commands),
        integral=dict(state.integral),
        active_vars=dict(state.active_vars),
    )
    ctx = situation.context
    cycle_sec = ctx.get('cycle_sec', 60.0)
    a_idx = actuator_index or {}

    # ── 1. 수동 락 처리 + live_effect 계산 (C2) ──────────────────────────────
    for p in profiles:
        if p.manual_lock.is_active():
            commands[p.actuator_id] = ActuatorCommand(
                value=p.manual_lock.manual_value,
                reason=REASON_MANUAL_OVERRIDE,
            )
            _log_cmd(unique_id, p.actuator_id, a_idx, p.manual_lock.manual_value,
                     REASON_MANUAL_OVERRIDE)
            continue

        p.live_effect = {
            var: p.effect_model[var](ctx, 100.0, p)   # G3: profile 전달
            for var in p.effect_model
        }

    # 아직 명령 받지 않은 프로필만 후보
    available = [p for p in profiles if p.actuator_id not in commands]

    # ── 2. 변수 우선순위 정렬 (native deviation / tolerance × priority) ────────
    sorted_vars = _sort_vars(situation)

    # ── 3. 변수별 순회 ────────────────────────────────────────────────────────
    for var in sorted_vars:
        if var not in situation.deviation_native:
            continue
        target_var = situation.target.get(var)
        if target_var is None:
            continue

        tol      = target_var.tolerance
        residual = situation.deviation_native[var] - accumulated.get(var, 0.0)

        # 히스테리시스 (C3 §4.1) ─────────────────────────────────────────────
        was_active = new_state.active_vars.get(var, False)
        tol_enter = tol * 0.5
        tol_exit  = tol * 1.0

        if was_active:
            active_now = abs(residual) >= tol_enter
        else:
            active_now = abs(residual) >= tol_exit

        new_state.active_vars[var] = active_now

        if not active_now:
            new_state.integral[var] = new_state.integral.get(var, 0.0) * 0.95
            continue

        needed_dir = '↓' if residual > 0 else '↑'

        # 적분 누적
        new_state.integral[var] = (
            new_state.integral.get(var, 0.0) + residual * (cycle_sec / 60.0)
        )

        # 후보 수집 + 비용 정렬
        helpers = [
            p for p in available
            if p.actuator_id not in commands
            and var in p.live_effect
            and p.live_effect[var].direction == needed_dir
        ]
        helpers.sort(key=lambda p: p.cost_fn(ctx, 100.0))

        is_first = True
        for p in helpers:
            if abs(residual) < tol * 0.5:
                break

            # 부작용 충돌 검사 (C4) ───────────────────────────────────────────
            if _creates_conflict(p, situation, accumulated, var):
                _log_cmd(unique_id, p.actuator_id, a_idx, 0.0, REASON_SIDE_EFFECT)
                continue

            # PI 명령 산출 (C3) ────────────────────────────────────────────────
            unit_mag = p.live_effect[var].magnitude_native
            if unit_mag < 1e-9:
                continue

            kp = p.gains.get('kp', 1.0)
            ki = p.gains.get('ki', 0.05)
            p_term = kp * residual
            i_term = ki * new_state.integral.get(var, 0.0)
            cmd_raw = (p_term + i_term) / unit_mag * 100.0
            cmd_raw = _clamp(cmd_raw, 0.0, 100.0)

            # Anti-windup ─────────────────────────────────────────────────────
            if (cmd_raw <= 0.0 or cmd_raw >= 100.0):
                if _same_sign(residual, new_state.integral.get(var, 0.0)):
                    new_state.integral[var] -= residual * (cycle_sec / 60.0)

            # Slew rate 제한 ───────────────────────────────────────────────────
            prev_val = state.prev_commands.get(p.actuator_id, 0.0)
            slew = p.cmd_constraints.slew_per_cycle
            cmd_slew = _clamp(cmd_raw, prev_val - slew, prev_val + slew)

            # 최소 ON 스냅 ─────────────────────────────────────────────────────
            if 0.0 < cmd_slew < p.cmd_constraints.min_on_pct:
                cmd_slew = 0.0

            reason = REASON_PRIMARY if is_first else REASON_SECONDARY
            commands[p.actuator_id] = ActuatorCommand(
                value=cmd_slew, reason=reason, var_source=var)
            is_first = False

            # 누적 효과 업데이트 (모든 변수) ──────────────────────────────────
            for v, eff in p.live_effect.items():
                sign = 1.0 if eff.direction == '↑' else (-1.0 if eff.direction == '↓' else 0.0)
                contribution = eff.magnitude_native * (cmd_slew / 100.0) * sign
                accumulated[v] = accumulated.get(v, 0.0) + contribution
                if v == var:
                    residual -= contribution

            _log_cmd(unique_id, p.actuator_id, a_idx, cmd_slew, reason)

    # ── 4. 명령 안 받은 액추에이터 → 안전 기본값 ─────────────────────────────
    for p in profiles:
        if p.actuator_id not in commands:
            commands[p.actuator_id] = ActuatorCommand(
                value=p.safe_default, reason=REASON_IDLE)
            _log_cmd(unique_id, p.actuator_id, a_idx, p.safe_default, REASON_IDLE)

    # 다음 사이클을 위한 prev_commands 갱신
    new_state.prev_commands = {aid: cmd.value for aid, cmd in commands.items()}

    return commands, new_state


# ─────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _sort_vars(situation: SituationReport) -> List[str]:
    """우선순위 정렬: |deviation_native| / tolerance × priority (내림차순)."""
    scores = {}
    for var, dev in situation.deviation_native.items():
        t = situation.target.get(var)
        if t is None:
            continue
        tol = t.tolerance if t.tolerance > 0 else 1e-6
        scores[var] = abs(dev) / tol * t.priority
    return sorted(scores, key=scores.get, reverse=True)


def _creates_conflict(
    p: ActuatorProfile,
    situation: SituationReport,
    accumulated: Dict[str, float],
    primary_var: str,
) -> bool:
    """이 액추에이터를 사용할 때 다른 변수의 편차를 악화시키는지 검사 (C4)."""
    for v, eff in p.live_effect.items():
        if v == primary_var or v not in situation.deviation_native:
            continue

        t = situation.target.get(v)
        if t is None:
            continue

        dev = situation.deviation_native[v] - accumulated.get(v, 0.0)
        if abs(dev) < t.tolerance * 0.3:
            continue  # 여유 충분 — 문제 없음

        # 효과 방향이 편차와 같은 방향 = 악화
        effect_sign = 1.0 if eff.direction == '↑' else (-1.0 if eff.direction == '↓' else 0.0)
        dev_sign    = 1.0 if dev > 0 else -1.0
        if effect_sign == dev_sign:
            return True

    return False


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def _same_sign(a: float, b: float) -> bool:
    return (a > 0 and b > 0) or (a < 0 and b < 0)


def _log_cmd(
    unique_id: str,
    actuator_id: str,
    a_idx: Dict[str, int],
    value: float,
    reason: int,
):
    if not unique_id or actuator_id not in a_idx:
        return
    idx = a_idx[actuator_id]
    write_decision_log(unique_id, f'coord_actuator_{actuator_id[:8]}_command',
                       ch_coord_cmd(idx), value)
    write_decision_log(unique_id, f'coord_actuator_{actuator_id[:8]}_reason',
                       ch_coord_reason(idx), float(reason))
