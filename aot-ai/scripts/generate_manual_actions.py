# -*- coding: utf-8 -*-
"""Generate markdown file of Action information to be inserted into the manual."""
import os
import sys

sys.path.append(os.path.abspath(os.path.join(__file__, "../../..")))

from collections import OrderedDict
from aot-ai.config import INSTALL_DIRECTORY
from aot-ai.scripts.generate_doc_output import generate_controller_doc
from aot-ai.utils.actions import parse_action_information

save_path = os.path.join(INSTALL_DIRECTORY, "docs/Supported-Actions.md")

actions_info = OrderedDict()
aot-ai_info = OrderedDict()


def repeat_to_length(s, wanted):
    return (s * (wanted//len(s) + 1))[:wanted]


if __name__ == "__main__":
    for action_id, action_data in parse_action_information(exclude_custom=True).items():
        name_str = ""
        if 'manufacturer' in action_data and action_data['manufacturer']:
            name_str += f"{action_data['manufacturer']}"
        if 'name' in action_data and action_data['name']:
            name_str += f": {action_data['name']}"
        if 'library' in action_data and action_data['library']:
            name_str += f": {action_data['library']}"

        if ('manufacturer' in action_data and
                action_data['manufacturer'] in ['Linux', 'AoT-AI', 'Raspberry Pi', 'System']):

            if name_str in aot-ai_info and 'dependencies_module' in aot-ai_info[name_str]:
                # Multiple sets of dependencies, append library
                aot-ai_info[name_str]['dependencies_module'].append(action_data['dependencies_module'])
            else:
                # Only one set of dependencies
                aot-ai_info[name_str] = action_data
                if 'dependencies_module' in action_data:
                    aot-ai_info[name_str]['dependencies_module'] = [action_data['dependencies_module']]  # turn into list
        else:
            if name_str in actions_info and 'dependencies_module' in actions_info[name_str]:
                # Multiple sets of dependencies, append library
                actions_info[name_str]['dependencies_module'].append(action_data['dependencies_module'])
            else:
                # Only one set of dependencies
                actions_info[name_str] = action_data
                if 'dependencies_module' in action_data:
                    actions_info[name_str]['dependencies_module'] = [action_data['dependencies_module']]  # turn into list

    aot-ai_info = dict(OrderedDict(sorted(aot-ai_info.items(), key = lambda t: t[0])))
    actions_info = dict(OrderedDict(sorted(actions_info.items(), key = lambda t: t[0])))

    list_actions = [
        (aot-ai_info, "Built-In Actions (System)"),
        (actions_info, "Built-In Actions (Devices)")
    ]

    with open(save_path, 'w') as out_file:
        for each_list in list_actions:
            if not each_list[0]:
                continue

            out_file.write(f"## {each_list[1]}\n\n")

            for each_id, each_data in each_list[0].items():
                name_str = ""
                if 'name' in each_data and each_data['name']:
                    name_str += each_data['name']

                out_file.write(f"### {name_str}\n\n")

                if 'manufacturer' in each_data and each_data['manufacturer']:
                    out_file.write(f"- Manufacturer: {each_data['manufacturer']}\n")

                if 'library' in each_data and each_data['library']:
                    out_file.write(f"- Libraries: {each_data['library']}\n")

                if 'application' in each_data and each_data['application']:
                    out_file.write(f"- Works with: {', '.join(each_data['application']).title()}\n")

                generate_controller_doc(out_file, each_data)
