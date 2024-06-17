#!/usr/bin/env bash
###
# File: entrypoint.sh
# Project: docker
# File Created: Monday, 13th May 2024 4:20:35 pm
# Author: Josh.5 (jsunnex@gmail.com)
# -----
# Last Modified: Tuesday, 18th June 2024 1:49:37 am
# Modified By: Josh5 (jsunnex@gmail.com)
###

set -e

# All printed log lines from this script should be formatted with this function
print_log() {
    local timestamp
    local pid
    local level
    local message
    timestamp="$(date +'%Y-%m-%d %H:%M:%S %z')"
    pid="$$"
    level="$1"
    message="${*:2}"
    echo "[${timestamp}] [${pid}] [${level^^}] ${message}"
}

# Catch term signal and terminate any child processes
_term() {
    kill -TERM "$proxy_pid" 2>/dev/null
    if [ -n "$tvh_pid" ]; then
        kill -SIGINT "$tvh_pid" 2>/dev/null
    fi
}
trap _term SIGTERM SIGINT

# Ensure the customer is set
print_log info "APP_HOST_IP: ${APP_HOST_IP:-APP_HOST_IP variable has not been set}"
print_log info "APP_PORT: ${APP_PORT:-APP_PORT variable has not been set}"
print_log info "ENABLE_DEBUGGING: ${ENABLE_DEBUGGING:-ENABLE_DEBUGGING variable has not been set}"

# Configure required directories
mkdir -p \
    /config/.tvh_iptv_config

# Exec provided command
if [ "X$*" != "X" ]; then
    print_log info "Running command '${*}'"
    exec "$*"
else
    # Install packages (if requested)
    if [ "${RUN_PIP_INSTALL}" = "true" ]; then
        python3 -m venv --symlinks --clear /var/venv-docker
        source /var/venv-docker/bin/activate
        python3 -m pip install --no-cache-dir -r /app/requirements.txt
    else
        source /var/venv-docker/bin/activate
    fi

    # Execute migrations
    if [ "${SKIP_MIGRATIONS}" != "true" ]; then
        print_log info "Running TVH-IPTV-Config DB migrations"
        alembic upgrade head
    fi

    # If the 'tvheadend' binary exists in the path, start it
    if command -v tvheadend >/dev/null 2>&1; then
        # Install default TVH config
        if [ ! -d /config/.tvheadend/accesscontrol ]; then
            print_log info "Installing default tvheadend accesscontrol"
            mkdir -p /config/.tvheadend/accesscontrol
            cp -rf /defaults/tvheadend/admin_accesscontrol /config/.tvheadend/accesscontrol/83e4a7e5712d79a97b570b54e8e0e781
        fi
        if [ ! -d /config/.tvheadend/passwd ]; then
            print_log info "Installing default tvheadend passwd"
            mkdir -p /config/.tvheadend/passwd
            cp -rf /defaults/tvheadend/admin_auth /config/.tvheadend/passwd/c0a8261ea68035cd447a29a57d12ff7c
        fi
        if [ ! -f /config/.tvheadend/config ]; then
            print_log info "Installing default tvheadend config"
            mkdir -p /config/.tvheadend
            cp -rf /defaults/tvheadend/config /config/.tvheadend/config
        fi
        print_log info "Starting tvheadend service"
        tvheadend --config /config/.tvheadend &
        tvh_pid=$!
        print_log info "Started tvheadend service with PID $tvh_pid"
    fi

    # Run TIC server
    print_log info "Starting TIC server"
    python3 /app/run.py

    # Terminate TVH process if TIC service ends
    if [ -n "$tvh_pid" ]; then
        kill -SIGINT "$tvh_pid"
    fi
fi
