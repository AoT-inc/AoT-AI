# coding=utf-8
#
# on_off_mqtt_farmon_v1.py - Output for FarmOn v1 boards (MQTT toggle protocol).
#
# Derived from on_off_mqtt_multi.py.
#
# Protocol (FarmOn firmware v8.5x ~):
#   Control (app -> board):
#       topic   : w-<MAC>/appTopic
#       payload : "#a{nnn}*{password}@"
#         - relays  1~8  -> nnn = "001".."008"
#         - relays  9~16 -> nnn = "109".."116"   (NOT "009".."016")
#         - password is PER-CHANNEL (each relay has its own code, e.g. 49185, 12321...)
#         - "#a{nnn}*@" if a channel has no password
#       NOTE    : single command TOGGLES the channel. Idempotency is handled here.
#
#   Status (board -> app):
#       topic   : w-<MAC>/mcuTopic
#       payload : "d:<HEX20>:<sensors...>:<extras...>/<HH:MM:SS:DOW>/<ver>/<n_relay>/<modes>"
#       relay state lives in 4 nibbles of HEX20:
#           HEX20[0]  = Hex0  -> relays 1-4   (bit0..3)
#           HEX20[1]  = Hex1  -> relays 5-8
#           HEX20[11] = Hex11 -> relays 9-12
#           HEX20[12] = Hex12 -> relays 13-16
#       bit set (=1) -> relay ON.
#
import json
import re
import threading

from flask_babel import lazy_gettext

from aot.databases.models import OutputChannel
from aot.outputs.base_output import AbstractOutput
from aot.utils.constraints_pass import constraints_pass_positive_or_zero_value
from aot.utils.database import db_retrieve_table_daemon
from aot.utils.utils import random_alphanumeric

measurements_dict = {
    0: {
        'measurement': 'duration_time',
        'unit': 's'
    }
}

channels_dict = {
    0: {
        'types': ['on_off'],
        'measurements': [0]
    }
}

# d:HHHHHHHHHHHHHHHHHHHH:...  — 20 hex chars right after "d:"
FARMON_HEX_RE = re.compile(r'^d:([0-9A-Fa-f]{20})')

# Toggle payload format: "#a{nnn}*{pw}@"
FARMON_PAYLOAD_RE = re.compile(r'^#a(\d{3})\*[^@]*@$')


def _relay_from_payload(payload):
    """Parse a FarmOn toggle payload and return the relay number 1~16, or None."""
    if not payload:
        return None
    m = FARMON_PAYLOAD_RE.match(payload.strip())
    if not m:
        return None
    nnn = int(m.group(1))
    if 1 <= nnn <= 8:
        return nnn
    if 109 <= nnn <= 116:
        return nnn - 100
    return None

