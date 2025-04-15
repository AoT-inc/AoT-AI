# coding=utf-8
import copy

import requests
from flask_babel import lazy_gettext

from aot-ai.inputs.base_input import AbstractInput
from aot-ai.inputs.sensorutils import calculate_dewpoint

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
        'measurement': 'speed',
        'unit': 'm_s',
        'name': 'Wind'
    },
    5: {
        'measurement': 'direction',
        'unit': 'bearing',
        'name': 'Wind'
    }
}

# Input information
INPUT_INFORMATION = {
    'input_name_unique': 'OPENWEATHERMAP_CALL_WEATHER',
    'input_manufacturer': 'Weather',
    'input_name': 'OpenWeatherMap (도시, 현재)',
    'input_name_short': 'OpenWeather 도시',
    'measurements_name': '습도/온도/기압/풍속',
    'measurements_dict': measurements_dict,
    'url_additional': 'https://openweathermap.org',
    'measurements_rescale': False,

    'message': 'openweathermap.org에서 무료 API 키를 발급받으세요. 입력한 도시에서 측정값이 반환되지 않는 경우, 다른 도시를 시도해 보세요. 참고: 무료 API 구독은 분당 60회 호출로 제한됩니다.',

    'options_enabled': [
        'measurements_select',
        'period',
        'pre_output'
    ],

    'custom_options': [
        {
            'id': 'api_key',
            'type': 'text',
            'default_value': '',
            'required': True,
            'name': lazy_gettext('API 키'),
            'phrase': "이 서비스의 API를 위한 API 키"
        },
        {
            'id': 'city',
            'type': 'text',
            'default_value': '',
            'required': True,
            'name': lazy_gettext('도시'),
            'phrase': "날씨 데이터를 가져올 도시"
        }
    ]
}


class InputModule(AbstractInput):
    """도시의 날씨를 가져오는 센서 지원 클래스."""
    def __init__(self, input_dev, testing=False):
        super().__init__(input_dev, testing=testing, name=__name__)

        self.api_url = None
        self.api_key = None
        self.city = None

        if not testing:
            self.setup_custom_options(
                INPUT_INFORMATION['custom_options'], input_dev)
            self.try_initialize()

    def initialize(self):
        if self.api_key and self.city:
            self.api_url = "http://api.openweathermap.org/data/2.5/weather?appid={key}&units=metric&q={city}".format(
                key=self.api_key, city=self.city)
            self.logger.debug("URL: {}".format(self.api_url))

    def get_measurement(self):
        """날씨 데이터를 가져옵니다."""
        if not self.api_url:
            self.logger.error("API 키와 도시가 필요합니다.")
            return

        self.return_dict = copy.deepcopy(measurements_dict)

        try:
            response = requests.get(self.api_url)
            x = response.json()
            self.logger.debug("응답: {}".format(x))

            if x["cod"] != "404":
                temperature = x["main"]["temp"]
                pressure = x["main"]["pressure"]
                humidity = x["main"]["humidity"]
                wind_speed = x["wind"]["speed"]
                wind_deg = x["wind"]["deg"]
            else:
                self.logger.error("도시를 찾을 수 없습니다.")
                return
        except Exception as e:
            self.logger.error("날씨 정보를 가져오는 중 오류 발생: {}".format(e))
            return

        self.logger.debug("온도: {}, 습도: {}, 기압: {}, 풍속: {}, 풍향: {}".format(
            temperature, humidity, pressure, wind_speed, wind_deg))

        if self.is_enabled(0):
            self.value_set(0, temperature)
        if self.is_enabled(1):
            self.value_set(1, humidity)
        if self.is_enabled(2):
            self.value_set(2, pressure)

        if self.is_enabled(0) and self.is_enabled(1) and self.is_enabled(3):
            self.value_set(3, calculate_dewpoint(temperature, humidity))

        if self.is_enabled(4):
            self.value_set(4, wind_speed)
        if self.is_enabled(5):
            self.value_set(5, wind_deg)

        return self.return_dict