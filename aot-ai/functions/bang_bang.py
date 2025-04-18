# coding=utf-8
#
#  bang_bang.py - A hysteretic control for On/Off Outputs
#
#  Copyright (C) 2015-2020 Rob Bultman <rob@firstbuild.com>
#
import time

from flask_babel import lazy_gettext

from aot-ai.databases.models import CustomController
from aot-ai.functions.base_function import AbstractFunction
from aot-ai.aot-ai_client import DaemonControl
from aot-ai.utils.constraints_pass import constraints_pass_positive_value
from aot-ai.utils.database import db_retrieve_table_daemon

# TODO: Remove this at next major version (obsolete because a On/Off Raise/Lower/Both Bang-Bang exists
FUNCTION_INFORMATION = {
    'function_name_unique': 'bang_bang',
    'function_name': '뱅-뱅 히스테릭(On/Off) (Raise/Lower)',
    'function_name_short': 'Bang-Bang (On/Off, Raise/Lower)',

    'message': '단순한 Bang-Bang 제어 방식으로, 하나의 입력값을 사용하여 하나의 출력을 제어합니다.'
               '입력을 선택하고, **출력, 설정값(Setpoint), 히스테리시스(Hysteresis)**를 입력한 후, 방향(Direction)을 선택하세요.'
               '	•	Raise 모드 (예: 난방): 입력값이 (설정값 - 히스테리시스) 이하일 때 출력이 켜지고, 입력값이 (설정값 + 히스테리시스) 이상일 때 출력이 꺼집니다.'
               '	•	Lower 모드 (예: 냉각): 위 동작과 반대로, 입력값을 낮추기 위해 출력을 켜려 합니다.',

    'options_disabled': [
        'measurements_select',
        'measurements_configure'
    ],

    'custom_options': [
        {
            'id': 'measurement',
            'type': 'select_measurement',
            'default_value': '',
            'required': True,
            'options_select': [
                'Input',
                'Function'
            ],
            'name': lazy_gettext('Measurement'),
            'phrase': lazy_gettext('Select a measurement the selected output will affect')
        },
        {
            'id': 'measurement_max_age',
            'type': 'integer',
            'default_value': 360,
            'required': True,
            'name': "{}: {} ({})".format(lazy_gettext("Measurement"), lazy_gettext("Max Age"),
                                           lazy_gettext("Seconds")),
            'phrase': lazy_gettext('The maximum age of the measurement to use')
        },
        {
            'id': 'output',
            'type': 'select_measurement_channel',
            'default_value': '',
            'required': True,
            'options_select': [
                'Output_Channels_Measurements',
            ],
            'name': lazy_gettext('Output'),
            'phrase': lazy_gettext('Select an output to control that will affect the measurement')
        },
        {
            'id': 'setpoint',
            'type': 'float',
            'default_value': 50,
            'required': True,
            'name': lazy_gettext('Setpoint'),
            'phrase': lazy_gettext('The desired setpoint')
        },
        {
            'id': 'hysteresis',
            'type': 'float',
            'default_value': 1,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Hysteresis'),
            'phrase': lazy_gettext('The amount above and below the setpoint that defines the control band')
        },
        {
            'id': 'direction',
            'type': 'select',
            'default_value': 'raise',
            'required': True,
            'options_select': [
                ('raise', 'Raise'),
                ('lower', 'Lower')
            ],
            'name': lazy_gettext('Direction'),
            'phrase': 'Raise means the measurement will increase when the control is on (heating). Lower means the measurement will decrease when the output is on (cooling)'
        },
        {
            'id': 'update_period',
            'type': 'float',
            'default_value': 5,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': "{} ({})".format(lazy_gettext('Period'), lazy_gettext('Seconds')),
            'phrase': lazy_gettext('The duration between measurements or actions')
        }
    ]
}


class CustomModule(AbstractFunction):
    """
    Class to operate custom controller
    """
    def __init__(self, function, testing=False):
        super().__init__(function, testing=testing, name=__name__)

        self.control_variable = None
        self.control = DaemonControl()
        self.outputIsOn = False
        self.timer_loop = time.time()

        # Initialize custom options
        self.measurement_device_id = None
        self.measurement_measurement_id = None
        self.measurement_max_age = None
        self.output_device_id = None
        self.output_measurement_id = None
        self.output_channel_id = None
        self.setpoint = None
        self.hysteresis = None
        self.direction = None
        self.output_channel = None
        self.update_period = None

        # Set custom options
        custom_function = db_retrieve_table_daemon(
            CustomController, unique_id=self.unique_id)
        self.setup_custom_options(
            FUNCTION_INFORMATION['custom_options'], custom_function)

        if not testing:
            self.try_initialize()

    def initialize(self):
        self.output_channel = self.get_output_channel_from_channel_id(
            self.output_channel_id)

        self.logger.info(
            "Bang-Bang controller started with options: "
            "Measurement Device: {}, Measurement: {}, Output: {}, "
            "Output_Channel: {}, Setpoint: {}, Hysteresis: {}, "
            "Direction: {}, Period: {}".format(
                self.measurement_device_id,
                self.measurement_measurement_id,
                self.output_device_id,
                self.output_channel,
                self.setpoint,
                self.hysteresis,
                self.direction,
                self.update_period))

    def loop(self):
        if self.timer_loop > time.time():
            return

        while self.timer_loop < time.time():
            self.timer_loop += self.update_period

        if self.output_channel is None:
            self.logger.error("Cannot run bang-bang controller: Check output channel.")
            return

        last_measurement = self.get_last_measurement(
            self.measurement_device_id,
            self.measurement_measurement_id,
            max_age=self.measurement_max_age)

        if not last_measurement:
            self.logger.error("Could not acquire a measurement")
            return

        output_state = self.control.output_state(self.output_device_id, self.output_channel)

        self.logger.debug(
            f"Input: {last_measurement[1]}, output: {output_state}, target: {self.setpoint}, hyst: {self.hysteresis}")

        if self.direction == 'raise':
            if last_measurement[1] > (self.setpoint + self.hysteresis):
                if output_state == 'on':
                    self.control.output_off(
                        self.output_device_id,
                        output_channel=self.output_channel)
            else:
                if last_measurement[1] < (self.setpoint - self.hysteresis):
                    self.control.output_on(
                        self.output_device_id,
                        output_channel=self.output_channel)
        elif self.direction == 'lower':
            if last_measurement[1] < (self.setpoint - self.hysteresis):
                if output_state == 'on':
                    self.control.output_off(
                        self.output_device_id,
                        output_channel=self.output_channel)
            else:
                if last_measurement[1] > (self.setpoint + self.hysteresis):
                    self.control.output_on(
                        self.output_device_id,
                        output_channel=self.output_channel)
        else:
            self.logger.error("Unknown controller direction: '{}'".format(self.direction))

    def stop_function(self):
        self.control.output_off(self.output_device_id, self.output_channel)
