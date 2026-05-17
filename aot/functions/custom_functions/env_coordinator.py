# coding=utf-8
"""
env_coordinator.py — Integrated Facility Environment Control Function (L1+L2+L3).

Goal: photosynthesis optimisation.
Primary control: VPD → decomposes to T/RH adjustments.
Secondary: Light (shade / supplemental), CO₂.
Constraints: Temperature and Humidity min/max bounds (prevent VPD bypass).
Safety gates: Wind, Time window.

Actuators are registered via Actions (add env_actuator actions as needed).
On each initialisation / reload the Function queries the Actions table and
builds ActuatorProfiles.

Reference: docs/dev/integrated_env_control_design.md §8, §11, §12, §13
"""

import time

from aot.aot_client import DaemonControl
from aot.databases.models import CustomController
from aot.functions.base_function import AbstractFunction
from aot.utils.database import db_retrieve_table_daemon

from aot.functions.utils.env_control.coordinator import CoordinatorState
from aot.functions.utils.env_control.ext_context_fallback import ExtContextCache
from aot.functions.utils.env_control.safety_gates import (
    PreGateConfig, SafetyPreGate, SafetyPostGate,
)
from aot.functions.utils.env_control.situation import TrendState

from aot.functions.custom_functions.env_coordinator_impl._function_info import (
    FUNCTION_INFORMATION,
)
from aot.functions.custom_functions.env_coordinator_impl._profile_loader_mixin import (
    ProfileLoaderMixin,
)
from aot.functions.custom_functions.env_coordinator_impl._runtime_state_mixin import (
    RuntimeStateMixin,
)
from aot.functions.custom_functions.env_coordinator_impl._helpers_mixin import (
    HelpersMixin,
)
from aot.functions.custom_functions.env_coordinator_impl._cycle_mixin import (
    CycleMixin,
)


