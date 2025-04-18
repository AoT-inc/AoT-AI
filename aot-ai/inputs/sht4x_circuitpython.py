# coding=utf-8
import copy

from aot-ai.inputs.base_input import AbstractInput
from aot-ai.inputs.sensorutils import calculate_dewpoint
from aot-ai.inputs.sensorutils import calculate_vapor_pressure_deficit

# Measurements
measurements_dict = {
    0: {
        'measurement': 'temperature',
        'unit': 'C'
    },
    1: {
        'measurement': 'humidity',
        'unit': 'percent'
    },
    2: {
        'measurement': 'dewpoint',
        'unit': 'C'
    },
    3: {
        'measurement': 'vapor_pressure_deficit',
        'unit': 'Pa'
    }
}

# Input information
INPUT_INFORMATION = {
    'input_name_unique': 'SHT4X_CP',
    'input_manufacturer': 'Sensirion',
    'input_name': 'SHT4X',
    'input_library': 'Adafruit_CircuitPython_SHT4X',
    'measurements_name': 'Humidity/Temperature',
    'measurements_dict': measurements_dict,
    'url_manufacturer': 'https://www.sensirion.com/en/environmental-sensors/humidity-sensors/digital-humidity-sensors-for-various-applications/',

    'options_enabled': [
        'i2c_location',
        'measurements_select',
        'period',
        'pre_output'
    ],
    'options_disabled': ['interface'],

    'dependencies_module': [
        ('pip-pypi', 'usb.core', 'pyusb==1.1.1'),
        ('pip-pypi', 'adafruit_extended_bus', 'Adafruit-extended-bus==1.0.2'),
        ('pip-pypi', 'adafruit_sht4x', 'adafruit_circuitpython_sht4x==1.0.3')
    ],

    'interfaces': ['I2C'],
    'i2c_location': ['0x44', '0x45'],
    'i2c_address_editable': False
}


class InputModule(AbstractInput):
    """A sensor support class that measures SHT4x type devices."""
    def __init__(self, input_dev, testing=False):
        super().__init__(input_dev, testing=testing, name=__name__)

        self.sensor = None

        if not testing:
            self.try_initialize()

    def initialize(self):
        import adafruit_sht4x
        from adafruit_extended_bus import ExtendedI2C

        try:
            self.sensor = adafruit_sht4x.SHT4x(
                ExtendedI2C(self.input_dev.i2c_bus),
                address=int(str(self.input_dev.i2c_location), 16))
        except:
            self.logger.exception("Setting up sensor")

    def get_measurement(self):
        if not self.sensor:
            self.logger.error("Error 101: Device not set up. See https://aot-inc.github.io/AoT-AI/Error-Codes#error-101 for more info.")
            return

        self.return_dict = copy.deepcopy(measurements_dict)

        if self.is_enabled(0) or self.is_enabled(1):
            temperature, relative_humidity = self.sensor.measurements
        else:
            temperature = 0
            relative_humidity = 0

        if self.is_enabled(0):
            self.value_set(0, temperature)

        if self.is_enabled(1):
            self.value_set(1, relative_humidity)

        if self.is_enabled(2) and self.is_enabled(0) and self.is_enabled(1):
            self.value_set(2, calculate_dewpoint(self.value_get(0), self.value_get(1)))

        if self.is_enabled(3) and self.is_enabled(0) and self.is_enabled(1):
            self.value_set(3, calculate_vapor_pressure_deficit(self.value_get(0), self.value_get(1)))

        return self.return_dict
