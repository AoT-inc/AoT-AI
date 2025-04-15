#!/bin/bash
#
#  upgrade_commands.sh - AoT-AI commands
#

exec 2>&1

if [[ "$EUID" -ne 0 ]]; then
    printf "Must be run as root.\n"
    exit 1
fi

# Current AoT-AI major version number
AOT-AI_MAJOR_VERSION="8"

# Dependency versions/URLs
PIGPIO_URL="https://github.com/joan2937/pigpio/archive/v79.tar.gz"
MCB2835_URL="http://www.airspayce.com/mikem/bcm2835/bcm2835-1.50.tar.gz"
WIRINGPI_URL_ARMHF="https://github.com/WiringPi/WiringPi/releases/download/2.61-1/wiringpi-2.61-1-armhf.deb"
WIRINGPI_URL_ARM64="https://github.com/WiringPi/WiringPi/releases/download/2.61-1/wiringpi-2.61-1-arm64.deb"

INFLUXDB1_VERSION="1.8.10"

# Required apt packages
APT_PKGS="gawk gcc g++ git jq libatlas-base-dev libffi-dev libi2c-dev logrotate moreutils netcat-openbsd nginx python3 python3-dev python3-pip python3-setuptools python3-venv rng-tools sqlite3 unzip wget"

UNAME_TYPE=$(uname -m)
MACHINE_TYPE=$(dpkg --print-architecture)

# Get the AoT-AI root directory
SOURCE="${BASH_SOURCE[0]}"

