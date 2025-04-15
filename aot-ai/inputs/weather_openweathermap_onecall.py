# -*- coding: utf-8 -*-

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
        'measurement': 'temperature',
        'unit': 'C',
        'name': 'Min'
    },
    2: {
        'measurement': 'temperature',
        'unit': 'C',
        'name': 'Max'
    },
    3: {
        'measurement': 'humidity',
        'unit': 'percent'
    },
    4: {
        'measurement': 'pressure',
        'unit': 'Pa'
    },
    5: {
        'measurement': 'dewpoint',
        'unit': 'C'
    },
    6: {
        'measurement': 'speed',
        'unit': 'm_s',
        'name': 'Wind'
    },
    7: {
        'measurement': 'direction',
        'unit': 'bearing',
        'name': 'Wind'
    },
    8: {
        'measurement': 'duration_time',
        'unit': 'h',
        'name': 'Hours in Future'
    }
}

# Input information
INPUT_INFORMATION = {
    'input_name_unique': 'OPENWEATHERMAP_CALL_ONECALL',
    'input_manufacturer': 'Weather',
    'input_name': 'OpenWeatherMap (Lat/Lon, Current/Future)',
    'input_name_short': 'OpenWeather Lat/Lon',
    'measurements_name': 'Humidity/Temperature/Pressure/Wind',
    'measurements_dict': measurements_dict,
    'url_additional': 'https://openweathermap.org',
    'measurements_rescale': False,

    'message': 'openweathermap.org에서 무료 API 키를 발급받으세요. '
               '참고: 무료 API 구독은 분당 60회 호출로 제한됩니다. '
               '만약 Day (Future) 시간이 선택되면, 최소 및 최대 온도가 측정값으로 제공됩니다.',

    'options_enabled': [
        'measurements_select',
        'period',
        'pre_output'
    ],
    'options_disabled': ['interface'],

    'dependencies_module': [],
    'interfaces': ['AoT-AI'],

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
            'id': 'latitude',
            'type': 'float',
            'default_value': 33.441792,
            'required': True,
            'name': lazy_gettext('위도 (소수점)'),
            'phrase': "날씨 데이터를 가져올 위도"
        },
        {
            'id': 'longitude',
            'type': 'float',
            'default_value': -94.037689,
            'required': True,
            'name': lazy_gettext('경도 (소수점)'),
            'phrase': "날씨 데이터를 가져올 경도"
        },
        {
            'id': 'weather_time',
            'type': 'select',
            'default_value': 'current',
            'options_select': [
                ('current', '현재 (현재)'),
                ('day1', '1일 (미래)'),
                ('day2', '2일 (미래)'),
                ('day3', '3일 (미래)'),
                ('day4', '4일 (미래)'),
                ('day5', '5일 (미래)'),
                ('day6', '6일 (미래)'),
                ('day7', '7일 (미래)'),
                ('hour1', '1시간 (미래)'),
                ('hour2', '2시간 (미래)'),
                ('hour3', '3시간 (미래)'),
                ('hour4', '4시간 (미래)'),
                ('hour5', '5시간 (미래)'),
                ('hour6', '6시간 (미래)'),
                ('hour7', '7시간 (미래)'),
                ('hour8', '8시간 (미래)'),
                ('hour9', '9시간 (미래)'),
                ('hour10', '10시간 (미래)'),
                ('hour11', '11시간 (미래)'),
                ('hour12', '12시간 (미래)'),
                ('hour13', '13시간 (미래)'),
                ('hour14', '14시간 (미래)'),
                ('hour15', '15시간 (미래)'),
                ('hour16', '16시간 (미래)'),
                ('hour17', '17시간 (미래)'),
                ('hour18', '18시간 (미래)'),
                ('hour19', '19시간 (미래)'),
                ('hour20', '20시간 (미래)'),
                ('hour21', '21시간 (미래)'),
                ('hour22', '22시간 (미래)'),
                ('hour23', '23시간 (미래)'),
                ('hour24', '24시간 (미래)'),
                ('hour25', '25시간 (미래)'),
                ('hour26', '26시간 (미래)'),
                ('hour27', '27시간 (미래)'),
                ('hour28', '28시간 (미래)'),
                ('hour29', '29시간 (미래)'),
                ('hour30', '30시간 (미래)'),
                ('hour31', '31시간 (미래)'),
                ('hour32', '32시간 (미래)'),
                ('hour33', '33시간 (미래)'),
                ('hour34', '34시간 (미래)'),
                ('hour35', '35시간 (미래)'),
                ('hour36', '36시간 (미래)'),
                ('hour37', '37시간 (미래)'),
                ('hour38', '38시간 (미래)'),
                ('hour39', '39시간 (미래)'),
                ('hour40', '40시간 (미래)'),
                ('hour41', '41시간 (미래)'),
                ('hour42', '42시간 (미래)'),
                ('hour43', '43시간 (미래)'),
                ('hour44', '44시간 (미래)'),
                ('hour45', '45시간 (미래)'),
                ('hour46', '46시간 (미래)'),
                ('hour47', '47시간 (미래)'),
                ('hour48', '48시간 (미래)')
            ],
            'name': lazy_gettext('시간'),
            'phrase': '현재 또는 예보 날씨에 대한 시간을 선택하세요'
        }
    ]
}


