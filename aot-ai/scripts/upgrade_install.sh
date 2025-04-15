#!/bin/bash
# Upgrade from a previous release to this current release.
# Check currently-installed version for the ability to upgrade to this release version.

exec 2>&1

RELEASE_WIPE=$1

if [ "$EUID" -ne 0 ] ; then
  printf "Must be run as root.\n"
  exit 1
fi

runSelfUpgrade() {
  function error_found {
    echo '2' > "${INSTALL_DIRECTORY}"/AoT-AI/.upgrade
    printf "\n\n"
    printf "#### ERROR ####\n"
    printf "There was an error detected during the upgrade. Please review the log at /var/log/aot-ai/aot-aiupgrade.log"
    exit 1
  }

  printf "\n#### Beginning Upgrade Stage 2 of 3 ####\n\n"
  TIMER_START_stage_two=$SECONDS

  printf "RELEASE_WIPE = %s\n" "$RELEASE_WIPE"

  CURRENT_AOT-AI_DIRECTORY=$( cd -P /var/aot-ai-root && pwd -P )
  CURRENT_AOT-AI_INSTALL_DIRECTORY=$( cd -P /var/aot-ai-root/.. && pwd -P )
  THIS_AOT-AI_DIRECTORY=$( cd "$( dirname "${BASH_SOURCE[0]}" )/../.." && pwd -P )
  NOW=$(date +"%Y-%m-%d_%H-%M-%S")

  if [ "$CURRENT_AOT-AI_DIRECTORY" == "$THIS_AOT-AI_DIRECTORY" ] ; then
    printf "Cannot perform upgrade to the AoT-AI instance already installed. Halting upgrade.\n"
    exit 1
  fi

  if [ -d "${CURRENT_AOT-AI_DIRECTORY}" ] ; then
    printf "Found currently-installed version of AoT-AI. Checking version...\n"
    CURRENT_VERSION=$("${CURRENT_AOT-AI_INSTALL_DIRECTORY}"/AoT-AI/env/bin/python3 "${CURRENT_AOT-AI_INSTALL_DIRECTORY}"/AoT-AI/aot-ai/utils/github_release_info.py -c 2>&1)
    MAJOR=$(echo "$CURRENT_VERSION" | cut -d. -f1)
    MINOR=$(echo "$CURRENT_VERSION" | cut -d. -f2)
    REVISION=$(echo "$CURRENT_VERSION" | cut -d. -f3)
    if [ -z "$MAJOR" ] || [ -z "$MINOR" ] || [ -z "$REVISION" ] ; then
      printf "Could not determine AoT-AI version\n"
      exit 1
    else
      printf "AoT-AI version found installed: %s.%s.%s\n" "${MAJOR}" "${MINOR}" "${REVISION}"
    fi
  else
    printf "Could not find a current version of AoT-AI installed. Check the symlink /var/mycdo-root that is supposed to point to the install directory"
    exit 1
  fi

  ################################
  # Begin tests prior to upgrade #
  ################################

  printf "\n#### Beginning pre-upgrade checks ####\n\n"

  # Upgrade requires Python >= 3.8
  printf "Checking Python version...\n"
  if hash python3 2>/dev/null; then
    if ! python3 "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/scripts/upgrade_check.py --min_python_version "3.8"; then
      printf "Error: Incorrect Python version found. AoT-AI requires Python >= 3.8.\n"
      echo '0' > "${CURRENT_AOT-AI_DIRECTORY}"/.upgrade
      exit 1
    else
      printf "Python >= 3.8 found. Continuing with the upgrade.\n"
    fi
  else
    printf "\nError: python3 binary required in PATH to proceed with the upgrade.\n"
    echo '0' > "${CURRENT_AOT-AI_DIRECTORY}"/.upgrade
    exit 1
  fi

  # If upgrading from version 7 and Python >= 3.6 found (from previous check), upgrade without wiping database
  if [[ "$MAJOR" == 7 ]] && [[ "$RELEASE_WIPE" = true ]]; then
    printf "Your system was found to have Python >= 3.6 installed. Proceeding with upgrade without wiping database.\n"
    RELEASE_WIPE=false
  fi

  printf "All pre-upgrade checks passed. Proceeding with upgrade.\n\n"

  ##############################
  # End tests prior to upgrade #
  ##############################

  THIS_VERSION=$("${CURRENT_AOT-AI_DIRECTORY}"/env/bin/python3 "${THIS_AOT-AI_DIRECTORY}"/aot-ai/utils/github_release_info.py -c 2>&1)
  printf "Upgrading AoT-AI to version %s\n\n" "$THIS_VERSION"

  printf "Stopping the AoT-AI daemon..."
  if ! service aot-ai stop ; then
    printf "Error: Unable to stop the daemon. Continuing anyway...\n"
  fi
  printf "Done.\n"

  if [ -d "${CURRENT_AOT-AI_DIRECTORY}"/env ] ; then
    printf "Moving env directory..."
    if ! mv "${CURRENT_AOT-AI_DIRECTORY}"/env "${THIS_AOT-AI_DIRECTORY}" ; then
      printf "Failed: Error while trying to move env directory.\n"
      error_found
    fi
    printf "Done.\n"
  fi

  printf "Copying databases..."
  if ! cp "${CURRENT_AOT-AI_DIRECTORY}"/databases/*.db "${THIS_AOT-AI_DIRECTORY}"/databases ; then
    printf "Failed: Error while trying to copy databases."
    error_found
  fi
  printf "Done.\n"

  if [ -f "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/config_override.py ] ; then
    printf "Copying config_override.py..."
    if ! cp "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/config_override.py "${THIS_AOT-AI_DIRECTORY}"/aot-ai/ ; then
      printf "Failed: Error while trying to copy config_override.py."
    fi
    printf "Done.\n"
  fi

  printf "Copying flask_secret_key..."
  if ! cp "${CURRENT_AOT-AI_DIRECTORY}"/databases/flask_secret_key "${THIS_AOT-AI_DIRECTORY}"/databases ; then
    printf "Failed: Error while trying to copy flask_secret_key."
  fi
  printf "Done.\n"

  if [ -d "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/aot-ai_flask/ssl_certs ] ; then
    printf "Copying SSL certificates..."
    if ! cp -R "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/aot-ai_flask/ssl_certs "${THIS_AOT-AI_DIRECTORY}"/aot-ai/aot-ai_flask/ssl_certs ; then
      printf "Failed: Error while trying to copy SSL certificates."
      error_found
    fi
    printf "Done.\n"
  fi

  # TODO: Remove in next major release
  if [ -d "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/controllers/custom_controllers ] ; then
    printf "Copying aot-ai/controllers/custom_controllers..."
    if ! cp "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/controllers/custom_controllers/*.py "${THIS_AOT-AI_DIRECTORY}"/aot-ai/functions/custom_functions/ ; then
      printf "Failed: Error while trying to copy aot-ai/controllers/custom_controllers"
      error_found
    fi
    printf "Done.\n"
  fi

  if [ -d "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/functions/custom_functions ] ; then
    printf "Copying aot-ai/functions/custom_functions..."
    if ! cp "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/functions/custom_functions/*.py "${THIS_AOT-AI_DIRECTORY}"/aot-ai/functions/custom_functions/ ; then
      printf "Failed: Error while trying to copy aot-ai/functions/custom_functions"
      error_found
    fi
    printf "Done.\n"
  fi

  if [ -d "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/actions/custom_actions ] ; then
    printf "Copying aot-ai/actions/custom_actions..."
    if ! cp "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/actions/custom_actions/*.py "${THIS_AOT-AI_DIRECTORY}"/aot-ai/actions/custom_actions/ ; then
      printf "Failed: Error while trying to copy aot-ai/actions/custom_actions"
      error_found
    fi
    printf "Done.\n"
  fi

  if [ -d "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/inputs/custom_inputs ] ; then
    printf "Copying aot-ai/inputs/custom_inputs..."
    if ! cp "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/inputs/custom_inputs/*.py "${THIS_AOT-AI_DIRECTORY}"/aot-ai/inputs/custom_inputs/ ; then
      printf "Failed: Error while trying to copy aot-ai/inputs/custom_inputs"
      error_found
    fi
    printf "Done.\n"
  fi

  if [ -d "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/outputs/custom_outputs ] ; then
    printf "Copying aot-ai/outputs/custom_outputs..."
    if ! cp "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/outputs/custom_outputs/*.py "${THIS_AOT-AI_DIRECTORY}"/aot-ai/outputs/custom_outputs/ ; then
      printf "Failed: Error while trying to copy aot-ai/outputs/custom_outputs"
      error_found
    fi
    printf "Done.\n"
  fi

  if [ -d "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/widgets/custom_widgets ] ; then
    printf "Copying aot-ai/widgets/custom_widgets..."
    if ! cp "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/widgets/custom_widgets/*.py "${THIS_AOT-AI_DIRECTORY}"/aot-ai/widgets/custom_widgets/ ; then
      printf "Failed: Error while trying to copy aot-ai/widgets/custom_widgets"
      error_found
    fi
    printf "Done.\n"
  fi

  if [ -d "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/user_python_code ] ; then
    printf "Copying aot-ai/user_python_code..."
    if ! cp "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/user_python_code/*.py "${THIS_AOT-AI_DIRECTORY}"/aot-ai/user_python_code/ ; then
      printf "Failed: Error while trying to copy aot-ai/user_python_code"
      error_found
    fi
    printf "Done.\n"
  fi

  if [ -d "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/note_attachments ] ; then
    printf "Copying aot-ai/note_attachments..."
    if ! cp -r "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/note_attachments "${THIS_AOT-AI_DIRECTORY}"/aot-ai/ ; then
      printf "Failed: Error while trying to copy aot-ai/note_attachments"
      error_found
    fi
    printf "Done.\n"
  fi

  if [ -d "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/aot-ai_flask/static/js/user_js ] ; then
    printf "Copying aot-ai/aot-ai_flask/static/js/user_js..."
    if ! cp -r "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/aot-ai_flask/static/js/user_js "${THIS_AOT-AI_DIRECTORY}"/aot-ai/aot-ai_flask/static/js/ ; then
      printf "Failed: Error while trying to copy aot-ai/aot-ai_flask/static/js/user_js"
      error_found
    fi
    printf "Done.\n"
  fi

  if [ -d "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/aot-ai_flask/static/css/user_css ] ; then
    printf "Copying aot-ai/aot-ai_flask/static/css/user_css..."
    if ! cp -r "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/aot-ai_flask/static/css/user_css "${THIS_AOT-AI_DIRECTORY}"/aot-ai/aot-ai_flask/static/css/ ; then
      printf "Failed: Error while trying to copy aot-ai/aot-ai_flask/static/css/user_css"
      error_found
    fi
    printf "Done.\n"
  fi

  if [ -d "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/aot-ai_flask/static/fonts/user_fonts ] ; then
    printf "Copying aot-ai/aot-ai_flask/static/fonts/user_fonts..."
    if ! cp -r "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/aot-ai_flask/static/fonts/user_fonts "${THIS_AOT-AI_DIRECTORY}"/aot-ai/aot-ai_flask/static/fonts/ ; then
      printf "Failed: Error while trying to copy aot-ai/aot-ai_flask/static/fonts/user_fonts"
      error_found
    fi
    printf "Done.\n"
  fi

  if [ -d "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/user_scripts ] ; then
    printf "Copying aot-ai/user_scripts..."
    if ! cp -r "${CURRENT_AOT-AI_DIRECTORY}"/aot-ai/user_scripts "${THIS_AOT-AI_DIRECTORY}"/aot-ai/ ; then
      printf "Failed: Error while trying to copy aot-ai/user_scripts"
      error_found
    fi
    printf "Done.\n"
  fi

  if [ -d "${CURRENT_AOT-AI_DIRECTORY}"/output_usage_reports ] ; then
    printf "Moving output_usage_reports directory..."
    if ! mv "${CURRENT_AOT-AI_DIRECTORY}"/output_usage_reports "${THIS_AOT-AI_DIRECTORY}" ; then
      printf "Failed: Error while trying to move output_usage_reports directory.\n"
    fi
    printf "Done.\n"
  fi

  if [ -d "${CURRENT_AOT-AI_DIRECTORY}"/cameras ] ; then
    printf "Moving cameras directory..."
    if ! mv "${CURRENT_AOT-AI_DIRECTORY}"/cameras "${THIS_AOT-AI_DIRECTORY}" ; then
      printf "Failed: Error while trying to move cameras directory.\n"
    fi
    printf "Done.\n"
  fi

  if [ -d "${CURRENT_AOT-AI_DIRECTORY}"/.upgrade ] ; then
    printf "Moving .upgrade file..."
    if ! mv "${CURRENT_AOT-AI_DIRECTORY}"/.upgrade "${THIS_AOT-AI_DIRECTORY}" ; then
      printf "Failed: Error while trying to move .upgrade file.\n"
    fi
    printf "Done.\n"
  fi

  if [ ! -d "/var/AoT-AI-backups" ] ; then
    mkdir /var/AoT-AI-backups
  fi

  BACKUP_DIR="/var/AoT-AI-backups/AoT-AI-backup-${NOW}-${CURRENT_VERSION}"

  printf "Moving current AoT-AI install from %s to %s..." "${CURRENT_AOT-AI_DIRECTORY}" "${BACKUP_DIR}"
  if ! mv "${CURRENT_AOT-AI_DIRECTORY}" "${BACKUP_DIR}" ; then
    printf "Failed: Error while trying to move old AoT-AI install from %s to %s.\n" "${CURRENT_AOT-AI_DIRECTORY}" "${BACKUP_DIR}"
    error_found
  fi
  printf "Done.\n"

  mkdir -p /opt

  printf "Moving downloaded AoT-AI version from %s to /opt/AoT-AI..." "${THIS_AOT-AI_DIRECTORY}"
  if ! mv "${THIS_AOT-AI_DIRECTORY}" /opt/AoT-AI ; then
    printf "Failed: Error while trying to move new AoT-AI install from %s to /opt/AoT-AI.\n" "${THIS_AOT-AI_DIRECTORY}"
    error_found
  fi
  printf "Done.\n"

  sleep 30

  cd /opt/AoT-AI || return

  ############################################
  # Begin tests prior to post-upgrade script #
  ############################################

  if [ "$RELEASE_WIPE" = true ] ; then
    # Instructed to wipe configuration files (database, virtualenv)

    if [ -d /opt/AoT-AI/env ] ; then
      printf "Removing virtualenv at /opt/AoT-AI/env..."
      if ! rm -rf /opt/AoT-AI/env ; then
        printf "Failed: Error while trying to delete virtaulenv at /opt/AoT-AI/env.\n"
      fi
      printf "Done.\n"
    fi

    if [ -d /opt/AoT-AI/databases/aot-ai.db ] ; then
      printf "Removing database at /opt/AoT-AI/databases/aot-ai.db..."
      if ! rm -f /opt/AoT-AI/databases/aot-ai.db ; then
        printf "Failed: Error while trying to delete database at /opt/AoT-AI/databases/aot-ai.db.\n"
      fi
      printf "Done.\n"
    fi

  fi

  printf "\n#### Completed Upgrade Stage 2 of 3 in %s seconds ####\n" "$((SECONDS - TIMER_START_stage_two))"

  ##########################################
  # End tests prior to post-upgrade script #
  ##########################################

  printf "\n#### Beginning Upgrade Stage 3 of 3 ####\n\n"
  TIMER_START_stage_three=$SECONDS

  printf "Running post-upgrade script...\n"
  if ! /opt/AoT-AI/aot-ai/scripts/upgrade_post.sh ; then
    printf "Failed: Error while running post-upgrade script.\n"
    error_found
  fi

  printf "\n#### Completed Upgrade Stage 3 of 3 in %s seconds ####\n\n" "$((SECONDS - TIMER_START_stage_three))"

  printf "Upgrade completed. Review the log to ensure no critical errors were encountered\n"

  #############################
  # Begin tests after upgrade #
  #############################



  ###########################
  # End tests after upgrade #
  ###########################

  echo '0' > /opt/AoT-AI/.upgrade

  exit 0
}

runSelfUpgrade
