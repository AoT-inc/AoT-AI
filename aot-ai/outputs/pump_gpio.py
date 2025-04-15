# coding=utf-8
#
# pump_gpio.py - Output for a generic pump controlled by a GPIO
#
import copy
import datetime
import threading
import time

from flask_babel import lazy_gettext

from aot-ai.databases.models import OutputChannel
from aot-ai.outputs.base_output import AbstractOutput
from aot-ai.utils.constraints_pass import constraints_pass_positive_or_zero_value
from aot-ai.utils.constraints_pass import constraints_pass_positive_value
from aot-ai.utils.database import db_retrieve_table_daemon
from aot-ai.utils.influx import add_measurements_influxdb

# Measurements
measurements_dict = {
    0: {
        'measurement': 'duration_time',
        'unit': 's',
        'name': 'Pump On',
    },
    1: {
        'measurement': 'volume',
        'unit': 'ml',
        'name': 'Dispense Volume',
    },
    2: {
        'measurement': 'duration_time',
        'unit': 's',
        'name': 'Dispense Duration',
    }
}

channels_dict = {
    0: {
        'types': ['volume', 'on_off'],
        'measurements': [0, 1, 2]
    }
}

# Output information
OUTPUT_INFORMATION = {
    'output_name_unique': 'peristaltic_pump',
    'output_name': "{}: Raspberry Pi GPIO (Pi <= 4)".format(lazy_gettext('Peristaltic Pump')),
    'output_library': 'RPi.GPIO',
    'measurements_dict': measurements_dict,
    'channels_dict': channels_dict,
    'output_types': ['volume', 'on_off'],

    'message': "이 출력은 일반 연축 펌프의 전원을 제어하기 위해 GPIO 핀을 HIGH와 LOW 상태로 전환합니다. "
               "이후 연축 펌프는 일정 시간 동안 작동하거나, 펌프의 최대 유량이 결정된 후 최대 유량 또는 지정된 유량에 따라 특정 부피를 분사하도록 지시할 수 있습니다.",

    'options_enabled': [
        'button_on',
        'button_send_volume',
        'button_send_duration'
    ],
    'options_disabled': ['interface'],

    'dependencies_module': [
        ('pip-pypi', 'RPi.GPIO', 'RPi.GPIO==0.7.1')
    ],

    'interfaces': ['GPIO'],
    
    'custom_options_message': "정확하게 특정 부피를 분사하기 위해서는 다음 옵션들을 올바르게 설정해야 합니다. 펌프의 유량을 결정하기 위해 먼저 유체 라인에서 공기를 제거하여 청소하십시오." 
                              "그 후, 펌프를 60초 동안 작동시켜 분사된 유체를 모으고, 마지막으로 모은 유체의 양(ml)을 '최고 속도 (ml/분)' 필드에 입력하세요. 이제 펌프가 정확하게 부피를 분사하도록 보정됩니다." ,
    'custom_channel_options': [
        {
            'id': 'pin',
            'type': 'integer',
            'default_value': None,
            'required': False,
            'constraints_pass': constraints_pass_positive_or_zero_value,
            'name': "{}: {} ({})".format(lazy_gettext('핀'), lazy_gettext('GPIO'), lazy_gettext('BCM')),
            'phrase': lazy_gettext('상태를 제어할 핀')
        },
        {
            'id': 'on_state',
            'type': 'select',
            'default_value': 1,
            'options_select': [
                (1, 'HIGH'),
                (0, 'LOW')
            ],
            'name': lazy_gettext('켜짐 상태'),
            'phrase': 'GPIO에서 켜짐 상태에 해당하는 값'
        },
        {
            'id': 'fastest_dispense_rate_ml_min',
            'type': 'float',
            'default_value': 150.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Fastest Rate (ml/min)',
            'phrase': '펌프가 가장 빠르게 분사할 수 있는 속도 (ml/분)'
        },
        {
            'id': 'minimum_sec_on_per_min',
            'type': 'float',
            'default_value': 1.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Minimum On (Seconds)',
            'phrase': '60초 동안 펌프가 최소한 켜져 있어야 하는 시간 (초)'
        },
        {
            'id': 'flow_mode',
            'type': 'select',
            'default_value': 'fastest_flow_rate',
            'options_select': [
                ('fastest_flow_rate', 'Fastest Flow Rate'),
                ('specify_flow_rate', 'Specify Flow Rate')
            ],
            'name': 'Flow Rate Method',
            'phrase': '펌프로 분사할 때 사용할 유량 방식'
        },
        {
            'id': 'flow_rate',
            'type': 'float',
            'default_value': 10.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': "{} ({})".format(lazy_gettext('희망 유량'), lazy_gettext('ml/분')),
            'phrase': 'Specify Flow Rate가 설정되었을 때 원하는 유량 (ml/분)'
        },
        {
            'id': 'amps',
            'type': 'float',
            'default_value': 0.0,
            'required': True,
            'name': "{} ({})".format(lazy_gettext('현재'), lazy_gettext('암페어')),
            'phrase': '제어되는 장치의 전류 소모'
        }
    ]
}