OUTPUT_INFORMATION = {
    'output_name_unique': 'MQTT_FARMON_V1',
    'output_name': "{}: MQTT Publish FarmOn v1".format(lazy_gettext('On/Off')),
    'output_manufacturer': 'FarmOn',
    'output_library': 'paho-mqtt',
    'measurements_dict': measurements_dict,
    'channels_dict': channels_dict,
    'output_types': ['on_off'],

    'url_additional': 'http://www.eclipse.org/paho/',

    'message': (
        'FarmOn v1 board controller. Publishes toggle commands of the form '
        '"#a{nnn}*{password}@" to the Control Topic and parses "d:<HEX20>:..." '
        'status frames on the Status Topic. Each channel maps to a relay number '
        '(1~16); ON/OFF is the bit of that relay in the appropriate HEX nibble. '
        'Toggle commands are sent only when current state differs from target.'
    ),

    'dependencies_module': [
        ('pip-pypi', 'paho', 'paho-mqtt==1.5.1')
    ],

    'execute_at_modification': None,  # set below

    'options_enabled': [
        'button_on',
        'button_send_duration'
    ],
    'options_disabled': ['interface'],

    'interfaces': ['IP'],

    # ── 공통(디바이스 레벨) 설정 ──────────────────────────────────────────
    'custom_options': [
        {
            'id': 'num_channels',
            'type': 'integer',
            'default_value': 1,
            'required': True,
            'name': lazy_gettext('Number of Channels'),
            'phrase': 'Number of channels. Save to add or remove channel rows.'
        },
        {
            'id': 'hostname',
            'type': 'text',
            'default_value': 'localhost',
            'required': True,
            'name': lazy_gettext('Hostname'),
            'phrase': 'The hostname of the MQTT server'
        },
        {
            'id': 'port',
            'type': 'integer',
            'default_value': 1883,
            'required': True,
            'name': lazy_gettext('Port'),
            'phrase': 'The port of the MQTT server'
        },
        {
            'id': 'topic_control',
            'type': 'text',
            'default_value': 'w-XXXXXX/appTopic',
            'required': True,
            'name': lazy_gettext('Control Topic'),
            'phrase': 'FarmOn appTopic. Example: w-c0e93a/appTopic'
        },
        {
            'id': 'topic_status',
            'type': 'text',
            'default_value': 'w-XXXXXX/mcuTopic',
            'required': False,
            'name': lazy_gettext('Status Topic'),
            'phrase': 'FarmOn mcuTopic. Example: w-c0e93a/mcuTopic. '
                      'Leave blank to disable status feedback.'
        },
        {
            'id': 'keepalive',
            'type': 'integer',
            'default_value': 60,
            'required': True,
            'constraints_pass': constraints_pass_positive_or_zero_value,
            'name': lazy_gettext('Keep Alive'),
            'phrase': 'The keepalive timeout value for the client. Set to 0 to disable.'
        },
        {
            'id': 'clientid',
            'type': 'text',
            'default_value': 'client_{}'.format(random_alphanumeric(8)),
            'required': True,
            'name': 'Client ID',
            'phrase': 'Unique client ID for connecting to the MQTT server'
        },
        {
            'id': 'login',
            'type': 'bool',
            'default_value': False,
            'name': 'Use Login',
            'phrase': 'Send broker login credentials'
        },
        {
            'id': 'username',
            'type': 'text',
            'default_value': 'user',
            'required': False,
            'name': lazy_gettext('Username'),
            'phrase': 'Broker username'
        },
        {
            'id': 'password',
            'type': 'text',
            'default_value': '',
            'required': False,
            'name': lazy_gettext('Password'),
            'phrase': 'Broker password. Leave blank to disable.'
        },
        {
            'id': 'mqtt_use_websockets',
            'type': 'bool',
            'default_value': False,
            'required': False,
            'name': 'Use Websockets',
            'phrase': 'Use websockets to connect to the server.'
        }
    ],

    # ── 채널별 설정 ───────────────────────────────────────────────────────
    'custom_channel_options': [
        {
            'id': 'name',
            'type': 'text',
            'default_value': '',
            'required': False,
            'name': lazy_gettext('Channel Name'),
            'phrase': 'A friendly name shown in the UI for this channel.'
        },
        {
            'id': 'toggle_payload',
            'type': 'text',
            'default_value': '-',
            'required': True,
            'name': lazy_gettext('Toggle Payload'),
            'phrase': 'Full FarmOn toggle command. Example: #a001*49185@ (relay 1) or '
                      '#a109*64551@ (relay 9). Relay number is parsed from this string '
                      'and used to locate the matching bit in the status frame.'
        },
        {
            'id': 'state_startup',
            'type': 'select',
            'default_value': -1,
            'options_select': [
                (-1, 'Do Nothing'),
                (0, 'Off'),
                (1, 'On')
            ],
            'name': lazy_gettext('Startup State'),
            'phrase': 'Set the channel state when AoT starts'
        },
        {
            'id': 'state_shutdown',
            'type': 'select',
            'default_value': -1,
            'options_select': [
                (-1, 'Do Nothing'),
                (0, 'Off'),
                (1, 'On')
            ],
            'name': lazy_gettext('Shutdown State'),
            'phrase': 'Set the channel state when AoT shuts down'
        },
        {
            'id': 'amps',
            'type': 'float',
            'default_value': 0.0,
            'required': True,
            'name': "{} ({})".format(lazy_gettext('Current'), lazy_gettext('Amps')),
            'phrase': 'The current draw of the device being controlled'
        }
    ]
}


def execute_at_modification(
        messages,
        mod_output,
        request_form,
        custom_options_dict_presave,
        custom_options_channels_dict_presave,
        custom_options_dict_postsave,
        custom_options_channels_dict_postsave):
    """Add or remove OutputChannel records when num_channels changes."""
    from aot.aot_flask.extensions import db

    messages["page_refresh"] = True

    try:
        num_channels = int(custom_options_dict_postsave.get('num_channels', 1))
        if num_channels < 1:
            num_channels = 1
        if num_channels > 16:
            num_channels = 16
    except (TypeError, ValueError):
        num_channels = 1

    current_channels = OutputChannel.query.filter(
        OutputChannel.output_id == mod_output.unique_id
    ).order_by(OutputChannel.channel).all()
    current_count = len(current_channels)

    if num_channels < current_count:
        for ch in current_channels[num_channels:]:
            db.session.delete(ch)

    elif num_channels > current_count:
        for i in range(current_count, num_channels):
            new_ch = OutputChannel()
            new_ch.output_id = mod_output.unique_id
            new_ch.channel = i
            new_ch.custom_options = json.dumps({
                'name': '',
                'toggle_payload': '-',
                'state_startup': -1,
                'state_shutdown': -1,
                'amps': 0.0
            })
            db.session.add(new_ch)

    mod_output.size_y = num_channels + 1

    return (
        messages,
        mod_output,
        custom_options_dict_postsave,
        custom_options_channels_dict_postsave
    )


