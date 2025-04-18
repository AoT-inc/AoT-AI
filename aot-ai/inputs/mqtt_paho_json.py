# coding=utf-8
import datetime
import json

from flask_babel import lazy_gettext
from aot-ai.utils.actions import run_input_actions
from aot-ai.config_translations import TRANSLATIONS
from aot-ai.databases.models import Conversion
from aot-ai.databases.models import InputChannel
from aot-ai.inputs.base_input import AbstractInput
from aot-ai.utils.constraints_pass import constraints_pass_positive_value
from aot-ai.utils.database import db_retrieve_table_daemon
from aot-ai.utils.influx import add_measurements_influxdb
from aot-ai.utils.inputs import parse_measurement
from aot-ai.utils.utils import random_alphanumeric

# Measurements
measurements_dict = {}

# Channels
channels_dict = {
    0: {}
}

# Input information
INPUT_INFORMATION = {
    'input_name_unique': 'MQTT_PAHO_JSON',
    'input_manufacturer': 'MQTT',
    'input_name': 'MQTT 구독 (JSON 페이로드)',
    'input_name_short': 'MQTT JSON',
    'input_library': 'paho-mqtt, jmespath',
    'measurements_name': 'Variable measurements',
    'measurements_dict': measurements_dict,
    'channels_dict': channels_dict,

    'measurements_variable_amount': True,
    'channel_quantity_same_as_measurements': True,
    'measurements_use_same_timestamp': False,

    'message': (
        '하나의 토픽에 대해 구독하며, 반환된 JSON 페이로드에는 하나 이상의 키/값이 포함됩니다. '
        '지정된 JSON 키는 해당 채널에 저장될 값을 찾기 위한 JMESPATH 표현식으로 사용됩니다. '
        '각 채널의 측정 단위를 선택하고 저장했는지 확인하십시오. 단위가 저장되면, 측정 변환 섹션에서 다른 단위로 변환할 수 있습니다. '
        'jmespath(https://jmespath.org)의 예시 표현식으로는 <i>temperature</i>, <i>sensors[0].temperature</i>, '
        '및 <i>bathroom.temperature</i> 등이 있으며, 이는 각각 센서 배열의 첫 번째 항목 내의 직접 키 또는 '
        'bathroom의 하위 키로서 온도를 나타냅니다. 특수 문자가 포함된 jmespath 요소와 키는 반드시 큰따옴표로 감싸야 합니다. 예: <i>"sensor-1".temperature</i>. '
        '<br>경고: 여러 MQTT 입력 또는 기능을 사용할 경우, 클라이언트 ID가 고유한지 확인하십시오.'
    ),

    'options_enabled': [
        'measurements_select'
    ],
    'options_disabled': ['interface'],

    'interfaces': ['AoT-AI'],

    'dependencies_module': [
        ('pip-pypi', 'paho', 'paho-mqtt==1.5.1'),
        ('pip-pypi', 'jmespath', 'jmespath==0.10.0')
    ],

    'custom_options': [
        {
            'id': 'mqtt_hostname',
            'type': 'text',
            'default_value': 'localhost',
            'required': True,
            'name': TRANSLATIONS["host"]["title"],
            'phrase': TRANSLATIONS["host"]["phrase"]
        },
        {
            'id': 'mqtt_port',
            'type': 'integer',
            'default_value': 1883,
            'required': True,
            'name': TRANSLATIONS["port"]["title"],
            'phrase': TRANSLATIONS["port"]["phrase"]
        },
        {
            'id': 'mqtt_channel',
            'type': 'text',
            'default_value': 'mqtt/test/input',
            'required': True,
            'name': '토픽',
            'phrase': '구독할 토픽'
        },
        {
            'id': 'mqtt_keepalive',
            'type': 'integer',
            'default_value': 60,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('연결 유지 시간'),
            'phrase': '수신 신호 간 최대 시간입니다. 0으로 설정하면 비활성화됩니다.'
        },
        {
            'id': 'mqtt_clientid',
            'type': 'text',
            'default_value': 'client_{}'.format(random_alphanumeric(8)),
            'required': True,
            'name': '클라이언트 ID',
            'phrase': '서버에 연결하기 위한 고유 클라이언트 ID'
        },
        {
            'id': 'mqtt_login',
            'type': 'bool',
            'default_value': False,
            'name': '로그인 사용',
            'phrase': '로그인 자격 증명을 전송합니다.'
        },
        {
            'id': 'mqtt_use_tls',
            'type': 'bool',
            'default_value': False,
            'name': 'TLS 사용',
            'phrase': 'TLS를 사용하여 로그인 자격 증명을 전송합니다.'
        },
        {
            'id': 'mqtt_username',
            'type': 'text',
            'default_value': 'user',
            'required': False,
            'name': lazy_gettext('사용자 이름'),
            'phrase': lazy_gettext('서버 연결을 위한 사용자 이름')
        },
        {
            'id': 'mqtt_password',
            'type': 'text',
            'default_value': '',
            'required': False,
            'name': lazy_gettext('비밀번호'),
            'phrase': '서버 연결을 위한 비밀번호입니다. 비워두면 비활성화됩니다.'
        },
        {
            'id': 'mqtt_use_websockets',
            'type': 'bool',
            'default_value': False,
            'required': False,
            'name': '웹소켓 사용',
            'phrase': '서버에 연결하기 위해 웹소켓을 사용합니다.'
        }
    ],

    'custom_channel_options': [
        {
            'id': 'name',
            'type': 'text',
            'default_value': '',
            'required': False,
            'name': TRANSLATIONS['name']['title'],
            'phrase': TRANSLATIONS['name']['phrase']
        },
        {
            'id': 'json_name',
            'type': 'text',
            'default_value': '',
            'required': True,
            'name': 'JMESPATH 표현식',
            'phrase': 'JSON 응답에서 값을 찾기 위한 JMESPATH 표현식'
        }
    ]
}


