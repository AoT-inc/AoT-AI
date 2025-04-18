# coding=utf-8
#
#  lcd_grove_16x2_i2c.py - Function to output to Grove LCD
#
#  Copyright (C) 2015-2020 Kyle T. Gabriel <aot-ai@aot-inc.com>
#
#  This file is part of AoT-AI
#
#  AoT-AI is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  AoT-AI is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with AoT-AI. If not, see <http://www.gnu.org/licenses/>.
#
#  Contact at aot-inc.com
#
import datetime
import json
import math
import time
import traceback

from flask_babel import lazy_gettext

from aot-ai.config import AOT-AI_VERSION
from aot-ai.config_translations import TRANSLATIONS
from aot-ai.databases.models import CustomController, FunctionChannel
from aot-ai.functions.base_function import AbstractFunction
from aot-ai.aot-ai_flask.utils.utils_general import (
    custom_channel_options_return_json, delete_entry_with_id)
from aot-ai.utils.constraints_pass import (
    constraints_pass_positive_or_zero_value, constraints_pass_positive_value)
from aot-ai.utils.database import db_retrieve_table_daemon
from aot-ai.utils.functions import parse_function_information
from aot-ai.utils.lcd import format_measurement_line
from aot-ai.utils.system_pi import cmd_output

# Set to how many lines the LCD has
lcd_lines = 2
lcd_x_characters = 16


def execute_at_creation(error, new_func, dict_functions=None):
    try:
        dict_controllers = parse_function_information()

        for channel in range(lcd_lines):
            new_channel = FunctionChannel()
            new_channel.name = "Set 0 Line {}".format(channel)
            new_channel.function_id = new_func.unique_id
            new_channel.channel = channel

            error, custom_options = custom_channel_options_return_json(
                error, dict_controllers, None,
                new_func.unique_id, channel,
                device=new_func.device, use_defaults=True)
            custom_options_dict = json.loads(custom_options)
            custom_options_dict["name"] = new_channel.name
            new_channel.custom_options = json.dumps(custom_options_dict)
            new_channel.save()
    except Exception:
        error.append("execute_at_modification() Error: {}".format(traceback.print_exc()))

    return error, new_func


def execute_at_modification(
        messages,
        mod_function,
        request_form,
        custom_options_dict_presave,
        custom_options_channels_dict_presave,
        custom_options_dict_postsave,
        custom_options_channels_dict_postsave):
    """
    This function allows you to view and modify the output and channel settings when the user clicks
    save on the user interface. Both the output and channel settings are passed to this function, as
    dictionaries. Additionally, both the pre-saved and post-saved options are available, as it's
    sometimes useful to know what settings changed and from what values. You can modify the post-saved
    options and these will be stored in the database.
    :param mod_function: The post-saved output database entry, minus the custom_options settings
    :param request_form: The requests.form object the user submitted
    :param custom_options_dict_presave: dict of pre-saved custom output options
    :param custom_options_channels_dict_presave: dict of pre-saved custom output channel options
    :param custom_options_dict_postsave: dict of post-saved custom output options
    :param custom_options_channels_dict_postsave: dict of post-saved custom output channel options
    :return:
    """
    page_refresh = False

    try:
        dict_controllers = parse_function_information()

        channels = FunctionChannel.query.filter(
            FunctionChannel.function_id == mod_function.unique_id)

        # Ensure name doesn't get overwritten
        selector_set = 0
        selector_line = 0
        for channel in range(channels.count()):
            custom_options_channels_dict_postsave[channel]["name"] = "Set {} Line {}".format(
                selector_set, selector_line)
            selector_line += 1
            if selector_line == lcd_lines:
                selector_set += 1
                selector_line = 0

        end_channel = custom_options_dict_postsave['number_line_sets'] * lcd_lines

        # Increase number of channels
        if (custom_options_dict_postsave['number_line_sets'] >
                custom_options_dict_presave['number_line_sets']):

            page_refresh = True
            start_channel = channels.count()

            for index in range(start_channel, end_channel):
                new_channel = FunctionChannel()
                new_channel.name = "Set {} Line {}".format(
                    math.trunc(index / lcd_lines),
                    index - (math.trunc(index / lcd_lines) * lcd_lines))
                new_channel.function_id = mod_function.unique_id
                new_channel.channel = index

                messages["error"], custom_options = custom_channel_options_return_json(
                    messages["error"],
                    dict_controllers,
                    request_form,
                    mod_function.unique_id,
                    index,
                    device=mod_function.device,
                    use_defaults=True)
                custom_options_dict = json.loads(custom_options)
                custom_options_dict["name"] = new_channel.name
                new_channel.custom_options = json.dumps(custom_options_dict)

                new_channel.save()

        # Decrease number of channels
        elif (custom_options_dict_postsave['number_line_sets'] <
                custom_options_dict_presave['number_line_sets']):

            page_refresh = True
            for index, each_channel in enumerate(channels.all()):
                if index >= end_channel:
                    delete_entry_with_id(FunctionChannel, each_channel.unique_id)

    except Exception:
        messages["error"].append("execute_at_modification() Error: {}".format(traceback.print_exc()))

    return (messages,
            mod_function,
            custom_options_dict_postsave,
            custom_options_channels_dict_postsave,
            page_refresh)


