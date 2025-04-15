# coding=utf-8
#
# pump_pcf8574.py - Pump Output for PCF8574
#
import copy
import datetime
import threading
import time
from collections import OrderedDict

from flask_babel import lazy_gettext

from aot-ai.databases.models import OutputChannel
from aot-ai.outputs.base_output import AbstractOutput
from aot-ai.utils.constraints_pass import constraints_pass_positive_value
from aot-ai.utils.database import db_retrieve_table_daemon
from aot-ai.utils.influx import add_measurements_influxdb
from aot-ai.utils.lockfile import LockFile

# Measurements
measurements_dict = OrderedDict()
channels_dict = OrderedDict()
measure = 0
for each_channel in range(8):
    measurements_dict[measure] = {
        'measurement': 'duration_time',
        'unit': 's',
        'name': 'Pump On',
    }
    measurements_dict[measure + 1] = {
        'measurement': 'volume',
        'unit': 'ml',
        'name': 'Dispense Volume',
    }
    measurements_dict[measure + 2] = {
        'measurement': 'duration_time',
        'unit': 's',
        'name': 'Dispense Duration',
    }

    channels_dict[each_channel] = {
        'types': ['volume', 'on_off'],
        'measurements': [measure, measure + 1, measure + 2]
    }
    measure += 3

