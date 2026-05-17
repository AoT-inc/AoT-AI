# coding=utf-8
"""
_helpers_mixin.py — HelpersMixin: small per-cycle helpers.
"""

import json
import time
from datetime import datetime, timezone as _tz

from aot.databases.models import Actions
from aot.functions.utils.env_control import (
    CH_DISPATCH_FAIL,
    write_decision_log,
)
from aot.utils.database import db_retrieve_table_daemon


class HelpersMixin:
    """Mixin: VPD setpoint, time window, end behaviors, sensor collection, gate env, dispatch."""

    # ── Growth Schedule ───────────────────────────────────────────────────────

    def _get_weeks_elapsed(self) -> float:
        """Return fractional weeks elapsed since schedule_start_time + week_offset.

        Wall-clock policy: missed downtime is NOT compensated automatically.
        Use schedule_week_offset (positive = fast-forward) for manual adjustment.

        입력 형식:
          - 날짜만 (YYYY-MM-DD): 시설 시간대 자정 00:00으로 해석.
            시설 시간대 미설정 시 시스템 로컬 시간대 사용.
            (농업인은 UTC 개념을 모르므로 UTC 가정 금지)
          - 날짜+시간 (ISO 8601 with tz): 그대로 사용.
        Returns 0.0 when schedule_start_time is not set.
        """
        start_raw = (self.schedule_start_time or '').strip()
        if not start_raw:
            return 0.0
        try:
            import re as _re
            from dateutil.parser import isoparse

            # 날짜만 입력됐는지 판별: YYYY-MM-DD 패턴 (시간 정보 없음)
            date_only = bool(_re.fullmatch(r'\d{4}-\d{2}-\d{2}', start_raw))

            # 장치 위치 좌표 기반 시간대 결정 (농업인은 UTC 개념 없음)
            fac_tz = self._get_facility_tz()

            if date_only:
                # 날짜만 입력 → 장치 위치 시간대 자정 00:00으로 해석
                if fac_tz is None:
                    self.logger.warning(
                        '_get_weeks_elapsed: 장치 위치 좌표 없음 — '
                        'schedule_start_time 시간대 결정 불가. '
                        '장치에 GPS 위치를 설정하거나 GeoFacility를 연결하세요.')
                    return 0.0
                import datetime as _dt
                year, month, day = map(int, start_raw.split('-'))
                local_midnight = _dt.datetime(year, month, day, 0, 0, 0)
                try:
                    start_dt = fac_tz.localize(local_midnight)
                except AttributeError:
                    start_dt = local_midnight.replace(tzinfo=fac_tz)
            else:
                start_dt = isoparse(start_raw)
                if start_dt.tzinfo is None:
                    # 시간은 있지만 tz 없음 → 장치 위치 시간대로 해석
                    if fac_tz is not None:
                        try:
                            start_dt = fac_tz.localize(start_dt)
                        except AttributeError:
                            start_dt = start_dt.replace(tzinfo=fac_tz)
                    else:
                        self.logger.warning(
                            '_get_weeks_elapsed: 장치 위치 없음, UTC로 fallback')
                        start_dt = start_dt.replace(tzinfo=_tz.utc)

            now_utc = datetime.now(_tz.utc)
            elapsed_sec = (now_utc - start_dt).total_seconds()
            offset = float(self.schedule_week_offset or 0.0)
            return max(0.0, elapsed_sec / (7 * 86400) + offset)
        except Exception as exc:
            self.logger.warning('_get_weeks_elapsed parse error: %s', exc)
            return 0.0

    def _get_facility_tz(self):
        """장치/시설 위치 좌표로부터 시간대를 결정해 pytz 객체를 반환한다.

        initialize() 시점에 결정된 값이 _cached_tz에 있으면 즉시 반환.
        (매 사이클 DB 조회·TimezoneFinder 생성 비용 0)

        우선순위:
          1. 이 Function 자체의 latitude/longitude (CustomController 레코드)
          2. 연결된 GeoFacility → GeoShape 중심점 좌표
          3. GeoFacility.timezone 명시 필드
          4. None (호출자가 처리)

        timezonefinder로 좌표 → IANA 시간대 자동 결정.
        농업인은 UTC를 모르므로 시스템 로컬 시간대 fallback은 사용하지 않는다.
        """
        # 캐시 히트 — initialize() 이후 매 사이클은 여기서 즉시 반환
        cached = getattr(self, '_cached_tz', None)
        if cached is not None:
            return cached

        import pytz

        def _tz_from_coords(lat, lng):
            try:
                from timezonefinder import TimezoneFinder
                tz_name = TimezoneFinder().timezone_at(lat=lat, lng=lng)
                if tz_name:
                    return pytz.timezone(tz_name)
            except Exception:
                pass
            return None

        # ── 1. Function 자체 좌표 ────────────────────────────────────────
        try:
            from aot.databases.models.function import CustomController as CC
            from aot.config import AOT_DB_PATH
            from aot.databases.utils import session_scope
            with session_scope(AOT_DB_PATH) as sess:
                row = sess.query(CC).filter(CC.unique_id == self.unique_id).first()
                if row and row.latitude is not None and row.longitude is not None:
                    tz = _tz_from_coords(row.latitude, row.longitude)
                    if tz:
                        return tz
        except Exception as exc:
            self.logger.debug('_get_facility_tz function-coord error: %s', exc)

        # ── 2 & 3. 연결된 GeoFacility ────────────────────────────────────
        facility_id = getattr(self, 'geo_facility_id_device_id', None) or ''
        if not facility_id:
            return None
        try:
            from aot.databases.models.geo import GeoFacility
            from aot.config import AOT_DB_PATH
            from aot.databases.utils import session_scope
            with session_scope(AOT_DB_PATH) as sess:
                fac = sess.query(GeoFacility).filter(
                    GeoFacility.unique_id == facility_id).first()
                if fac is None:
                    return None
                tz_obj = fac.resolve_timezone()   # GeoShape 좌표 → timezonefinder
                sess.expunge_all()
                return tz_obj
        except Exception as exc:
            self.logger.debug('_get_facility_tz facility error: %s', exc)
            return None

    # ── CO₂ setpoint ─────────────────────────────────────────────────────────

    def _get_co2_setpoint(self):
        """Return current CO₂ target (ppm) from static value or Method curve.

        Returns None when no CO₂ sensor is configured (CO₂ control disabled).
        """
        if not self.sensor_CO2_int:
            return None

        sp_type = self.co2_sp_type or 'static'

        if sp_type == 'static':
            val = self.target_co2
            return float(val) if val and float(val) > 0 else None

        if sp_type == 'method':
            method_id = self.co2_method_id_device_id or ''
            if not method_id:
                return self._co2_last_sp

            if getattr(self, '_co2_loaded_method_id', None) != method_id:
                self._co2_method_handler = None
                self._co2_loaded_method_id = method_id

            if self._co2_method_handler is None:
                try:
                    from aot.utils.method import load_method_handler
                    self._co2_method_handler = load_method_handler(method_id, self.logger)
                except Exception as exc:
                    self.logger.error(
                        'CO₂ method load failed (%s): %s', method_id, exc)
                    return self._co2_last_sp

            try:
                weeks_elapsed = self._get_weeks_elapsed() or None
                facility_tz   = self._get_facility_tz()
                sp_val, ended = self._co2_method_handler.calculate_setpoint(
                    time.time(),
                    weeks_elapsed=weeks_elapsed,
                    facility_tz=facility_tz,
                )
                if ended:
                    sp_val = self._co2_last_sp
                if sp_val is not None:
                    self._co2_last_sp = float(sp_val)
                return self._co2_last_sp
            except Exception as exc:
                self.logger.error('CO₂ method calculate_setpoint error: %s', exc)
                return self._co2_last_sp

        return None

    # ── VPD setpoint ─────────────────────────────────────────────────────────

    def _get_vpd_setpoint(self):
        """Return current VPD target (kPa) from static value or Method curve."""
        sp_type = self.vpd_sp_type or 'static'

        if sp_type == 'static':
            val = self.target_vpd
            return float(val) if val and float(val) > 0 else None

        if sp_type == 'method':
            method_id = self.vpd_method_id_device_id or ''
            if not method_id:
                return self._vpd_last_sp

            # method_id 변경 감지 → 핸들러 리셋
            if getattr(self, '_vpd_loaded_method_id', None) != method_id:
                self._vpd_method_handler = None
                self._vpd_method_start = None
                self._vpd_loaded_method_id = method_id

            if self._vpd_method_handler is None:
                try:
                    from aot.utils.method import load_method_handler, parse_db_time
                    from aot.databases.models import CustomController
                    from aot.utils.time_utils import utc_now
                    from aot.config import AOT_DB_PATH
                    from aot.databases.utils import session_scope

                    self._vpd_method_handler = load_method_handler(method_id, self.logger)

                    # DB 에 저장된 method_start_time 로드 (없으면 지금 시각 저장)
                    with session_scope(AOT_DB_PATH) as sess:
                        ctrl = sess.query(CustomController).filter(
                            CustomController.unique_id == self.unique_id).first()
                        if ctrl is not None:
                            stored = parse_db_time(ctrl.method_start_time)
                            if stored is None:
                                stored = utc_now()
                                ctrl.method_start_time = stored.isoformat()
                                sess.commit()
                            self._vpd_method_start = stored
                            sess.expunge_all()

                    if self._vpd_method_start is None:
                        self._vpd_method_start = utc_now()

                except Exception as exc:
                    self.logger.error(
                        'VPD method load failed (%s): %s', method_id, exc)
                    return self._vpd_last_sp

            try:
                weeks_elapsed = self._get_weeks_elapsed() or None
                facility_tz   = self._get_facility_tz()
                sp_val, ended = self._vpd_method_handler.calculate_setpoint(
                    time.time(),
                    method_start_time=self._vpd_method_start,
                    weeks_elapsed=weeks_elapsed,
                    facility_tz=facility_tz,
                )
                if ended:
                    sp_val = self._vpd_last_sp
                if sp_val is not None:
                    self._vpd_last_sp = float(sp_val)
                return self._vpd_last_sp
            except Exception as exc:
                self.logger.error('VPD method calculate_setpoint error: %s', exc)
                return self._vpd_last_sp

        return None

    # ── Photoperiod / time window ─────────────────────────────────────────────

    @staticmethod
    def _hours_to_hhmm(anchor: str, offset_hours: float) -> str:
        """Shift anchor HH:MM by offset_hours and return result as HH:MM string.

        Example: anchor='12:00', offset=-7.0 → '05:00'
        Wraps within 00:00–23:59 (24h clock).
        """
        try:
            ah, am = (int(x) for x in anchor.split(':'))
        except Exception:
            ah, am = 12, 0
        total_min = ah * 60 + am + int(round(offset_hours * 60))
        total_min = total_min % (24 * 60)
        return f'{total_min // 60:02d}:{total_min % 60:02d}'

    def _get_time_window(self):
        """Return (start_hhmm, end_hhmm) for the active time window.

        When photo_method_id is set, the Method returns photoperiod length (hours)
        and the window is centred on photo_anchor. Falls back to static
        time_start / time_end when no Method is configured.
        """
        method_id = self.photo_method_id_device_id or ''
        if not method_id:
            return self.time_start or '06:00', self.time_end or '20:00'

        if getattr(self, '_photo_loaded_method_id', None) != method_id:
            self._photo_method_handler = None
            self._photo_loaded_method_id = method_id

        if self._photo_method_handler is None:
            try:
                from aot.utils.method import load_method_handler
                self._photo_method_handler = load_method_handler(method_id, self.logger)
            except Exception as exc:
                self.logger.error('Photoperiod method load failed (%s): %s', method_id, exc)
                return self.time_start or '06:00', self.time_end or '20:00'

        try:
            weeks_elapsed = self._get_weeks_elapsed() or None
            facility_tz   = self._get_facility_tz()
            photo_h, _ = self._photo_method_handler.calculate_setpoint(
                time.time(),
                weeks_elapsed=weeks_elapsed,
                facility_tz=facility_tz,
            )
            if photo_h is None or photo_h <= 0:
                return self.time_start or '06:00', self.time_end or '20:00'

            anchor = self.photo_anchor or '12:00'
            start  = self._hours_to_hhmm(anchor, -photo_h / 2.0)
            end    = self._hours_to_hhmm(anchor, +photo_h / 2.0)
            return start, end
        except Exception as exc:
            self.logger.error('Photoperiod method calculate error: %s', exc)
            return self.time_start or '06:00', self.time_end or '20:00'

    def _in_time_window(self) -> bool:
        """Return True if current time is within the active time window."""
        try:
            now   = datetime.now().strftime('%H:%M')
            start, end = self._get_time_window()
            if start <= end:
                return start <= now <= end
            else:
                return now >= start or now <= end   # overnight window
        except Exception:
            return True

    # ── 이메일 알림 헬퍼 ─────────────────────────────────────────────────────

    def _get_email_actions(self):
        """이 Function에 등록된 email 액션 목록을 반환 (캐시 5분)."""
        now = time.time()
        cache_ts  = getattr(self, '_email_actions_ts',  0.0)
        cache_val = getattr(self, '_email_actions_cache', None)
        if cache_val is not None and (now - cache_ts) < 300:
            return cache_val

        try:
            actions = db_retrieve_table_daemon(Actions).filter(
                Actions.function_id == self.unique_id,
                Actions.action_type == 'email',
            ).all()
            self._email_actions_cache = actions
            self._email_actions_ts    = now
            return actions
        except Exception:
            return []

    def _send_critical_email(self, subject_key: str, message: str):
        """심각 이벤트를 이메일로 발송한다 (동일 subject_key 1일 1회 제한).

        subject_key: 중복 억제 키 (예: 'wind_gate', 'rain_gate', 'extreme_heat')
        message:     본문
        """
        now = time.time()
        if not hasattr(self, '_email_sent_ts'):
            self._email_sent_ts: dict = {}   # {subject_key: last_sent_ts}

        # 동일 메시지 1일 1회 제한
        last = self._email_sent_ts.get(subject_key, 0.0)
        if (now - last) < 86400:
            return

        email_actions = self._get_email_actions()
        if not email_actions:
            return

        try:
            from aot.utils.actions import parse_action_information, trigger_action
            dict_actions = parse_action_information()
            for action in email_actions:
                trigger_action(
                    dict_actions,
                    action.unique_id,
                    value={'message': message},
                )
            self._email_sent_ts[subject_key] = now
            self.logger.info(
                'EnvCoordinator: 심각 알림 이메일 발송 [%s]', subject_key)
        except Exception as exc:
            self.logger.error(
                'EnvCoordinator: 이메일 발송 실패 [%s] — %s', subject_key, exc)

    # ── P5-3: Authority 알림 + Unattainable 감지 ─────────────────────────────

    def _emit_authority_alerts(self, situation):
        """상태 전환·쿨다운 기반 알림 — 반복 알림 최소화.

        설계 원칙:
          1. 상태 전환(OK→문제) 시에만 알림. 같은 상태 지속 = 알림 없음.
          2. 조치 불가 상황(NATURAL + gradient 없음)은 24h 쿨다운.
             어차피 할 수 있는 것이 없으므로 반복 알림은 피로감만 누적.
          3. 조치 가능 상황(ACTIVE/PASSIVE 액추에이터 있음)은 1h 쿨다운.
          4. 상태가 해소되면 카운터·쿨다운 초기화 → 다음 발생 시 다시 알림.
        """
        from aot.functions.utils.env_control.authority import (
            detect_unattainable, LEVEL_ACTIVE, LEVEL_PASSIVE, LEVEL_NATURAL,
        )
        from aot.functions.utils.env_control.types import (
            MODE_NATURAL, MODE_DEGRADED,
        )

        now_ts = time.time()
        modes  = situation.modes
        auth   = situation.authority

        # ── 알림 쿨다운 상태 초기화 ──────────────────────────────────────────
        if not hasattr(self, '_alert_last_ts'):
            self._alert_last_ts: dict = {}    # {key: timestamp}
        if not hasattr(self, '_alert_state'):
            self._alert_state: dict = {}      # {key: bool} — 현재 알림 상태

        def _should_alert(key: str, cooldown_h: float) -> bool:
            """쿨다운 내에 있거나 이미 알린 상태면 False."""
            last = self._alert_last_ts.get(key, 0.0)
            return (now_ts - last) >= cooldown_h * 3600

        def _mark_alerted(key: str):
            self._alert_last_ts[key] = now_ts
            self._alert_state[key]   = True

        def _clear_alert(key: str):
            """조건 해소 시 상태 초기화 — 다음 발생 시 즉시 알림."""
            self._alert_state.pop(key, None)
            self._alert_last_ts.pop(key, None)

        # ── 1. NATURAL/DEGRADED 모드 전환 알림 ───────────────────────────────
        # 전환 순간만 알림. 이후 같은 모드 지속은 침묵.
        prev_modes = getattr(self, '_last_situation_modes', [])

        if MODE_NATURAL in modes and MODE_NATURAL not in prev_modes:
            self.logger.warning(
                'EnvCoordinator: 능동 액추에이터 없음 — 제어 불가, 외기 추적 전용')

        elif MODE_DEGRADED in modes and MODE_DEGRADED not in prev_modes:
            nat_vars = [k for k, v in auth.items() if v == LEVEL_NATURAL]
            self.logger.warning(
                'EnvCoordinator: %s 제어 불가 (액추에이터 없음) — 나머지 변수만 제어',
                ', '.join(nat_vars))

        elif MODE_NATURAL not in modes and MODE_NATURAL in prev_modes:
            # 해소: NATURAL → 정상
            self.logger.info('EnvCoordinator: 제어 가능 상태 복귀')

        self._last_situation_modes = list(modes)

        # ── 2. Unattainable 감지 + 스마트 알림 ───────────────────────────────
        unattainable = detect_unattainable(
            env_target=situation.target,
            deviation_native=situation.deviation_native,
            authority=auth,
            unattainable_state=self._unattainable_state,
            threshold_cycles=10,
        )

        # 이번 사이클에 unattainable이 아닌 변수 → 카운터·알림 해소
        for var in list(self._alert_state.keys()):
            if var.startswith('unat_') and var[5:] not in (unattainable or []):
                _clear_alert(var)

        if unattainable:
            for var in unattainable:
                key = f'unat_{var}'
                tv  = situation.target.get(var)
                dev = situation.deviation_native.get(var, 0.0)

                # 조치 가능 여부에 따라 쿨다운 결정
                var_auth = auth.get(var, LEVEL_NATURAL)
                if var_auth == LEVEL_NATURAL:
                    # 장치 없음 → 24h 쿨다운 (반복 알림 차단)
                    cooldown_h = 24.0
                    actionable = False
                else:
                    # ACTIVE/PASSIVE 장치 있는데도 도달 불가 → 1h 쿨다운
                    cooldown_h = 1.0
                    actionable = True

                if not _should_alert(key, cooldown_h):
                    continue   # 쿨다운 중 — 침묵

                if actionable:
                    self.logger.warning(
                        'EnvCoordinator: [조치필요] %s 목표 %.1f 도달 불가 '
                        '(편차 %.1f, 10사이클 이상). 액추에이터 점검 필요.',
                        var, tv.value if tv else 0.0, dev)
                    target_val = tv.value if tv else 0.0
                    current_val = target_val + dev
                    self._send_critical_email(
                        key,
                        f'[환경 제어 경보] {var} 목표값({target_val:.1f})에 '
                        f'10사이클 이상 도달 불가 (현재 {current_val:.1f}, 편차 {dev:+.1f}). '
                        f'해당 액추에이터를 점검하세요.',
                    )
                else:
                    # 장치 없는 경우: 일 1회만, 조용한 info 레벨
                    self.logger.info(
                        'EnvCoordinator: %s 제어 장치 없음 — 현재 %.1f (목표 %.1f). '
                        '내일 이 메시지가 반복되면 장치 추가를 검토하세요.',
                        var, (tv.value if tv else 0.0) + dev, tv.value if tv else 0.0)

                _mark_alerted(key)

    # ── P5-5: Cumulative Goal Tracker ─────────────────────────────────────────

    def _update_cumulative_tracker(self, internal: dict, cycle_sec: float,
                                   authority: dict):
        """DLI·GDD를 적산하고 일 마감 시 DB 저장 + 보상 제안을 생성한다."""
        from aot.functions.utils.env_control.cumulative_tracker import (
            DailyAccumulator, accumulate_cycle, generate_suggestions, save_daily_state,
        )
        from aot.functions.utils.env_control.photosynthesis import get_crop_params

        # 초기화 (lazy)
        if self._daily_acc is None:
            self._daily_acc = DailyAccumulator()

        crop = get_crop_params(self.crop_preset)
        T_base = crop.T_base

        rolled = accumulate_cycle(
            acc=self._daily_acc,
            light_ppfd=internal.get('light'),
            T_mean=internal.get('T', 20.0),
            VPD=internal.get('VPD', 0.5),
            CO2=internal.get('CO2', 400.0),
            cycle_sec=cycle_sec,
            T_base=T_base,
        )

        # 일 마감 처리
        if rolled:
            dli_t   = float(self.dli_target or 0.0) or None
            gdd_t   = float(self.gdd_target_daily or 0.0) or None
            suggestions = generate_suggestions(
                debt_dli  = (dli_t - self._daily_acc.dli) if dli_t else 0.0,
                debt_gdd  = (gdd_t - self._daily_acc.gdd) if gdd_t else 0.0,
                authority = authority,
                dli_target=dli_t,
                gdd_target=gdd_t,
            )
            save_daily_state(
                function_id=self.unique_id,
                acc=self._daily_acc,
                dli_target=dli_t,
                gdd_target=gdd_t,
                suggestions=suggestions,
            )
            for s in suggestions:
                self.logger.warning('CumulativeTracker: %s', s.message)

            # 새 날 초기화
            self._daily_acc = DailyAccumulator()

        # 주기적 중간 저장 (1시간마다)
        elif (int(time.time()) % 3600) < int(cycle_sec):
            dli_t = float(self.dli_target or 0.0) or None
            gdd_t = float(self.gdd_target_daily or 0.0) or None
            save_daily_state(
                function_id=self.unique_id,
                acc=self._daily_acc,
                dli_target=dli_t,
                gdd_target=gdd_t,
                suggestions=[],
            )

    def _apply_end_behaviors(self):
        """Send end-of-window commands to each actuator based on its end_behavior setting."""
        actions = db_retrieve_table_daemon(Actions).filter(
            Actions.function_id == self.unique_id,
            Actions.action_type == 'env_actuator',
        ).all()

        for action in actions:
            try:
                opts = json.loads(action.custom_options or '{}')
            except Exception:
                continue

            output_val = opts.get('output', '')
            if not output_val:
                continue
            parts      = str(output_val).split(',')
            device_id  = parts[0].strip()
            channel_id = parts[1].strip() if len(parts) > 1 else None
            ch_obj = 0
            if channel_id:
                try:
                    ch_obj = self.get_output_channel_from_channel_id(channel_id)
                except Exception:
                    pass

            behavior = opts.get('end_behavior', 'nothing')
            if behavior == 'off':
                self.control.output_off(device_id, output_channel=ch_obj)
            elif behavior == 'on':
                self.control.output_on(device_id, output_channel=ch_obj)
            elif behavior == 'open_pct':
                pct = float(opts.get('end_open_pct', 0.0) or 0.0)
                self.control.output_on(device_id, output_type='value',
                                       amount=pct, output_channel=ch_obj)

    def _collect_internal(self, max_age: float) -> dict:
        result = {}

        def _fetch(selector, key):
            if not selector:
                return
            try:
                dev_id, meas_id = str(selector).split(',')[:2]
                val = self.get_last_measurement(dev_id, meas_id, max_age=max_age)
                if val is not None:
                    result[key] = float(val)
            except Exception:
                pass

        _fetch(self.sensor_T_int,    'T')
        _fetch(self.sensor_RH_int,   'RH')
        _fetch(self.sensor_CO2_int,  'CO2')
        _fetch(self.sensor_vpd,      'VPD')
        _fetch(self.sensor_light,    'light')
        _fetch(self.sensor_wind,     'wind')
        _fetch(self.sensor_wind_dir, 'wind_dir')

        # D2: 시설 공간 센서 보완 (sensors_resolved 캐시 활용)
        # 주 센서(sensor_T_int/sensor_RH_int) 미설정 시 위치 가중 공간 평균을 대리값으로 사용.
        # 주 센서가 설정된 경우 spatial 은 핫스팟 감지에만 사용.
        _sr = getattr(self, '_sensors_resolved', [])
        if _sr:
            try:
                from aot.aot_flask.geo.facility_sensors import compute_spatial_internal
                spatial = compute_spatial_internal(_sr, max_age=int(max_age))
                if spatial.get('T') is not None and 'T' not in result:
                    result['T'] = spatial['T']
                if spatial.get('RH') is not None and 'RH' not in result:
                    result['RH'] = spatial['RH']
                # 핫스팟 플래그 — coordinator 및 게이트가 읽을 수 있도록 보존
                if spatial.get('hotspot_T'):
                    result['_spatial_hotspot_T']  = True
                if spatial.get('hotspot_RH'):
                    result['_spatial_hotspot_RH'] = True
            except Exception as _se:
                self.logger.debug('D2 spatial collect failed: %s', _se)

        return result

    def _build_gate_env(self, internal: dict, external: dict) -> dict:
        wind_val     = internal.get('wind',     external.get('wind',     0.0))
        wind_dir_val = internal.get('wind_dir', external.get('wind_dir', None))
        return {
            'internal': {
                'T':  internal.get('T',  25.0),
                'RH': internal.get('RH', 60.0),
            },
            'external': {
                'T':        external.get('T_ext', 20.0),
                'RH':       external.get('RH_ext', 60.0),
                'wind':     wind_val,
                'wind_dir': wind_dir_val,
                'rain':     external.get('rain', 0.0),
            },
            'now_ts':      time.time(),
            'last_ext_ts': external.get('last_ext_ts', time.time()),
            'last_int_ts': time.time(),
        }

    def _dispatch(self, commands: dict) -> set:
        """Dispatch commands. Returns set of actuator_ids that FAILED.

        P0 강화 (2026-05-16): 실패 액추에이터 집합을 반환하여 호출자가
        prev_commands 업데이트에서 제외하거나 다음 사이클에서 재시도 가능.
        실패 1회는 WARNING, 누적 카운트는 decision_log (CH_DISPATCH_FAIL).
        """
        failed: set = set()
        for actuator_id, cmd in commands.items():
            val = (cmd.get('value', 0.0) if isinstance(cmd, dict)
                   else getattr(cmd, 'value', 0.0))
            ch = self._channel_map.get(actuator_id, 0)
            try:
                if val and val > 0.0:
                    self.control.output_on(
                        actuator_id,
                        output_type='value',
                        amount=val,
                        output_channel=ch,
                    )
                else:
                    self.control.output_off(actuator_id, output_channel=ch)
            except Exception as exc:
                failed.add(actuator_id)
                self.logger.warning(
                    'EnvCoordinator: dispatch 실패 actuator=%s val=%s ch=%s err=%s',
                    actuator_id, val, ch, exc)

        if failed:
            try:
                write_decision_log(
                    self.unique_id, 'dispatch_fail_count',
                    CH_DISPATCH_FAIL, float(len(failed)))
            except Exception:
                pass
        return failed
