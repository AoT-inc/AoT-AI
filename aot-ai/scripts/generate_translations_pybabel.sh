#!/bin/bash
#
# Generates the AoT-AI translation .po files
#
# Requires: pybabel in virtualenv
#

INSTALL_DIRECTORY=$( cd "$( dirname "${BASH_SOURCE[0]}" )/../../" && pwd -P )
CURRENT_VERSION=$("${INSTALL_DIRECTORY}"/env/bin/python3 "${INSTALL_DIRECTORY}"/aot-ai/utils/github_release_info.py -c 2>&1)

INFO_ARGS=(
  --project "AoT-AI"
  --version "${CURRENT_VERSION}"
  --copyright "Kyle T. Gabriel"
  --msgid-bugs-address "aot-ai@aot-inc.com"
)

cd "${INSTALL_DIRECTORY}"/aot-ai || return

printf "\n#### Extracting translatable texts\n"

"${INSTALL_DIRECTORY}"/env/bin/pybabel extract "${INFO_ARGS[@]}" -s -F babel.cfg -k lazy_gettext -o aot-ai_flask/translations/messages.pot .

printf "\n#### Generating translations\n"

"${INSTALL_DIRECTORY}"/env/bin/pybabel update --ignore-obsolete --update-header-comment -i aot-ai_flask/translations/messages.pot -d aot-ai_flask/translations