class InputModule(AbstractInput):
    """위도/경도 위치의 날씨를 가져오는 센서 지원 클래스."""
    def __init__(self, input_dev, testing=False):
        super().__init__(input_dev, testing=testing, name=__name__)

        self.api_url = None
        self.api_key = None
        self.latitude = None
        self.longitude = None
        self.weather_time = None
        self.weather_time_dict = {}

        if not testing:
            self.setup_custom_options(
                INPUT_INFORMATION['custom_options'], input_dev)
            self.try_initialize()

    def initialize(self):
        if self.api_key and self.latitude and self.longitude and self.weather_time:
            base_url = "https://api.openweathermap.org/data/2.5/onecall?lat={lat}&lon={lon}&units=metric&appid={key}".format(
                lat=self.latitude, lon=self.longitude, key=self.api_key)
            if self.weather_time == 'current':
                self.weather_time_dict["time"] = "current"
                self.api_url = "{base}&exclude=minutely,hourly,daily,alerts".format(base=base_url)
            elif self.weather_time.startswith("day"):
                self.weather_time_dict["time"] = "day"
                self.weather_time_dict["amount"] = int(self.weather_time.split("day")[1])
                self.api_url = "{base}&exclude=current,minutely,hourly,alerts".format(base=base_url)
            elif self.weather_time.startswith("hour"):
                self.weather_time_dict["time"] = "hour"
                self.weather_time_dict["amount"] = int(self.weather_time.split("hour")[1])
                self.api_url = "{base}&exclude=current,minutely,daily,alerts".format(base=base_url)

            self.logger.debug("URL: {}".format(self.api_url))
            self.logger.debug("Time Dict: {}".format(self.weather_time_dict))

    def get_measurement(self):
        """날씨 데이터를 가져옵니다."""
        if not self.api_url:
            self.logger.error("API 키, 위도, 경도가 필요합니다.")
            return

        self.return_dict = copy.deepcopy(measurements_dict)

        try:
            response = requests.get(self.api_url)
            x = response.json()
            self.logger.debug("응답: {}".format(x))

            if self.weather_time_dict["time"] == "current":
                if 'current' not in x:
                    self.logger.error("응답이 없습니다. 설정을 확인하세요.")
                    return
                temperature = x["current"]["temp"]
                pressure = x["current"]["pressure"]
                humidity = x["current"]["humidity"]
                wind_speed = x["current"]["wind_speed"]
                wind_deg = x["current"]["wind_deg"]
                if self.is_enabled(8):
                    self.value_set(8, 0)
            elif self.weather_time_dict["time"] == "hour":
                if 'hourly' not in x:
                    self.logger.error("응답이 없습니다. 설정을 확인하세요.")
                    return
                temperature = x["hourly"][self.weather_time_dict["amount"] - 1]["temp"]
                pressure = x["hourly"][self.weather_time_dict["amount"] - 1]["pressure"]
                humidity = x["hourly"][self.weather_time_dict["amount"] - 1]["humidity"]
                wind_speed = x["hourly"][self.weather_time_dict["amount"] - 1]["wind_speed"]
                wind_deg = x["hourly"][self.weather_time_dict["amount"] - 1]["wind_deg"]
                if self.is_enabled(8):
                    self.value_set(8, self.weather_time_dict["amount"])
            elif self.weather_time_dict["time"] == "day":
                if 'daily' not in x:
                    self.logger.error("응답이 없습니다. 설정을 확인하세요.")
                    return
                temperature = x["daily"][self.weather_time_dict["amount"]]["temp"]["day"]
                temperature_min = x["daily"][self.weather_time_dict["amount"]]["temp"]["min"]
                temperature_max = x["daily"][self.weather_time_dict["amount"]]["temp"]["max"]
                pressure = x["daily"][self.weather_time_dict["amount"]]["pressure"]
                humidity = x["daily"][self.weather_time_dict["amount"]]["humidity"]
                wind_speed = x["daily"][self.weather_time_dict["amount"]]["wind_speed"]
                wind_deg = x["daily"][self.weather_time_dict["amount"]]["wind_deg"]

                if self.is_enabled(1):
                    self.value_set(1, temperature_min)
                if self.is_enabled(2):
                    self.value_set(2, temperature_max)
                if self.is_enabled(8):
                    self.value_set(8, self.weather_time_dict["amount"] * 24)
            else:
                self.logger.error("유효하지 않은 날씨 시간")
                return
        except Exception as e:
            self.logger.error("날씨 정보를 가져오는 중 오류 발생: {}".format(e))
            return

        self.logger.debug("온도: {}, 습도: {}, 기압: {}, 풍속: {}, 풍향: {}".format(
            temperature, humidity, pressure, wind_speed, wind_deg))

        if self.is_enabled(0):
            self.value_set(0, temperature)
        if self.is_enabled(3):
            self.value_set(3, humidity)
        if self.is_enabled(4):
            self.value_set(4, pressure)

        if self.is_enabled(0) and self.is_enabled(3) and self.is_enabled(5):
            self.value_set(5, calculate_dewpoint(temperature, humidity))

        if self.is_enabled(6):
            self.value_set(6, wind_speed)
        if self.is_enabled(7):
            self.value_set(7, wind_deg)

        return self.return_dict