# coding=utf-8
import copy
import time

from flask_babel import lazy_gettext

from aot.databases.models import OutputChannel
from aot.outputs.base_output import AbstractOutput
from aot.utils.database import db_retrieve_table_daemon
from aot.utils.influx import add_measurements_influxdb

measurements_dict = {0: {'measurement': 'duty_cycle', 'unit': 'percent'}}
channels_dict = {0: {'types': ['value'], 'measurements': [0]}}

ACTUATOR_KIND_OPTIONS = [
    ('side_vent',       lazy_gettext('Side Vent')),
    ('roof_vent',       lazy_gettext('Roof Vent')),
    ('thermal_curtain', lazy_gettext('Thermal Curtain')),
    ('shade_curtain',   lazy_gettext('Shade Curtain')),
    ('ball_valve',      lazy_gettext('Ball Valve')),
]

KIND_TO_PROFILE_KIND = {
    'side_vent':       'opening',
    'roof_vent':       'opening',
    'thermal_curtain': 'curtain',
    'shade_curtain':   'shade',
    'ball_valve':      'opening',
}

OUTPUT_INFORMATION = {
    'output_name_unique': 'actuator_paired',
    'output_name': "{}: Actuator Paired".format(lazy_gettext('Value')),
    'output_manufacturer': 'AoT',
    'measurements_dict': measurements_dict,
    'channels_dict': channels_dict,
    'output_types': ['value'],

    'message': lazy_gettext(
        'Time-based opening control (0–100%) for vents, curtains, and ball valves. '
        'Connects an Open relay and a Close relay to a single percentage command.'
    ),

    'options_enabled': ['button_send_value'],

    'custom_channel_options': [
        {
            'id': 'actuator_kind',
            'type': 'select',
            'default_value': 'side_vent',
            'required': True,
            'options_select': ACTUATOR_KIND_OPTIONS,
            'name': lazy_gettext('Actuator Kind'),
            'phrase': lazy_gettext('Type of actuator being controlled.'),
        },
        {
            'id': 'output_open_id',
            'type': 'select_device',
            'default_value': '',
            'required': False,
            'options_select': ['Output'],
            'name': lazy_gettext('Output: Open'),
            'phrase': lazy_gettext('on/off Output connected to the OPEN relay.'),
        },
        {
            'id': 'output_close_id',
            'type': 'select_device',
            'default_value': '',
            'required': False,
            'options_select': ['Output'],
            'name': lazy_gettext('Output: Close'),
            'phrase': lazy_gettext('on/off Output connected to the CLOSE relay.'),
        },
        {
            'id': 'travel_time_sec',
            'type': 'float',
            'default_value': 0.0,
            'required': False,
            'name': lazy_gettext('Full Travel Time (s)'),
            'phrase': lazy_gettext(
                'Seconds for the actuator to travel from fully closed (0%) to fully open (100%). '
                'Use the Calibration buttons below to measure automatically.'),
        },
        {
            'id': 'calib_direction',
            'type': 'select',
            'default_value': 'open',
            'required': False,
            'options_select': [('open', 'Open'), ('close', 'Close')],
            'name': lazy_gettext('Calibration Direction'),
            'phrase': lazy_gettext(
                'Click ▶ Start → actuator moves → click ■ Stop when fully open/closed → '
                'elapsed time is saved as Full Travel Time.'),
        },
    ],
    'custom_commands': [
        {
            'id': 'calib_run',
            'type': 'button',
            'name': lazy_gettext('▶ Start Calibration'),
            'phrase': lazy_gettext(
                'Drives the actuator in the selected direction. Click Stop when done.'),
        },
        {
            'id': 'calib_stop',
            'type': 'button',
            'name': lazy_gettext('■ Stop & Save'),
            'phrase': lazy_gettext(
                'Stops the actuator and saves elapsed time as Full Travel Time.'),
        },
    ],
}


