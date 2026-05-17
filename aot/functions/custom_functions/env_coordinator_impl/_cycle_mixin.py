# coding=utf-8
"""
_cycle_mixin.py — CycleMixin: _run_cycle() (L1→L2→L3 pipeline).
"""

import time

from aot.functions.utils.env_control.authority import authority_summary, derive_authority
from aot.functions.utils.env_control.coordinator import coordinate
from aot.functions.utils.env_control.ext_context_fallback import build_fallback_context
from aot.functions.utils.env_control.goal import build_env_target
from aot.functions.utils.env_control.group_expander import expand_group_commands
from aot.functions.utils.env_control.log_channels import (
    CH_SAFETY_GATE, CH_SITUATION_LIMIT, CH_SITUATION_MODE,
    GATE_BIT_WIND, GATE_BIT_RAIN, GATE_BIT_HEAT, GATE_BIT_COLD,
    LIMIT_CODES, MODE_CODES,
    ch_goal_priority, ch_goal_target, ch_situation_deviation,
    write_cycle_metrics, write_decision_log,
)
from aot.functions.utils.env_control.forecast_feedforward import (
    FeedforwardSignal, apply_feedforward, build_feedforward_signal,
)
from aot.functions.utils.env_control.situation import assess, decompose_vpd_to_T_RH


