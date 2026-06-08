#!/usr/bin/env bash
# Runs ON the EC2 box (by the self-hosted GitHub Actions runner, or by hand for a
# manual deploy). Installs the toolchain + Python deps, refreshes the systemd
# unit, and restarts the service. Idempotent: safe to run on every deploy.
set -euo pipefail

# Resolve the project dir from this script's location (.cicd/ -> parent).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$APP_DIR"

echo "==> Deploying in $APP_DIR"

# System toolchain (only installs if missing). Works on both dnf-based distros
# (Amazon Linux 2023, Fedora, RHEL) and apt-based ones (Ubuntu, Debian).
if ! command -v rsync >/dev/null 2>&1 || ! python3 -m venv --help >/dev/null 2>&1; then
  echo "==> Installing python venv + rsync"
  if command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y -q python3 python3-pip rsync
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3-venv rsync
  else
    echo "::error::No supported package manager (dnf/apt-get) found" >&2
    exit 1
  fi
fi

# Virtualenv + Python deps.
[ -d venv ] || python3 -m venv venv
echo "==> Installing Python dependencies"
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt

# Lock down the secrets file written by the deploy step.
[ -f .env ] && chmod 600 .env

# Install / refresh the systemd unit (lives in .cicd/), templating the user +
# working dir so it works regardless of which user you deploy as.
echo "==> Installing systemd unit"
sed -e "s|/home/ubuntu/telegram-discord-forwarder|$APP_DIR|g" \
    -e "s|^User=.*|User=$(whoami)|" \
    "$SCRIPT_DIR/telegram-forwarder.service" | sudo tee /etc/systemd/system/telegram-forwarder.service >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable telegram-forwarder
sudo systemctl restart telegram-forwarder

echo "==> Deploy complete"
