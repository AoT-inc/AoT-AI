# coding=utf-8
"""
_function_info.py — FUNCTION_INFORMATION 및 액추에이터 종류 상수.

env_coordinator.py 에서 `from ._function_info import *` 로 임포트.
"""

from flask_babel import lazy_gettext

from aot.utils.constraints_pass import constraints_pass_positive_value

# ─────────────────────────────────────────────────────────────────────────────
# 액추에이터 종류 상수 (env_coordinator.py 전역 참조)
# ─────────────────────────────────────────────────────────────────────────────

_KIND_CAPABILITIES = {
    'opening':          ['ventilation', 'cooling_passive', 'co2_dilution'],
    'cooler':           ['cooling'],
    'heater':           ['heating'],
    'fogger':           ['humidify', 'cooling_passive'],
    'co2_injector':     ['co2_enrich'],
    'shade':            ['shading', 'cooling_passive'],
    'curtain':          ['insulation'],
    'lighting':         ['light_enrich'],
    'circulation_fan':  ['ventilation'],                            # P3-1
    'exhaust_fan':      ['ventilation', 'cooling_passive', 'co2_dilution'],  # P3-1
    'intake_fan':       ['ventilation', 'cooling_passive'],          # P3-1
}

# GeoFacility.actuators 슬롯 → ActuatorProfile.kind 매핑.
_FACILITY_SLOT_KIND = {
    'outer_side_vent_motor': 'opening',
    'outer_roof_vent_motor': 'opening',
    'inner_side_vent_motor': 'opening',
    'inner_roof_vent_motor': 'opening',
    'thermal_curtain':       'curtain',
    'shade_curtain':         'shade',
    'circulation_fan':       'circulation_fan',   # P3-1
    'exhaust_fan':           'exhaust_fan',        # P3-1
    'intake_fan':            'intake_fan',         # P3-1
}

