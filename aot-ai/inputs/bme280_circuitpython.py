# coding=utf-8
import copy

from aot-ai.inputs.base_input import AbstractInput
from aot-ai.inputs.sensorutils import calculate_dewpoint
from aot-ai.inputs.sensorutils import calculate_vapor_pressure_deficit
from aot-ai.inputs.sensorutils import convert_from_x_to_y_unit

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
        'measurement': 'pressure',
        'unit': 'Pa'
    },
    3: {
        'measurement': 'dewpoint',
        'unit': 'C'
    },
    4: {
        'measurement': 'altitude',
        'unit': 'm'
    },
    5: {
        'measurement': 'vapor_pressure_deficit',
        'unit': 'Pa'
    }
}

# Input information
INPUT_INFORMATION = {
    'input_name_unique': 'BME280_CP',
    'input_manufacturer': 'BOSCH',
    'input_name': 'BME280',
    'input_library': 'Adafruit_CircuitPython_BME280',
    'measurements_name': 'Pressure/Humidity/Temperature',
    'measurements_dict': measurements_dict,
    'url_manufacturer': 'https://www.bosch-sensortec.com/bst/products/all_products/bme280',
    'url_datasheet': 'https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bme280-ds002.pdf',
    'url_product_purchase': [
        'https://www.adafruit.com/product/2652',
        'https://www.sparkfun.com/products/13676'
    ],

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
        ('pip-pypi', 'adafruit_bme280', 'adafruit-circuitpython-bme280==2.5.4')
    ],

    'interfaces': ['I2C'],
    'i2c_location': ['0x76', '0x77'],
    'i2c_address_editable': False
}


class InputModule(AbstractInput):
    """A sensor support class that measures the BME280"""

    def __init__(self, input_dev, testing=False):
        super().__init__(input_dev, testing=testing, name=__name__)

        self.sensor = None

        if not testing:
            self.try_initialize()

    def initialize(self):
        import adafruit_bme280
        from adafruit_extended_bus import ExtendedI2C

        try:
            self.sensor = adafruit_bme280.Adafruit_BME280_I2C(
                ExtendedI2C(self.input_dev.i2c_bus),
                address=int(str(self.input_dev.i2c_location), 16))
        except:
            self.logger.exception("Setting up sensor")

    def get_measurement(self):
        """Gets the measurements."""
        if not self.sensor:
            self.logger.error("Error 101: Device not set up. See https://aot-inc.github.io/AoT-AI/Error-Codes#error-101 for more info.")
            return

        self.return_dict = copy.deepcopy(measurements_dict)

        if self.is_enabled(0):
            self.value_set(0, self.sensor.temperature)

        if self.is_enabled(1):
            self.value_set(1, self.sensor.relative_humidity)

        if self.is_enabled(2):
            self.value_set(2, convert_from_x_to_y_unit('hPa', 'Pa', self.sensor.pressure))

        if self.is_enabled(0) and self.is_enabled(1) and self.is_enabled(3):
            self.value_set(3, calculate_dewpoint(self.value_get(0), self.value_get(1)))

        if self.is_enabled(4):
            self.value_set(4, self.sensor.altitude)

        if self.is_enabled(0) and self.is_enabled(1) and self.is_enabled(5):
            self.value_set(5, calculate_vapor_pressure_deficit(self.value_get(0), self.value_get(1)))

        return self.return_dict