# ─────────────────────────────────────────────────────────────────────────────
class CustomModule(
    AbstractFunction,
    ProfileLoaderMixin,
    RuntimeStateMixin,
    CycleMixin,
    HelpersMixin,
):
    """Integrated facility environment control — L1+L2+L3 single Function."""

    def __init__(self, function, testing=False):
        super().__init__(function, testing=testing, name=__name__)

        self.control = DaemonControl()
        self.timer_loop: float = 0.0

        # Basic
        self.update_period  = None
        self.sensor_max_age = None

        # Growth Schedule
        self.schedule_start_time   = None
        self.schedule_week_offset  = None

        # Facility link (optional)
        self.geo_facility_id           = None
        self.geo_facility_id_device_id = None

        # Time Control
        self.time_enable = None
        self.time_start  = None
        self.time_end    = None

        # Photoperiod Method
        self.photo_method_id_device_id = None
        self.photo_anchor              = None
        self._photo_method_handler     = None
        self._photo_loaded_method_id   = None

        # VPD
        self.sensor_vpd              = None
        self.vpd_sp_type             = None
        self.target_vpd              = None
        self.vpd_method_id_device_id = None
        self.priority_vpd            = None
        self.tolerance_vpd           = None

        # Light
        self.sensor_light = None
        self.light_max    = None
        self.light_min    = None

        # CO₂
        self.sensor_CO2_int          = None
        self.co2_sp_type             = None
        self.target_co2              = None
        self.co2_method_id_device_id = None
        self.priority_co2            = None
        self.tolerance_co2           = None

        # CO₂ Method runtime state
        self._co2_method_handler    = None
        self._co2_last_sp: float    = None
        self._co2_loaded_method_id  = None

        # Temperature (constraints)
        self.sensor_T_int = None
        self.temp_max     = None
        self.temp_min     = None

        # Humidity (constraints)
        self.sensor_RH_int = None
        self.humid_max     = None
        self.humid_min     = None

        # Photosynthesis Model
        self.photosynth_mode_enabled = None
        self.crop_preset             = None
        self._priority_ewa_state: dict = {}   # P5-4: {var: ewa_priority}

        # Cumulative Goal Tracker (P5-5)
        self.cumulative_tracker_enabled = None
        self.dli_target                 = None
        self.gdd_target_daily           = None
        self._daily_acc                 = None  # DailyAccumulator (lazy init)

        # VPD Decomposition
        self.vpd_weight_T = None

        # Guide Ranges (T / RH)
        self.guide_T_min  = None
        self.guide_T_max  = None
        self.guide_RH_min = None
        self.guide_RH_max = None

        # Wind
        self.sensor_wind         = None
        self.sensor_wind_dir     = None
        self.gate_wind_threshold = None

        # Forecast Feedforward (P3-4)
        self.forecast_feedforward_enabled = None
        self.forecast_lookahead_h         = None
        self._last_ff_signal              = None   # FeedforwardSignal (last cycle)

        # Internal state
        self._vpd_method_handler = None
        self._vpd_method_start   = None
        self._vpd_last_sp        = None

        self._coord_state  = CoordinatorState()
        self._trend_state  = TrendState()
        self._profiles     = []
        self._unattainable_state: dict = {}   # P5-3: {var: 연속 초과 사이클 수}
        self._groups: list = []
        self._channel_map  = {}
        self._actuator_idx = {}
        self._pre_gate: SafetyPreGate   = None
        self._post_gate: SafetyPostGate = SafetyPostGate()
        self._last_cycle_ts: float      = 0.0
        self._ext_cache = ExtContextCache()
        self._cached_tz = None   # initialize()에서 1회 결정, 이후 재사용

        if not testing:
            custom_function = db_retrieve_table_daemon(
                CustomController, unique_id=self.unique_id)
            self.setup_custom_options(
                FUNCTION_INFORMATION['custom_options'], custom_function)
            self.try_initialize()

    # ─────────────────────────────────────────────────────────────────────────
    def initialize(self):
        cfg = PreGateConfig(
            wind_threshold=self.gate_wind_threshold or 12.0,
            rain_threshold=0.5,
            heat_ext_threshold=45.0,
            cold_ext_threshold=-5.0,
        )
        self._pre_gate = SafetyPreGate(cfg)
        self._reload_profiles()
        self._load_runtime_state()

        # 시간대: 장치 위치 좌표 기반으로 1회 결정 후 캐시
        self._cached_tz = self._get_facility_tz()
        if self._cached_tz:
            self.logger.info('EnvCoordinator timezone: %s', self._cached_tz)
        else:
            self.logger.warning(
                'EnvCoordinator: 장치 위치 좌표 없음 — '
                'Growth Schedule 날짜 입력 시 시간대를 결정할 수 없습니다. '
                '장치에 GPS 위치를 설정하거나 GeoFacility를 연결하세요.')

        self.logger.info(
            'EnvCoordinator initialised — %d actuator(s), period=%.0fs',
            len(self._profiles), self.update_period or 60)

    # ─────────────────────────────────────────────────────────────────────────
    def stop_function(self):
        """비활성화 시 각 액추에이터를 end_behavior 설정에 따라 복귀시킨다.

        FunctionController.run_finally() → stop_function() 순서로 호출된다.
        output_off() 는 Pyro5 RPC → Output 컨트롤러(독립 스레드)에 즉시 전달된다.
        """
        self._apply_end_behaviors()
        super().stop_function()

    # ─────────────────────────────────────────────────────────────────────────
    def cmd_reload(self, args_dict):
        self._reload_profiles()
        return f'Reloaded — {len(self._profiles)} actuator(s)'

    def cmd_run_now(self, args_dict):
        self.timer_loop = 0.0

    def cmd_emergency_stop(self, args_dict):
        """긴급정지: 모든 액추에이터 즉시 output_off + 다음 사이클 60s 지연.

        call_module_function() → threading.Thread 로 실행되므로
        현재 돌아가는 loop()와 무관하게 즉시 Output 컨트롤러에 전달된다.
        """
        failed = 0
        for p in self._profiles:
            ch = self._channel_map.get(p.actuator_id, 0)
            try:
                self.control.output_off(p.actuator_id, output_channel=ch)
            except Exception as exc:
                failed += 1
                self.logger.error(
                    'EnvCoordinator emergency_stop: %s off 실패 — %s',
                    p.actuator_id, exc)

        self.timer_loop = time.time() + 60.0
        msg = (f'Emergency stop: {len(self._profiles)}개 output_off 전달 '
               f'(실패 {failed}), 다음 사이클 60s 지연')
        self.logger.warning(msg)
        return msg

    # ─────────────────────────────────────────────────────────────────────────
    def loop(self):
        now = time.time()
        if now < self.timer_loop:
            return
        period = self.update_period or 60.0
        self.timer_loop = now + period

        # Watchdog: 마지막 사이클로부터 3×period 이상 경과 시 경고
        if self._last_cycle_ts > 0 and (now - self._last_cycle_ts) > period * 3:
            gap = now - self._last_cycle_ts
            self.logger.warning(
                'EnvCoordinator watchdog: %.0fs 동안 사이클 미실행 (기대 %.0fs)',
                gap, period)
            # 24h 이상 중단 시 Growth Schedule 영향 알림
            if gap > 86400:
                gap_h = gap / 3600
                self.logger.warning(
                    'EnvCoordinator: %.1fh 중단 감지 — 식물은 계속 성장했습니다. '
                    'schedule_week_offset 으로 성장 주수를 보정하세요.',
                    gap_h)

        try:
            self._run_cycle(period)
        except Exception:
            self.logger.exception('EnvCoordinator cycle error')
