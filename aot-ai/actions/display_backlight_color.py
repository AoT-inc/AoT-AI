# coding=utf-8
import threading

from flask_babel import lazy_gettext
from aot-ai.utils.functions import parse_function_information
from aot-ai.config_translations import TRANSLATIONS
from aot-ai.databases.models import Actions
from aot-ai.databases.models import CustomController
from aot-ai.actions.base_action import AbstractFunctionAction
from aot-ai.utils.database import db_retrieve_table_daemon

ACTION_INFORMATION = {
    'name_unique': 'display_backlight_color',
    'name': "{}: {}: {}".format(TRANSLATIONS['display']['title'], lazy_gettext('Backlight'), lazy_gettext('Color')),
    'library': None,
    'manufacturer': 'AoT-AI',
    'application': ['functions'],

    'url_manufacturer': None,
    'url_datasheet': None,
    'url_product_purchase': None,
    'url_additional': None,

    'message': 'Set the display backlight color',

    'usage': 'Executing <strong>self.run_action("ACTION_ID")</strong> will change the backlight color on the selected display. '
             'Executing <strong>self.run_action("ACTION_ID", value={"display_id": "959019d1-c1fa-41fe-a554-7be3366a9c5b", "color": "255,0,0"})</strong> will change the backlight color on the controller with the specified ID and color. Don\'t forget to change the display_id value to an actual Function ID that exists in your system.',

    'custom_options': [
        {
            'id': 'controller',
            'type': 'select_device',
            'default_value': '',
            'options_select': [
                'Function'
            ],
            'name': lazy_gettext('Display'),
            'phrase': 'Select the display to set the backlight color'
        },
        {
            'id': 'color',
            'type': 'text',
            'default_value': '255,0,0',
            'required': False,
            'name': 'Color (RGB)',
            'phrase': 'Color as R,G,B values (e.g. "255,0,0" without quotes)'
        }
    ]
}


class ActionModule(AbstractFunctionAction):
    """Function Action: Set the Display Backlight Color."""
    def __init__(self, action_dev, testing=False):
        super().__init__(action_dev, testing=testing, name=__name__)

        self.controller_id = None
        self.color = None

        action = db_retrieve_table_daemon(
            Actions, unique_id=self.unique_id)
        self.setup_custom_options(
            ACTION_INFORMATION['custom_options'], action)

        if not testing:
            self.try_initialize()

    def initialize(self):
        self.action_setup = True

    def run_action(self, dict_vars):
        try:
            controller_id = dict_vars["value"]["display_id"]
        except:
            controller_id = self.controller_id

        try:
            color = dict_vars["value"]["color"]
        except:
            color = self.color

        display = db_retrieve_table_daemon(
            CustomController, unique_id=controller_id)

        if not display:
            msg = f" Error: Display with ID '{controller_id}' not found."
            dict_vars['message'] += msg
            self.logger.error(msg)
            return dict_vars

        functions = parse_function_information()
        if (display.device not in functions or
                "function_actions" not in functions[display.device] or
                "display_backlight_color" not in functions[display.device]["function_actions"]):
            msg = " Selected display is not capable of setting the backlight color."
            dict_vars['message'] += msg
            self.logger.error(msg)
            return dict_vars

        dict_vars['message'] += f" Set display {controller_id} ({display.name}) backlight color to {color}."

        start_flashing = threading.Thread(
            target=self.control.module_function,
            args=("Function", controller_id, "display_backlight_color", {"color": color},))
        start_flashing.start()

        self.logger.debug(f"Message: {dict_vars['message']}")

        return dict_vars

    def is_setup(self):
        return self.action_setup
