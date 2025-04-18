# coding=utf-8
import copy

from aot-ai.inputs.base_input import AbstractInput

# Measurements
measurements_dict = {
    0: {
        'measurement': 'moisture',
        'unit': 'unitless'
    },
    1: {
        'measurement': 'temperature',
        'unit': 'C'
    }
}

# Input information
INPUT_INFORMATION = {
    'input_name_unique': 'ADAFRUIT_I2C_SOIL',
    'input_manufacturer': 'Adafruit',
    'input_name': 'I2C Capacitive Moisture Sensor',
    'input_name_short': 'Capacitive Moisture',
    'input_library': 'adafruit_seesaw',
    'measurements_name': 'Moisture/Temperature',
    'measurements_dict': measurements_dict,
    'url_manufacturer': 'https://learn.adafruit.com/adafruit-stemma-soil-sensor-i2c-capacitive-moisture-sensor',
    'url_product_purchase': 'https://www.adafruit.com/product/4026',

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
        ('pip-pypi', 'adafruit_seesaw', 'adafruit-circuitpython-seesaw==1.7.2')
    ],

    'interfaces': ['I2C'],
    'i2c_location': ['0x36','0x37','0x38','0x39'],
    'i2c_address_editable': False
}


class InputModule(AbstractInput):
    """A sensor support class that measures soil moisture using adafruit's i2c soil sensor."""
    def __init__(self, input_dev, testing=False):
        super().__init__(input_dev, testing=testing, name=__name__)

        self.sensor = None

        if not testing:
            self.try_initialize()

    def initialize(self):
        from adafruit_seesaw.seesaw import Seesaw
        from adafruit_extended_bus import ExtendedI2C

        try:
            self.sensor = Seesaw(
                ExtendedI2C(self.input_dev.i2c_bus),
                addr=int(str(self.input_dev.i2c_location), 16))
        except:
            self.logger.exception("Setting up sensor")

    def get_measurement(self):
        if not self.sensor:
            self.logger.error("Error 101: Device not set up. See https://aot-inc.github.io/AoT-AI/Error-Codes#error-101 for more info.")
            return

        self.return_dict = copy.deepcopy(measurements_dict)

        if self.is_enabled(0):
            self.value_set(0, self.sensor.moisture_read())

        if self.is_enabled(1):
            self.value_set(1, self.sensor.get_temp())

        return self.return_dict
