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

import json
import time
from datetime import datetime

from flask_babel import lazy_gettext

from aot.aot_client import DaemonControl
from aot.databases.models import Actions, CustomController, GeoFacility, GeoShape, Output
from aot.functions.base_function import AbstractFunction
from aot.utils.constraints_pass import constraints_pass_positive_value
from aot.utils.database import db_retrieve_table_daemon

from aot.functions.utils.env_control.coordinator import CoordinatorState, coordinate
from aot.functions.utils.env_control.effect_functions import build_effect_model
from aot.functions.utils.env_control.goal import build_env_target
from aot.functions.utils.env_control.log_channels import (
    CH_SAFETY_GATE, CH_SITUATION_LIMIT, CH_SITUATION_MODE,
    LIMIT_CODES, MODE_CODES,
    ch_goal_priority, ch_goal_target, ch_situation_deviation,
    write_decision_log,
)
from aot.functions.utils.env_control.safety_gates import (
    PreGateConfig, SafetyPreGate, SafetyPostGate,
)
from aot.functions.utils.env_control.situation import TrendState, assess
from aot.functions.utils.env_control.types import (
    ActuatorProfile, CmdConstraints, ManualLockState,
)

_KIND_CAPABILITIES = {
    'opening':      ['ventilation', 'cooling_passive', 'co2_dilution'],
    'cooler':       ['cooling'],
    'heater':       ['heating'],
    'fogger':       ['humidify', 'cooling_passive'],
    'co2_injector': ['co2_enrich'],
    'shade':        ['shading', 'cooling_passive'],
    'curtain':      ['insulation'],
    'lighting':     ['light_enrich'],
}

# GeoFacility.actuators 슬롯 → ActuatorProfile.kind 매핑.
# fans (circulation/exhaust)는 현재 ACTUATOR_KINDS에 없어 facility 자동 등록에서 제외.
# (수동 env_actuator action으로 보강 가능)
_FACILITY_SLOT_KIND = {
    'outer_side_vent_motor': 'opening',
    'outer_roof_vent_motor': 'opening',
    'inner_side_vent_motor': 'opening',
    'inner_roof_vent_motor': 'opening',
    'thermal_curtain':       'curtain',
    'shade_curtain':         'shade',
    # 'circulation_fan', 'exhaust_fan' — 별도 처리 필요 (현 단계 제외)
}

