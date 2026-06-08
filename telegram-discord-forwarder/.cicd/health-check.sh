#!/usr/bin/env bash
# Runs ON the EC2 box after a deploy. Waits for the service to reach "active",
# and dumps recent logs to fail the CI job loudly if it didn't come up.
set -euo pipefail

for _ in $(seq 1 10); do
  if systemctl is-active --quiet telegram-forwarder; then
    echo "Service is active."
    sudo systemctl status telegram-forwarder --no-pager --lines=15 || true
    exit 0
  fi
  sleep 2
done

echo "::error::telegram-forwarder did not reach active state"
sudo journalctl -u telegram-forwarder --no-pager --lines=50 || true
exit 1