class OutputModule(AbstractOutput):
    """An output support class that operates an output."""
    def __init__(self, output, testing=False):
        super().__init__(output, testing=testing, name=__name__)

        self.GPIO = None
        self.currently_dispensing = False

        output_channels = db_retrieve_table_daemon(
            OutputChannel).filter(OutputChannel.output_id == self.output.unique_id).all()
        self.options_channels = self.setup_custom_channel_options_json(
            OUTPUT_INFORMATION['custom_channel_options'], output_channels)

    def initialize(self):
        import RPi.GPIO as GPIO

        self.GPIO = GPIO

        self.setup_output_variables(OUTPUT_INFORMATION)

        if self.options_channels['pin'][0] is None:
            self.logger.warning("Invalid pin for output: {}.".format(self.options_channels['pin'][0]))
            return

        try:
            try:
                self.GPIO.setmode(self.GPIO.BCM)
                self.GPIO.setwarnings(True)
                self.GPIO.setup(self.options_channels['pin'][0], self.GPIO.OUT)
                self.GPIO.output(self.options_channels['pin'][0], not self.options_channels['on_state'][0])
                self.output_setup = True
            except Exception as e:
                self.logger.error("Setup error: {}".format(e))
            state = 'LOW' if self.options_channels['on_state'][0] else 'HIGH'
            self.logger.info(
                "Output setup on pin {pin} and turned OFF (OFF={state})".format(
                    pin=self.options_channels['pin'][0], state=state))
        except Exception as except_msg:
            self.logger.exception(
                "Output was unable to be setup on pin {pin} with trigger={trigger}: {err}".format(
                    pin=self.options_channels['pin'][0],
                    trigger=self.options_channels['on_state'][0],
                    err=except_msg))

    def dispense_volume_fastest(self, amount, total_dispense_seconds):
        """Dispense at fastest flow rate, a 100 % duty cycle."""
        self.currently_dispensing = True
        self.logger.debug("Output turned on")
        self.GPIO.output(self.options_channels['pin'][0], self.options_channels['on_state'][0])
        timer_dispense = time.time() + total_dispense_seconds
        timestamp_start = datetime.datetime.utcnow()

        while time.time() < timer_dispense and self.currently_dispensing:
            time.sleep(0.01)

        self.GPIO.output(self.options_channels['pin'][0], not self.options_channels['on_state'][0])
        self.currently_dispensing = False
        self.logger.debug("Output turned off")
        self.record_dispersal(amount, total_dispense_seconds, total_dispense_seconds, timestamp=timestamp_start)

    def dispense_volume_rate(self, amount, dispense_rate):
        """Dispense at a specific flow rate."""
        # Calculate total disperse time and durations to cycle on/off to reach total volume
        total_dispense_seconds = amount / dispense_rate * 60
        self.logger.debug("Total duration to run: {0:.1f} seconds".format(total_dispense_seconds))

        duty_cycle = dispense_rate / self.options_channels['fastest_dispense_rate_ml_min'][0]
        self.logger.debug("Duty Cycle: {0:.1f} %".format(duty_cycle * 100))

        total_seconds_on = total_dispense_seconds * duty_cycle
        self.logger.debug("Total seconds on: {0:.1f}".format(total_seconds_on))

        total_seconds_off = total_dispense_seconds - total_seconds_on
        self.logger.debug("Total seconds off: {0:.1f}".format(total_seconds_off))

        repeat_seconds_on = self.options_channels['minimum_sec_on_per_min'][0]
        repeat_seconds_off = self.options_channels['minimum_sec_on_per_min'][0] / duty_cycle
        self.logger.debug("Repeat for {rep:.2f} seconds: on {on:.1f} seconds, off {off:.1f} seconds".format(
            rep=repeat_seconds_off, on=repeat_seconds_on, off=repeat_seconds_off))

        self.currently_dispensing = True
        timer_dispense = time.time() + total_dispense_seconds
        timestamp_start = datetime.datetime.utcnow()

        while time.time() < timer_dispense and self.currently_dispensing:
            # On for duration
            timer_dispense_on = time.time() + repeat_seconds_on
            self.logger.debug("Output turned on")
            self.GPIO.output(self.options_channels['pin'][0], self.options_channels['on_state'][0])
            while time.time() < timer_dispense_on and self.currently_dispensing:
                time.sleep(0.01)

            # Off for duration
            timer_dispense_off = time.time() + repeat_seconds_off
            self.logger.debug("Output turned off")
            self.GPIO.output(self.options_channels['pin'][0], not self.options_channels['on_state'][0])
            while time.time() < timer_dispense_off and self.currently_dispensing:
                time.sleep(0.01)

        self.currently_dispensing = False
        self.record_dispersal(amount, total_seconds_on, total_dispense_seconds, timestamp=timestamp_start)

    def record_dispersal(self, amount, total_on_seconds, total_dispense_seconds, timestamp=None):
        measure_dict = copy.deepcopy(measurements_dict)
        measure_dict[0]['value'] = total_on_seconds
        measure_dict[1]['value'] = amount
        measure_dict[2]['value'] = total_dispense_seconds
        if timestamp:
            measure_dict[0]['timestamp_utc'] = timestamp
            measure_dict[1]['timestamp_utc'] = timestamp
            measure_dict[2]['timestamp_utc'] = timestamp
        add_measurements_influxdb(self.unique_id, measure_dict, use_same_timestamp=False)

    def output_switch(self, state, output_type=None, amount=None, output_channel=None):
        self.logger.debug("state: {}, output_type: {}, amount: {}".format(
            state, output_type, amount))

        if amount is not None and amount < 0:
            self.logger.error("Amount cannot be less than 0")
            return

        if state == 'off':
            if self.currently_dispensing:
                self.currently_dispensing = False
            self.logger.debug("Output turned off")
            self.GPIO.output(self.options_channels['pin'][0], not self.options_channels['on_state'][0])

        elif state == 'on' and output_type in ['vol', None] and amount:
            if self.currently_dispensing:
                self.logger.debug("Pump instructed to turn on for a volume while it's already dispensing. "
                                  "Overriding current dispense with new instruction.")

            if self.options_channels['flow_mode'][0] == 'fastest_flow_rate':
                total_dispense_seconds = amount / self.options_channels['fastest_dispense_rate_ml_min'][0] * 60
                msg = "Turning pump on for {sec:.1f} seconds to dispense {ml:.1f} ml (at {rate:.1f} ml/min, " \
                      "the fastest flow rate).".format(
                        sec=total_dispense_seconds,
                        ml=amount,
                        rate=self.options_channels['fastest_dispense_rate_ml_min'][0])
                self.logger.debug(msg)

                write_db = threading.Thread(
                    target=self.dispense_volume_fastest,
                    args=(amount, total_dispense_seconds,))
                write_db.start()
                return

            elif self.options_channels['flow_mode'][0] == 'specify_flow_rate':
                slowest_rate_ml_min = (self.options_channels['fastest_dispense_rate_ml_min'][0] /
                                       60 * self.options_channels['minimum_sec_on_per_min'][0])
                if self.options_channels['flow_rate'][0] < slowest_rate_ml_min:
                    self.logger.debug(
                        "Instructed to dispense {ir:.1f} ml/min, "
                        "however the slowest rate is set to {sr:.1f} ml/min.".format(
                            ir=self.options_channels['flow_rate'][0], sr=slowest_rate_ml_min))
                    dispense_rate = slowest_rate_ml_min
                elif self.options_channels['flow_rate'][0] > self.options_channels['fastest_dispense_rate_ml_min'][0]:
                    self.logger.debug(
                        "Instructed to dispense {ir:.1f} ml/min, "
                        "however the fastest rate is set to {fr:.1f} ml/min.".format(
                            ir=self.options_channels['flow_rate'][0],
                            fr=self.options_channels['fastest_dispense_rate_ml_min'][0]))
                    dispense_rate = self.options_channels['fastest_dispense_rate_ml_min'][0]
                else:
                    dispense_rate = self.options_channels['flow_rate'][0]

                self.logger.debug("Turning pump on to dispense {ml:.1f} ml at {rate:.1f} ml/min.".format(
                    ml=amount, rate=dispense_rate))

                write_db = threading.Thread(
                    target=self.dispense_volume_rate,
                    args=(amount, dispense_rate,))
                write_db.start()
                return

            else:
                self.logger.error("Invalid Output Mode: '{}'. Make sure it is properly set.".format(
                    self.options_channels['flow_mode'][0]))
                return

        elif state == 'on' and output_type == 'sec':
            if self.currently_dispensing:
                self.logger.debug(
                    "Pump instructed to turn on while it's already dispensing. "
                    "Overriding current dispense with new instruction.")
            self.logger.debug("Output turned on")
            self.GPIO.output(self.options_channels['pin'][0], self.options_channels['on_state'][0])

        else:
            self.logger.error(
                "Invalid parameters: State: {state}, Type: {ot}, Mode: {mod}, Amount: {amt}, Flow Rate: {fr}".format(
                    state=state,
                    ot=output_type,
                    mod=self.options_channels['flow_mode'][0],
                    amt=amount,
                    fr=self.options_channels['flow_rate'][0]))
            return

    def is_on(self, output_channel=None):
        if self.is_setup():
            try:
                if self.currently_dispensing:
                    return True
                return self.options_channels['on_state'][0] == self.GPIO.input(self.options_channels['pin'][0])
            except Exception as e:
                self.logger.error("Status check error: {}".format(e))

    def is_setup(self):
        return self.output_setup