class OutputModule(AbstractOutput):
    """Time-based opening control for vents, curtains, and ball valves."""

    def __init__(self, output, testing=False):
        super().__init__(output, testing=testing, name=__name__)

        output_channels = db_retrieve_table_daemon(
            OutputChannel).filter(
                OutputChannel.output_id == self.output.unique_id).all()
        self.options_channels = self.setup_custom_channel_options_json(
            OUTPUT_INFORMATION['custom_channel_options'], output_channels)

        self._position_pct = 0.0
        self._last_direction = 'idle'
        self._last_direction_change_ts = 0.0
        self._calib_start_ts = 0.0

    def initialize(self):
        self.setup_output_variables(OUTPUT_INFORMATION)
        self.output_setup = True
        self.logger.info("actuator_paired ready — kind=%s open=%s close=%s",
                         self._opt('actuator_kind') or '?',
                         self._opt('output_open_id') or '(none)',
                         self._opt('output_close_id') or '(none)')

    # ── public ──────────────────────────────────────────────────────────────
    def output_switch(self, state, output_type=None, amount=None, output_channel=0):
        target = 0.0 if state == 'off' else float(amount or 0.0)
        target = max(0.0, min(100.0, target))

        self._drive(target)

        self.output_states[output_channel] = target if target > 0 else False
        measure = copy.deepcopy(measurements_dict)
        measure[0]['value'] = target
        add_measurements_influxdb(self.unique_id, measure)
        self._position_pct = target

    def is_on(self, output_channel=0):
        if self.is_setup():
            if output_channel is not None and output_channel in self.output_states:
                return self.output_states[output_channel]
            return self.output_states

    def is_setup(self):
        return self.output_setup

    def stop_output(self):
        self._relay_off(self._opt('output_open_id'))
        self._relay_off(self._opt('output_close_id'))
        self.running = False

    # ── drive ────────────────────────────────────────────────────────────────
    def _drive(self, target_pct: float):
        delta = target_pct - self._position_pct
        if abs(delta) < 0.5:
            return

        open_id  = self._opt('output_open_id')  or ''
        close_id = self._opt('output_close_id') or ''
        travel   = max(float(self._opt('travel_time_sec') or 60.0), 1.0)
        new_dir  = 'open' if delta > 0 else 'close'

        if self._last_direction not in ('idle', new_dir):
            self._relay_off(open_id)
            self._relay_off(close_id)
            waited = time.time() - self._last_direction_change_ts
            pause = max(5.0 - waited, 0.0)
            if pause > 0:
                time.sleep(pause)

        run_sec = (abs(delta) / 100.0) * travel

        if new_dir == 'open':
            self._relay_off(close_id)
            time.sleep(0.05)
            self._relay_on(open_id, duration=run_sec)
        else:
            self._relay_off(open_id)
            time.sleep(0.05)
            self._relay_on(close_id, duration=run_sec)

        self._last_direction = new_dir
        self._last_direction_change_ts = time.time()

    # ── relay helpers ────────────────────────────────────────────────────────
    def _relay_on(self, output_id: str, duration: float = 0.0):
        if not output_id:
            return
        try:
            from aot.aot_client import DaemonControl
            ctrl = DaemonControl()
            if duration > 0:
                ctrl.output_on(output_id, output_type='sec',
                               amount=duration, output_channel=0)
            else:
                ctrl.output_on(output_id, output_channel=0)
        except Exception as e:
            self.logger.warning("relay_on %s failed: %s", output_id, e)

    def _relay_off(self, output_id: str):
        if not output_id:
            return
        try:
            from aot.aot_client import DaemonControl
            DaemonControl().output_off(output_id, output_channel=0)
        except Exception as e:
            self.logger.warning("relay_off %s failed: %s", output_id, e)

    # ── calibration ──────────────────────────────────────────────────────────
    def calib_run(self, args_dict=None):
        direction = self._opt('calib_direction') or 'open'
        open_id  = self._opt('output_open_id')  or ''
        close_id = self._opt('output_close_id') or ''
        self._calib_start_ts = time.time()
        if direction == 'open':
            self._relay_off(close_id)
            time.sleep(0.05)
            self._relay_on(open_id)
        else:
            self._relay_off(open_id)
            time.sleep(0.05)
            self._relay_on(close_id)
        self.logger.info("Calibration started — direction=%s", direction)
        return "Running. Click '■ Stop & Save' when fully {}.".format(direction)

    def calib_stop(self, args_dict=None):
        self._relay_off(self._opt('output_open_id'))
        self._relay_off(self._opt('output_close_id'))
        elapsed = round(time.time() - self._calib_start_ts, 1)
        try:
            import json
            from aot.databases.models import OutputChannel
            from aot.databases.utils import session_scope
            with session_scope() as sess:
                ch = sess.query(OutputChannel).filter(
                    OutputChannel.output_id == self.output.unique_id,
                    OutputChannel.channel == 0).first()
                if ch:
                    opts = json.loads(ch.custom_options or '{}')
                    opts['travel_time_sec'] = elapsed
                    ch.custom_options = json.dumps(opts)
        except Exception as e:
            self.logger.warning("calib_stop save failed: %s", e)
            return "Stopped after {:.1f}s but failed to save: {}".format(elapsed, e)
        self.logger.info("Calibration done — %.1fs saved as travel_time_sec", elapsed)
        return "Full Travel Time saved as {:.1f} s. Reload page to confirm.".format(elapsed)

    # ── util ─────────────────────────────────────────────────────────────────
    def _opt(self, key):
        vals = self.options_channels.get(key, [None])
        return vals[0] if vals else None
