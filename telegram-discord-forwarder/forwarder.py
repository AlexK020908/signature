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
from telethon.errors import (
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
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
# Channel(s) to watch: @username, t.me link, or numeric id (e.g. -1001234567890).
# Multiple channels: comma-separate them, e.g. "@one, @two, -1001234567890".
CHANNEL = os.getenv("TELEGRAM_CHANNEL")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
# What to ping. Use "@here", "@everyone", or "" for no ping.
MENTION = os.getenv("DISCORD_MENTION", "@here")
SESSION_NAME = os.getenv("TELEGRAM_SESSION", "forwarder_session")

# Discord-based login (only used when there's no valid Telegram session yet).
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_AUTH_CHANNEL_ID = os.getenv("DISCORD_AUTH_CHANNEL_ID")
DISCORD_OWNER_ID = os.getenv("DISCORD_OWNER_ID")  # optional: restrict who can reply
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


def _parse_channel(raw):
    """Normalize one channel ref: numeric ids -> int, usernames/links stay str."""
    raw = raw.strip()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return raw


# Split the (possibly comma-separated) list into individual channel refs.
# Telethon accepts a numeric channel id as an int; usernames/links stay strings.
CHANNELS = [_parse_channel(c) for c in CHANNEL.split(",") if c.strip()]


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


def post_discord(content=None, image_bytes=None, image_name="pick.jpg", mention="", username=None):
    """Send one Discord message. Retries on 429 (rate limit) and transient errors.

    username, if given, overrides the displayed sender name on the webhook — used
    to label each post with the source Telegram channel.
    """
    content = content or ""
    if mention:
        content = f"{mention} {content}".strip()
    # allow @here/@everyone to actually ping
    payload = {
        "content": content[:DISCORD_MAX],
        "allowed_mentions": {"parse": ["everyone"]},
    }
    if username:
        # Discord webhook username override: max 80 chars, can't contain
        # "discord" or "clyde". Strip those so the post never gets rejected.
        clean = username[:80]
        if not any(bad in clean.lower() for bad in ("discord", "clyde")):
            payload["username"] = clean

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


def _source_name(entity):
    """Discord sender label for a channel: its name + a public/private marker.

    A channel is "public" when it has a @username (joinable by link); a private
    channel has none and is referenced by numeric id. We surface that so each
    Discord post shows which kind of channel it came from.
    """
    name = (
        getattr(entity, "title", None)
        or getattr(entity, "username", None)
        or "Telegram"
    )
    marker = " • 🌐 Public" if getattr(entity, "username", None) else " • 🔒 Private"
    # Discord caps the webhook username at 80 chars; keep the marker, trim name.
    return f"{name[: 80 - len(marker)]}{marker}"


def _telegram_link(msg):
    """Best-effort public link to a channel post (so video posts are viewable)."""
    chat = getattr(msg, "chat", None)
    username = getattr(chat, "username", None)
    if username:
        return f"https://t.me/{username}/{msg.id}"
    # Private channel: link uses the raw channel id (no -100 prefix), e.g.
    # https://t.me/c/3579719770/788
    peer = getattr(msg, "peer_id", None)
    channel_id = getattr(peer, "channel_id", None)
    if channel_id:
        return f"https://t.me/c/{channel_id}/{msg.id}"
    return None


async def forward_message(msg, mention="", source=None):
    """Forward one Telegram message (text and/or image) to Discord.

    Images are downloaded and re-uploaded. Other media (video, audio, files) is
    NOT re-uploaded — instead we post a note with a link to the original post so
    people can watch it on Telegram. ``source`` (the channel name) labels each
    Discord message so you can tell which channel a post came from.
    """
    text = msg.message or ""
    has_image = isinstance(msg.media, MessageMediaPhoto) or (
        isinstance(msg.media, MessageMediaDocument)
        and getattr(msg.media.document, "mime_type", "").startswith("image/")
    )
    # Media we don't re-upload (video/audio/files): note it with a link instead.
    has_other_media = bool(msg.media) and not has_image

    try:
        if has_image:
            blob = await msg.download_media(file=bytes)  # download to memory
            buf = io.BytesIO(blob)
            buf.seek(0)
            # caption goes with the image; remaining chunks sent as follow-ups
            chunks = _chunk(text, DISCORD_MAX) if text else [""]
            ok = post_discord(content=chunks[0], image_bytes=buf, mention=mention, username=source)
            for extra in chunks[1:]:
                post_discord(content=extra, username=source)
        elif text:
            chunks = _chunk(text, DISCORD_MAX)
            ok = post_discord(content=chunks[0], mention=mention, username=source)
            for extra in chunks[1:]:
                post_discord(content=extra, username=source)
            # If there's also video/other media attached, link to the original.
            if has_other_media:
                link = _telegram_link(msg)
                if link:
                    post_discord(
                        content=f"🎬 _Media in this post — watch on Telegram:_ {link}",
                        username=source,
                    )
        elif has_other_media:
            # Video-only / file-only post with no caption: post a note + link
            # instead of silently skipping it.
            link = _telegram_link(msg)
            note = "🎬 _New media post on Telegram"
            note = f"{note}:_ {link}" if link else f"{note} — open the channel to view._"
            ok = post_discord(content=note, mention=mention, username=source)
        else:
            log.info("Skipping post id=%s (no text, no media)", msg.id)
            return

        if ok:
            log.info("Forwarded post id=%s to Discord", msg.id)
        else:
            log.error("Gave up forwarding post id=%s", msg.id)
    except Exception:
        log.exception("Error handling post id=%s", msg.id)


@client.on(events.NewMessage(chats=CHANNELS))
async def on_new_message(event):
    msg = event.message
    chat = await event.get_chat()
    source = _source_name(chat)
    log.info(
        "New post in %r (id=%s, %d chars, media=%s)",
        source,
        msg.id,
        len(msg.message or ""),
        bool(msg.media),
    )
    await forward_message(msg, mention=MENTION, source=source)


async def discord_login(client):
    """Authenticate Telegram interactively over Discord (no terminal needed).

    Spins up a temporary Discord bot that asks for the phone number, login code,
    and (if enabled) the 2FA password in a Discord channel, reading your replies.
    Returns once the Telegram session is authorized; raises on giving up.
    """
    import discord

    for name, value in (
        ("DISCORD_BOT_TOKEN", DISCORD_BOT_TOKEN),
        ("DISCORD_AUTH_CHANNEL_ID", DISCORD_AUTH_CHANNEL_ID),
    ):
        if not value:
            log.error(
                "Telegram session not authorized and %s is not set. "
                "Set it (see .env.example) to enable Discord login.",
                name,
            )
            sys.exit(1)

    channel_id = int(DISCORD_AUTH_CHANNEL_ID)
    owner_id = int(DISCORD_OWNER_ID) if DISCORD_OWNER_ID else None

    intents = discord.Intents.default()
    intents.message_content = True  # privileged: enable in the Developer Portal
    bot = discord.Client(intents=intents)
    result = {"ok": False}

    @bot.event
    async def on_ready():
        log.info("Discord login bot connected as %s", bot.user)
        try:
            channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)

            def is_reply(m):
                if m.channel.id != channel_id or m.author.bot:
                    return False
                return owner_id is None or m.author.id == owner_id

            async def ask(prompt):
                await channel.send(prompt)
                msg = await bot.wait_for("message", check=is_reply)
                return msg.content.strip()

            await channel.send(
                "🔑 **Telegram login needed.**\nReply with your phone number in "
                "international format (e.g. `+17786827953`)."
            )

            # Phone + send-code loop (retry on a bad number).
            phone = None
            while phone is None:
                candidate = (await bot.wait_for("message", check=is_reply)).content.strip()
                try:
                    await client.send_code_request(candidate)
                    phone = candidate
                except PhoneNumberInvalidError:
                    await channel.send(
                        "❌ That phone number was invalid. Try again "
                        "(must start with `+` and the country code)."
                    )

            # Code loop (retry on invalid; restart phone on expiry).
            await channel.send(
                "📨 Code sent — check your Telegram app (or SMS). Reply with the code."
            )
            while True:
                code = (await bot.wait_for("message", check=is_reply)).content.strip()
                try:
                    await client.sign_in(phone, code)
                    break
                except SessionPasswordNeededError:
                    password = await ask(
                        "🔒 Two-factor auth is on. Reply with your Telegram password."
                    )
                    await client.sign_in(password=password)
                    break
                except PhoneCodeInvalidError:
                    await channel.send("❌ Wrong code. Reply with the correct one.")
                except PhoneCodeExpiredError:
                    await client.send_code_request(phone)
                    await channel.send("⌛ That code expired. I sent a new one — reply with it.")

            me = await client.get_me()
            await channel.send(
                f"✅ Logged in as **{me.username or me.first_name}**. Forwarder is starting."
            )
            result["ok"] = True
        except Exception as e:
            log.exception("Discord login failed")
            try:
                await channel.send(f"❌ Login failed: `{e}`. Restart the process to retry.")
            except Exception:
                pass
        finally:
            await bot.close()

    await bot.start(DISCORD_BOT_TOKEN)  # returns once on_ready calls bot.close()
    if not result["ok"]:
        sys.exit(1)