# ─────────────────────────────────────────────────────────────────────────────
FUNCTION_INFORMATION = {
    'function_name_unique': 'env_coordinator',
    'function_name': lazy_gettext('Integrated Environment Control'),
    'function_name_short': 'Env Coordinator',

    'message': lazy_gettext(
        'Coordinates registered Output actuators to optimise photosynthesis. '
        'VPD is the primary control target; temperature and humidity act as '
        'safety constraints. Add "Environment Control: Register Actuator" actions '
        'to register devices. Requires ext_context_collector to be running.'
    ),

    'options_enabled': ['custom_options', 'enable_actions'],
    'options_disabled': ['measurements_select', 'measurements_configure'],

    'custom_commands_message': lazy_gettext(
        'Trigger an immediate cycle or reload the actuator list.'
    ),
    'custom_commands': [
        {
            'id': 'cmd_reload',
            'type': 'button',
            'wait_for_return': True,
            'name': lazy_gettext('Reload Actuators'),
            'phrase': lazy_gettext(
                'Re-read the Actions table and rebuild actuator profiles.'
            ),
        },
        {
            'id': 'cmd_run_now',
            'type': 'button',
            'wait_for_return': False,
            'name': lazy_gettext('Run Now'),
            'phrase': lazy_gettext(
                'Execute one coordination cycle immediately using current sensor readings.'
            ),
        },
    ],

    'custom_options': [

        # ── Basic ─────────────────────────────────────────────────────────────
        {
            'type': 'header',
            'name': lazy_gettext('Basic'),
        },
        {
            'id': 'update_period',
            'type': 'float',
            'default_value': 60.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Period (seconds)'),
            'phrase': lazy_gettext(
                'Coordination cycle interval. Recommended: slowest actuator response time × 1.5.'
            ),
        },
        {
            'id': 'sensor_max_age',
            'type': 'float',
            'default_value': 120.0,
            'required': False,
            'name': lazy_gettext('Max Sensor Age (seconds)'),
            'phrase': lazy_gettext(
                'Reject sensor readings older than this value. 0 = no limit.'
            ),
        },

        # ── Facility (optional) ──────────────────────────────────────────────
        {
            'type': 'header',
            'name': lazy_gettext('Facility (optional)'),
        },
        {
            'id': 'geo_facility_id',
            'type': 'select_device',
            'default_value': '',
            'required': False,
            'options_select': ['GeoFacility'],
            'name': lazy_gettext('Linked Facility'),
            'phrase': lazy_gettext(
                'When set, actuators are auto-discovered from this facility (envelope, '
                'side/roof vents, curtains, fans). GIS metadata (azimuth, area, U-value) '
                'is attached to each actuator profile so wind direction and facility '
                'geometry can be considered. Manual "Environment Control" actions below '
                'still apply and are merged with the facility-derived list. '
                'Leave empty to use manual actions only.'
            ),
        },

        # ── Time Control ──────────────────────────────────────────────────────
        {
            'type': 'header',
            'name': lazy_gettext('Time Control'),
        },
        {
            'id': 'time_enable',
            'type': 'bool',
            'default_value': False,
            'required': False,
            'name': lazy_gettext('Enable Time Window'),
            'phrase': lazy_gettext(
                'When enabled, control only runs between Start and End times.'
            ),
        },
        {
            'id': 'time_start',
            'type': 'text',
            'default_value': '06:00',
            'required': False,
            'name': lazy_gettext('Start Time (HH:MM)'),
            'phrase': '',
        },
        {
            'id': 'time_end',
            'type': 'text',
            'default_value': '20:00',
            'required': False,
            'name': lazy_gettext('End Time (HH:MM)'),
            'phrase': lazy_gettext(
                'On-end behavior per actuator is configured in each Action.'
            ),
        },

        # ── VPD (Primary control target) ──────────────────────────────────────
        {
            'type': 'header',
            'name': lazy_gettext('VPD'),
        },
        {
            'id': 'sensor_vpd',
            'type': 'select_measurement',
            'default_value': '',
            'required': False,
            'options_select': ['Input', 'Function'],
            'name': lazy_gettext('VPD Sensor'),
            'phrase': lazy_gettext(
                'Direct VPD measurement. If empty, VPD is computed from T/RH sensors.'
            ),
        },
        {
            'id': 'vpd_sp_type',
            'type': 'select',
            'default_value': 'static',
            'required': False,
            'options_select': [
                ('static', lazy_gettext('Static Target')),
                ('method', lazy_gettext('Method (time-varying)')),
            ],
            'name': lazy_gettext('Setpoint Type'),
            'phrase': lazy_gettext(
                'Static: use the fixed target value below. '
                'Method: follow an AoT Method curve.'
            ),
        },
        {
            'id': 'target_vpd',
            'type': 'float',
            'default_value': 0.8,
            'required': False,
            'name': lazy_gettext('Target VPD (kPa)'),
            'phrase': lazy_gettext('Used when Setpoint Type = Static. 0 = disable VPD control.'),
        },
        {
            'id': 'vpd_method_id',
            'type': 'select_device',
            'default_value': '',
            'required': False,
            'options_select': ['Method'],
            'name': lazy_gettext('Method'),
            'phrase': lazy_gettext(
                'Used when Setpoint Type = Method. '
                'Select an AoT Method that returns a VPD setpoint (kPa).'
            ),
        },
        {
            'id': 'priority_vpd',
            'type': 'float',
            'default_value': 1.2,
            'required': False,
            'name': lazy_gettext('VPD Priority'),
            'phrase': lazy_gettext('Higher value = processed first. Default 1.2.'),
        },
        {
            'id': 'tolerance_vpd',
            'type': 'float',
            'default_value': 0.1,
            'required': False,
            'name': lazy_gettext('VPD Tolerance (kPa)'),
            'phrase': '',
        },

        # ── Light ─────────────────────────────────────────────────────────────
        {
            'type': 'header',
            'name': lazy_gettext('Light'),
        },
        {
            'id': 'sensor_light',
            'type': 'select_measurement',
            'default_value': '',
            'required': False,
            'options_select': ['Input'],
            'name': lazy_gettext('Light / Solar Sensor'),
            'phrase': lazy_gettext(
                'Solar irradiance (W/m²) or PPFD (µmol/m²/s). '
                'Used for shade activation and photosynthesis limit assessment.'
            ),
        },
        {
            'id': 'light_max',
            'type': 'float',
            'default_value': 800.0,
            'required': False,
            'name': lazy_gettext('Max Light Threshold'),
            'phrase': lazy_gettext(
                'Activate shade screen when light exceeds this value. 0 = disabled.'
            ),
        },
        {
            'id': 'light_min',
            'type': 'float',
            'default_value': 0.0,
            'required': False,
            'name': lazy_gettext('Min Light Threshold (Supplemental)'),
            'phrase': lazy_gettext(
                'Activate supplemental lighting when light falls below this value. '
                '0 = disabled (most facilities — natural light only).'
            ),
        },

        # ── CO₂ ───────────────────────────────────────────────────────────────
        {
            'type': 'header',
            'name': lazy_gettext('CO₂'),
        },
        {
            'id': 'sensor_CO2_int',
            'type': 'select_measurement',
            'default_value': '',
            'required': False,
            'options_select': ['Input', 'Function'],
            'name': lazy_gettext('CO₂ Sensor'),
            'phrase': lazy_gettext('Leave empty to disable CO₂ control.'),
        },
        {
            'id': 'target_co2',
            'type': 'float',
            'default_value': 1000.0,
            'required': False,
            'name': lazy_gettext('Target CO₂ (ppm)'),
            'phrase': '',
        },
        {
            'id': 'priority_co2',
            'type': 'float',
            'default_value': 0.8,
            'required': False,
            'name': lazy_gettext('CO₂ Priority'),
            'phrase': '',
        },
        {
            'id': 'tolerance_co2',
            'type': 'float',
            'default_value': 100.0,
            'required': False,
            'name': lazy_gettext('CO₂ Tolerance (ppm)'),
            'phrase': '',
        },

        # ── Temperature (Constraints — not a primary target) ──────────────────
        {
            'type': 'header',
            'name': lazy_gettext('Temperature'),
        },
        {
            'id': 'sensor_T_int',
            'type': 'select_measurement',
            'default_value': '',
            'required': True,
            'options_select': ['Input', 'Function'],
            'name': lazy_gettext('Temperature Sensor'),
            'phrase': lazy_gettext(
                'Required for VPD computation when no direct VPD sensor is available.'
            ),
        },
        {
            'id': 'temp_max',
            'type': 'float',
            'default_value': 35.0,
            'required': False,
            'name': lazy_gettext('Max Temperature (°C)'),
            'phrase': lazy_gettext(
                'Hard upper limit. Forces cooling when exceeded, regardless of VPD target.'
            ),
        },
        {
            'id': 'temp_min',
            'type': 'float',
            'default_value': 5.0,
            'required': False,
            'name': lazy_gettext('Min Temperature (°C)'),
            'phrase': lazy_gettext(
                'Hard lower limit. Forces heating when below, regardless of VPD target.'
            ),
        },

        # ── Humidity (Constraints — not a primary target) ─────────────────────
        {
            'type': 'header',
            'name': lazy_gettext('Humidity'),
        },
        {
            'id': 'sensor_RH_int',
            'type': 'select_measurement',
            'default_value': '',
            'required': True,
            'options_select': ['Input', 'Function'],
            'name': lazy_gettext('Humidity Sensor'),
            'phrase': lazy_gettext(
                'Required for VPD computation when no direct VPD sensor is available.'
            ),
        },
        {
            'id': 'humid_max',
            'type': 'float',
            'default_value': 90.0,
            'required': False,
            'name': lazy_gettext('Max Humidity (%)'),
            'phrase': lazy_gettext(
                'Hard upper limit. Prevents VPD bypass via extreme humidity.'
            ),
        },
        {
            'id': 'humid_min',
            'type': 'float',
            'default_value': 30.0,
            'required': False,
            'name': lazy_gettext('Min Humidity (%)'),
            'phrase': lazy_gettext(
                'Hard lower limit. Prevents VPD bypass via extreme dryness.'
            ),
        },

        # ── Wind ──────────────────────────────────────────────────────────────
        {
            'type': 'header',
            'name': lazy_gettext('Wind'),
        },
        {
            'id': 'sensor_wind',
            'type': 'select_measurement',
            'default_value': '',
            'required': False,
            'options_select': ['Input'],
            'name': lazy_gettext('Wind Speed Sensor'),
            'phrase': lazy_gettext(
                'If empty, wind data from ext_context_collector is used.'
            ),
        },
        {
            'id': 'sensor_wind_dir',
            'type': 'select_measurement',
            'default_value': '',
            'required': False,
            'options_select': ['Input'],
            'name': lazy_gettext('Wind Direction Sensor (0-360°, bearing)'),
            'phrase': lazy_gettext(
                'Wind direction in degrees (0=N, 90=E, 180=S, 270=W). '
                'Combined with each opening\'s GIS-derived azimuth from facility geometry, '
                'used to choose leeward (downwind) openings and close windward (upwind) ones. '
                'If empty, wind direction from ext_context_collector is used.'
            ),
        },
        {
            'id': 'gate_wind_threshold',
            'type': 'float',
            'default_value': 12.0,
            'required': False,
            'name': lazy_gettext('Strong Wind Threshold (m/s)'),
            'phrase': lazy_gettext(
                'Openings (vents, side walls) are forced closed above this wind speed.'
            ),
        },
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
class CustomModule(AbstractFunction):
    """Integrated facility environment control — L1+L2+L3 single Function."""

    def __init__(self, function, testing=False):
        super().__init__(function, testing=testing, name=__name__)

        self.control = DaemonControl()
        self.timer_loop: float = 0.0

        # Basic
        self.update_period  = None
        self.sensor_max_age = None

        # Facility link (optional)
        self.geo_facility_id           = None
        self.geo_facility_id_device_id = None  # set by setup_custom_options for select_device

        # Time Control
        self.time_enable = None
        self.time_start  = None
        self.time_end    = None

        # VPD
        self.sensor_vpd          = None
        self.vpd_sp_type         = None
        self.target_vpd          = None
        self.vpd_method_id_device_id = None   # set by setup_custom_options for select_device
        self.priority_vpd        = None
        self.tolerance_vpd       = None

        # Light
        self.sensor_light = None
        self.light_max    = None
        self.light_min    = None

        # CO₂
        self.sensor_CO2_int = None
        self.target_co2     = None
        self.priority_co2   = None
        self.tolerance_co2  = None

        # Temperature (constraints)
        self.sensor_T_int = None
        self.temp_max     = None
        self.temp_min     = None

        # Humidity (constraints)
        self.sensor_RH_int = None
        self.humid_max     = None
        self.humid_min     = None

        # Wind
        self.sensor_wind         = None
        self.sensor_wind_dir     = None
        self.gate_wind_threshold = None

        # Internal state
        self._vpd_method_handler = None
        self._vpd_method_start   = None
        self._vpd_last_sp        = None

        self._coord_state  = CoordinatorState()
        self._trend_state  = TrendState()
        self._profiles     = []
        self._channel_map  = {}
        self._actuator_idx = {}
        self._pre_gate: SafetyPreGate   = None
        self._post_gate: SafetyPostGate = SafetyPostGate()

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
        self.logger.info(
            'EnvCoordinator initialised — %d actuator(s), period=%.0fs',
            len(self._profiles), self.update_period or 60)

    # ─────────────────────────────────────────────────────────────────────────
    def _reload_profiles(self):
        """Hybrid loader: facility-derived profiles + manual env_actuator action profiles.

        Order:
          1. If geo_facility_id_device_id is set → load GeoFacility, iterate
             facility.actuators and build ActuatorProfile per slot with GIS metadata
             (slot_key, geo_facility_id; azimuth/area filled when geo helpers ready).
          2. Iterate env_actuator Actions and build/merge profiles.
             - If an action's Output matches a facility-derived actuator_id, the
               action augments cost/k_override on the existing profile.
             - Otherwise the action creates an additional standalone profile.
        """
        profiles = []
        channel_map = {}
        by_id = {}  # actuator_id → profile (for de-dupe / merge)
        n_facility = 0
        n_manual_new = 0
        n_manual_merged = 0

        # ── 1. Facility-driven profiles ──────────────────────────────────────
        facility_uuid = self.geo_facility_id_device_id or ''
        facility_meta = {}  # device_id → dict(slot_key, kind, area_m2, azimuth_deg)
        if facility_uuid:
            try:
                facility = GeoFacility.query.filter_by(unique_id=facility_uuid).first()
            except Exception:
                facility = None
            if facility:
                computed = facility.computed or {}
                envelope = facility.envelope or {}
                actuators_dict = facility.actuators or {}
                # rough per-slot area split from computed.vent_open_m2 (placeholder)
                vent_total = float(computed.get('vent_open_m2', 0.0) or 0.0)
                # how many vent slots are mapped → equal split
                vent_slots = [k for k, v in actuators_dict.items()
                              if v and 'vent' in k]
                area_per_vent = (vent_total / len(vent_slots)) if vent_slots else 0.0

                # G2: device GeoShape 우선 → facility fallback
                from aot.aot_flask.geo.facility_geo_helpers import shape_azimuth_area

                gis_resolved = 0  # device GeoShape 에서 azimuth 또는 area 얻은 수

                for slot_key, output_uuid in actuators_dict.items():
                    if not output_uuid:
                        continue
                    kind = _FACILITY_SLOT_KIND.get(slot_key)
                    if not kind:
                        continue  # fans 등 미지원 슬롯

                    # area / azimuth fallback (facility 단위 추정)
                    if 'vent' in slot_key:
                        fb_area = area_per_vent
                    elif slot_key == 'thermal_curtain':
                        fb_area = float(computed.get('envelope_m2', 0.0) or 0.0)
                    elif slot_key == 'shade_curtain':
                        fb_area = float(computed.get('roof_m2', 0.0) or 0.0)
                    else:
                        fb_area = 0.0

                    # 1) device GeoShape 우선 조회
                    azimuth_deg = None
                    area_m2 = fb_area
                    try:
                        shape = GeoShape.query.filter_by(
                            device_id=output_uuid).first()
                    except Exception:
                        shape = None

                    if shape and shape.feature:
                        az_shp, ar_shp = shape_azimuth_area(shape.feature)
                        if az_shp is not None:
                            azimuth_deg = az_shp
                            gis_resolved += 1
                        if ar_shp is not None and ar_shp > 0:
                            area_m2 = ar_shp
                            if azimuth_deg is None:
                                gis_resolved += 1   # area 만이라도 GIS 기여

                    facility_meta[output_uuid] = {
                        'slot_key': slot_key,
                        'kind': kind,
                        'area_m2': area_m2,
                        'azimuth_deg': azimuth_deg,
                        'capacity_meta': {
                            'volume_m3':   float(computed.get('volume_m3', 0.0) or 0.0),
                            'u_effective': float(computed.get('u_effective', 0.0) or 0.0),
                            'envelope_m2': float(computed.get('envelope_m2', 0.0) or 0.0),
                        },
                    }

                    # Resolve channel from Output (slot mapping has no channel detail;
                    # default to channel 0 unless overridden by manual action below).
                    effect_model = build_effect_model(kind, {})
                    profile = ActuatorProfile(
                        actuator_id=output_uuid,
                        kind=kind,
                        capabilities=_KIND_CAPABILITIES.get(kind, []),
                        cost_fn=lambda env, pct, _c=5.0: _c,
                        response_sec=60.0,
                        safe_default=0.0,
                        manual_lock=ManualLockState(),
                        effect_model=effect_model,
                        cmd_constraints=CmdConstraints(),
                        geo_facility_id=facility_uuid,
                        slot_key=slot_key,
                        azimuth_deg=azimuth_deg,
                        area_m2=area_m2,
                        capacity_meta=facility_meta[output_uuid]['capacity_meta'],
                    )
                    profiles.append(profile)
                    by_id[output_uuid] = profile
                    channel_map[output_uuid] = 0
                    n_facility += 1

                self.logger.info(
                    '_reload_profiles: %d facility-derived actuator(s) from "%s" '
                    '(gis_resolved=%d/%d)',
                    n_facility, facility.name, gis_resolved, n_facility)

        # ── 2. actuator_paired Outputs (자동 발견) ────────────────────────────
        # 사용자가 'actuator_paired' 타입 Output 을 등록한 모든 장치를 스캔.
        # Output 자체에 actuator_kind/azimuth/area/cost/k_override 가 있어
        # env_actuator action 없이도 ActuatorProfile 생성 가능.
        n_paired = 0
        try:
            from aot.aot_flask.geo.facility_geo_helpers import shape_azimuth_area
            from aot.outputs.actuator_paired import KIND_TO_PROFILE_KIND
            paired_outputs = Output.query.filter_by(
                output_type='actuator_paired').all()
        except Exception:
            paired_outputs = []
            KIND_TO_PROFILE_KIND = {}

        for out in paired_outputs:
            out_uuid = out.unique_id
            if out_uuid in by_id:
                continue   # facility 단계에서 이미 매칭

            # output_channel 0 의 custom_options 조회
            try:
                from aot.databases.models import OutputChannel
                ch = OutputChannel.query.filter_by(
                    output_id=out_uuid, channel=0).first()
                ch_opts = json.loads(ch.custom_options or '{}') if ch else {}
            except Exception:
                ch_opts = {}

            actuator_kind = ch_opts.get('actuator_kind') or 'side_vent'
            profile_kind = KIND_TO_PROFILE_KIND.get(actuator_kind)
            if not profile_kind:
                continue

            azimuth_deg = ch_opts.get('azimuth_deg')
            area_m2     = ch_opts.get('area_m2')
            cost        = float(ch_opts.get('cost', 5.0) or 5.0)
            k_override  = float(ch_opts.get('k_override', 0.0) or 0.0)

            # Output 에 azimuth/area 비어 있으면 GeoShape 에서 보강
            if azimuth_deg is None or area_m2 is None:
                try:
                    shape = GeoShape.query.filter_by(device_id=out_uuid).first()
                except Exception:
                    shape = None
                if shape and shape.feature:
                    az_shp, ar_shp = shape_azimuth_area(shape.feature)
                    if azimuth_deg is None and az_shp is not None:
                        azimuth_deg = az_shp
                    if area_m2 is None and ar_shp is not None and ar_shp > 0:
                        area_m2 = ar_shp

            k = {}
            if k_override:
                _K_PRIMARY = {
                    'opening':      'K_OPENING_T',
                    'cooler':       'K_COOLER_T',
                    'heater':       'K_HEATER_T',
                    'fogger':       'K_FOG_RH',
                    'co2_injector': 'K_CO2_INJ',
                    'shade':        'K_SHADE_T',
                    'curtain':      'K_CURTAIN_T',
                    'lighting':     'K_LIGHT_PPFD',
                }
                k_key = _K_PRIMARY.get(profile_kind)
                if k_key:
                    k[k_key] = k_override

            effect_model = build_effect_model(profile_kind, k)
            profile = ActuatorProfile(
                actuator_id=out_uuid,
                kind=profile_kind,
                capabilities=_KIND_CAPABILITIES.get(profile_kind, []),
                cost_fn=lambda env, pct, _c=cost: _c,
                response_sec=60.0,
                safe_default=0.0,
                manual_lock=ManualLockState(),
                effect_model=effect_model,
                cmd_constraints=CmdConstraints(),
                slot_key='actuator_paired',
                azimuth_deg=azimuth_deg,
                area_m2=area_m2,
            )
            profiles.append(profile)
            by_id[out_uuid] = profile
            channel_map[out_uuid] = 0
            n_paired += 1

        if n_paired:
            self.logger.info(
                '_reload_profiles: %d paired-actuator output(s) auto-discovered',
                n_paired)

        # ── 3. Manual env_actuator actions (merge or append) ─────────────────
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
            parts = str(output_val).split(',')
            device_id  = parts[0].strip() if parts else ''
            channel_id = parts[1].strip() if len(parts) > 1 else None

            kind = opts.get('kind', '') or ''
            cost = float(opts.get('cost', 5.0) or 5.0)
            k_override = float(opts.get('k_override', 0.0) or 0.0)

            if not device_id or not kind:
                continue

            ch_obj = 0
            if channel_id:
                try:
                    ch_obj = self.get_output_channel_from_channel_id(channel_id)
                except Exception:
                    ch_obj = 0

            k = {}
            if k_override:
                _K_PRIMARY = {
                    'opening':      'K_OPENING_T',
                    'cooler':       'K_COOLER_T',
                    'heater':       'K_HEATER_T',
                    'fogger':       'K_FOG_RH',
                    'co2_injector': 'K_CO2_INJ',
                    'shade':        'K_SHADE_T',
                    'curtain':      'K_CURTAIN_T',
                    'lighting':     'K_LIGHT_PPFD',
                }
                k_key = _K_PRIMARY.get(kind)
                if k_key:
                    k[k_key] = k_override

            effect_model = build_effect_model(kind, k)

            existing = by_id.get(device_id)
            if existing:
                # Merge: action augments facility-derived profile (cost / k_override / channel)
                existing.cost_fn = (lambda env, pct, _c=cost: _c)
                existing.effect_model = effect_model
                channel_map[device_id] = ch_obj
                n_manual_merged += 1
            else:
                # Standalone manual profile (no facility link)
                profile = ActuatorProfile(
                    actuator_id=device_id,
                    kind=kind,
                    capabilities=_KIND_CAPABILITIES.get(kind, []),
                    cost_fn=lambda env, pct, _c=cost: _c,
                    response_sec=60.0,
                    safe_default=0.0,
                    manual_lock=ManualLockState(),
                    effect_model=effect_model,
                    cmd_constraints=CmdConstraints(),
                )
                profiles.append(profile)
                by_id[device_id] = profile
                channel_map[device_id] = ch_obj
                n_manual_new += 1

        self._profiles    = profiles
        self._channel_map = channel_map
        self._actuator_idx = {p.actuator_id: i for i, p in enumerate(profiles)}
        self.logger.info(
            '_reload_profiles: total=%d (facility=%d, paired=%d, manual_new=%d, manual_merged=%d)',
            len(profiles), n_facility, n_paired, n_manual_new, n_manual_merged)

    # ─────────────────────────────────────────────────────────────────────────
    def cmd_reload(self, args_dict):
        self._reload_profiles()
        return f'Reloaded — {len(self._profiles)} actuator(s)'

    def cmd_run_now(self, args_dict):
        self.timer_loop = 0.0

    # ─────────────────────────────────────────────────────────────────────────
    def loop(self):
        if time.time() < self.timer_loop:
            return
        period = self.update_period or 60.0
        self.timer_loop = time.time() + period
        try:
            self._run_cycle(period)
        except Exception:
            self.logger.exception('EnvCoordinator cycle error')

    # ─────────────────────────────────────────────────────────────────────────
    def _run_cycle(self, cycle_sec: float):
        uid = self.unique_id
        max_age = self.sensor_max_age or 120.0

        if not self._profiles:
            self.logger.debug('EnvCoordinator: no actuators registered — skipping cycle')
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

        # ── Internal sensors ──────────────────────────────────────────────────
        internal = self._collect_internal(max_age)
        if not internal:
            self.logger.warning('EnvCoordinator: no internal sensor data — skipping cycle')
            return

        # ── Pre-Gate ──────────────────────────────────────────────────────────
        gate_env = self._build_gate_env(internal, external)
        gate_result = self._pre_gate.evaluate(gate_env, self._profiles, uid)

        if gate_result.triggered:
            self._dispatch(gate_result.forced_commands)
            write_decision_log(uid, 'safety_gate_active',
                               CH_SAFETY_GATE, float(gate_result.gate_mask))
            return
        elif not gate_result.triggered and gate_result.gate_mask == 0:
            self._coord_state.integral.clear()
            self._coord_state.active_vars.clear()
        # partial=True (풍향 차등 모드) 인 경우 forced_commands 는 일부 windward openings.
        # L1~L3 정상 실행 후 _dispatch 직전에 override 로 적용한다.
        partial_overrides = (gate_result.forced_commands
                             if gate_result.partial else {})

        # ── T/RH constraint check (before L1) ────────────────────────────────
        t_val  = internal.get('T')
        rh_val = internal.get('RH')
        if t_val is not None:
            if self.temp_max and t_val > self.temp_max:
                self.logger.warning('T=%.1f > max=%.1f — forcing cooling', t_val, self.temp_max)
                internal['_force_cool'] = True
            if self.temp_min and t_val < self.temp_min:
                self.logger.warning('T=%.1f < min=%.1f — forcing heating', t_val, self.temp_min)
                internal['_force_heat'] = True
        if rh_val is not None:
            if self.humid_max and rh_val > self.humid_max:
                internal['_force_dehumid'] = True
            if self.humid_min and rh_val < self.humid_min:
                internal['_force_humid'] = True

        # ── L1: EnvTarget (VPD-primary) ───────────────────────────────────────
        vpd_t = self._get_vpd_setpoint()
        co2_t = self.target_co2 if (self.target_co2 or 0) > 0 and self.sensor_CO2_int else None

        env_target = build_env_target(
            T_target   = 24.0,      # placeholder — VPD drives T/RH via L2 decomposition
            T_tol      = 1.0,
            T_pri      = 0.5,       # lower priority: T is a constraint, not a target
            RH_target  = 65.0,
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

        for var, tv in env_target.items():
            if var.startswith('_'):
                continue
            write_decision_log(uid, f'goal_target_{var}',   ch_goal_target(var),   tv.value)
            write_decision_log(uid, f'goal_priority_{var}', ch_goal_priority(var), tv.priority)

        # ── L2: SituationReport ───────────────────────────────────────────────
        situation, self._trend_state = assess(
            env_target=env_target,
            internal=internal,
            external=external,
            cycle_sec=cycle_sec,
            now_ts=time.time(),
            last_ext_ts=external.get('last_ext_ts'),
            last_int_ts=None,
            trend_state=self._trend_state,
        )

        for var, dev in situation.deviation_native.items():
            write_decision_log(uid, f'situation_deviation_{var}',
                               ch_situation_deviation(var), dev)
        mode_code = MODE_CODES.get(situation.modes[0] if situation.modes else '', 0)
        write_decision_log(uid, 'situation_mode', CH_SITUATION_MODE, float(mode_code))
        if situation.limiting_factor:
            write_decision_log(uid, 'situation_limiting_factor',
                               CH_SITUATION_LIMIT,
                               float(LIMIT_CODES.get(situation.limiting_factor, 0)))

        # ── L3: Coordination ──────────────────────────────────────────────────
        commands, new_state = coordinate(
            situation=situation,
            profiles=self._profiles,
            state=self._coord_state,
            unique_id=uid,
            actuator_index=self._actuator_idx,
        )
        self._coord_state = new_state

        # ── Post-Gate ─────────────────────────────────────────────────────────
        final_cmds, _ = self._post_gate.check(
            {aid: {'value': c.value, 'reason': c.reason} for aid, c in commands.items()},
            self._profiles,
            uid,
        )

        # ── Pre-Gate partial overrides (풍향 차등 windward 폐쇄) ────────────────
        # G4: 강풍 단독 + per-opening 모드일 때 windward openings 만 강제 폐쇄.
        # leeward openings 는 final_cmds 그대로 유지.
        if partial_overrides:
            for aid, override in partial_overrides.items():
                final_cmds[aid] = override

        self._dispatch(final_cmds)

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

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

            if self._vpd_method_handler is None:
                try:
                    from aot.utils.method import load_method_handler
                    self._vpd_method_handler = load_method_handler(
                        method_id, self.logger)
                    self._vpd_method_start = time.time()
                except Exception as exc:
                    self.logger.error('VPD method load failed (%s): %s', method_id, exc)
                    return self._vpd_last_sp

            try:
                sp_val, ended = self._vpd_method_handler.calculate_setpoint(
                    time.time(), method_start_time=self._vpd_method_start)
                if ended:
                    sp_val = self._vpd_last_sp
                if sp_val is not None:
                    self._vpd_last_sp = float(sp_val)
                return self._vpd_last_sp
            except Exception as exc:
                self.logger.error('VPD method calculate_setpoint error: %s', exc)
                return self._vpd_last_sp

        return None

    def _in_time_window(self) -> bool:
        """Return True if current time is within the configured window."""
        try:
            now = datetime.now().strftime('%H:%M')
            start = self.time_start or '00:00'
            end   = self.time_end   or '23:59'
            if start <= end:
                return start <= now <= end
            else:
                return now >= start or now <= end   # overnight window
        except Exception:
            return True

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
            parts     = str(output_val).split(',')
            device_id = parts[0].strip()
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

        _fetch(self.sensor_T_int,   'T')
        _fetch(self.sensor_RH_int,  'RH')
        _fetch(self.sensor_CO2_int, 'CO2')
        _fetch(self.sensor_vpd,     'VPD')
        _fetch(self.sensor_light,   'light')
        _fetch(self.sensor_wind,     'wind')
        _fetch(self.sensor_wind_dir, 'wind_dir')
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

    def _dispatch(self, commands: dict):
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
            except Exception:
                self.logger.exception('dispatch failed for %s', actuator_id)