# ─────────────────────────────────────────────────────────────────────────────
# FUNCTION_INFORMATION
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
        'Trigger an immediate cycle, reload actuators, or issue an emergency stop.'
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
        {
            'id': 'cmd_emergency_stop',
            'type': 'button',
            'wait_for_return': True,
            'name': lazy_gettext('Emergency Stop'),
            'phrase': lazy_gettext(
                'Immediately set all actuators to safe_default and pause control for 60 s.'
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

        # ── Growth Schedule ───────────────────────────────────────────────────
        {
            'type': 'header',
            'name': lazy_gettext('Growth Schedule'),
        },
        {
            'id': 'schedule_start_time',
            'type': 'text',
            'default_value': '',
            'required': False,
            'name': lazy_gettext('Schedule Start (ISO 8601 UTC)'),
            'phrase': lazy_gettext(
                'Planting / germination date-time in UTC, e.g. 2025-01-01T00:00:00. '
                'Used to compute weeks_elapsed for all Method curves. '
                'Leave empty to disable week-based progression (Methods use wall-clock day only).'
            ),
        },
        {
            'id': 'schedule_week_offset',
            'type': 'float',
            'default_value': 0.0,
            'required': False,
            'name': lazy_gettext('Week Offset'),
            'phrase': lazy_gettext(
                'Direct week adjustment applied on top of elapsed weeks. '
                'Use a positive value to fast-forward (e.g. system started mid-cycle), '
                'or negative to compensate for downtime. Default 0.'
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
                'On-end behavior per actuator is configured in each Action. '
                'Ignored when Photoperiod Method is set.'
            ),
        },
        {
            'id': 'photo_method_id',
            'type': 'select_device',
            'default_value': '',
            'required': False,
            'options_select': ['Method'],
            'name': lazy_gettext('Photoperiod Method'),
            'phrase': lazy_gettext(
                'Optional. Select an AoT Method that returns photoperiod length in hours '
                '(e.g. 14.0 = 14 h light). The function computes time_start/end '
                'symmetrically around the Anchor time. '
                'When set, the static Start/End times above are overridden.'
            ),
        },
        {
            'id': 'photo_anchor',
            'type': 'text',
            'default_value': '12:00',
            'required': False,
            'name': lazy_gettext('Photoperiod Anchor (HH:MM)'),
            'phrase': lazy_gettext(
                'Solar-noon equivalent. The photoperiod window is centred on this time. '
                'Default 12:00. Adjust for your latitude / season if needed.'
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
            'id': 'co2_sp_type',
            'type': 'select',
            'default_value': 'static',
            'required': False,
            'options_select': [
                ('static', lazy_gettext('Static Target')),
                ('method', lazy_gettext('Method (time-varying)')),
            ],
            'name': lazy_gettext('CO₂ Setpoint Type'),
            'phrase': lazy_gettext(
                'Static: use the fixed target below. '
                'Method: follow an AoT Method curve (ppm vs time-of-day / growth week).'
            ),
        },
        {
            'id': 'target_co2',
            'type': 'float',
            'default_value': 1000.0,
            'required': False,
            'name': lazy_gettext('Target CO₂ (ppm)'),
            'phrase': lazy_gettext('Used when CO₂ Setpoint Type = Static.'),
        },
        {
            'id': 'co2_method_id',
            'type': 'select_device',
            'default_value': '',
            'required': False,
            'options_select': ['Method'],
            'name': lazy_gettext('CO₂ Method'),
            'phrase': lazy_gettext(
                'Used when CO₂ Setpoint Type = Method. '
                'Select an AoT Method that returns a CO₂ setpoint (ppm).'
            ),
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

        # ── VPD Decomposition ─────────────────────────────────────────────────
        {
            'type': 'header',
            'name': lazy_gettext('VPD Decomposition'),
        },
        {
            'id': 'vpd_weight_T',
            'type': 'float',
            'default_value': 0.6,
            'required': False,
            'name': lazy_gettext('T Weight (0-1)'),
            'phrase': lazy_gettext(
                'VPD decomposition: fraction of adjustment via temperature (rest via humidity). '
                '0.6 = favour temperature adjustment. Range 0.0~1.0.'
            ),
        },

        # ── Photosynthesis Model (optional) ──────────────────────────────────
        {
            'type': 'header',
            'name': lazy_gettext('Photosynthesis Model'),
        },
        {
            'id': 'photosynth_mode_enabled',
            'type': 'bool',
            'default_value': False,
            'required': False,
            'name': lazy_gettext('Enable Photosynthesis-Oriented Control'),
            'phrase': lazy_gettext(
                'When enabled, the Big-Leaf photosynthesis model identifies the current '
                'limiting factor (Light / CO₂ / Temperature / VPD) each cycle and '
                'dynamically raises that variable\'s priority. '
                'Requires Light sensor. Recommended when ≥ 3 active actuator types are available.'
            ),
        },
        {
            'id': 'crop_preset',
            'type': 'select',
            'default_value': 'tomato',
            'required': False,
            'options_select': [
                ('tomato',     lazy_gettext('Tomato')),
                ('lettuce',    lazy_gettext('Lettuce / Leafy greens')),
                ('cucumber',   lazy_gettext('Cucumber')),
                ('strawberry', lazy_gettext('Strawberry')),
                ('pepper',     lazy_gettext('Pepper / Paprika')),
            ],
            'name': lazy_gettext('Crop Preset'),
            'phrase': lazy_gettext(
                'Selects Big-Leaf model parameters (A_max, K_L, K_C, T_opt, VPD_half). '
                'Used only when Photosynthesis-Oriented Control is enabled.'
            ),
        },

        # ── Guide Ranges (T/RH) ───────────────────────────────────────────────
        {
            'type': 'header',
            'name': lazy_gettext('Guide Ranges (T / RH)'),
        },
        {
            'id': 'guide_T_min',
            'type': 'float',
            'default_value': 12.0,
            'required': False,
            'name': lazy_gettext('Guide T Min (°C)'),
            'phrase': lazy_gettext(
                'Advisory lower bound for temperature. '
                'Triggers forced heating when exceeded (replaces Min Temperature setting '
                'when using crop-preset-derived guide ranges).'
            ),
        },
        {
            'id': 'guide_T_max',
            'type': 'float',
            'default_value': 32.0,
            'required': False,
            'name': lazy_gettext('Guide T Max (°C)'),
            'phrase': lazy_gettext('Advisory upper bound for temperature.'),
        },
        {
            'id': 'guide_RH_min',
            'type': 'float',
            'default_value': 40.0,
            'required': False,
            'name': lazy_gettext('Guide RH Min (%)'),
            'phrase': lazy_gettext('Advisory lower bound for relative humidity.'),
        },
        {
            'id': 'guide_RH_max',
            'type': 'float',
            'default_value': 85.0,
            'required': False,
            'name': lazy_gettext('Guide RH Max (%)'),
            'phrase': lazy_gettext('Advisory upper bound for relative humidity.'),
        },

        # ── Cumulative Goal Tracker ───────────────────────────────────────────
        {
            'type': 'header',
            'name': lazy_gettext('Cumulative Goal Tracker'),
        },
        {
            'id': 'cumulative_tracker_enabled',
            'type': 'bool',
            'default_value': False,
            'required': False,
            'name': lazy_gettext('Enable DLI / GDD Tracker'),
            'phrase': lazy_gettext(
                'Tracks daily light integral (DLI) and growing degree-days (GDD). '
                'Generates compensation suggestions when debt accumulates. '
                'Requires Light sensor for DLI tracking.'
            ),
        },
        {
            'id': 'dli_target',
            'type': 'float',
            'default_value': 0.0,
            'required': False,
            'name': lazy_gettext('DLI Target (mol/m²/day)'),
            'phrase': lazy_gettext(
                'Daily light integral target. 0 = disable DLI tracking. '
                'Typical values: leafy greens 12-17, tomato 20-30.'
            ),
        },
        {
            'id': 'gdd_target_daily',
            'type': 'float',
            'default_value': 0.0,
            'required': False,
            'name': lazy_gettext('GDD Target (°C·day/day)'),
            'phrase': lazy_gettext(
                'Growing degree-day target per day. 0 = disable GDD tracking. '
                'Computed as max(0, T_mean - T_base) per cycle.'
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

        # ── Forecast Feedforward (P3-4) ───────────────────────────────────────
        {
            'type': 'header',
            'name': lazy_gettext('Forecast Feedforward'),
        },
        {
            'id': 'forecast_feedforward_enabled',
            'type': 'bool',
            'default_value': False,
            'required': False,
            'name': lazy_gettext('Enable Forecast Feedforward'),
            'phrase': lazy_gettext(
                'Use KMA short-term weather forecast (forecast.json) to proactively '
                'shift temperature/humidity setpoints and inhibit ventilation '
                'before adverse weather arrives.'
            ),
        },
        {
            'id': 'forecast_lookahead_h',
            'type': 'float',
            'default_value': 3.0,
            'required': False,
            'name': lazy_gettext('Forecast Lookahead (hours)'),
            'phrase': lazy_gettext(
                'How many hours ahead to check for incoming adverse weather (1–6 h). '
                'Longer lookahead gives earlier warning but may over-correct.'
            ),
        },
    ],
}
