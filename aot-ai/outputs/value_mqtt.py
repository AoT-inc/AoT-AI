# coding=utf-8
#
# value_mqtt.py - Output for publishing a value via MQTT
#
import copy

from flask_babel import lazy_gettext

from aot-ai.databases.models import OutputChannel
from aot-ai.outputs.base_output import AbstractOutput
from aot-ai.utils.constraints_pass import constraints_pass_positive_or_zero_value
from aot-ai.utils.database import db_retrieve_table_daemon
from aot-ai.utils.influx import add_measurements_influxdb
from aot-ai.utils.utils import random_alphanumeric

measurements_dict = {
    0: {
        'measurement': 'unitless',
        'unit': 'none'
    }
}

channels_dict = {
    0: {
        'types': ['value'],
        'measurements': [0]
    }
}

OUTPUT_INFORMATION = {
    'output_name_unique': 'MQTT_PAHO_VALUE',
    'output_name': "{}: MQTT Publish".format(lazy_gettext('Value')),
    'output_library': 'paho-mqtt',
    'output_manufacturer': 'AoT-AI',
    'measurements_dict': measurements_dict,
    'channels_dict': channels_dict,
    'output_types': ['value'],

    'url_additional': 'http://www.eclipse.org/paho/',

    'message': 'MQTT 서버로 값을 발행합니다.',

    'dependencies_module': [
        ('pip-pypi', 'paho', 'paho-mqtt==1.5.1')
    ],

    'options_enabled': [
        'button_send_value'
    ],

    'custom_channel_options': [
        {
            'id': 'hostname',
            'type': 'text',
            'default_value': 'localhost',
            'required': True,
            'name': lazy_gettext('호스트명'),
            'phrase': 'MQTT 서버의 호스트명을 입력하세요'
        },
        {
            'id': 'port',
            'type': 'integer',
            'default_value': 1883,
            'required': True,
            'name': lazy_gettext('포트'),
            'phrase': 'MQTT 서버의 포트를 입력하세요'
        },
        {
            'id': 'topic',
            'type': 'text',
            'default_value': 'paho/test/single',
            'required': True,
            'name': "토픽",
            'phrase': '발행에 사용할 토픽을 입력하세요'
        },
        {
            'id': 'keepalive',
            'type': 'integer',
            'default_value': 60,
            'required': True,
            'constraints_pass': constraints_pass_positive_or_zero_value,
            'name': lazy_gettext('유지 시간'),
            'phrase': '클라이언트의 유지 시간 타임아웃 값입니다. 0으로 설정하면 비활성화됩니다.'
        },
        {
            'id': 'clientid',
            'type': 'text',
            'default_value': 'client_{}'.format(random_alphanumeric(8)),
            'required': True,
            'name': "클라이언트 ID",
            'phrase': 'MQTT 서버에 연결하기 위한 고유한 클라이언트 ID를 입력하세요'
        },
        {
            'id': 'off_value',
            'type': 'integer',
            'default_value': 0,
            'required': True,
            'name': lazy_gettext('꺼짐 값'),
            'phrase': '꺼짐 명령 시 전송할 값을 입력하세요'
        },
        {
            'id': 'login',
            'type': 'bool',
            'default_value': False,
            'name': "로그인 사용",
            'phrase': '로그인 자격 증명을 전송합니다'
        },
        {
            'id': 'username',
            'type': 'text',
            'default_value': 'user',
            'required': False,
            'name': lazy_gettext('사용자 이름'),
            'phrase': '서버에 연결하기 위한 사용자 이름을 입력하세요'
        },
        {
            'id': 'password',
            'type': 'text',
            'default_value': '',
            'required': False,
            'name': lazy_gettext('비밀번호'),
            'phrase': '서버에 연결하기 위한 비밀번호를 입력하세요'
        },
        {
            'id': 'mqtt_use_websockets',
            'type': 'bool',
            'default_value': False,
            'required': False,
            'name': "웹소켓 사용",
            'phrase': '서버에 연결하기 위해 웹소켓을 사용합니다'
        }
    ]
}


class OutputModule(AbstractOutput):
    """An output support class that operates an output."""
    def __init__(self, output, testing=False):
        super().__init__(output, testing=testing, name=__name__)

        self.publish = None

        output_channels = db_retrieve_table_daemon(
            OutputChannel).filter(OutputChannel.output_id == self.output.unique_id).all()
        self.options_channels = self.setup_custom_channel_options_json(
            OUTPUT_INFORMATION['custom_channel_options'], output_channels)

    def initialize(self):
        import paho.mqtt.publish as publish

        self.publish = publish

        self.setup_output_variables(OUTPUT_INFORMATION)
        self.output_setup = True

    def output_switch(self, state, output_type=None, amount=None, output_channel=0):
        measure_dict = copy.deepcopy(measurements_dict)

        try:
            auth_dict = None
            if self.options_channels['login'][0]:
                if not self.options_channels['password'][0]:
                    self.options_channels['password'][0] = None
                auth_dict = {
                    "username": self.options_channels['username'][0],
                    "password": self.options_channels['password'][0]
                }

            if state == 'on' and amount is not None:
                self.publish.single(
                    self.options_channels['topic'][0],
                    amount,
                    hostname=self.options_channels['hostname'][0],
                    port=self.options_channels['port'][0],
                    client_id=self.options_channels['clientid'][0],
                    keepalive=self.options_channels['keepalive'][0],
                    auth=auth_dict,
                    transport='websockets' if self.options_channels['mqtt_use_websockets'][0] else 'tcp')
                self.output_states[output_channel] = amount
                measure_dict[0]['value'] = amount
            elif state == 'off':
                self.publish.single(
                    self.options_channels['topic'][0],
                    payload=self.options_channels['off_value'][0],
                    hostname=self.options_channels['hostname'][0],
                    port=self.options_channels['port'][0],
                    client_id=self.options_channels['clientid'][0],
                    keepalive=self.options_channels['keepalive'][0],
                    auth=auth_dict,
                    transport='websockets' if self.options_channels['mqtt_use_websockets'][0] else 'tcp')
                self.output_states[output_channel] = False
                measure_dict[0]['value'] = self.options_channels['off_value'][0]
        except Exception as e:
            self.logger.error("State change error: {}".format(e))
            return

        add_measurements_influxdb(self.unique_id, measure_dict)

    def is_on(self, output_channel=0):
        if self.is_setup():
            if output_channel is not None and output_channel in self.output_states:
                return self.output_states[output_channel]
            else:
                return self.output_states

    def is_setup(self):
        return self.output_setup