FUNCTION_INFORMATION = {
    'function_name_unique': 'display_grove_lcd_16x2_i2c',
    'function_name': 'Display: Grove LCD 16x2 (I2C)',
    'function_manufacturer': 'Grove',
    'function_library': 'smbus2',
    'execute_at_creation': execute_at_creation,
    'execute_at_modification': execute_at_modification,

    'message': '이 기능은 I2C를 통해 Grove 16x2 LCD 디스플레이에 출력을 제공합니다. 이 디스플레이는 한 번에 2줄을 표시할 수 있으므로, 라인 세트 수(Number of Line Sets)가 변경되면 2개 채널씩 추가됩니다. 설정된 주기(Period)마다 LCD가 새로고침되며, 다음 세트의 라인이 표시됩니다. 따라서 처음 표시되는 2줄은 채널 0과 1, 이후 채널 2와 3, 그다음 채널 4와 5가 표시되는 방식으로 진행됩니다. 모든 채널이 표시된 후에는 다시 처음부터 순환됩니다.',

    'dependencies_module': [
        ('pip-pypi', 'smbus2', 'smbus2==0.4.1')
    ],

    'options_disabled': [
        'measurements_select',
        'measurements_configure'
    ],

    'function_actions': [
        'backlight_on',
        'backlight_off',
        'display_backlight_color'
    ],

    'custom_commands': [
        {
            'id': 'backlight_on',
            'type': 'button',
            'wait_for_return': False,
            'name': 'Backlight On',
            'phrase': "Turn backlight on"
        },
        {
            'id': 'backlight_off',
            'type': 'button',
            'wait_for_return': False,
            'name': 'Backlight Off',
            'phrase': "Turn backlight off"
        },
        {
            'type': 'new_line'
        },
        {
            'id': 'color',
            'type': 'text',
            'default_value': '255,0,0',
            'name': 'Color (RGB)',
            'phrase': 'Color as R,G,B values (e.g. "255,0,0" without quotes)'
        },
        {
            'id': 'display_backlight_color',
            'type': 'button',
            'name': "Set Backlight Color"
        }
    ],

    'custom_options': [
        {
            'id': 'period',
            'type': 'float',
            'default_value': 10,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': "{} ({})".format(lazy_gettext('Period'), lazy_gettext('Seconds')),
            'phrase': lazy_gettext('The duration between measurements or actions')
        },
        {
            'id': 'i2c_address',
            'type': 'text',
            'default_value': '0x3e',
            'required': True,
            'name': TRANSLATIONS['i2c_location']['title'],
            'phrase': ''
        },
        {
            'id': 'i2c_bus',
            'type': 'integer',
            'default_value': 1,
            'required': True,
            'name': TRANSLATIONS['i2c_bus']['title'],
            'phrase': ''
        },
        {
            'id': 'location_backlight',
            'type': 'text',
            'default_value': '0x62',
            'required': True,
            'name': 'Backlight I2C Address',
            'phrase': 'I2C address to control the backlight'
        },
        {
            'id': 'number_line_sets',
            'type': 'integer',
            'default_value': 1,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Number of Line Sets',
            'phrase': 'How many sets of lines to cycle on the LCD'
        },
        {
            'id': 'backlight_red',
            'type': 'integer',
            'default_value': 255,
            'required': True,
            'name': 'Backlight Red (0 - 255)',
            'phrase': 'Set the red color value of the backlight on startup.'
        },
        {
            'id': 'backlight_green',
            'type': 'integer',
            'default_value': 255,
            'required': True,
            'name': 'Backlight Green (0 - 255)',
            'phrase': 'Set the green color value of the backlight on startup.'
        },
        {
            'id': 'backlight_blue',
            'type': 'integer',
            'default_value': 255,
            'required': True,
            'name': 'Backlight Blue (0 - 255)',
            'phrase': 'Set the blue color value of the backlight on startup.'
        }
    ],

    'custom_channel_options': [
        {
            'id': 'line_display_type',
            'type': 'select',
            'default_value': '',
            'required': True,
            'options_select': [
                ('measurement_value', 'Last Measurement Value'),
                ('measurement_ts', 'Last Measurement Timestamp'),
                ('blank_line', 'Blank Line'),
                ('ip_address', 'IP Address'),
                ('current_time', 'Current Time'),
                ('text', 'Text')
            ],
            'name': 'Line Display Type',
            'phrase': 'What to display on the line'
        },
        {
            'id': 'select_measurement',
            'type': 'select_measurement',
            'default_value': '',
            'options_select': [
                'Input',
                'Function',
                'Output',
                'PID'
            ],
            'name': 'Measurement',
            'phrase': 'Measurement to display on the line'
        },
        {
            'id': 'measure_max_age',
            'type': 'integer',
            'default_value': 360,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': "{} ({})".format(lazy_gettext('Max Age'), lazy_gettext('Seconds')),
            'phrase': lazy_gettext('The maximum age of the measurement to use')
        },
        {
            'id': 'measurement_label',
            'type': 'text',
            'default_value': '',
            'required': False,
            'name': 'Measurement Label',
            'phrase': 'Set to overwrite the default measurement label'
        },
        {
            'id': 'measure_decimal',
            'type': 'integer',
            'default_value': 1,
            'required': True,
            'constraints_pass': constraints_pass_positive_or_zero_value,
            'name': 'Measurement Decimal',
            'phrase': 'The number of digits after the decimal'
        },
        {
            'id': 'text',
            'type': 'text',
            'default_value': 'Text',
            'required': True,
            'name': TRANSLATIONS['text']['title'],
            'phrase': "Text to display"
        },
        {
            'id': 'display_unit',
            'type': 'bool',
            'default_value': True,
            'required': True,
            'name': 'Display Unit',
            'phrase': "Display the measurement unit (if available)"
        }
    ]
}


