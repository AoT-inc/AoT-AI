# coding=utf-8
import datetime
import json
import time

import requests

from aot-ai.config import AOT-AI_DB_PATH
from aot-ai.config_translations import TRANSLATIONS
from aot-ai.databases.models import Conversion
from aot-ai.databases.models import Input
from aot-ai.databases.models import InputChannel
from aot-ai.databases.utils import session_scope
from aot-ai.inputs.base_input import AbstractInput
from aot-ai.utils.actions import run_input_actions
from aot-ai.utils.database import db_retrieve_table_daemon
from aot-ai.utils.influx import add_measurements_influxdb
from aot-ai.utils.inputs import parse_measurement


def constraints_pass_positive_value(mod_input, value):
    """
    Check if the user input is acceptable
    :param mod_input: SQL object with user-saved Input options
    :param value: float or int
    :return: tuple: (bool, list of strings)
    """
    errors = []
    all_passed = True
    # Ensure value is positive
    if value <= 0:
        all_passed = False
        errors.append("Must be a positive value")
    if value > 100:
        all_passed = False
        errors.append("Number of measurements cannot exceed 100")
    return all_passed, errors, mod_input

# Measurements
measurements_dict = {}

# Channels
channels_dict = {
    0: {}
}

# Input information
INPUT_INFORMATION = {
    'input_name_unique': 'TTN_DATA_STORAGE_TTN_V3_JMESPATH',
    'input_manufacturer': 'The Things Network',
    'input_name': 'The Things Network: 데이터 저장 (TTN v3, 페이로드 jmespath 표현식)',
    'input_name_short': 'TTN (v3) 데이터 저장',
    'input_library': 'requests, jmespath',
    'measurements_name': '가변 측정값',
    'measurements_dict': measurements_dict,
    'channels_dict': channels_dict,

    'message': '이 입력은 The Things Network의 데이터 저장 통합에서 측정값을 수신하고 저장합니다. '
               '제공된 페이로드 jmespath 표현식은 해당 채널에 저장될 값을 찾기 위해 JMESPATH 표현식으로 사용됩니다. '
               '각 채널에 대해 측정 단위를 선택하고 저장했는지 확인하세요. 단위가 저장되면, 측정 변환 섹션에서 다른 단위로 변환할 수 있습니다. '
               'jmespath (https://jmespath.org)의 예시 표현식으로는 <i>temperature</i>, <i>sensors[0].temperature</i>, '
               '및 <i>bathroom.temperature</i>가 있으며, 이는 각각 센서 배열의 첫 번째 항목에 있는 직접 키 또는 '
               'bathroom의 하위 키로 온도를 나타냅니다. 특수 문자가 포함된 jmespath 요소와 키는 반드시 큰따옴표로 감싸야 합니다. '
               '예: <i>"sensor-1".temperature</i>.',

    'measurements_variable_amount': True,
    'channel_quantity_same_as_measurements': True,
    'measurements_use_same_timestamp': False,

    'options_enabled': [
        'measurements_select',
        'period',
        'start_offset',
        'pre_output'
    ],

    'dependencies_module': [
        ('pip-pypi', 'requests', 'requests==2.31.0'),
        ('pip-pypi', 'jmespath', 'jmespath==0.10.0')
    ],

    'custom_options': [
        {
            'id': 'application_id',
            'type': 'text',
            'default_value': '',
            'required': True,
            'name': '애플리케이션 ID',
            'phrase': 'The Things Network 애플리케이션 ID'
        },
        {
            'id': 'app_api_key',
            'type': 'text',
            'default_value': '',
            'required': True,
            'name': '앱 API 키',
            'phrase': 'The Things Network 애플리케이션 API 키'
        },
        {
            'id': 'device_id',
            'type': 'text',
            'default_value': '',
            'required': True,
            'name': '디바이스 ID',
            'phrase': 'The Things Network 디바이스 ID'
        }
    ],

    'custom_channel_options': [
        {
            'id': 'name',
            'type': 'text',
            'default_value': '',
            'required': False,
            'name': TRANSLATIONS['name']['title'],
            'phrase': TRANSLATIONS['name']['phrase']
        },
        {
            'id': 'jmespath_expression',
            'type': 'text',
            'default_value': '',
            'required': True,
            'name': '페이로드 jmespath 표현식',
            'phrase': '저장할 값을 반환하기 위한 TTN jmespath 표현식'
        }
    ]
}


