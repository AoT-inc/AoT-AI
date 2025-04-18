#!/bin/bash
#
# Runs all pytests
#

INSTALL_DIRECTORY=$( cd "$( dirname "${BASH_SOURCE[0]}" )/../../" && pwd -P )

cd "${INSTALL_DIRECTORY}"/aot-ai || return

"${INSTALL_DIRECTORY}"/env/bin/pytest -s tests/software_tests

rm "${INSTALL_DIRECTORY}"/databases/flask_secret_key
rm -r "${INSTALL_DIRECTORY}"/aot-ai/.pytest_cache
