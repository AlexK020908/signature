"""
Telegram channel -> Discord webhook forwarder.

Logs in as YOUR Telegram account (a "userbot") so it can read any channel
you're a member of, then forwards new posts to a Discord channel via webhook.

Forwards:
  - plain text (chunked to respect Discord's 2000-char limit)
  - photos / image documents (downloaded and re-uploaded to Discord)
  - the message caption alongside any media

See README.md for setup (API credentials, first-run login, EC2 deploy).
"""

import asyncio
import io
import json
import logging
import os
import sys
import time

import requests
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

# --------------------------------------------------------------------------- #
# Config (from environment / .env)
# --------------------------------------------------------------------------- #
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # dotenv is optional; env vars can be set directly

API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
# Channel to watch: @username, t.me link, or numeric id (e.g. -1001234567890)
CHANNEL = os.getenv("TELEGRAM_CHANNEL")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
# What to ping. Use "@here", "@everyone", or "" for no ping.
MENTION = os.getenv("DISCORD_MENTION", "@here")
SESSION_NAME = os.getenv("TELEGRAM_SESSION", "forwarder_session")
# On startup, forward the most recent existing post so you see the latest pick
# right away. Set to "false"/"0"/"no" to skip. How many to send: FORWARD_LAST_COUNT.
FORWARD_LAST_ON_START = os.getenv("FORWARD_LAST_ON_START", "true").lower() not in (
    "false",
    "0",
    "no",
    "off",
)
FORWARD_LAST_COUNT = int(os.getenv("FORWARD_LAST_COUNT", "1"))

DISCORD_MAX = 2000  # Discord hard limit per message
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
log = logging.getLogger("forwarder")


def _require(name, value):
    if not value:
        log.error("Missing required env var: %s", name)
        sys.exit(1)
    return value


API_ID = int(_require("TELEGRAM_API_ID", API_ID))
API_HASH = _require("TELEGRAM_API_HASH", API_HASH)
CHANNEL = _require("TELEGRAM_CHANNEL", CHANNEL)
DISCORD_WEBHOOK_URL = _require("DISCORD_WEBHOOK_URL", DISCORD_WEBHOOK_URL)

# Telethon accepts a numeric channel id as an int; usernames/links stay strings.
try:
    CHANNEL = int(CHANNEL)
except (TypeError, ValueError):
    pass


# --------------------------------------------------------------------------- #
# Discord helpers
# --------------------------------------------------------------------------- #
def _chunk(text, size):
    """Split text into <=size pieces, preferring to break on newlines."""
    chunks = []
    while text:
        if len(text) <= size:
            chunks.append(text)
            break
        # try to break on the last newline within the window
        split = text.rfind("\n", 0, size)
        if split <= 0:
            split = size
        chunks.append(text[:split])
        text = text[split:].lstrip("\n")
    return chunks


def post_discord(content=None, image_bytes=None, image_name="pick.jpg", mention=""):
    """Send one Discord message. Retries on 429 (rate limit) and transient errors."""
    content = content or ""
    if mention:
        content = f"{mention} {content}".strip()
    # allow @here/@everyone to actually ping
    payload = {
        "content": content[:DISCORD_MAX],
        "allowed_mentions": {"parse": ["everyone"]},
    }

    for attempt in range(5):
        try:
            if image_bytes is not None:
                resp = requests.post(
                    DISCORD_WEBHOOK_URL,
                    data={"payload_json": json.dumps(payload)},
                    files={"file": (image_name, image_bytes)},
                    timeout=30,
                )
            else:
                resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=30)

            if resp.status_code == 429:
                retry = resp.json().get("retry_after", 1)
                log.warning("Discord rate limited, retrying in %ss", retry)
                time.sleep(float(retry) + 0.5)
                continue
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            log.error("Discord post failed (attempt %d): %s", attempt + 1, e)
            time.sleep(2 * (attempt + 1))
    return False


# --------------------------------------------------------------------------- #
# Telegram client + handler
# --------------------------------------------------------------------------- #
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)


async def forward_message(msg, mention=""):
    """Forward one Telegram message (text and/or image) to Discord."""
    text = msg.message or ""
    has_image = isinstance(msg.media, MessageMediaPhoto) or (
        isinstance(msg.media, MessageMediaDocument)
        and getattr(msg.media.document, "mime_type", "").startswith("image/")
    )

    try:
        if has_image:
            blob = await msg.download_media(file=bytes)  # download to memory
            buf = io.BytesIO(blob)
            buf.seek(0)
            # caption goes with the image; remaining chunks sent as follow-ups
            chunks = _chunk(text, DISCORD_MAX) if text else [""]
            ok = post_discord(content=chunks[0], image_bytes=buf, mention=mention)
            for extra in chunks[1:]:
                post_discord(content=extra)
        elif text:
            chunks = _chunk(text, DISCORD_MAX)
            ok = post_discord(content=chunks[0], mention=mention)
            for extra in chunks[1:]:
                post_discord(content=extra)
        else:
            log.info("Skipping post id=%s (no text, no image)", msg.id)
            return

        if ok:
            log.info("Forwarded post id=%s to Discord", msg.id)
        else:
            log.error("Gave up forwarding post id=%s", msg.id)
    except Exception:
        log.exception("Error handling post id=%s", msg.id)


@client.on(events.NewMessage(chats=CHANNEL))
async def on_new_message(event):
    msg = event.message
    log.info(
        "New post (id=%s, %d chars, media=%s)",
        msg.id,
        len(msg.message or ""),
        bool(msg.media),
    )
    await forward_message(msg, mention=MENTION)


async def main():
    await client.start()  # interactive login on first run (phone + code)
    me = await client.get_me()
    log.info("Logged in as %s (id=%s)", me.username or me.first_name, me.id)

    # Resolve & confirm the channel so config errors surface immediately.
    entity = await client.get_entity(CHANNEL)
    title = getattr(entity, "title", getattr(entity, "username", CHANNEL))
    log.info("Watching channel: %s", title)

    # On startup, forward the most recent existing post(s) so the latest pick
    # shows up immediately instead of waiting for the next one.
    if FORWARD_LAST_ON_START and FORWARD_LAST_COUNT > 0:
        recent = await client.get_messages(entity, limit=FORWARD_LAST_COUNT)
        # get_messages returns newest-first; send oldest-first so order reads right
        for msg in reversed(recent):
            log.info("Startup: forwarding last post id=%s", msg.id)
            await forward_message(msg, mention=MENTION)

    log.info("Forwarding to Discord with mention=%r. Waiting for new posts...", MENTION)

    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.get_event_loop().run_until_complete(main())
    except KeyboardInterrupt:
        log.info("Shutting down.")