class InputModule(AbstractInput):
    """A sensor support class that retrieves stored data from The Things Network."""

    def __init__(self, input_dev, testing=False):
        super().__init__(input_dev, testing=testing, name=__name__)

        self.log_level_debug = None
        self.jmespath = None
        self.first_run = True

        self.application_id = None
        self.app_api_key = None
        self.device_id = None

        self.interface = None
        self.period = None
        self.latest_datetime = None
        self.options_channels = {}

        self.timestamp_format = '%Y-%m-%dT%H:%M:%S.%f'

        if not testing:
            self.setup_custom_options(
                INPUT_INFORMATION['custom_options'], input_dev)
            self.try_initialize()

    def initialize(self):
        import jmespath

        self.jmespath = jmespath

        self.log_level_debug = self.input_dev.log_level_debug
        self.interface = self.input_dev.interface
        self.period = self.input_dev.period
        self.latest_datetime = self.input_dev.datetime

        input_channels = db_retrieve_table_daemon(
            InputChannel).filter(InputChannel.input_id == self.input_dev.unique_id).all()
        self.options_channels = self.setup_custom_channel_options_json(
            INPUT_INFORMATION['custom_channel_options'], input_channels)

    def get_new_data(self, past_seconds):
        try:
            seconds = int(past_seconds)
        except:
            self.logger.error("past_seconds does not represent an integer")
            return

        endpoint = "https://nam1.cloud.thethings.network" \
                   "/api/v3/as/applications/{app}/devices/{dev}/packages/storage/uplink_message?" \
                   "last={time}s&field_mask=up.uplink_message.decoded_payload".format(
            app=self.application_id, dev=self.device_id, time=seconds)
        headers = {"Authorization": "Bearer {k}".format(k=self.app_api_key)}

        self.logger.debug("endpoint: {}".format(endpoint))
        self.logger.debug("headers: {}".format(headers))

        # Get measurement data from TTN
        try:
            response = requests.get(endpoint, headers=headers)
        except requests.exceptions.ConnectionError as err:
            self.logger.error("requests.exceptions.ConnectionError: {}".format(err))
            return
        except Exception as err:
            self.logger.error("Exception: {}".format(err))
            return

        if response.status_code != 200:
            self.logger.info("response.status_code != 200: {}".format(response.reason))
        self.logger.debug("response.content: {}".format(response.content))

        list_dicts = response.content.decode().split("\n")
        self.logger.debug("list_dicts: {}".format(list_dicts))

        for each_resp in list_dicts:
            measurements = {}

            if not self.running:
                break

            if not each_resp:
                continue
            self.logger.debug("each_resp: {}".format(each_resp))

            try:
                resp_json = json.loads(each_resp)
            except:
                resp_json = {}
            self.logger.debug("resp_json: {}".format(resp_json))

            try:
                datetime_utc = datetime.datetime.strptime(
                    resp_json['result']['received_at'][:-7], self.timestamp_format)
            except Exception:
                # Sometimes the original timestamp is in milliseconds
                # instead of nanoseconds. Therefore, remove 3 less digits
                # past the decimal and try again to parse.
                try:
                    datetime_utc = datetime.datetime.strptime(
                        resp_json['result']['received_at'][:-4], self.timestamp_format)
                except Exception as e:
                    self.logger.error("Could not parse timestamp '{}': {}".format(
                        resp_json['result']['received_at'], e))
                    continue  # Malformed timestamp encountered. Discard measurement.

            if ('result' not in resp_json or
                    'uplink_message' not in resp_json['result'] or
                    'decoded_payload' not in resp_json['result']['uplink_message'] or
                    not resp_json['result']['uplink_message']['decoded_payload']):
                self.logger.debug("resp_json empty or malformed: {}".format(resp_json))
                continue

            payload = resp_json['result']['uplink_message']['decoded_payload']

            if (not self.latest_datetime or
                    self.latest_datetime < datetime_utc):
                self.latest_datetime = datetime_utc

            for channel in self.channels_measurement:
                jmespath_expression = self.options_channels['jmespath_expression'][channel]
                try:
                    jmesexpression = self.jmespath.compile(jmespath_expression)
                    value = jmesexpression.search(payload)
                    self.logger.debug(
                        "Expression: {}, value: {}".format(jmespath_expression, value))
                except Exception as err:
                    self.logger.error(
                        "Error in JSON '{}' finding expression '{}': {}".format(
                            payload, jmespath_expression, err))
                    continue

                if value is None:
                    continue

                # Original value/unit
                measurements[channel] = {}
                measurements[channel]['measurement'] = self.channels_measurement[channel].measurement
                measurements[channel]['unit'] = self.channels_measurement[channel].unit
                measurements[channel]['timestamp_utc'] = datetime_utc

                try:
                    measurements[channel]['value'] = float(value)
                except:
                    self.logger.error(f"Value doesn't represent float: {value}")

                # Convert value/unit is conversion_id present and valid
                if self.channels_conversion[channel]:
                    conversion = db_retrieve_table_daemon(
                        Conversion, unique_id=self.channels_measurement[channel].conversion_id)
                    if conversion:
                        meas = parse_measurement(
                            self.channels_conversion[channel],
                            self.channels_measurement[channel],
                            measurements,
                            channel,
                            measurements[channel],
                            timestamp=datetime_utc)

                        measurements[channel]['measurement'] = meas[channel]['measurement']
                        measurements[channel]['unit'] = meas[channel]['unit']
                        measurements[channel]['value'] = float(meas[channel]['value'])

            if measurements:
                message, measurements = run_input_actions(self.unique_id, "", measurements, self.log_level_debug)

                self.logger.debug("Adding measurements to influxdb: {}".format(measurements))
                add_measurements_influxdb(
                    self.unique_id, measurements,
                    use_same_timestamp=INPUT_INFORMATION['measurements_use_same_timestamp'])
            else:
                self.logger.debug("No measurements to add to influxdb.")

        # set datetime to latest timestamp
        if self.running:
            with session_scope(AOT-AI_DB_PATH) as new_session:
                mod_input = new_session.query(Input).filter(
                    Input.unique_id == self.unique_id).first()
                if not mod_input.datetime or mod_input.datetime < self.latest_datetime:
                    mod_input.datetime = self.latest_datetime
                    new_session.commit()

    def get_measurement(self):
        """Gets the data."""
        if self.first_run:
            # Get data for up to 7 days (longest Data Storage Integration
            # stores data) in the past or until last_datetime.
            seconds_seven_days = 604800  # 604800 seconds = 7 days
            seconds_download = seconds_seven_days
            start = time.time()
            self.first_run = False

            if self.latest_datetime:
                utc_now = datetime.datetime.utcnow()
                seconds_since_last = (utc_now - self.latest_datetime).total_seconds()
                if seconds_since_last < seconds_seven_days:
                    seconds_download = seconds_since_last

            if seconds_download == seconds_seven_days:
                self.logger.info(
                    "This appears to be the first data download. Downloading and parsing past 7 days of data...")
            else:
                self.logger.info("Downloading and parsing past {} seconds of data...".format(int(seconds_download)))

            try:
                self.get_new_data(seconds_download)
            except Exception:
                self.logger.exception("Getting data")

            if seconds_download == seconds_seven_days:
                elapsed = time.time() - start
                self.logger.info("Download and parsing completed in {} seconds.".format(int(elapsed)))
        else:
            try:
                self.get_new_data(self.period)
            except Exception:
                self.logger.exception("Getting data")

        return {}
