# coding=utf-8
import copy
import threading
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
            'type': 'select_channel',
            'default_value': '',
            'required': False,
            'options_select': ['Output_Channels'],
            'name': lazy_gettext('Output: Open'),
            'phrase': lazy_gettext('on/off Output channel connected to the OPEN relay.'),
        },
        {
            'id': 'output_close_id',
            'type': 'select_channel',
            'default_value': '',
            'required': False,
            'options_select': ['Output_Channels'],
            'name': lazy_gettext('Output: Close'),
            'phrase': lazy_gettext('on/off Output channel connected to the CLOSE relay.'),
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
            'id': 'last_position_pct',
            'type': 'float',
            'default_value': 0.0,
            'required': False,
            'name': lazy_gettext('Last Position (%)'),
            'phrase': lazy_gettext(
                'Last known position. Updated automatically on each move so the value '
                'survives daemon restarts. Edit manually only if you know the actual position.'),
        },
        {
            'id': 'min_command_interval_sec',
            'type': 'float',
            'default_value': 1.0,
            'required': False,
            'name': lazy_gettext('Min Command Interval (s)'),
            'phrase': lazy_gettext(
                'Reject any new Open/Close command that arrives within this many seconds of the '
                'previous one. Prevents queued-up motor whiplash from rapid button presses. '
                'Stop is always accepted regardless of this interval.'),
        },
        {
            'id': 'reverse_pause_sec',
            'type': 'float',
            'default_value': 5.0,
            'required': False,
            'name': lazy_gettext('Reverse Pause (s)'),
            'phrase': lazy_gettext(
                'Dwell time inserted when reversing direction (open↔close) to protect the motor. '
                'Both relays stay OFF for this many seconds before the new direction starts.'),
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

        try:
            self._position_pct = float(self._opt('last_position_pct') or 0.0)
        except (TypeError, ValueError):
            self._position_pct = 0.0
        self._last_direction = 'idle'
        self._last_direction_change_ts = 0.0
        self._calib_start_ts = 0.0
        self._watchdog_timer = None
        self._last_command_ts = 0.0
        # In-flight motion record so we can compute true position if stopped mid-travel.
        self._motion_start_ts = 0.0
        self._motion_start_pos = 0.0
        self._motion_target = 0.0
        self._motion_dir = 'idle'
        self._motion_run_sec = 0.0

    def initialize(self):
        self.setup_output_variables(OUTPUT_INFORMATION)
        self.output_setup = True
        self.logger.info("actuator_paired ready — kind=%s open=%s close=%s",
                         self._opt('actuator_kind') or '?',
                         self._opt('output_open_id') or '(none)',
                         self._opt('output_close_id') or '(none)')

    # ── public ──────────────────────────────────────────────────────────────
    def output_switch(self, state, output_type=None, amount=None, output_channel=0):
        if state == 'off':
            # Stop: immediately halt whichever relay is running; recompute actual position
            # based on elapsed travel. Always accepted — Stop bypasses rate limit.
            self._cancel_watchdog()
            self._relay_off(self._opt('output_open_id'))
            self._relay_off(self._opt('output_close_id'))
            self._position_pct = self._compute_current_position()
            self._motion_dir = 'idle'
            self._last_direction = 'idle'
            self._last_direction_change_ts = time.time()
            self._last_command_ts = time.time()
            # Publish the actual position (numeric) so the UI displays it.
            # Use False only when fully closed so output_state returns 'off'.
            self.output_states[output_channel] = (
                self._position_pct if self._position_pct > 0 else False)
            measure = copy.deepcopy(measurements_dict)
            measure[0]['value'] = self._position_pct
            add_measurements_influxdb(self.unique_id, measure)
            self._save_position(self._position_pct)
            return

        # Rate-limit Open/Close: reject commands arriving within min_command_interval_sec
        min_interval = max(float(self._opt('min_command_interval_sec') or 0.0), 0.0)
        if min_interval > 0:
            elapsed = time.time() - self._last_command_ts
            if elapsed < min_interval:
                self.logger.info(
                    "Command rejected (rate limit) — %.2fs since last, need %.2fs",
                    elapsed, min_interval)
                return
        self._last_command_ts = time.time()

        # If a motion is already in progress, fold its real-time progress into _position_pct
        # before computing the next move so the delta is accurate.
        if self._motion_dir != 'idle':
            self._position_pct = self._compute_current_position()

        target = float(amount or 0.0)
        target = max(0.0, min(100.0, target))

        moved = self._drive(target)
        if not moved:
            # Already at target — nothing to do, but still publish state.
            self.output_states[output_channel] = target if target > 0 else False
            measure = copy.deepcopy(measurements_dict)
            measure[0]['value'] = self._position_pct
            add_measurements_influxdb(self.unique_id, measure)
            return

        # Publish the target as the state (numeric for Active, False for fully-closed).
        self.output_states[output_channel] = target if target > 0 else False
        measure = copy.deepcopy(measurements_dict)
        measure[0]['value'] = target
        add_measurements_influxdb(self.unique_id, measure)
        # _position_pct will be set to target by _motion_complete (natural finish) or
        # recomputed from elapsed time if interrupted by Stop / next command.

    def is_on(self, output_channel=0):
        if self.is_setup():
            if output_channel is not None and output_channel in self.output_states:
                # While moving, report the live elapsed-based position so the UI
                # shows progressing % instead of the static target.
                if self._motion_dir != 'idle':
                    live = self._compute_current_position()
                    return live if live > 0 else False
                return self.output_states[output_channel]
            return self.output_states

    def is_setup(self):
        return self.output_setup

    def stop_output(self):
        self._cancel_watchdog()
        self._relay_off(self._opt('output_open_id'))
        self._relay_off(self._opt('output_close_id'))
        self.running = False

    # ── drive ────────────────────────────────────────────────────────────────
    def _drive(self, target_pct: float):
        delta = target_pct - self._position_pct
        if abs(delta) < 0.5:
            return False

        open_id  = self._opt('output_open_id')  or ''
        close_id = self._opt('output_close_id') or ''
        travel   = max(float(self._opt('travel_time_sec') or 60.0), 1.0)
        rev_pause = max(float(self._opt('reverse_pause_sec') or 0.0), 0.0)
        new_dir  = 'open' if delta > 0 else 'close'

        primary_id  = open_id  if new_dir == 'open' else close_id
        opposite_id = close_id if new_dir == 'open' else open_id

        # Only touch the opposite relay when actually reversing direction.
        # Some underlying outputs (e.g. FarmOn MQTT) use a toggle protocol where
        # a redundant OFF on an already-off relay can flip it ON.
        if self._last_direction not in ('idle', new_dir):
            self._relay_off(opposite_id)
            waited = time.time() - self._last_direction_change_ts
            pause = max(rev_pause - waited, 0.0)
            if pause > 0:
                time.sleep(pause)

        run_sec = (abs(delta) / 100.0) * travel
        start_pos = self._position_pct

        self._relay_on(primary_id, duration=run_sec)

        self._last_direction = new_dir
        self._last_direction_change_ts = time.time()
        # Record motion state for elapsed-based position recovery on Stop.
        self._motion_dir = new_dir
        self._motion_start_ts = time.time()
        self._motion_start_pos = start_pos
        self._motion_target = target_pct
        self._motion_run_sec = run_sec
        self._arm_watchdog(run_sec)
        return True

    def _compute_current_position(self) -> float:
        """Estimate actual actuator position based on elapsed motion time."""
        if self._motion_dir == 'idle' or self._motion_run_sec <= 0:
            return self._position_pct
        travel = max(float(self._opt('travel_time_sec') or 60.0), 1.0)
        elapsed = max(time.time() - self._motion_start_ts, 0.0)
        # If we have already exceeded the planned run, motion is complete.
        if elapsed >= self._motion_run_sec:
            return self._motion_target
        moved_pct = (elapsed / travel) * 100.0
        sign = 1.0 if self._motion_dir == 'open' else -1.0
        actual = self._motion_start_pos + sign * moved_pct
        return max(0.0, min(100.0, actual))

    def _arm_watchdog(self, run_sec: float):
        self._cancel_watchdog()
        # Safety margin: stop slightly after the expected run time in case the
        # relay's own duration timer was missed (e.g. daemon restart, network blip).
        timeout = max(run_sec + 1.0, 1.5)
        t = threading.Timer(timeout, self._watchdog_fire)
        t.daemon = True
        self._watchdog_timer = t
        t.start()

    def _cancel_watchdog(self):
        t = self._watchdog_timer
        if t is not None:
            try:
                t.cancel()
            except Exception:
                pass
            self._watchdog_timer = None

    def _watchdog_fire(self):
        """Travel timer expired — motion is finished. Force relays off, finalize state."""
        self.logger.info("Travel time elapsed — motion complete, forcing Stop")
        self._relay_off(self._opt('output_open_id'))
        self._relay_off(self._opt('output_close_id'))
        # Snap to target since motion ran the full expected time.
        target = self._motion_target
        self._position_pct = target
        self._motion_dir = 'idle'
        self._last_direction = 'idle'
        self._last_direction_change_ts = time.time()
        self._watchdog_timer = None
        # Update card state + persist so UI reflects completion immediately on next poll.
        try:
            self.output_states[0] = target if target > 0 else False
            measure = copy.deepcopy(measurements_dict)
            measure[0]['value'] = target
            add_measurements_influxdb(self.unique_id, measure)
            self._save_position(target)
        except Exception as e:
            self.logger.warning("watchdog state update failed: %s", e)

    # ── relay helpers ────────────────────────────────────────────────────────
    def _parse_ref(self, ref):
        """Resolve an output reference to (output_id, channel_number).

        The select_channel form type is parsed by the framework into a dict
        {'device_id': ..., 'channel_id': ...} where channel_id is the
        OutputChannel.unique_id. We look up the channel number from the DB.

        Legacy string formats are also accepted:
          - 'output_id'              → (output_id, 0)
          - 'output_id,channel_uid'  → (output_id, looked_up_channel_number)
        """
        if not ref:
            return '', 0

        out_id = ''
        chan_uid = ''

        if isinstance(ref, dict):
            out_id = ref.get('device_id') or ''
            chan_uid = ref.get('channel_id') or ''
        elif isinstance(ref, str):
            if ',' in ref:
                parts = ref.split(',', 1)
                out_id = parts[0]
                chan_uid = parts[1] if len(parts) > 1 else ''
            else:
                out_id = ref
        else:
            return '', 0

        if not out_id:
            return '', 0
        if not chan_uid:
            return out_id, 0
        try:
            ch = db_retrieve_table_daemon(OutputChannel, unique_id=chan_uid)
            ch_num = ch.channel if ch else 0
            self.logger.debug("_parse_ref ref=%r -> out_id=%s ch_uid=%s ch=%s",
                              ref, out_id, chan_uid, ch_num)
            return out_id, ch_num
        except Exception as e:
            self.logger.warning("_parse_ref lookup failed for %s: %s", chan_uid, e)
            return out_id, 0

    def _relay_on(self, output_id, duration: float = 0.0):
        if not output_id:
            return
        out_id, ch_num = self._parse_ref(output_id)
        if not out_id:
            self.logger.warning("relay_on aborted — could not resolve ref %r", output_id)
            return
        self.logger.info("relay_on  ref=%r -> out_id=%s ch=%s dur=%.2f",
                         output_id, out_id, ch_num, duration)
        try:
            from aot.aot_client import DaemonControl
            ctrl = DaemonControl()
            if duration > 0:
                ctrl.output_on(out_id, output_type='sec',
                               amount=duration, output_channel=ch_num)
            else:
                ctrl.output_on(out_id, output_channel=ch_num)
        except Exception as e:
            self.logger.warning("relay_on %s failed: %s", output_id, e)

    def _relay_off(self, output_id):
        if not output_id:
            return
        out_id, ch_num = self._parse_ref(output_id)
        if not out_id:
            self.logger.warning("relay_off aborted — could not resolve ref %r", output_id)
            return
        self.logger.info("relay_off ref=%r -> out_id=%s ch=%s", output_id, out_id, ch_num)
        try:
            from aot.aot_client import DaemonControl
            DaemonControl().output_off(out_id, output_channel=ch_num)
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
            self.set_custom_channel_option(0, 'travel_time_sec', elapsed)
        except Exception as e:
            self.logger.warning("calib_stop save failed: %s", e)
            return "Stopped after {:.1f}s but failed to save: {}".format(elapsed, e)
        self.logger.info("Calibration done — %.1fs saved as travel_time_sec", elapsed)
        return "Full Travel Time saved as {:.1f} s. Reload page to confirm.".format(elapsed)

    # ── util ─────────────────────────────────────────────────────────────────
    def _opt(self, key):
        vals = self.options_channels.get(key, [None])
        return vals[0] if vals else None

    def _save_position(self, position_pct: float):
        # Persist last known position to channel custom_options so it survives daemon restarts.
        try:
            value = round(float(position_pct), 1)
            self.set_custom_channel_option(0, 'last_position_pct', value)
        except Exception as e:
            self.logger.warning("save_position failed: %s", e)
