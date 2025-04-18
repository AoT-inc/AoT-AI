# coding=utf-8
# Input module for Sonoff TH16 or TH10.
# Requires Tasmota firmware flashed to the Sonoff's ESP8266
# https://github.com/arendst/Sonoff-Tasmota
import datetime
import json

import copy
import requests
from flask_babel import lazy_gettext

from aot-ai.inputs.base_input import AbstractInput
from aot-ai.inputs.sensorutils import convert_from_x_to_y_unit

# Measurements
measurements_dict = {
    0: {
        'measurement': 'temperature',
        'unit': 'C'
    }
}

# Input information
INPUT_INFORMATION = {
    'input_name_unique': 'TH16_10_DS18B20',
    'input_manufacturer': 'Sonoff',
    'input_name': 'TH16/10 (Tasmota firmware) with DS18B20',
    'input_name_short': 'TH16/10 + DS18B20',
    'input_library': 'requests',
    'measurements_name': 'Temperature',
    'measurements_dict': measurements_dict,
    'url_manufacturer': 'https://sonoff.tech/product/wifi-diy-smart-switches/th10-th16',

    'measurements_use_same_timestamp': False,

    'options_enabled': [
        'measurements_select',
        'period',
        'pre_output'
    ],
    'options_disabled': ['interface'],

    'dependencies_module': [
        ('pip-pypi', 'requests', 'requests==2.31.0'),
    ],

    'custom_options': [
        {
            'id': 'ip_address',
            'type': 'text',
            'default_value': '192.168.0.100',
            'required': True,
            'name': lazy_gettext('IP Address'),
            'phrase': 'The IP address of the device'
        }
    ]
}


class InputModule(AbstractInput):
    def __init__(self, input_dev, testing=False):
        super().__init__(input_dev, testing=testing, name=__name__)

        self.ip_address = None

        if not testing:
            self.setup_custom_options(
                INPUT_INFORMATION['custom_options'], input_dev)
            self.ip_address = self.ip_address.replace(" ", "")  # Remove spaces

    def get_measurement(self):
        self.return_dict = copy.deepcopy(measurements_dict)

        url = "http://{ip}/cm?cmnd=status%2010".format(ip=self.ip_address)
        r = requests.get(url)
        str_json = r.text
        dict_data = json.loads(str_json)

        self.logger.debug("Returned Data: {}".format(dict_data))

        # Convert string to datetime object
        datetime_timestmp = datetime.datetime.strptime(dict_data['StatusSNS']['Time'], '%Y-%m-%dT%H:%M:%S')

        if 'TempUnit' in dict_data['StatusSNS'] and dict_data['StatusSNS']['TempUnit']:
            # Convert temperature to SI unit Celsius
            temp_c = convert_from_x_to_y_unit(
                dict_data['StatusSNS']['TempUnit'],
                'C',
                dict_data['StatusSNS']['DS18B20']['Temperature'])
        else:
            temp_c = dict_data['StatusSNS']['DS18B20']['Temperature']
        self.value_set(0, temp_c, timestamp=datetime_timestmp)

        return self.return_dict
