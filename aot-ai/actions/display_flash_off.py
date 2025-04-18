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
    'name_unique': 'display_flash_off',
    'name': "{}: {}: {}".format(TRANSLATIONS['display']['title'], lazy_gettext('Flashing'), lazy_gettext('Off')),
    'library': None,
    'manufacturer': 'AoT-AI',
    'application': ['functions'],

    'url_manufacturer': None,
    'url_datasheet': None,
    'url_product_purchase': None,
    'url_additional': None,

    'message': 'Turn display flashing off',

    'usage': 'Executing <strong>self.run_action("ACTION_ID")</strong> will stop the backlight flashing on the selected display. '
             'Executing <strong>self.run_action("ACTION_ID", value={"display_id": "959019d1-c1fa-41fe-a554-7be3366a9c5b"})</strong> will stop the backlight flashing on the controller with the specified ID. Don\'t forget to change the display_id value to an actual Function ID that exists in your system.',

    'custom_options': [
        {
            'id': 'controller',
            'type': 'select_device',
            'default_value': '',
            'options_select': [
                'Function'
            ],
            'name': lazy_gettext('Display'),
            'phrase': 'Select the display to stop flashing the backlight'
        }
    ]
}


class ActionModule(AbstractFunctionAction):
    """Function Action: Turn Off Display Backlight Flashing."""
    def __init__(self, action_dev, testing=False):
        super().__init__(action_dev, testing=testing, name=__name__)

        self.controller_id = None

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

        display = db_retrieve_table_daemon(
            CustomController, unique_id=controller_id)

        if not display:
            msg = f" Error: Display with ID '{controller_id}' not found."
            dict_vars['message'] += msg
            self.logger.error(msg)
            return dict_vars

        functions = parse_function_information()
        if display.device in functions and "function_actions" in functions[display.device]:
            if "backlight_flash" not in functions[display.device]["function_actions"]:
                msg = " Selected display is not capable of flashing"
                dict_vars['message'] += msg
                self.logger.error(msg)
                return dict_vars

        dict_vars['message'] += f" Display {controller_id} ({display.name}) Flash Off."

        stop_flashing = threading.Thread(
            target=self.control.module_function,
            args=("Function", controller_id, "backlight_flash_off", {},))
        stop_flashing.start()

        self.logger.debug(f"Message: {dict_vars['message']}")

        return dict_vars

    def is_setup(self):
        return self.action_setup
