#!/usr/bin/env bash
# Build the .env file from environment variables (populated from GitHub Secrets
# in CI). Writes to the path given as $1 with 0600 perms.
#
# Required env: TELEGRAM_API_ID TELEGRAM_API_HASH TELEGRAM_CHANNEL
#               DISCORD_WEBHOOK_URL DISCORD_BOT_TOKEN DISCORD_AUTH_CHANNEL_ID
# Optional env: DISCORD_OWNER_ID DISCORD_MENTION LOG_LEVEL
#               FORWARD_LAST_ON_START FORWARD_LAST_COUNT
set -euo pipefail

OUT="${1:?usage: build-env.sh <output-path>}"

# Fail loudly if a required secret is missing rather than shipping a broken .env.
for var in TELEGRAM_API_ID TELEGRAM_API_HASH TELEGRAM_CHANNEL \
           DISCORD_WEBHOOK_URL DISCORD_BOT_TOKEN DISCORD_AUTH_CHANNEL_ID; do
  if [ -z "${!var:-}" ]; then
    echo "::error::Missing required secret: $var" >&2
    exit 1
  fi
done

umask 077
{
  echo "TELEGRAM_API_ID=${TELEGRAM_API_ID}"
  echo "TELEGRAM_API_HASH=${TELEGRAM_API_HASH}"
  echo "TELEGRAM_CHANNEL=${TELEGRAM_CHANNEL}"
  echo "DISCORD_WEBHOOK_URL=${DISCORD_WEBHOOK_URL}"
  echo "DISCORD_BOT_TOKEN=${DISCORD_BOT_TOKEN}"
  echo "DISCORD_AUTH_CHANNEL_ID=${DISCORD_AUTH_CHANNEL_ID}"
  echo "DISCORD_OWNER_ID=${DISCORD_OWNER_ID:-}"
  # Non-secret tuning, with sane defaults if not provided.
  echo "DISCORD_MENTION=${DISCORD_MENTION:-@here}"
  echo "LOG_LEVEL=${LOG_LEVEL:-INFO}"
  echo "FORWARD_LAST_ON_START=${FORWARD_LAST_ON_START:-true}"
  echo "FORWARD_LAST_COUNT=${FORWARD_LAST_COUNT:-1}"
} > "$OUT"

echo "Wrote $(wc -l < "$OUT") env vars to $OUT"