class CustomModule(AbstractFunction):
    """
    Class to operate custom controller
    """
    def __init__(self, function, testing=False):
        super().__init__(function, testing=testing, name=__name__)

        self.options_channels = {}
        self.lcd = None
        self.timer_loop = time.time()
        self.line_sets = []
        self.current_line_set = 0
        self.line_y_dimensions = [0, 8]
        self.pad = -2
        self.lcd_is_on = None
        self.lines_being_written = False

        # Initialize custom options
        self.period = None
        self.i2c_address = None
        self.i2c_bus = None
        self.location_backlight = None
        self.backlight_red = None
        self.backlight_green = None
        self.backlight_blue = None
        self.number_line_sets = None

        # Set custom options
        custom_function = db_retrieve_table_daemon(
            CustomController, unique_id=self.unique_id)
        self.setup_custom_options(
            FUNCTION_INFORMATION['custom_options'], custom_function)

        if not testing:
            self.try_initialize()

    def initialize(self):
        from aot-ai.devices.lcd_grove_lcd_rgb import LCD_Grove_LCD_RGB

        try:
            function_channels = db_retrieve_table_daemon(
                FunctionChannel).filter(FunctionChannel.function_id == self.unique_id).all()
            self.options_channels = self.setup_custom_channel_options_json(
                FUNCTION_INFORMATION['custom_channel_options'], function_channels)

            for each_set in range(self.number_line_sets):
                self.line_sets.append([])
                for each_line in range(lcd_lines):
                    self.line_sets[each_set].append(each_line)

            self.logger.debug("Line sets: {}".format(self.line_sets))

            lcd_settings_dict = {
                "unique_id": self.unique_id,
                "i2c_address": self.i2c_address,
                "i2c_bus": self.i2c_bus,
                "location_backlight": self.location_backlight,
                "red": self.backlight_red,
                "green": self.backlight_green,
                "blue": self.backlight_blue,
                "x_characters": lcd_x_characters,
                "y_lines": lcd_lines
            }

            self.lcd = LCD_Grove_LCD_RGB(lcd_settings_dict=lcd_settings_dict)
            self.lcd.lcd_init()
            self.lcd_is_on = True

            self.logger.debug("LCD Function started")
        except:
            self.logger.exception("Starting LCD Function")

    def loop(self):
        if self.timer_loop > time.time():
            return

        while self.timer_loop < time.time():
            self.timer_loop += self.period

        if not self.lcd:
            self.logger.error("LCD not set up")
            return

        if not self.lcd_is_on:
            return  # Don't draw anything on an LCD that has the backlight off

        # Generate lines to display
        self.lines_being_written = True
        lines_display = {}
        for line in range(lcd_lines):
            lines_display[line] = ""

        for current_line in self.line_sets[self.current_line_set]:
            current_channel = (self.current_line_set * lcd_lines) + current_line
            self.logger.debug("Channel: {}, Set: {} Line: {}, ".format(
                current_channel, self.current_line_set, current_line))

            try:
                # Get measurement value and timestamp
                if self.options_channels['line_display_type'][current_channel] in [
                        'measurement_value', 'measurement_ts']:
                    lines_display[current_line] = "NONE"
                    measure_ts = None
                    measure_value = None

                    last_measurement = self.get_last_measurement(
                        self.options_channels['select_measurement'][current_channel]['device_id'],
                        self.options_channels['select_measurement'][current_channel]['measurement_id'],
                        max_age=self.options_channels['measure_max_age'][current_channel])

                    if last_measurement:
                        measure_ts = last_measurement[0]
                        measure_value = last_measurement[1]

                    if self.options_channels['line_display_type'][current_channel] == 'measurement_value':
                        if measure_value:
                            if self.options_channels['measure_decimal'][current_channel] == 0:
                                val_rounded = int(measure_value)
                            else:
                                val_rounded = round(
                                    measure_value,
                                    self.options_channels['measure_decimal'][current_channel])

                            lines_display[current_line] = format_measurement_line(
                                self.options_channels['select_measurement'][current_channel]['device_id'],
                                self.options_channels['select_measurement'][current_channel]['measurement_id'],
                                val_rounded,
                                lcd_x_characters,
                                display_unit=self.options_channels['display_unit'][current_channel],
                                label=self.options_channels['measurement_label'][current_channel])

                    elif self.options_channels['line_display_type'][current_channel] == 'measurement_ts':
                        if measure_ts:
                            # Convert UTC timestamp to local timezone
                            lines_display[current_line] = str(datetime.datetime.fromtimestamp(measure_ts))

                elif self.options_channels['line_display_type'][current_channel] == 'current_time':
                    lines_display[current_line] = time.strftime('%Y-%m-%d %H:%M:%S')

                elif self.options_channels['line_display_type'][current_channel] == 'text':
                    lines_display[current_line] = self.options_channels['text'][current_channel]

                elif self.options_channels['line_display_type'][current_channel] == 'blank_line':
                    lines_display[current_line] = ""

                elif self.options_channels['line_display_type'][current_channel] == 'ip_address':
                    str_ip_cmd = "ip addr | " \
                                 "grep 'state UP' -A2 | " \
                                 "tail -n1 | " \
                                 "awk '{print $2}' | " \
                                 "cut -f1  -d'/'"
                    ip_out, _, _ = cmd_output(str_ip_cmd)
                    lines_display[current_line] = ip_out.rstrip().decode("utf-8")
            except Exception as err:
                self.logger.error(
                    "Error generating channel {} line: {}".format(
                        current_channel, err))
                lines_display[current_line] = "ERROR"

        if self.current_line_set == len(self.line_sets) - 1:
            self.current_line_set = 0
        else:
            self.current_line_set += 1

        self.logger.debug("Displaying: {}".format(lines_display))

        # Display lines
        self.lcd.lcd_write_lines(
            lines_display[0], lines_display[1], "", "")

        self.lines_being_written = False

    def stop_function(self):
        self.lcd.lcd_init()
        self.lcd_is_on = True
        self.lcd.lcd_write_lines(
            "AoT-AI {}".format(AOT-AI_VERSION), "LCD Deactivated", "", "")

    #
    # Actions
    #

    def display_backlight_color(self, args_dict=None):
        """Set backlight color."""
        if 'color' not in args_dict or not args_dict['color']:
            self.logger.error("color required")
            return
        self.lcd.display_backlight_color(args_dict['color'])
        self.timer_loop = time.time() - 1  # Induce LCD to update after turning backlight on

    def backlight_on(self, args_dict=None):
        """Turn the backlight on."""
        self.lcd_is_on = True
        self.lcd.lcd_backlight(1)

    def backlight_off(self, args_dict=None):
        """Turn the backlight off."""
        self.lcd_is_on = False
        while self.lines_being_written:
            time.sleep(0.1)  # Wait for lines to be written before turning backlight off
        self.lcd.lcd_backlight(0)
