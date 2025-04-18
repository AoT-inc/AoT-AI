#!/bin/bash

exec 2>&1

if [ "$EUID" -ne 0 ] ; then
    printf "Must be run as root.\n"
    exit 1
fi

INSTALL_DIRECTORY=$( cd -P /var/aot-ai-root/.. && pwd -P )

function error_found {
    date
    printf "\n#### ERROR ####"
    printf "\nThere was an error detected while creating the backup. Please review the log at /var/log/aot-ai/aot-aibackup.log"
    exit 1
}

CURRENT_VERSION=$("${INSTALL_DIRECTORY}"/AoT-AI/env/bin/python "${INSTALL_DIRECTORY}"/AoT-AI/aot-ai/utils/github_release_info.py -c 2>&1)
NOW=$(date +"%Y-%m-%d_%H-%M-%S")
TMP_DIR="/var/tmp/AoT-AI-backup-${NOW}-${CURRENT_VERSION}"
BACKUP_DIR="/var/AoT-AI-backups/AoT-AI-backup-${NOW}-${CURRENT_VERSION}"

printf "\n#### Create backup initiated %s ####\n" "${NOW}"

mkdir -p /var/AoT-AI-backups

printf "Backing up current AoT-AI from %s/AoT-AI to %s..." "${INSTALL_DIRECTORY}" "${TMP_DIR}"
if ! rsync -avq --exclude=cameras --exclude=env --exclude=.upgrade "${INSTALL_DIRECTORY}"/AoT-AI "${TMP_DIR}" ; then
    printf "Failed: Error while trying to back up current AoT-AI install from %s/AoT-AI to %s.\n" "${INSTALL_DIRECTORY}" "${BACKUP_DIR}"
    error_found
fi
printf "Done.\n"

printf "Moving %s/AoT-AI to %s..." "${TMP_DIR}" "${BACKUP_DIR}"
if ! mv "${TMP_DIR}"/AoT-AI "${BACKUP_DIR}" ; then
    printf "Failed: Error while trying to move %s/AoT-AI to %s.\n" "${TMP_DIR}" "${BACKUP_DIR}"
    error_found
fi
printf "Done.\n"

date
printf "Backup completed successfully without errors.\n"