class InputModule(AbstractInput):
    """A sensor support class that retrieves stored data from MQTT."""

    def __init__(self, input_dev, testing=False):
        super().__init__(input_dev, testing=testing, name=__name__)

        self.log_level_debug = None
        self.client = None
        self.jmespath = None
        self.options_channels = None

        self.mqtt_hostname = None
        self.mqtt_port = None
        self.mqtt_channel = None
        self.mqtt_keepalive = None
        self.mqtt_clientid = None
        self.mqtt_login = None
        self.mqtt_use_tls = None
        self.mqtt_username = None
        self.mqtt_password = None
        self.mqtt_use_websockets = None

        if not testing:
            self.setup_custom_options(
                INPUT_INFORMATION['custom_options'], input_dev)
            self.try_initialize()

    def initialize(self):
        import paho.mqtt.client as mqtt
        import jmespath

        self.jmespath = jmespath
        self.log_level_debug = self.input_dev.log_level_debug

        input_channels = db_retrieve_table_daemon(
            InputChannel).filter(InputChannel.input_id == self.input_dev.unique_id).all()
        self.options_channels = self.setup_custom_channel_options_json(
            INPUT_INFORMATION['custom_channel_options'], input_channels)

        self.client = mqtt.Client(
            self.mqtt_clientid,
            transport='websockets' if self.mqtt_use_websockets else 'tcp')
        self.logger.debug("Client created with ID {}".format(self.mqtt_clientid))
        if self.mqtt_login:
            if not self.mqtt_password:
                self.mqtt_password = None
            self.logger.debug("Sending username and password credentials")
            self.client.username_pw_set(self.mqtt_username, self.mqtt_password)
        if self.mqtt_use_tls:
            self.client.tls_set()

    def listener(self):
        self.callbacks_connect()
        self.connect()
        self.client.loop_start()

    def callbacks_connect(self):
        """Connect the callback functions."""
        try:
            self.logger.debug("Connecting MQTT callback functions")
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
            self.client.on_message = self.on_message
            self.client.on_subscribe = self.on_subscribe
            self.logger.debug("MQTT callback functions connected")
        except:
            self.logger.error("Unable to connect mqtt callback functions")

    def connect(self):
        """Set up the connection to the MQTT Server."""
        try:
            self.client.connect(
                self.mqtt_hostname,
                port=self.mqtt_port,
                keepalive=self.mqtt_keepalive)
            self.logger.info("Connected to {} as {}".format(
                self.mqtt_hostname, self.mqtt_clientid))
        except:
            self.logger.error("Could not connect to mqtt host: {}:{}".format(
                self.mqtt_hostname, self.mqtt_port))

    def subscribe(self):
        """Subscribe to the proper MQTT channel to listen to."""
        try:
            self.logger.debug("Subscribing to MQTT topic '{}'".format(
                self.mqtt_channel))
            self.client.subscribe(self.mqtt_channel)
        except:
            self.logger.error("Could not subscribe to MQTT channel '{}'".format(
                self.mqtt_channel))

    def on_connect(self, client, obj, flags, rc):
        self.logger.debug(f"Connected: {rc}")
        self.subscribe()

    def on_disconnect(self, client, userdata, rc):
        self.logger.debug(f"Disconnected: {rc}")

    def on_subscribe(self, client, obj, mid, granted_qos):
        self.logger.debug("Subscribed to mqtt topic: {}, {}, {}".format(
            self.mqtt_channel, mid, granted_qos))

    def on_log(self, mqttc, obj, level, string):
        self.logger.info("Log: {}".format(string))

    def on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode()
            self.logger.debug(
                "Received message: topic: {}, payload: {}".format(
                    msg.topic, payload))
        except Exception as exc:
            self.logger.error(
                "Payload could not be decoded: {}".format(exc))
            return

        try:
            json_values = json.loads(payload)
        except ValueError as err:
            self.logger.error(
                "Error parsing payload '{}' as JSON: {} ".format(
                    msg.payload.decode(), err))
            return

        datetime_utc = datetime.datetime.utcnow()
        measurement = {}
        for each_channel in self.channels_measurement:
            json_name = self.options_channels['json_name'][each_channel]
            self.logger.debug("Searching JSON for {}".format(json_name))

            try:
                jmesexpression = self.jmespath.compile(json_name)
                value = float(jmesexpression.search(json_values))
                self.logger.debug(
                    "Found key: {}, value: {}".format(json_name, value))
                measurement[each_channel] = {}
                measurement[each_channel]['measurement'] = self.channels_measurement[each_channel].measurement
                measurement[each_channel]['unit'] = self.channels_measurement[each_channel].unit
                measurement[each_channel]['value'] = value
                measurement[each_channel]['timestamp_utc'] = datetime_utc
                measurement = self.check_conversion(each_channel, measurement)
            except Exception as err:
                self.logger.error(
                    "Error in JSON '{}' finding '{}': {}".format(
                        json_values, json_name, err))

        message, measurement = run_input_actions(self.unique_id, "", measurement, self.log_level_debug)

        self.logger.debug(f"Adding measurement to influxdb: {measurement}")
        add_measurements_influxdb(
            self.unique_id,
            measurement,
            use_same_timestamp=INPUT_INFORMATION['measurements_use_same_timestamp'])

    def check_conversion(self, channel, measurement):
        # Convert value/unit is conversion_id present and valid
        try:
            if self.channels_conversion[channel]:
                conversion = db_retrieve_table_daemon(
                    Conversion,
                    unique_id=self.channels_measurement[channel].conversion_id)
                if conversion:
                    meas = parse_measurement(
                        self.channels_conversion[channel],
                        self.channels_measurement[channel],
                        measurement,
                        channel,
                        measurement[channel],
                        timestamp=measurement[channel]['timestamp_utc'])

                    measurement[channel]['measurement'] = meas[channel]['measurement']
                    measurement[channel]['unit'] = meas[channel]['unit']
                    measurement[channel]['value'] = meas[channel]['value']
        except:
            self.logger.exception("Checking conversion")
        
        return measurement

    def stop_input(self):
        """Called when Input is deactivated."""
        self.running = False
        self.client.loop_stop()
        self.client.disconnect()
