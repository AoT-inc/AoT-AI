# coding=utf-8
#
# on_off_gpio.py - Output for simple GPIO switching
#
from flask_babel import lazy_gettext

from aot-ai.databases.models import OutputChannel
from aot-ai.outputs.base_output import AbstractOutput
from aot-ai.utils.constraints_pass import constraints_pass_positive_or_zero_value
from aot-ai.utils.database import db_retrieve_table_daemon

# Measurements
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

# Output information
OUTPUT_INFORMATION = {
    'output_name_unique': 'wired',
    'output_name': "{}: Raspberry Pi GPIO (Pi <= 4)".format(lazy_gettext('On/Off')),
    'output_library': 'RPi.GPIO',
    'measurements_dict': measurements_dict,
    'channels_dict': channels_dict,
    'output_types': ['on_off'],

    'message': '지정된 GPIO 핀은 On State 옵션에 따라 켜지면 HIGH (3.3 볼트)로, 꺼지면 LOW (0 볼트)로 설정됩니다.',

    'options_enabled': [
        'button_on',
        'button_send_duration'
    ],
    'options_disabled': ['interface'],

    'dependencies_module': [
        ('pip-pypi', 'RPi.GPIO', 'RPi.GPIO==0.7.1')
    ],

    'interfaces': ['GPIO'],

    'custom_channel_options': [
        {
            'id': 'pin',
            'type': 'integer',
            'default_value': None,
            'required': False,
            'constraints_pass': constraints_pass_positive_or_zero_value,
            'name': "{}: {} ({})".format(lazy_gettext('Pin'), lazy_gettext('GPIO'), lazy_gettext('BCM')),
            'phrase': lazy_gettext('제어할 핀')
        },
        {
            'id': 'state_startup',
            'type': 'select',
            'default_value': 0,
            'options_select': [
                (0, 'Off'),
                (1, 'On')
            ],
            'name': lazy_gettext('시작 시 상태'),
            'phrase': 'AoT-AI 시작 시 상태 설정'
        },
        {
            'id': 'state_shutdown',
            'type': 'select',
            'default_value': 0,
            'options_select': [
                (0, 'Off'),
                (1, 'On')
            ],
            'name': lazy_gettext('종료 시 상태'),
            'phrase': 'AoT-AI 종료 시 상태 설정'
        },
        {
            'id': 'on_state',
            'type': 'select',
            'default_value': 1,
            'options_select': [
                (1, 'HIGH'),
                (0, 'LOW')
            ],
            'name': lazy_gettext('On 상태'),
            'phrase': 'On 상태에 해당하는 GPIO 상태'
        },
        {
            'id': 'trigger_functions_startup',
            'type': 'bool',
            'default_value': False,
            'name': lazy_gettext('시작 시 작동'),
            'phrase': '출력이 시작될 때 함수를 트리거할지 여부'
        },
        {
            'id': 'amps',
            'type': 'float',
            'default_value': 0.0,
            'required': True,
            'name': "{} ({})".format(lazy_gettext('사용'), lazy_gettext('전류')),
            'phrase': '제어되는 장치의 전류 소모'
        }
    ]
}


class OutputModule(AbstractOutput):
    """An output support class that operates an output."""
    def __init__(self, output, testing=False):
        super().__init__(output, testing=testing, name=__name__)

        self.GPIO = None

        output_channels = db_retrieve_table_daemon(
            OutputChannel).filter(OutputChannel.output_id == self.output.unique_id).all()
        self.options_channels = self.setup_custom_channel_options_json(
            OUTPUT_INFORMATION['custom_channel_options'], output_channels)

    def initialize(self):
        import RPi.GPIO as GPIO

        self.GPIO = GPIO

        self.setup_output_variables(OUTPUT_INFORMATION)

        if self.options_channels['pin'][0] is None:
            self.logger.error("Pin must be set")
        else:

            try:
                if self.options_channels['state_startup'][0]:
                    startup_state = self.options_channels['on_state'][0]
                else:
                    startup_state = not self.options_channels['on_state'][0]

                self.GPIO.setmode(self.GPIO.BCM)
                self.GPIO.setwarnings(True)
                self.GPIO.setup(self.options_channels['pin'][0], self.GPIO.OUT)
                self.GPIO.output(self.options_channels['pin'][0], startup_state)
                self.output_setup = True

                if self.options_channels['trigger_functions_startup'][0]:
                    try:
                        self.check_triggers(self.unique_id, output_channel=0)
                    except Exception as err:
                        self.logger.error(
                            "Could not check Trigger for channel 0 of output {}: {}".format(
                                self.unique_id, err))

                startup = 'ON' if self.options_channels['state_startup'][0] else 'OFF'
                state = 'HIGH' if self.options_channels['on_state'][0] else 'LOW'
                self.logger.info(
                    "Output setup on pin {pin} and turned {startup} (ON={state})".format(
                        pin=self.options_channels['pin'][0], startup=startup, state=state))
            except Exception as except_msg:
                self.logger.exception(
                    "Output was unable to be setup on pin {pin} with trigger={trigger}: {err}".format(
                        pin=self.options_channels['pin'][0],
                        trigger=self.options_channels['on_state'][0],
                        err=except_msg))

    def output_switch(self, state, output_type=None, amount=None, output_channel=0):
        try:
            if state == 'on':
                self.GPIO.output(self.options_channels['pin'][output_channel],
                                 self.options_channels['on_state'][output_channel])
            elif state == 'off':
                self.GPIO.output(self.options_channels['pin'][output_channel],
                                 not self.options_channels['on_state'][output_channel])
            msg = "success"
        except Exception as e:
            msg = "State change error: {}".format(e)
            self.logger.exception(msg)
        return msg

    def is_on(self, output_channel=0):
        if self.is_setup():
            try:
                return self.options_channels['on_state'][output_channel] == self.GPIO.input(
                    self.options_channels['pin'][output_channel])
            except Exception as e:
                self.logger.error("Status check error: {}".format(e))

    def is_setup(self):
        return self.output_setup

    def stop_output(self):
        """Called when Output is stopped."""
        if self.is_setup():
            if self.options_channels['state_shutdown'][0] == 1:
                self.output_switch('on', output_channel=0)
            elif self.options_channels['state_shutdown'][0] == 0:
                self.output_switch('off', output_channel=0)
        self.running = False