# Output information
OUTPUT_INFORMATION = {
    'output_name_unique': 'PCF8574_PUMP',
    'output_name': "{}: PCF8574 8-Channel {}".format(lazy_gettext('Peristaltic Pump'), lazy_gettext('I/O Expander')),
    'output_manufacturer': 'Texas Instruments',
    'output_library': 'smbus2',
    'measurements_dict': measurements_dict,
    'channels_dict': channels_dict,
    'output_types': ['volume', 'on_off'],

    'url_manufacturer': 'https://www.ti.com/product/PCF8574',
    'url_datasheet': 'https://www.ti.com/lit/ds/symlink/pcf8574.pdf',
    'url_product_purchase': 'https://www.amazon.com/gp/product/B07JGSNWFF',

    'message': 'Controls the 8 channels of the PCF8574 with a relay and peristaltic pump connected to each channel.',

    'options_enabled': [
        'i2c_location',
        'button_on',
        'button_send_duration'
    ],
    'options_disabled': ['interface'],

    'dependencies_module': [
        ('pip-pypi', 'smbus2', 'smbus2==0.4.1')
    ],

    'interfaces': ['I2C'],
    'i2c_location': [
        '0x20', '0x21', '0x22', '0x23', '0x24', '0x25', '0x26', '0x27',
        '0x38', '0x39', '0x3a', '0x3b', '0x3c', '0x3d', '0x3e', '0x3f'
    ],
    'i2c_address_editable': False,
    'i2c_address_default': '0x20',

    'custom_options_message': "To accurately dispense specific volumes, the following options need to be correctly "
                              "set. To determine the flow rate of your pump, first purge the fluid line to remove "
                              "air. Next, turn the pump on for 60 seconds and collect the fluid that's dispensed. "
                              "Last, measure and enter the amount of fluid that was dispensed, in ml, into the "
                              "Fastest Rate (ml/min) field. Your pump should now be calibrated to dispense volumes "
                              "accurately." ,
    'custom_channel_options': [
        {
            'id': 'on_state',
            'type': 'select',
            'default_value': 1,
            'options_select': [
                (1, 'HIGH'),
                (0, 'LOW')
            ],
            'name': lazy_gettext('On State'),
            'phrase': 'The state of the output channel that corresponds to the pump being on'
        },
        {
            'id': 'fastest_dispense_rate_ml_min',
            'type': 'float',
            'default_value': 150.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Fastest Rate (ml/min)',
            'phrase': 'The fastest rate that the pump can dispense (ml/min)'
        },
        {
            'id': 'minimum_sec_on_per_min',
            'type': 'float',
            'default_value': 1.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Minimum On (Seconds)',
            'phrase': 'The minimum duration the pump should be turned on for every 60 second period'
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
            'phrase': 'The flow rate to use when pumping a volume'
        },
        {
            'id': 'flow_rate',
            'type': 'float',
            'default_value': 10.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Desired Flow Rate (ml/min)',
            'phrase': 'Desired flow rate in ml/minute when Specify Flow Rate set'
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


class OutputModule(AbstractOutput):
    """An output support class that operates an output"""
    def __init__(self, output, testing=False):
        super().__init__(output, testing=testing, name=__name__)

        self.sensor = None
        self.lock_file = None
        self.output_states = {}
        self.currently_dispensing = {}

        output_channels = db_retrieve_table_daemon(
            OutputChannel).filter(OutputChannel.output_id == output.unique_id).all()
        self.options_channels = self.setup_custom_channel_options_json(
            OUTPUT_INFORMATION['custom_channel_options'], output_channels)

    def initialize(self):
        import smbus2

        self.setup_output_variables(OUTPUT_INFORMATION)

        try:
            self.logger.debug(f"I2C: Address: {self.output.i2c_location}, Bus: {self.output.i2c_bus}")
            if self.output.i2c_location:
                self.sensor = PCF8574(smbus2, self.output.i2c_bus, int(str(self.output.i2c_location), 16))
                self.lock_file = f'/var/lock/pcf8574_{self.output.i2c_bus}_{self.output.i2c_location}'
                self.output_setup = True
        except:
            self.logger.exception("Could not set up output")
            return

        dict_states = {}
        for channel in channels_dict:
            dict_states[channel] = bool(not self.options_channels['on_state'][channel])
            state = 'LOW' if self.options_channels['on_state'][channel] else 'HIGH'
            self.currently_dispensing[channel] = False
            self.logger.info(f"Output setup on channel {channel} and turned OFF (OFF={state})")

        try:
            self.sensor.port(self.dict_to_list_states(dict_states))
            self.logger.debug(f"List sent to device: {dict_states}")
        except OSError as err:
            self.logger.error(
                f"OSError: {err}. Check that the device is connected properly, the correct "
                "address is selected, and you can communicate with the device.")

        self.output_states = dict_states

    def turn_on_off(self, switch_channel, state):
        msg = ""
        lf = LockFile()
        if lf.lock_acquire(self.lock_file, timeout=10):
            try:
                dict_states = {}
                for channel in channels_dict:
                    if switch_channel == channel:
                        if state == 'on':
                            dict_states[channel] = bool(self.options_channels['on_state'][channel])
                            on_state = 'HIGH' if self.options_channels['on_state'][channel] else 'LOW'
                            self.logger.debug(f"Output turned on (Channel {channel} {on_state})")
                        elif state == 'off':
                            dict_states[channel] = bool(not self.options_channels['on_state'][channel])
                            off_state = 'LOW' if self.options_channels['on_state'][channel] else 'HIGH'
                            self.logger.debug(f"Output turned off (Channel {channel} {off_state})")
                    else:
                        dict_states[channel] = self.output_states[channel]

                self.sensor.port(self.dict_to_list_states(dict_states))
                self.logger.debug(f"List sent to device: {dict_states}")
                self.output_states[switch_channel] = dict_states[switch_channel]
                msg = "success"
            except Exception as err:
                msg = f"CH{switch_channel} state change error: {err}"
                self.logger.error(msg)
            finally:
                lf.lock_release(self.lock_file)

        return msg

    def dispense_volume_fastest(self, channel, amount, total_dispense_seconds):
        """Dispense at fastest flow rate, a 100 % duty cycle."""
        self.currently_dispensing[channel] = True
        self.logger.debug("Output turned on")
        self.turn_on_off(channel, "on")
        timer_dispense = time.time() + total_dispense_seconds
        timestamp_start = datetime.datetime.utcnow()

        while time.time() < timer_dispense and self.currently_dispensing[channel]:
            time.sleep(0.01)

        self.turn_on_off(channel, "off")
        self.currently_dispensing[channel] = False
        self.logger.debug("Output turned off")
        self.record_dispersal(channel, amount, total_dispense_seconds, total_dispense_seconds, timestamp=timestamp_start)

    def dispense_volume_rate(self, channel, amount, dispense_rate):
        """Dispense at a specific flow rate."""
        # Calculate total disperse time and durations to cycle on/off to reach total volume
        total_dispense_seconds = amount / dispense_rate * 60
        self.logger.debug(f"Total duration to run: {total_dispense_seconds:.1f} seconds")

        duty_cycle = dispense_rate / self.options_channels['fastest_dispense_rate_ml_min'][0]
        self.logger.debug(f"Duty Cycle: {duty_cycle * 100:.1f} %")

        total_seconds_on = total_dispense_seconds * duty_cycle
        self.logger.debug(f"Total seconds on: {total_seconds_on:.1f}")

        total_seconds_off = total_dispense_seconds - total_seconds_on
        self.logger.debug(f"Total seconds off: {total_seconds_off:.1f}")

        repeat_seconds_on = self.options_channels['minimum_sec_on_per_min'][0]
        repeat_seconds_off = self.options_channels['minimum_sec_on_per_min'][0] / duty_cycle
        self.logger.debug(
            f"Repeat for {repeat_seconds_off:.2f} seconds: "
            f"on {repeat_seconds_on:.1f} seconds, "
            f"off {repeat_seconds_off:.1f} seconds")

        self.currently_dispensing[channel] = True
        timer_dispense = time.time() + total_dispense_seconds
        timestamp_start = datetime.datetime.utcnow()

        while time.time() < timer_dispense and self.currently_dispensing[channel]:
            # On for duration
            timer_dispense_on = time.time() + repeat_seconds_on
            self.turn_on_off(channel, "on")
            while time.time() < timer_dispense_on and self.currently_dispensing[channel]:
                time.sleep(0.01)

            # Off for duration
            timer_dispense_off = time.time() + repeat_seconds_off
            self.turn_on_off(channel, "off")
            while time.time() < timer_dispense_off and self.currently_dispensing[channel]:
                time.sleep(0.01)

        self.currently_dispensing[channel] = False
        self.f(amount, total_seconds_on, total_dispense_seconds, timestamp=timestamp_start)

    def record_dispersal(self, channel, amount, total_on_seconds, total_dispense_seconds, timestamp=None):
        measure_dict = copy.deepcopy(measurements_dict)
        measure_dict[channel * 3]['value'] = total_on_seconds
        measure_dict[(channel * 3) + 1]['value'] = amount
        measure_dict[(channel * 3) + 2]['value'] = total_dispense_seconds
        if timestamp:
            measure_dict[channel * 3]['timestamp_utc'] = timestamp
            measure_dict[(channel * 3) + 1]['timestamp_utc'] = timestamp
            measure_dict[(channel * 3) + 2]['timestamp_utc'] = timestamp
        add_measurements_influxdb(self.unique_id, measure_dict, use_same_timestamp=False)

    def output_switch(self, state, output_type=None, amount=None, output_channel=None):
        if output_channel is None:
            msg = "Output channel needs to be specified"
            self.logger.error(msg)
            return msg

        if amount is not None and amount < 0:
            self.logger.error("Amount cannot be less than 0")
            return

        self.logger.debug(f"state: {state}, output_type: {output_type}, amount: {amount}")

        if state == 'off':
            if self.currently_dispensing[output_channel]:
                self.currently_dispensing[output_channel] = False
            self.turn_on_off(output_channel, "off")

        elif state == 'on' and output_type in ['vol', None] and amount is not None:
            if self.currently_dispensing[output_channel]:
                self.logger.debug("Pump instructed to turn on for a volume while it's already dispensing. "
                                  "Overriding current dispense with new instruction.")

            if self.options_channels['flow_mode'][output_channel] == 'fastest_flow_rate':
                total_dispense_seconds = amount / self.options_channels['fastest_dispense_rate_ml_min'][output_channel] * 60
                msg = f"Turning pump on for {total_dispense_seconds:.1f} seconds to dispense {amount:.1f} ml " \
                      f"(at {self.options_channels['fastest_dispense_rate_ml_min'][output_channel]:.1f} ml/min, " \
                      f"the fastest flow rate)."
                self.logger.debug(msg)

                write_db = threading.Thread(
                    target=self.dispense_volume_fastest,
                    args=(output_channel, amount, total_dispense_seconds,))
                write_db.start()
                return

            elif self.options_channels['flow_mode'][output_channel] == 'specify_flow_rate':
                slowest_rate_ml_min = (self.options_channels['fastest_dispense_rate_ml_min'][output_channel] /
                                       60 * self.options_channels['minimum_sec_on_per_min'][output_channel])
                if self.options_channels['flow_rate'][output_channel] < slowest_rate_ml_min:
                    self.logger.debug(
                        f"Instructed to dispense {self.options_channels['flow_rate'][output_channel]:.1f} ml/min, "
                        f"however the slowest rate is set to {slowest_rate_ml_min:.1f} ml/min.")
                    dispense_rate = slowest_rate_ml_min
                elif self.options_channels['flow_rate'][output_channel] > self.options_channels['fastest_dispense_rate_ml_min'][output_channel]:
                    self.logger.debug(
                        f"Instructed to dispense {self.options_channels['flow_rate'][output_channel]:.1f} ml/min, "
                        f"however the fastest rate is set to {self.options_channels['fastest_dispense_rate_ml_min'][output_channel]:.1f} ml/min.")
                    dispense_rate = self.options_channels['fastest_dispense_rate_ml_min'][output_channel]
                else:
                    dispense_rate = self.options_channels['flow_rate'][output_channel]

                self.logger.debug(f"Turning pump on to dispense {amount:.1f} ml at {dispense_rate:.1f} ml/min.")

                write_db = threading.Thread(
                    target=self.dispense_volume_rate,
                    args=(output_channel, amount, dispense_rate,))
                write_db.start()
                return

            else:
                self.logger.error(f"Invalid Output Mode: '{self.options_channels['flow_mode'][output_channel]}'. "
                                  f"Make sure it is properly set.")
                return

        elif state == 'on' and output_type == 'sec':
            if self.currently_dispensing[output_channel]:
                self.logger.debug(
                    "Pump instructed to turn on while it's already dispensing. "
                    "Overriding current dispense with new instruction.")
            self.turn_on_off(output_channel, "on")

        else:
            self.logger.error(
                f"Invalid parameters: State: {state}, "
                f"Type: {output_type}, "
                f"Mode: {self.options_channels['flow_mode'][output_channel]}, "
                f"Amount: {amount}, "
                f"Flow Rate: {self.options_channels['flow_rate'][output_channel]}")
            return

    def is_on(self, output_channel=None):
        if self.is_setup():
            return self.output_states[output_channel] == bool(self.options_channels['on_state'][output_channel])

    def is_setup(self):
        return self.output_setup

    @staticmethod
    def dict_to_list_states(dict_states):
        list_states = []
        for i, _ in enumerate(dict_states):
            list_states.append(dict_states[i])
        return list_states

    def stop_output(self):
        """Called when Output is stopped."""
        dict_states = {}
        if self.is_setup():
            for channel in channels_dict:
                dict_states[channel] = bool(not self.options_channels['on_state'][channel])
            self.sensor.port(self.dict_to_list_states(dict_states))
            self.logger.debug(f"List sent to device: {dict_states}")
        self.running = False


class PCF8574(object):
    """A software representation of a single PCF8574 IO expander chip."""
    def __init__(self, smbus, i2c_bus, i2c_address):
        self.bus_no = i2c_bus
        self.bus = smbus.SMBus(i2c_bus)
        self.address = i2c_address

    def __repr__(self):
        return f"PCF8574(i2c_bus_no={self.bus_no}, address={self.address})"

    def port(self, value):
        """Set the whole port using a list"""
        if not isinstance(value, list):
            raise AssertionError
        if len(value) != 8:
            raise AssertionError
        new_state = 0
        for i, val in enumerate(value):
            if val:
                new_state |= 1 << i
        self.bus.write_byte(self.address, new_state)