class CycleMixin:
    """Mixin: one coordination cycle (L1 target → L2 situation → L3 coordinate → dispatch)."""

    def _run_cycle(self, cycle_sec: float):
        uid     = self.unique_id
        max_age = self.sensor_max_age or 120.0

        if not self._profiles:
            self.logger.debug(
                'EnvCoordinator: no actuators registered — skipping cycle')
            return

        # ── Time window gate ──────────────────────────────────────────────────
        if self.time_enable and not self._in_time_window():
            self._apply_end_behaviors()
            return

        # ── External context ──────────────────────────────────────────────────
        try:
            from aot.functions.ext_context_collector import get_shared_context
            external = get_shared_context()
        except Exception:
            external = {}

        # P2-2: 외부 컨텍스트 신선도 확인 — 유효하면 캐시 갱신, 만료면 fallback 준비
        now_ts      = time.time()
        ext_max_age = self._pre_gate.config.ext_context_max_age if self._pre_gate else 300.0
        last_ext_ts = external.get('last_ext_ts', now_ts)
        ext_stale   = (now_ts - last_ext_ts) > ext_max_age

        if not ext_stale:
            self._ext_cache.update(external, now=now_ts)

        # ── Internal sensors ──────────────────────────────────────────────────
        internal = self._collect_internal(max_age)
        if not internal:
            self.logger.warning(
                'EnvCoordinator: no internal sensor data — skipping cycle')
            return

        # P2-2: 외부 센서 만료 시 fallback 컨텍스트로 교체
        if ext_stale:
            stale_age = self._ext_cache.age(now_ts)
            self.logger.warning(
                'EnvCoordinator: 외부 센서 만료 %.0fs — fallback 컨텍스트 사용', stale_age)
            external_for_control = build_fallback_context(
                self._ext_cache, internal, now_ts)
        else:
            external_for_control = external

        # ── Pre-Gate ──────────────────────────────────────────────────────────
        gate_env    = self._build_gate_env(internal, external)
        gate_result = self._pre_gate.evaluate(gate_env, self._profiles, uid)

        if gate_result.triggered:
            self._dispatch(gate_result.forced_commands)
            write_decision_log(uid, 'safety_gate_active',
                               CH_SAFETY_GATE, float(gate_result.gate_mask))
            # ── 심각 이벤트 이메일 알림 (1일 1회) ─────────────────────────────
            mask   = gate_result.gate_mask
            ext_t  = gate_env.get('external', {})
            int_t  = gate_env.get('internal', {})
            if mask & GATE_BIT_WIND:
                wind_v = ext_t.get('wind', 0.0)
                self._send_critical_email(
                    'wind_gate',
                    f'[돌풍 경보] 풍속 {wind_v:.1f} m/s 감지 — '
                    f'환기구 전체 강제 폐쇄 중. 시설 고정 상태를 점검하세요.',
                )
            if mask & GATE_BIT_RAIN:
                self._send_critical_email(
                    'rain_gate',
                    '[강우 경보] 강우 감지 — 환기구 폐쇄. '
                    '전기 장치 수분 노출 여부를 점검하세요.',
                )
            if mask & GATE_BIT_HEAT:
                T_e = ext_t.get('T', 0.0)
                T_i = int_t.get('T', 0.0)
                self._send_critical_email(
                    'extreme_heat',
                    f'[폭염 경보] 외부 {T_e:.1f}°C / 내부 {T_i:.1f}°C — '
                    f'냉방 장치 최대 가동 중. 그늘막·차광 설비를 점검하세요.',
                )
            if mask & GATE_BIT_COLD:
                T_e = ext_t.get('T', 0.0)
                T_i = int_t.get('T', 0.0)
                self._send_critical_email(
                    'extreme_cold',
                    f'[한파 경보] 외부 {T_e:.1f}°C / 내부 {T_i:.1f}°C — '
                    f'난방 장치 최대 가동 중. 보온재 및 배관 동결 여부를 점검하세요.',
                )
            return
        elif gate_result.gate_mask == 0:
            self._coord_state.integral.clear()
            self._coord_state.active_vars.clear()

        # partial=True: EXT_EXP 단독 또는 풍향 차등 모드.
        # L1~L3 정상 실행 후 _dispatch 직전 forced_commands 를 override 로 적용.
        partial_overrides = (gate_result.forced_commands
                             if gate_result.partial else {})

        # ── T/RH constraint check (before L1) ────────────────────────────────
        t_val  = internal.get('T')
        rh_val = internal.get('RH')
        if t_val is not None:
            if self.temp_max and t_val > self.temp_max:
                self.logger.warning(
                    'T=%.1f > max=%.1f — forcing cooling', t_val, self.temp_max)
                internal['_force_cool'] = True
            if self.temp_min and t_val < self.temp_min:
                self.logger.warning(
                    'T=%.1f < min=%.1f — forcing heating', t_val, self.temp_min)
                internal['_force_heat'] = True
        if rh_val is not None:
            if self.humid_max and rh_val > self.humid_max:
                internal['_force_dehumid'] = True
            if self.humid_min and rh_val < self.humid_min:
                internal['_force_humid'] = True

        # ── L1: EnvTarget (VPD-primary) ───────────────────────────────────────
        vpd_t = self._get_vpd_setpoint()
        co2_t = self._get_co2_setpoint()

        # Guide 범위
        T_g_min  = self.guide_T_min  if self.guide_T_min  is not None else 12.0
        T_g_max  = self.guide_T_max  if self.guide_T_max  is not None else 32.0
        RH_g_min = self.guide_RH_min if self.guide_RH_min is not None else 40.0
        RH_g_max = self.guide_RH_max if self.guide_RH_max is not None else 85.0

        T_int  = internal.get('T',  22.0)
        RH_int = internal.get('RH', 60.0)

        if vpd_t and vpd_t > 0.0:
            # VPD → (T_aux, RH_aux) 분해 후 guide 범위 클램프
            w_T = self.vpd_weight_T if self.vpd_weight_T is not None else 0.6
            T_aux, RH_aux = decompose_vpd_to_T_RH(
                vpd_target=vpd_t,
                T_int=T_int,
                RH_int=RH_int,
                w_T=w_T,
            )
            T_aux  = max(T_g_min, min(T_g_max,  T_aux))
            RH_aux = max(RH_g_min, min(RH_g_max, RH_aux))
        else:
            # VPD 타겟 없을 때 guide 중앙값 사용
            T_aux  = (T_g_min + T_g_max)  / 2.0
            RH_aux = (RH_g_min + RH_g_max) / 2.0

        env_target = build_env_target(
            T_target   = T_aux,
            T_tol      = 1.0,
            T_pri      = 0.5,
            RH_target  = RH_aux,
            RH_tol     = 5.0,
            RH_pri     = 0.5,
            CO2_target = co2_t or 1000.0,
            CO2_tol    = self.tolerance_co2 or 100.0,
            CO2_pri    = self.priority_co2  or 0.8,
            VPD_target = vpd_t,
            VPD_tol    = self.tolerance_vpd or 0.1,
            VPD_pri    = self.priority_vpd  or 1.2,
        )
        if co2_t is None:
            env_target.pop('co2', None)

        # ── P3-4: Forecast Feedforward ────────────────────────────────────────
        if getattr(self, 'forecast_feedforward_enabled', False):
            ff_sig = build_feedforward_signal(
                T_int          = T_int,
                RH_int         = RH_int,
                lookahead_h    = getattr(self, 'forecast_lookahead_h', 3.0) or 3.0,
                wind_threshold = self.gate_wind_threshold or 12.0,
            )
            if ff_sig.valid and ff_sig.reason != '정상 범위':
                self.logger.info('Feedforward: %s', ff_sig.reason)
                apply_feedforward(
                    env_target,
                    ff_sig,
                    T_g_min=T_g_min, T_g_max=T_g_max,
                    RH_g_min=RH_g_min, RH_g_max=RH_g_max,
                )
                # 환기 억제 신호를 internal에 전달 → safety_gates에서 참조 가능
                if ff_sig.wind_inhibit:
                    internal['_ff_wind_inhibit'] = True
            self._last_ff_signal = ff_sig
        else:
            self._last_ff_signal = FeedforwardSignal()

        for var, tv in env_target.items():
            if var.startswith('_'):
                continue
            write_decision_log(uid, f'goal_target_{var}',
                               ch_goal_target(var),   tv.value)
            write_decision_log(uid, f'goal_priority_{var}',
                               ch_goal_priority(var), tv.priority)

        # ── P5-2: Control Authority 도출 (매 사이클 — 프로파일 변경 대응) ─────
        authority = derive_authority(self._profiles)
        if not getattr(self, '_last_authority', None):
            self.logger.info(
                'EnvCoordinator authority: %s', authority_summary(authority))
        self._last_authority = authority

        # ── P5-4: Photosynthesis-oriented priority 격상 ───────────────────────
        if self.photosynth_mode_enabled and internal.get('light') is not None:
            from aot.functions.utils.env_control.photosynthesis import (
                boost_limiting_priority, decay_priorities,
                find_limiting_factor, get_crop_params,
            )
            crop = get_crop_params(self.crop_preset)
            vpd_now = internal.get('VPD') or 0.0
            limiting = find_limiting_factor(
                L=internal.get('light', 0.0),
                CO2=internal.get('CO2', 400.0),
                T=internal.get('T', 22.0),
                VPD=vpd_now,
                crop_params=crop,
            )
            base_priorities = {
                'temperature': self.priority_vpd  or 0.5,   # T 추적 우선순위 = vpd 기반
                'humidity':    0.5,
                'co2':         self.priority_co2  or 0.8,
                'vpd':         self.priority_vpd  or 1.2,
                'light':       0.9,
            }
            boost_limiting_priority(
                env_target=env_target,
                limiting_factor=limiting,
                authority=authority,
                priority_ewa_state=self._priority_ewa_state,
                base_priorities=base_priorities,
            )
            self.logger.debug(
                'Photosynthesis limiting factor: %s', limiting)
        elif self.photosynth_mode_enabled:
            # 광 센서 없음 — 우선순위 기본값으로 복귀
            from aot.functions.utils.env_control.photosynthesis import decay_priorities
            base_priorities = {
                'temperature': 0.5, 'humidity': 0.5,
                'co2': self.priority_co2 or 0.8,
                'vpd': self.priority_vpd or 1.2,
            }
            decay_priorities(env_target, self._priority_ewa_state, base_priorities)

        # ── L2: SituationReport ───────────────────────────────────────────────
        situation, self._trend_state = assess(
            env_target=env_target,
            internal=internal,
            external=external_for_control,
            cycle_sec=cycle_sec,
            now_ts=time.time(),
            last_ext_ts=external.get('last_ext_ts'),
            last_int_ts=None,
            trend_state=self._trend_state,
            authority=authority,
        )

        for var, dev in situation.deviation_native.items():
            write_decision_log(uid, f'situation_deviation_{var}',
                               ch_situation_deviation(var), dev)
        mode_code = MODE_CODES.get(
            situation.modes[0] if situation.modes else '', 0)
        write_decision_log(uid, 'situation_mode',
                           CH_SITUATION_MODE, float(mode_code))
        if situation.limiting_factor:
            write_decision_log(uid, 'situation_limiting_factor',
                               CH_SITUATION_LIMIT,
                               float(LIMIT_CODES.get(situation.limiting_factor, 0)))

        # ── P5-3: Passive/Natural 알림 ────────────────────────────────────────
        self._emit_authority_alerts(situation)

        # ── L3: Coordination ──────────────────────────────────────────────────
        commands, new_state = coordinate(
            situation=situation,
            profiles=self._profiles,
            state=self._coord_state,
            unique_id=uid,
            actuator_index=self._actuator_idx,
        )
        self._coord_state = new_state

        # ── P2-4: 복합 액추에이터 그룹 명령 확장 ──────────────────────────────────
        if self._groups:
            commands = expand_group_commands(
                commands, self._groups, new_state.prev_commands)

        # ── D1: 풍향 가중치 (opening 액추에이터 개방량 조정) ──────────────────────
        # vent_openings 가 프로파일 로드 시 캐시된 경우에만 적용.
        # wind_dir 는 외부 환경 컨텍스트에서 읽음 (기상 관측/예보 소스).
        _wind_dir_now = external.get('wind_dir')
        _vos = getattr(self, '_vent_openings', [])
        if _vos and _wind_dir_now is not None:
            from aot.aot_flask.geo.facility_wind import wind_biased_opening
            from aot.functions.utils.env_control.coordinator import ActuatorCommand
            _orient = getattr(self, '_facility_orientation_deg', 0.0)
            _bias   = wind_biased_opening(_vos, float(_wind_dir_now), _orient)
            for _aid, _cmd in list(commands.items()):
                _w = _bias.get(_aid)
                if _w is None:
                    continue
                _prof = (self._profiles[self._actuator_idx[_aid]]
                         if _aid in self._actuator_idx else None)
                if _prof and _prof.kind == 'opening':
                    commands[_aid] = ActuatorCommand(
                        value=round(max(0.0, min(100.0, _cmd.value * _w)), 1),
                        reason=_cmd.reason,
                        var_source=_cmd.var_source,
                    )

        # ── Post-Gate ─────────────────────────────────────────────────────────
        final_cmds, _ = self._post_gate.check(
            {aid: {'value': c.value, 'reason': c.reason}
             for aid, c in commands.items()},
            self._profiles,
            uid,
        )

        # ── Pre-Gate partial overrides ────────────────────────────────────────
        if partial_overrides:
            for aid, override in partial_overrides.items():
                final_cmds[aid] = override

        # ── P1-3: 사이클 메트릭 일괄 기록 ────────────────────────────────────────
        ctx_metrics = {
            'T_int':    internal.get('T',        0.0),
            'RH_int':   internal.get('RH',       0.0),
            'VPD_int':  internal.get('VPD',      0.0),
            'CO2_int':  internal.get('CO2',      0.0),
            'T_ext':    external.get('T_ext',    0.0),
            'RH_ext':   external.get('RH_ext',   0.0),
            'wind':     external.get('wind',     0.0),
            'wind_dir': external.get('wind_dir', 0.0),
            'rain':     external.get('rain',     0.0),
        }
        write_cycle_metrics(
            unique_id=uid,
            ctx=ctx_metrics,
            target=env_target,
            deviation=situation.deviation_native,
            commands=commands,
            limiting_factor=situation.limiting_factor,
            modes=situation.modes,
            facility_id=self.geo_facility_id_device_id or None,
        )

        self._dispatch(final_cmds)

        # ── P5-5: Cumulative Goal Tracker ────────────────────────────────────
        if self.cumulative_tracker_enabled:
            self._update_cumulative_tracker(
                internal=internal,
                cycle_sec=cycle_sec,
                authority=authority,
            )

        # ── P2-5: PI 상태 DB 저장 ────────────────────────────────────────────
        self._last_cycle_ts = time.time()
        self._save_runtime_state()