OUTPUT_INFORMATION['execute_at_modification'] = execute_at_modification


def _hex_nibble_for_relay(hex20, relay_number):
    """Return (nibble_value, bit_index) for given relay 1~16, or (None, None)."""
    if not hex20 or len(hex20) < 20 or relay_number < 1 or relay_number > 16:
        return None, None
    # relay 1-4 -> hex20[0], 5-8 -> [1], 9-12 -> [11], 13-16 -> [12]
    if 1 <= relay_number <= 4:
        pos, base = 0, 1
    elif 5 <= relay_number <= 8:
        pos, base = 1, 5
    elif 9 <= relay_number <= 12:
        pos, base = 11, 9
    else:
        pos, base = 12, 13
    try:
        return int(hex20[pos], 16), relay_number - base
    except ValueError:
        return None, None


class OutputModule(AbstractOutput):
    """FarmOn v1 MQTT toggle controller.

    @phase active
    @stability experimental
    @dependency AbstractOutput, paho-mqtt
    """

    def __init__(self, output, testing=False):
        super().__init__(output, testing=testing, name=__name__)

        self.publish = None
        self.status_client = None
        self._status_lock = threading.Lock()

        # device-level (set via setup_custom_options)
        self.num_channels = None
        self.hostname = None
        self.port = None
        self.topic_control = None
        self.topic_status = None
        self.keepalive = None
        self.clientid = None
        self.login = None
        self.username = None
        self.password = None
        self.mqtt_use_websockets = None

        output_channels = db_retrieve_table_daemon(
            OutputChannel).filter(OutputChannel.output_id == self.output.unique_id).all()
        self.options_channels = self.setup_custom_channel_options_json(
            OUTPUT_INFORMATION['custom_channel_options'], output_channels)

    def initialize(self):
        import paho.mqtt.publish as publish

        self.publish = publish

        self.setup_output_variables(OUTPUT_INFORMATION)
        self.setup_custom_options(OUTPUT_INFORMATION['custom_options'], self.output)

        # Register all runtime channels in base class dicts (channels_dict only defines ch0)
        for ch in self.options_channels.get('toggle_payload', {}):
            if ch not in self.output_states:
                self.output_states[ch] = None
                self.output_off_triggered[ch] = False
                self.output_time_turned_on[ch] = None
                self.output_on_duration[ch] = False
                self.output_last_duration[ch] = 0
                self.output_off_until[ch] = 0
                self._started_at_written[ch] = False
                # output_on_until intentionally omitted: loop checks `ch in output_on_until`
                # first; None would cause TypeError on `None < datetime` comparison

        self.output_setup = True

        # Subscribe FIRST so startup state changes are observable
        if self.topic_status:
            self._start_status_subscriber()

        for ch in self.options_channels.get('toggle_payload', {}):
            state_startup = self.options_channels['state_startup'].get(ch, -1)
            if state_startup == 1:
                self.output_switch('on', output_channel=ch)
            elif state_startup == 0:
                self.output_switch('off', output_channel=ch)

    def _start_status_subscriber(self):
        """Connect a paho-mqtt Client and subscribe to the FarmOn mcuTopic."""
        try:
            import paho.mqtt.client as mqtt_client

            transport = 'websockets' if self.mqtt_use_websockets else 'tcp'
            sub_client_id = "{}_sub_{}".format(self.clientid or 'aot', random_alphanumeric(4))

            self.status_client = mqtt_client.Client(
                client_id=sub_client_id, transport=transport)

            if self.login:
                pwd = self.password if self.password else None
                self.status_client.username_pw_set(self.username, pwd)

            self.status_client.on_connect = self._on_status_connect
            self.status_client.on_message = self._on_status_message
            self.status_client.on_disconnect = self._on_status_disconnect

            self.status_client.connect(self.hostname, self.port, self.keepalive or 60)
            self.status_client.loop_start()
            self.logger.info(
                "FarmOn status subscriber started for topic '{}'".format(self.topic_status))
        except Exception as err:
            self.logger.error("Failed to start status subscriber: {}".format(err))
            self.status_client = None

    def _on_status_connect(self, client, userdata, flags, rc):
        if rc == 0:
            try:
                client.subscribe(self.topic_status)
                self.logger.info("Subscribed to FarmOn status topic: {}".format(self.topic_status))
            except Exception as err:
                self.logger.error("Subscribe failed: {}".format(err))
        else:
            self.logger.error("Status subscriber connect failed (rc={})".format(rc))

    def _on_status_disconnect(self, client, userdata, rc):
        if rc != 0:
            self.logger.warning("Status subscriber unexpectedly disconnected (rc={})".format(rc))

    def _on_status_message(self, client, userdata, msg):
        """Parse FarmOn 'd:<HEX20>:...' frame and refresh each channel's state."""
        # Reject frames not from this instance's configured status topic.
        # Without this guard, a wildcard subscription or a co-located FarmOn
        # board sharing the broker can leak its HEX20 state into this Output's
        # channels, making unrelated devices appear simultaneously ON.
        if msg.topic != self.topic_status:
            return
        try:
            payload = msg.payload.decode('utf-8', errors='replace').strip()
        except Exception:
            return

        m = FARMON_HEX_RE.match(payload)
        if not m:
            return
        hex20 = m.group(1)

        with self._status_lock:
            for ch, payload_str in self.options_channels.get('toggle_payload', {}).items():
                relay_number = _relay_from_payload(payload_str)
                if relay_number is None:
                    continue

                nibble, bit_idx = _hex_nibble_for_relay(hex20, relay_number)
                if nibble is None:
                    continue

                is_on = bool((nibble >> bit_idx) & 1)
                prev = self.output_states.get(ch)
                if prev is not is_on:
                    self.output_states[ch] = is_on
                    self.logger.debug(
                        "FarmOn ch {} (relay {}) -> {} (HEX0/1/11/12 nibble={}, bit={})".format(
                            ch, relay_number, 'ON' if is_on else 'OFF', nibble, bit_idx))

    def _auth_dict(self):
        if self.login:
            pwd = self.password if self.password else None
            return {"username": self.username, "password": pwd}
        return None

    def output_switch(self, state, output_type=None, amount=None, output_channel=0):
        """Toggle the FarmOn relay only when current cached state differs from target.

        The board's only command is a single-channel TOGGLE, so we make it idempotent
        here by comparing against the last known state from the mcuTopic feed.
        """
        try:
            payload = (self.options_channels.get('toggle_payload', {})
                       .get(output_channel, '') or '').strip()
            relay_number = _relay_from_payload(payload)
            if relay_number is None:
                self.logger.error(
                    "Invalid toggle_payload for channel {}: {!r} "
                    "(expected '#a{{nnn}}*{{pw}}@', nnn in 001-008 or 109-116)".format(
                        output_channel, payload))
                return

            target = True if state == 'on' else False if state == 'off' else None
            if target is None:
                self.logger.error("Unknown state '{}'".format(state))
                return

            current = self.output_states.get(output_channel)
            if current is target:
                self.logger.debug(
                    "FarmOn ch {} already {} — skip toggle".format(
                        output_channel, 'ON' if target else 'OFF'))
                return

            transport = 'websockets' if self.mqtt_use_websockets else 'tcp'

            self.publish.single(
                self.topic_control,
                payload,
                hostname=self.hostname,
                port=self.port,
                client_id=self.clientid,
                keepalive=self.keepalive,
                auth=self._auth_dict(),
                transport=transport)

            # Optimistic local update; will be reconciled by the next mcuTopic frame.
            self.output_states[output_channel] = target
            self.logger.debug(
                "FarmOn toggle sent: ch {} relay {} -> {}".format(
                    output_channel, relay_number, 'ON' if target else 'OFF'))

        except Exception as e:
            self.logger.error("State change error on channel {}: {}".format(output_channel, e))

    def is_on(self, output_channel=0):
        if self.is_setup():
            return self.output_states.get(output_channel, False)

    def is_setup(self):
        return self.output_setup

    def stop_output(self):
        """Called when Output is stopped."""
        if self.is_setup():
            for ch in self.options_channels.get('toggle_payload', {}):
                state_shutdown = self.options_channels['state_shutdown'].get(ch, -1)
                if state_shutdown == 1:
                    self.output_switch('on', output_channel=ch)
                elif state_shutdown == 0:
                    self.output_switch('off', output_channel=ch)

            if self.status_client is not None:
                try:
                    self.status_client.loop_stop()
                    self.status_client.disconnect()
                except Exception as err:
                    self.logger.warning("Status subscriber stop error: {}".format(err))
                self.status_client = None

        self.running = False