while [[ -h "$SOURCE" ]]; do # resolve $SOURCE until the file is no longer a symlink
    DIR="$( cd -P "$( dirname "$SOURCE" )" && pwd )"
    SOURCE="$(readlink "$SOURCE")"
    [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE" # if $SOURCE was a relative symlink, we need to resolve it relative to the path where the symlink file was located
done

AOT-AI_PATH="$( cd -P "$( dirname "${SOURCE}" )/../.." && pwd )"

cd "${AOT-AI_PATH}" || return

HELP_OPTIONS="upgrade_commands.sh [option] - Program to execute various aot-ai commands

Options:
  backup-create                 Create a backup of the /opt/AoT-AI directory
  backup-restore [backup]       Restore [backup] location, which must be the full path to the backup.
                                Ex.: '/var/AoT-AI-backups/AoT-AI-backup-2018-03-11_21-19-15-5.6.4/'
  compile-aot-ai-wrapper        Compile aot-ai_wrapper.c
  compile-translations          Compile language translations for web interface
  create-files-directories      Create required directories
  create-symlinks               Create required symlinks
  create-user                   Create 'aot-ai' user and add to appropriate groups
  initialize                    Issues several commands to set up directories/files/permissions
  generate-widget-html          Generate HTML templates for all widgets
  restart-daemon                Restart the AoT-AI daemon
  setup-virtualenv              Create a Python virtual environment
  setup-virtualenv-full         Create a Python virtual environment and install dependencies
  ssl-certs-generate            Generate SSL certificates for the web user interface
  ssl-certs-regenerate          Regenerate SSL certificates
  uninstall-apt-pip             Uninstall the apt version of pip
  update-alembic                Use alembic to upgrade the aot-ai.db settings database
  update-alembic-post           Execute script following all alembic upgrades
  update-apt                    Update apt sources
  update-dependencies           Check for updates to dependencies and update
  install-bcm2835               Install bcm2835
  install-wiringpi              Install wiringpi
  install-pigpiod               Install pigpiod
  uninstall-pigpiod             Uninstall pigpiod
  disable-pigpiod               Disable pigpiod
  enable-pigpiod-low            Enable pigpiod with 1 ms sample rate
  enable-pigpiod-high           Enable pigpiod with 5 ms sample rate
  enable-pigpiod-disabled       Create empty service to indicate pigpiod is disabled
  uninstall                     Disable AoT-AI services (frontend/backend)
  update-pigpiod                Update to latest version of pigpiod service file
  update-influxdb-1             Update influxdb 1.x to the latest version
  update-influxdb-2             Update influxdb 2.x to the latest version
  update-influxdb-1-db-user     Create the influxdb 1.x database and user
  update-influxdb-2-db-user     Create the influxdb 2.x database and user
  update-logrotate              Install logrotate script
  update-aot-ai-service-disable Disable the AoT-AI daemon startup script
  update-aot-ai-service-enable  Enable the AoT-AI daemon startup script
  update-aot-ai-startup-script  Update the AoT-AI daemon startup script
  update-packages               Ensure required apt packages are installed/up-to-date
  update-permissions            Set permissions for AoT-AI directories/files
  update-pip3                   Update pip
  update-pip3-packages          Update required pip packages
  update-swap-size              Ensure swap size is sufficiently large (512 MB)
  upgrade-aot-ai                Upgrade AoT-AI to latest compatible release and preserve database and virtualenv
  upgrade-release-major {ver}   Upgrade AoT-AI to a major version release {ver} and preserve database and virtualenv
  upgrade-release-wipe {ver}    Upgrade AoT-AI to a major version release {ver} and wipe database and virtualenv
  upgrade-master                Upgrade AoT-AI to the master branch at https://github.com/aot-inc/AoT-AI
  upgrade-post                  Execute post-upgrade script
  web-server-connect            Attempt to connect to the web server
  web-server-restart            Restart the web server
  web-server-disable            Disable the web server service
  web-server-enable             Enable the web server service
  web-server-update             Update the web server configuration files

Docker-specific Commands:
  docker-update-pip             Update pip
  docker-update-pip-packages    Update required pip packages
  install-docker-ce-cli         Install Docker Client
"

case "${1:-''}" in
    'backup-create')
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/aot-ai_backup_create.sh
    ;;
    'backup-restore')
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/aot-ai_backup_restore.sh "${2}"
    ;;
    'compile-aot-ai-wrapper')
        printf "\n#### Compiling aot-ai_wrapper\n"
        gcc "${AOT-AI_PATH}"/aot-ai/scripts/aot-ai_wrapper.c -o "${AOT-AI_PATH}"/aot-ai/scripts/aot-ai_wrapper
        chown root:aot-ai "${AOT-AI_PATH}"/aot-ai/scripts/aot-ai_wrapper
        chmod 4770 "${AOT-AI_PATH}"/aot-ai/scripts/aot-ai_wrapper
    ;;
    'compile-translations')
        printf "\n#### Compiling Translations\n"
        sudo chmod -R +x "${AOT-AI_PATH}/env/bin/"
        cd "${AOT-AI_PATH}"/aot-ai || return
        "${AOT-AI_PATH}"/env/bin/pybabel compile -d aot-ai_flask/translations
    ;;
    'create-files-directories')
        printf "\n#### Creating files and directories\n"
        mkdir -p /var/log/aot-ai
        mkdir -p /var/AoT-AI-backups
        mkdir -p /usr/local/aot-ai

        mkdir -p "${AOT-AI_PATH}"/install
        mkdir -p "${AOT-AI_PATH}"/aot-ai
        mkdir -p "${AOT-AI_PATH}"/databases
        mkdir -p "${AOT-AI_PATH}"/databases/kma
        mkdir -p "${AOT-AI_PATH}"/note_attachments
        mkdir -p "${AOT-AI_PATH}"/aot-ai/scripts
        mkdir -p "${AOT-AI_PATH}"/aot-ai/aot-ai_flask/ssl_certs
        mkdir -p "${AOT-AI_PATH}"/aot-ai/aot-ai_flask/static/js/user_js
        mkdir -p "${AOT-AI_PATH}"/aot-ai/aot-ai_flask/static/css/user_css
        mkdir -p "${AOT-AI_PATH}"/aot-ai/aot-ai_flask/static/fonts/user_fonts

        if [[ ! -e /var/log/aot-ai/aot-ai.log ]]; then
            touch /var/log/aot-ai/aot-ai.log
        fi
        if [[ ! -e /var/log/aot-ai/aot-aibackup.log ]]; then
            touch /var/log/aot-ai/aot-aibackup.log
        fi
        if [[ ! -e /var/log/aot-ai/aot-aikeepup.log ]]; then
            touch /var/log/aot-ai/aot-aikeepup.log
        fi
        if [[ ! -e /var/log/aot-ai/aot-aidependency.log ]]; then
            touch /var/log/aot-ai/aot-aidependency.log
        fi
        if [[ ! -e /var/log/aot-ai/aot-aiimport.log ]]; then
            touch /var/log/aot-ai/aot-aiimport.log
        fi
        if [[ ! -e /var/log/aot-ai/aot-aiupgrade.log ]]; then
            touch /var/log/aot-ai/aot-aiupgrade.log
        fi
        if [[ ! -e /var/log/aot-ai/aot-airestore.log ]]; then
            touch /var/log/aot-ai/aot-airestore.log
        fi
        if [[ ! -e /var/log/aot-ai/login.log ]]; then
            touch /var/log/aot-ai/login.log
        fi

        # Create empty aot-ai database file if it doesn't exist
        if [[ ! -e ${AOT-AI_PATH}/databases/aot-ai.db ]]; then
            touch "${AOT-AI_PATH}"/databases/aot-ai.db
        fi
    ;;
    'create-symlinks')
        printf "\n#### Creating symlinks to AoT-AI executables\n"
        ln -sfn "${AOT-AI_PATH}" /var/aot-ai-root
        ln -sfn "${AOT-AI_PATH}"/aot-ai/aot-ai_daemon.py /usr/bin/aot-ai-daemon
        ln -sfn "${AOT-AI_PATH}"/aot-ai/aot-ai_client.py /usr/bin/aot-ai-client
        ln -sfn "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh /usr/bin/aot-ai-commands
        ln -sfn "${AOT-AI_PATH}"/aot-ai/scripts/aot-ai_backup_create.sh /usr/bin/aot-ai-backup
        ln -sfn "${AOT-AI_PATH}"/aot-ai/scripts/aot-ai_backup_restore.sh /usr/bin/aot-ai-restore
        ln -sfn "${AOT-AI_PATH}"/aot-ai/scripts/aot-ai_wrapper /usr/bin/aot-ai-wrapper
        ln -sfn "${AOT-AI_PATH}"/env/bin/pip3 /usr/bin/aot-ai-pip
        ln -sfn "${AOT-AI_PATH}"/env/bin/python /usr/bin/aot-ai-python
    ;;
    'create-user')
        printf "\n#### Creating aot-ai user\n"
        useradd -M aot-ai
        adduser aot-ai adm
        adduser aot-ai dialout
        adduser aot-ai i2c
        adduser aot-ai kmem
        adduser aot-ai video

        if getent group gpio; then
            adduser aot-ai gpio
        fi

        usermod -aG aot-ai $USER
        usermod -aG $USER aot-ai
    ;;
    'generate-widget-html')
        printf "\n#### Generating widget HTML files\n"
        "${AOT-AI_PATH}"/env/bin/python "${AOT-AI_PATH}"/aot-ai/utils/widget_generate_html.py
    ;;
    'initialize')
        printf "\n#### Running initialization\n"
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh create-user
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh compile-aot-ai-wrapper
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh create-symlinks
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh create-files-directories
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh update-permissions
        systemctl daemon-reload
    ;;
    'restart-daemon')
        printf "\n#### Restarting the AoT-AI daemon\n"
        service aot-ai restart
    ;;
    'setup-virtualenv')
        printf "\n#### Checking Python 3 virtual environment\n"
        if [[ ! -e ${AOT-AI_PATH}/env/bin/python ]]; then
            printf "#### Creating virtual environment at ${AOT-AI_PATH}/env\n"
            rm -rf "${AOT-AI_PATH}"/env
            python3 -m venv "${AOT-AI_PATH}"/env
        fi
    ;;
    'setup-virtualenv-full')
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh setup-virtualenv
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh update-pip3
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh update-pip3-packages
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh update-dependencies
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh update-permissions
    ;;
    'ssl-certs-generate')
        printf "\n#### Generating SSL certificates at %s/aot-ai/aot-ai_flask/ssl_certs (replace with your own if desired)\n" "${AOT-AI_PATH}"
        mkdir -p "${AOT-AI_PATH}"/aot-ai/aot-ai_flask/ssl_certs
        cd "${AOT-AI_PATH}"/aot-ai/aot-ai_flask/ssl_certs/ || return
        rm -f ./*.pem ./*.csr ./*.crt ./*.key

        openssl genrsa -out server.pass.key 4096
        openssl rsa -in server.pass.key -out server.key
        rm -f server.pass.key
        openssl req -new -key server.key -out server.csr \
            -subj "/O=aot-ai/OU=aot-ai/CN=aot-ai"
        openssl x509 -req \
            -days 3653 \
            -in server.csr \
            -signkey server.key \
            -out server.crt
    ;;
    'ssl-certs-regenerate')
        printf "\n#### Regenerating SSL certificates at %s/aot-ai/aot-ai_flask/ssl_certs\n" "${AOT-AI_PATH}"
        rm -rf "${AOT-AI_PATH}"/aot-ai/aot-ai_flask/ssl_certs/*.pem
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh ssl-certs-generate
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh initialize
        sudo service nginx restart
        sudo service aot-aiflask restart
    ;;
    'uninstall-apt-pip')
        printf "\n#### Uninstalling apt version of pip (if installed)\n"
        apt purge -y python-pip
    ;;
    'update-alembic')
        printf "\n#### Upgrading AoT-AI database with alembic (if needed)\n"
        cd "${AOT-AI_PATH}"/alembic_db || return
        "${AOT-AI_PATH}"/env/bin/python -m alembic upgrade head
    ;;
    'update-alembic-post')
        printf "\n#### Executing post-alembic script\n"
        "${AOT-AI_PATH}"/env/bin/python "${AOT-AI_PATH}"/alembic_db/alembic_post.py
    ;;
    'update-apt')
        printf "\n#### Updating apt repositories\n"
        apt update -y
    ;;
    'update-dependencies')
        printf "\n#### Checking for updates to dependencies\n"
        "${AOT-AI_PATH}"/env/bin/python "${AOT-AI_PATH}"/aot-ai/utils/update_dependencies.py
    ;;
    'install-bcm2835')
        printf "\n#### Installing bcm2835\n"
        cd "${AOT-AI_PATH}"/install || return
        apt install -y automake libtool
        wget ${MCB2835_URL} -O bcm2835.tar.gz
        mkdir bcm2835
        tar xzf bcm2835.tar.gz -C bcm2835 --strip-components=1
        cd bcm2835 || return
        autoreconf -vfi
        ./configure
        make
        sudo make check
        sudo make install
        cd "${AOT-AI_PATH}"/install || return
        rm -rf ./bcm2835
    ;;
    'install-wiringpi')
        if [[ ${MACHINE_TYPE} == 'armhf' ]]; then
            wget ${WIRINGPI_URL_ARMHF} -O wiringpi-latest.deb
            dpkg -i wiringpi-latest.deb
            rm -rf wiringpi-latest.deb
        elif [[ ${MACHINE_TYPE} == 'arm64' ]]; then
            wget ${WIRINGPI_URL_ARM64} -O wiringpi-latest.deb
            dpkg -i wiringpi-latest.deb
            rm -rf wiringpi-latest.deb
        else
            printf "\n#### WiringPi not supported on this architecture, skipping.\n"
        fi
    ;;
    'build-pigpiod')
        apt install -y python3-pigpio
        cd "${AOT-AI_PATH}"/install || return
        # wget --quiet -P "${AOT-AI_PATH}"/install abyz.co.uk/rpi/pigpio/pigpio.zip
        wget ${PIGPIO_URL} -O pigpio.tar.gz
        mkdir PIGPIO
        tar xzf pigpio.tar.gz -C PIGPIO --strip-components=1
        cd "${AOT-AI_PATH}"/install/PIGPIO || return
        make -j4
        make install
        cd "${AOT-AI_PATH}"/install || return
        rm -rf ./PIGPIO
        rm -rf pigpio.tar.gz
    ;;
    'install-pigpiod')
        printf "\n#### Installing pigpiod\n"
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh build-pigpiod
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh disable-pigpiod
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh enable-pigpiod-high
        mkdir -p /opt/AoT-AI
        touch /opt/AoT-AI/pigpio_installed
    ;;
    'uninstall-pigpiod')
        printf "\n#### Uninstalling pigpiod\n"
        apt remove -y python3-pigpio
        apt install -y jq
        cd "${AOT-AI_PATH}"/install || return
        # wget --quiet -P "${AOT-AI_PATH}"/install abyz.co.uk/rpi/pigpio/pigpio.zip
        wget ${PIGPIO_URL} -O pigpio.tar.gz
        mkdir PIGPIO
        tar xzf pigpio.tar.gz -C PIGPIO --strip-components=1
        cd "${AOT-AI_PATH}"/install/PIGPIO || return
        make uninstall
        cd "${AOT-AI_PATH}"/install || return
        rm -rf ./PIGPIO
        rm -rf pigpio.tar.gz
        touch /etc/systemd/system/pigpiod_uninstalled.service
        rm -f /opt/AoT-AI/pigpio_installed
    ;;
    'disable-pigpiod')
        printf "\n#### Disabling installed pigpiod startup script\n"
        service pigpiod stop
        systemctl disable pigpiod.service
        rm -rf /etc/systemd/system/pigpiod.service
        systemctl disable pigpiod_low.service
        rm -rf /etc/systemd/system/pigpiod_low.service
        systemctl disable pigpiod_high.service
        rm -rf /etc/systemd/system/pigpiod_high.service
        rm -rf /etc/systemd/system/pigpiod_disabled.service
        rm -rf /etc/systemd/system/pigpiod_uninstalled.service
    ;;
    'enable-pigpiod-low')
        printf "\n#### Enabling pigpiod startup script (1 ms sample rate)\n"
        systemctl enable "${AOT-AI_PATH}"/install/pigpiod_low.service
        service pigpiod restart
    ;;
    'enable-pigpiod-high')
        printf "\n#### Enabling pigpiod startup script (5 ms sample rate)\n"
        systemctl enable "${AOT-AI_PATH}"/install/pigpiod_high.service
        service pigpiod restart
    ;;
    'enable-pigpiod-disabled')
        printf "\n#### pigpiod has been disabled. It can be enabled in the web UI configuration\n"
        touch /etc/systemd/system/pigpiod_disabled.service
    ;;
    'uninstall')
        printf "\n#### Uninstalling: Stopping and disabling AoT-AI services (frontend/backend)\n"
        service aot-aiflask stop
        service aot-ai stop
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh web-server-disable
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh update-aot-ai-service-disable
    ;;
    'update-pigpiod')
        printf "\n#### Checking which pigpiod startup script is being used\n"
        GPIOD_SAMPLE_RATE=99
        if [[ -e /etc/systemd/system/pigpiod_low.service ]]; then
            GPIOD_SAMPLE_RATE=1
        elif [[ -e /etc/systemd/system/pigpiod_high.service ]]; then
            GPIOD_SAMPLE_RATE=5
        elif [[ -e /etc/systemd/system/pigpiod_disabled.service ]]; then
            GPIOD_SAMPLE_RATE=100
        fi

        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh disable-pigpiod

        if [[ "$GPIOD_SAMPLE_RATE" -eq "1" ]]; then
            /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh enable-pigpiod-low
        elif [[ "$GPIOD_SAMPLE_RATE" -eq "5" ]]; then
            /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh enable-pigpiod-high
        elif [[ "$GPIOD_SAMPLE_RATE" -eq "100" ]]; then
            /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh enable-pigpiod-disabled
        else
            printf "#### Could not determine pigpiod sample rate. Setting up pigpiod with 1 ms sample rate\n"
            /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh enable-pigpiod-low
        fi
    ;;
    'update-influxdb-1')
        printf "\n#### Ensuring compatible version of influxdb 1.x is installed ####\n"
        INSTALL_ADDRESS="https://dl.influxdata.com/influxdb/releases/"
        INSTALL_FILE="influxdb_${INFLUXDB1_VERSION}_${MACHINE_TYPE}.deb"
        CORRECT_VERSION="${INFLUXDB1_VERSION}-1"
        CURRENT_VERSION=$(apt-cache policy influxdb | grep 'Installed' | gawk '{print $2}')

        if [[ "${CURRENT_VERSION}" != "${CORRECT_VERSION}" ]]; then
            printf "#### Incorrect InfluxDB version (v${CURRENT_VERSION}) installed. Should be v${CORRECT_VERSION}\n"

            printf "#### Stopping influxdb 2.x (if installed)...\n"
            service influxd stop

            printf "#### Uninstalling influxdb 2.x (if installed)...\n"
            DEBIAN_FRONTEND=noninteractive apt remove -y influxdb2 influxdb2-cli

            printf "#### Installing InfluxDB v${CORRECT_VERSION}...\n"

            wget --quiet "${INSTALL_ADDRESS}${INSTALL_FILE}"
            dpkg -i "${INSTALL_FILE}"
            rm -rf "${INSTALL_FILE}"

            service influxdb restart
        else
            printf "Correct version of InfluxDB currently installed\n"
        fi

        if [[ $(grep "# flux-enabled = true" /etc/influxdb/influxdb.conf) || $(grep "flux-enabled = false" /etc/influxdb/influxdb.conf) ]]; then   
            printf "#### Flux found to not be enabled. Enabling and restarting InfluxDB.\n"
            sed -i 's/.*flux-enabled.*/flux-enabled = true/' /etc/influxdb/influxdb.conf
            service influxdb restart
        else
            printf "Flux is already enabled.\n"
        fi
    ;;
    'update-influxdb-2')
        printf "\n#### Ensuring compatible version of influxdb 2.x is installed ####\n"
        if [[ ${UNAME_TYPE} == 'x86_64' || ${MACHINE_TYPE} == 'arm64' ]]; then
            INSTALL_ADDRESS="https://dl.influxdata.com/influxdb/releases/"
            AMD64_INSTALL_FILE="influxdb2_2.7.8-1_amd64.deb"
            ARM64_INSTALL_FILE="influxdb2_2.7.8-1_arm64.deb"
            CORRECT_VERSION_INSTALL="2.7.8-1"
            AMD64_CLIENT_FILE="influxdb2-client-2.7.5-amd64.deb"
            ARM64_CLIENT_FILE="influxdb2-client-2.7.5-arm64.deb"
            CORRECT_VERSION_CLI="2.7.5-1"

            if [[ ${UNAME_TYPE} == 'x86_64' ]]; then
                printf "#### Detected x86_64 architecture\n"
                INSTALL_FILE=$AMD64_INSTALL_FILE
                CLIENT_FILE=$AMD64_CLIENT_FILE
            elif [[ ${MACHINE_TYPE} == 'arm64' ]]; then
                printf "#### Detected arm64 architecture\n"
                INSTALL_FILE=$ARM64_INSTALL_FILE
                CLIENT_FILE=$ARM64_CLIENT_FILE
            fi

            printf "#### Influxdb server file location: ${INSTALL_ADDRESS}${INSTALL_FILE}\n"

            CURRENT_VERSION=$(apt-cache policy influxdb2 | grep 'Installed' | gawk '{print $2}')

            if [[ "${CURRENT_VERSION}" != "${CORRECT_VERSION_INSTALL}" ]]; then
                printf "#### Incorrect InfluxDB version (v${CURRENT_VERSION}) installed. Should be v${CORRECT_VERSION_INSTALL}\n"

                printf "#### Stopping influxdb 1.x (if installed)...\n"
                service influxdb stop

                printf "#### Uninstalling influxdb 1.x (if installed)...\n"
                DEBIAN_FRONTEND=noninteractive apt remove -y influxdb

                printf "#### Installing InfluxDB v${CORRECT_VERSION_INSTALL}...\n"

                wget --quiet "${INSTALL_ADDRESS}${INSTALL_FILE}"
                dpkg -i "${INSTALL_FILE}"
                rm -rf "${INSTALL_FILE}"

                service influxd restart
            else
                printf "Correct version of InfluxDB currently installed (v${CORRECT_VERSION_INSTALL}).\n"
            fi

            printf "#### Influxdb client file location: ${INSTALL_ADDRESS}${CLIENT_FILE}\n"

            CURRENT_VERSION=$(apt-cache policy influxdb2-cli | grep 'Installed' | gawk '{print $2}')

            if [[ "${CURRENT_VERSION}" != "${CORRECT_VERSION_CLI}" ]]; then
                printf "#### Incorrect InfluxDB-Client version (v${CURRENT_VERSION}) installed. Should be v${CORRECT_VERSION_CLI}\n"

                printf "#### Installing InfluxDB-Client v${CORRECT_VERSION_CLI}...\n"

                wget --quiet "${INSTALL_ADDRESS}${CLIENT_FILE}"
                dpkg -i "${CLIENT_FILE}"
                rm -rf "${CLIENT_FILE}"

                service influxd restart
            else
                printf "Correct version of InfluxDB-Client currently installed (v${CORRECT_VERSION_CLI}).\n"
            fi
        else
            printf "ERROR: Could not detect 64-bit architecture (x86_64/arm64) to install Influxdb 2.x (found ${UNAME_TYPE}/${MACHINE_TYPE}).\n"
        fi
    ;;
    'update-influxdb-1-db-user')
        printf "\n#### Creating InfluxDB 1.x database and user\n"
        # Attempt to connect to influxdb 5 times, sleeping 60 seconds every fail
        for _ in {1..10}; do
            # Check if influxdb has successfully started and be connected to
            printf "#### Attempting to connect...\n" &&
            curl -sL -I localhost:8086/ping > /dev/null &&
            printf "#### Attempting to create database...\n" &&
            influx -execute "CREATE DATABASE aot-ai_db" &&
            printf "#### Attempting to set up user...\n" &&
            influx -database aot-ai_db -execute "CREATE USER aot-ai WITH PASSWORD 'mmdu77sj3nIoiajjs'" &&
            printf "#### Influxdb database and user successfully created\n" &&
            break ||
            # Else wait 60 seconds if the influxd port is not accepting connections
            # Everything below will begin executing if an error occurs before the break
            printf "#### Could not connect to Influxdb. Waiting 60 seconds then trying again...\n" &&
            sleep 60
        done
    ;;
    'update-influxdb-2-db-user')
        if influx config | grep -q 'aot-ai'; then
            printf "#### InfluxDB v2.x config already present, skipping DB/user creation...\n"
        else
            printf "\n#### Creating InfluxDB 2.x database and user\n"
            # Attempt to connect to influxdb 10 times, sleeping 60 seconds every fail
            for _ in {1..10}; do
                # Check if influxdb has successfully started and be connected to
                printf "#### Attempting to connect...\n" &&
                curl -sL -I localhost:8086/ping > /dev/null &&
                printf "#### Attempting to set up user...\n" &&
                influx setup \
                       --org aot-ai \
                       --bucket aot-ai_db \
                       --username aot-ai \
                       --password mmdu77sj3nIoiajjs \
                       --force &&
                printf "#### Influxdb database and user successfully created\n" &&
                break ||
                # Else wait 60 seconds if the influxd port is not accepting connections
                # Everything below will begin executing if an error occurs before the break
                printf "#### Could not connect to Influxdb. Waiting 60 seconds then trying again...\n" &&
                sleep 60
            done
        fi
    ;;
    'recreate-influxdb-1-db')
        printf "\n#### Recreating InfluxDB 1.x database (deletes all measurement data!)\n"
        # Attempt to connect to influxdb 10 times, sleeping 60 seconds every fail
        for _ in {1..10}; do
            # Check if influxdb has successfully started and be connected to
            printf "#### Attempting to connect...\n" &&
            curl -sL -I localhost:8086/ping > /dev/null &&
            printf "#### Attempting to recreate database...\n" &&
            influx -execute "DROP DATABASE aot-ai_db" &&
            influx -execute "CREATE DATABASE aot-ai_db" &&
            printf "#### Influxdb database successfully recreated\n" &&
            break ||
            # Else wait 60 seconds if the influxd port is not accepting connections
            # Everything below will begin executing if an error occurs before the break
            printf "#### Could not connect to Influxdb. Waiting 60 seconds then trying again...\n" &&
            sleep 60
        done
    ;;
    'recreate-influxdb-2-db')
        printf "\n#### Recreating InfluxDB 2.x database (deletes all measurement data!)\n"
        # Attempt to connect to influxdb 10 times, sleeping 60 seconds every fail
        for _ in {1..10}; do
            # Check if influxdb has successfully started and be connected to
            printf "#### Attempting to connect...\n" &&
            curl -sL -I localhost:8086/ping > /dev/null &&
            printf "#### Attempting to recreate database...\n" &&
            influx bucket delete -n aot-ai_db -o aot-ai &&
            influx bucket create -n aot-ai_db -o aot-ai &&
            printf "#### Influxdb database successfully recreated\n" &&
            break ||
            # Else wait 60 seconds if the influxd port is not accepting connections
            # Everything below will begin executing if an error occurs before the break
            printf "#### Could not connect to Influxdb. Waiting 60 seconds then trying again...\n" &&
            sleep 60
        done
    ;;
    'update-logrotate')
        printf "\n#### Installing logrotate scripts\n"
        if [[ -e /etc/cron.daily/logrotate ]]; then
            printf "logrotate execution moved from cron.daily to cron.hourly\n"
            mv -f /etc/cron.daily/logrotate /etc/cron.hourly/
        fi
        cp -f "${AOT-AI_PATH}"/install/logrotate_aot-ai /etc/logrotate.d/aot-ai
        printf "AoT-AI logrotate script installed\n"
    ;;
    'update-aot-ai-service-disable')
        printf "\n#### Disabling aot-ai startup script\n"
        systemctl disable aot-ai.service
        rm -rf /etc/systemd/system/aot-ai.service
    ;;
    'update-aot-ai-service-enable')
        printf "#### Enabling aot-ai startup script\n"
        systemctl enable "${AOT-AI_PATH}"/install/aot-ai.service
    ;;
    'update-aot-ai-startup-script')
        printf "\n#### Updating aot-ai startup script\n"
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh update-aot-ai-service-disable
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh update-aot-ai-service-enable
    ;;
    'update-packages')
        printf "\n#### Installing prerequisite apt packages and update pip\n"
        apt remove -y apache2
        apt install -y ${APT_PKGS}
        apt clean
    ;;
    'update-permissions')
        printf "\n#### Setting permissions\n"
        chown -LR aot-ai:aot-ai "${AOT-AI_PATH}"
        chown -R aot-ai:aot-ai /var/log/aot-ai
        chown -R aot-ai:aot-ai /var/AoT-AI-backups
        chown -R aot-ai:aot-ai /opt/AoT-AI

        find "${AOT-AI_PATH}" -type d -exec chmod 755 {} \;
        find "${AOT-AI_PATH}" -type f -exec chmod 644 {} \;
        chmod 770 /opt/AoT-AI  # Exclude other users from viewing files

        chown root:aot-ai "${AOT-AI_PATH}"/aot-ai/scripts/aot-ai_wrapper
        chmod 4770 "${AOT-AI_PATH}"/aot-ai/scripts/aot-ai_wrapper
    ;;
    'update-pip3')
        printf "\n#### Updating pip\n"
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh setup-virtualenv
        if [[ ! -d ${AOT-AI_PATH}/env ]]; then
            printf "\n## Error: Virtualenv doesn't exist. Create with %s setup-virtualenv\n" "${0}"
        else
            "${AOT-AI_PATH}"/env/bin/python -m pip install --upgrade pip
        fi
    ;;
    'update-pip3-packages')
        printf "\n#### Installing pip requirements\n"
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh setup-virtualenv
        if [[ ! -d ${AOT-AI_PATH}/env ]]; then
            printf "\n## Error: Virtualenv doesn't exist. Create with %s setup-virtualenv\n" "${0}"
        else
            "${AOT-AI_PATH}"/env/bin/python -m pip install --upgrade -r "${AOT-AI_PATH}"/install/requirements.txt
            "${AOT-AI_PATH}"/env/bin/python -m pip install --upgrade -r "${AOT-AI_PATH}"/install/requirements-testing.txt
        fi
    ;;
    'pip-clear-cache')
      "${AOT-AI_PATH}"/env/bin/python -m pip cache remove *
    ;;
    'update-swap-size')
        printf "\n#### Checking if swap size is 100 MB and needs to be changed to 512 MB\n"
        if grep -q -s "CONF_SWAPSIZE=100" "/etc/dphys-swapfile"; then
            printf "#### Swap currently set to 100 MB. Changing to 512 MB and restarting\n"
            sed -i 's/CONF_SWAPSIZE=100/CONF_SWAPSIZE=512/g' /etc/dphys-swapfile
            /etc/init.d/dphys-swapfile stop
            /etc/init.d/dphys-swapfile start
        else
            printf "#### Swap not currently set to 100 MB. Not changing.\n"
        fi
    ;;
    'upgrade-aot-ai')
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_download.sh upgrade-release-major "${AOT-AI_MAJOR_VERSION}"
    ;;
    'upgrade-release-major')
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_download.sh upgrade-release-major "${2}"
    ;;
    'upgrade-release-wipe')
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_download.sh upgrade-release-wipe "${2}"
    ;;
    'upgrade-master')
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_download.sh force-upgrade-master
    ;;
    'upgrade-post')
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_post.sh
    ;;
    'web-server-connect')
        printf "\n#### Connecting to http://localhost (creates AoT-AI database if it doesn't exist)\n"
        # Attempt to connect to localhost 10 times, sleeping 60 seconds every fail
        for _ in {1..10}; do
            wget --quiet --no-check-certificate -p http://localhost/ -O /dev/null &&
            printf "#### Successfully connected to http://localhost\n" &&
            break ||
            # Else wait 60 seconds if localhost is not accepting connections
            # Everything below will begin executing if an error occurs before the break
            printf "#### Could not connect to http://localhost. Waiting 60 seconds then trying again (up to 10 times)...\n" &&
            sleep 60 &&
            printf "#### Trying again...\n"
        done
    ;;
    'web-server-restart')
        printf "\n#### Restarting nginx\n"
        service nginx restart
        sleep 5
        printf "#### Checking aot-aiflask status and starting/restarting it\n"
        if ! systemctl is-active --quiet aot-aiflask; then
            systemctl start aot-aiflask
            printf "#### Waiting for aot-aiflask to start...\n"
            for i in {1..10}; do
                sleep 2
                if systemctl is-active --quiet aot-aiflask; then
                    printf "#### aot-aiflask has started successfully.\n"
                    break
                fi
            done
        fi
    ;;
    'web-server-disable')
        printf "\n#### Disabling service for nginx web server\n"
        systemctl disable aot-aiflask.service
        rm -rf /etc/systemd/system/aot-aiflask.service
    ;;
    'web-server-enable')
        printf "\n#### Enabling service for nginx web server\n"
        ln -sf "${AOT-AI_PATH}"/install/aot-aiflask_nginx.conf /etc/nginx/sites-enabled/default
        systemctl enable nginx
        systemctl enable "${AOT-AI_PATH}"/install/aot-aiflask.service
    ;;
    'web-server-update')
        printf "\n#### Installing and configuring nginx web server\n"
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh web-server-disable
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh web-server-enable
    ;;


    #
    # Docker-specific commands
    #

    'docker-create-files-directories-symlinks')
        printf "\n#### Creating files and directories\n"
        mkdir -p /var/log/aot-ai
        mkdir -p /var/AoT-AI-backups
        mkdir -p /usr/local/aot-ai

        mkdir -p "${AOT-AI_PATH}"/install
        mkdir -p "${AOT-AI_PATH}"/aot-ai
        mkdir -p "${AOT-AI_PATH}"/databases
        mkdir -p "${AOT-AI_PATH}"/databases/kma
        mkdir -p "${AOT-AI_PATH}"/note_attachments
        mkdir -p "${AOT-AI_PATH}"/aot-ai/scripts
        mkdir -p "${AOT-AI_PATH}"/aot-ai/aot-ai_flask/static/js/user_js
        mkdir -p "${AOT-AI_PATH}"/aot-ai/aot-ai_flask/static/css/user_css
        mkdir -p "${AOT-AI_PATH}"/aot-ai/aot-ai_flask/static/fonts/user_fonts

        if [[ ! -e /var/log/aot-ai/aot-ai.log ]]; then
            touch /var/log/aot-ai/aot-ai.log
        fi
        if [[ ! -e /var/log/aot-ai/aot-aibackup.log ]]; then
            touch /var/log/aot-ai/aot-aibackup.log
        fi
        if [[ ! -e /var/log/aot-ai/aot-aikeepup.log ]]; then
            touch /var/log/aot-ai/aot-aikeepup.log
        fi
        if [[ ! -e /var/log/aot-ai/aot-aidependency.log ]]; then
            touch /var/log/aot-ai/aot-aidependency.log
        fi
        if [[ ! -e /var/log/aot-ai/aot-aiimport.log ]]; then
            touch /var/log/aot-ai/aot-aiimport.log
        fi
        if [[ ! -e /var/log/aot-ai/aot-aiupgrade.log ]]; then
            touch /var/log/aot-ai/aot-aiupgrade.log
        fi
        if [[ ! -e /var/log/aot-ai/aot-airestore.log ]]; then
            touch /var/log/aot-ai/aot-airestore.log
        fi
        if [[ ! -e /var/log/aot-ai/login.log ]]; then
            touch /var/log/aot-ai/login.log
        fi

        # Create empty aot-ai database file if it doesn't exist
        if [[ ! -e /home/aot-ai/databases/aot-ai.db ]]; then
            touch /home/aot-ai/databases/aot-ai.db
        fi

        ln -sfn "${AOT-AI_PATH}" /var/aot-ai-root
    ;;
    'docker-compile-translations')
        printf "\n#### Compiling Translations\n"
        cd "${AOT-AI_PATH}"/aot-ai || exit
        "${AOT-AI_PATH}"/env/bin/pybabel compile -d aot-ai_flask/translations
    ;;
    'docker-update-pip')
        printf "\n#### Updating pip\n"
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh setup-virtualenv
        if [[ ! -d ${AOT-AI_PATH}/env ]]; then
            printf "\n## Error: Virtualenv doesn't exist. Create with %s setup-virtualenv\n" "${0}"
        else
            "${AOT-AI_PATH}"/env/bin/python -m pip install --upgrade pip
        fi
    ;;
    'docker-update-pip-packages')
        printf "\n#### Installing pip requirements\n"
        /bin/bash "${AOT-AI_PATH}"/aot-ai/scripts/upgrade_commands.sh setup-virtualenv
        if [[ ! -d ${AOT-AI_PATH}/env ]]; then
            printf "\n## Error: Virtualenv doesn't exist. Create with %s setup-virtualenv\n" "${0}"
        else
            "${AOT-AI_PATH}"/env/bin/python -m pip install --no-cache-dir -r "${AOT-AI_PATH}"/install/requirements.txt
        fi
    ;;
    'install-docker')
        printf "\n#### Installing Docker Client\n"
        apt install -y curl
        curl -fsSL https://get.docker.com -o get-docker.sh
        sh get-docker.sh
    ;;
    *)
        printf "Error: Unrecognized command: %s\n%s" "${1}" "${HELP_OPTIONS}"
    ;;
esac