async def main():
    await client.connect()
    if not await client.is_user_authorized():
        log.info("No valid Telegram session — starting Discord login flow.")
        await discord_login(client)
    me = await client.get_me()
    log.info("Logged in as %s (id=%s)", me.username or me.first_name, me.id)

    # Resolve & confirm each channel so config errors surface immediately.
    entities = []
    for channel in CHANNELS:
        entity = await client.get_entity(channel)
        title = getattr(entity, "title", getattr(entity, "username", channel))
        log.info("Watching channel: %s", title)
        entities.append(entity)

    # On startup, forward the most recent existing post(s) so the latest pick
    # shows up immediately instead of waiting for the next one.
    if FORWARD_LAST_ON_START and FORWARD_LAST_COUNT > 0:
        for entity in entities:
            source = _source_name(entity)
            recent = await client.get_messages(entity, limit=FORWARD_LAST_COUNT)
            if recent:
                # Let the channel know this is a replay of the latest post(s) on
                # startup, not necessarily a brand-new one.
                post_discord(
                    content="ℹ️ _Sending last message sent — disregard if it's already been sent._",
                    username=source,
                )
            # get_messages returns newest-first; send oldest-first so order reads right
            for msg in reversed(recent):
                log.info("Startup: forwarding last post id=%s from %r", msg.id, source)
                await forward_message(msg, mention=MENTION, source=source)

    log.info("Forwarding to Discord with mention=%r. Waiting for new posts...", MENTION)

    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.get_event_loop().run_until_complete(main())
    except KeyboardInterrupt:
        log.info("Shutting down.")
