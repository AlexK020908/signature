# Telegram → Discord Pick Forwarder

Watches a Telegram channel you're a member of and forwards every new post
(text **and** images) to a Discord channel via webhook, with an `@here` ping.

It logs in as **your own Telegram account** (a "userbot" via Telethon). This is
required: a normal bot cannot read channels it doesn't own. Your account just
needs to be a member of the channel — exactly like reading it in the app.

> ⚠️ Use one Telegram account, one channel, sensible volume. Don't share your
> session file — it's a full login to your account.

---

## How it works

```
Telegram channel  ──(your account, MTProto)──►  forwarder.py  ──(webhook)──►  Discord
```

`forwarder.py` keeps a live connection open and fires on each new post. No
polling, no missed messages while it's running.

---

## 1. Get your Telegram API credentials

1. Go to <https://my.telegram.org> and log in with your phone number.
2. Click **API development tools**.
3. Create an app (any name, e.g. "forwarder"). Platform: Desktop.
4. Copy the **api_id** (a number) and **api_hash** (a hex string).

## 2. Create the Discord webhook

1. In Discord: **Server Settings → Integrations → Webhooks → New Webhook**.
2. Pick the channel where picks should land. **Copy Webhook URL.**

## 3. Find your channel reference

- Public channel → use its `@username` or `https://t.me/...` link.
- Private channel (no username) → use the numeric id like `-1001234567890`.
  Easiest way to get it: set `LOG_LEVEL=DEBUG`, run the script once, and it logs
  the channels it sees, or temporarily set `TELEGRAM_CHANNEL` to any value and
  read the error. (Telegram desktop "Copy link" on a message also reveals it.)
- **Multiple channels** → comma-separate them in `TELEGRAM_CHANNEL`, e.g.
  `TELEGRAM_CHANNEL=@channelone, @channeltwo, -1001234567890`. Every channel
  forwards to the same Discord webhook.

---

## Logging in (no terminal needed — done over Discord)

Telegram requires a one-time login (phone + code) to create a session. This
project does that **through Discord** so it works on a headless server: when
there's no valid session, the script connects a small Discord bot that asks for
your phone number and login code in a channel, you reply there, and it signs in.
Once the `*.session` file exists, every later start reuses it silently — the
login flow never runs again unless the session is revoked.

### One-time Discord bot setup

1. <https://discord.com/developers/applications> → **New Application** → **Bot**
   → **Reset Token** → copy into `DISCORD_BOT_TOKEN`.
2. On the Bot page, turn on **MESSAGE CONTENT INTENT** (required to read your
   replies).
3. **OAuth2 → URL Generator** → scope **bot** → open the URL → add it to your
   server.
4. Enable **Developer Mode** (Discord Settings → Advanced), right-click the
   channel the bot can see → **Copy Channel ID** → `DISCORD_AUTH_CHANNEL_ID`.
   (Optional: right-click your name → **Copy User ID** → `DISCORD_OWNER_ID` to
   only accept replies from you.)

### Run it

```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                # Windows: copy .env.example .env
# edit .env with your real values (incl. the DISCORD_BOT_* vars above)

python forwarder.py
```

> You can run this first login either locally **or** straight on the server —
> either way you reply in Discord, so the server never needs terminal input.

On first run, the bot posts in your auth channel:
```
🔑 Telegram login needed. Reply with your phone number (e.g. +17786827953).
📨 Code sent — check your Telegram app. Reply with the code.
✅ Logged in as <you>. Forwarder is starting.
```

Reply to each prompt in Discord. After `✅`, `forwarder_session.session` is
created — **that's your login** — and the forwarder begins watching the channel.

---

## Deploy to EC2 — CI/CD (recommended)

Deploys are automated via **GitHub Actions** running on a **self-hosted runner
installed on the EC2 box itself** — so the job runs locally on the server, with
**no SSH and no connection secrets**. All config that used to live in `.env` now
lives in **GitHub Secrets**, and pushing to `main` ships the change. The pipeline
(workflow + systemd unit + deploy scripts) lives in [`.cicd/`](.cicd/README.md) —
see that README for the full secret list and the one-time runner install.

In short:
1. Launch a `t3.micro`/`t4g.nano` Ubuntu box.
2. SSH in once and install the self-hosted runner as the `ubuntu` user
   (Repo → Settings → Actions → Runners → New self-hosted runner gives the exact
   commands + token; run with `--labels self-hosted,linux`).
3. Add these GitHub **Secrets** (app config only — no host/key needed):
   `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_CHANNEL`,
   `DISCORD_WEBHOOK_URL`, `DISCORD_BOT_TOKEN`, `DISCORD_AUTH_CHANNEL_ID`,
   `DISCORD_OWNER_ID` (optional).
4. Push to `main` (or Actions → *Deploy forwarder to EC2* → *Run workflow*).

The first deploy starts the service; reply to the Discord login bot once to
create the `*.session` file, and every later deploy reuses it silently. The
pipeline never deletes the live `.env` or session file on the box.

### Manual deploy (no CI)

If you'd rather not use Actions, copy the project up (including the
already-logged-in `*.session` file and a hand-written `.env`) and run the same
script CI uses:

```bash
scp -i your-key.pem -r telegram-discord-forwarder ubuntu@<EC2_IP>:/home/ubuntu/
ssh -i your-key.pem ubuntu@<EC2_IP>
bash /home/ubuntu/telegram-discord-forwarder/.cicd/deploy.sh
```

Then check it:

```bash
systemctl status telegram-forwarder          # should be "active (running)"
journalctl -u telegram-forwarder -f
```

That's it. It now starts on boot and restarts if it crashes.

---

## Config reference (`.env`)

| Variable | Required | Meaning |
|---|---|---|
| `TELEGRAM_API_ID` | yes | from my.telegram.org |
| `TELEGRAM_API_HASH` | yes | from my.telegram.org |
| `TELEGRAM_CHANNEL` | yes | `@user`, `t.me/...` link, or numeric id |
| `DISCORD_WEBHOOK_URL` | yes | Discord webhook URL (where picks are posted) |
| `DISCORD_MENTION` | no | `@here` (default), `@everyone`, or blank |
| `DISCORD_BOT_TOKEN` | first login | bot token for the Discord login flow |
| `DISCORD_AUTH_CHANNEL_ID` | first login | channel id where the bot asks for phone/code |
| `DISCORD_OWNER_ID` | no | restrict login replies to your user id |
| `TELEGRAM_SESSION` | no | session filename (default `forwarder_session`) |
| `LOG_LEVEL` | no | `INFO` (default) or `DEBUG` |
| `FORWARD_LAST_ON_START` | no | `true` (default): on start, forward the most recent post so you see the latest pick immediately. `false` to skip. |
| `FORWARD_LAST_COUNT` | no | how many recent posts to forward on start (default `1`) |

---

## Troubleshooting

- **Triggers Discord login on EC2** → session file not present/owned wrong.
  Re-`scp` the `*.session` file (must be in the WorkingDirectory), or just reply
  to the bot's prompts to log in on the box directly.
- **Bot never posts the login prompt** → check `DISCORD_BOT_TOKEN` /
  `DISCORD_AUTH_CHANNEL_ID`, that the bot was invited to the server and can see
  that channel, and that **MESSAGE CONTENT INTENT** is enabled in the Developer
  Portal (without it, the bot can't read your replies).
- **No posts forwarded** → confirm your account is actually a member of that
  channel and the id/username is right (run with `LOG_LEVEL=DEBUG`).
- **`@here` not pinging** → the webhook posts to a channel; make sure your role
  can be pinged there. The code already sets `allowed_mentions` to permit it.
- **Images not coming through** → very large files may exceed Discord's webhook
  upload limit (~8 MB on non-boosted servers); text/caption still forwards.
- **Service logs** → `journalctl -u telegram-forwarder -f` or the `forwarder.log`.

---

## Notes & limits

- Only catches posts while the process is running (that's why EC2 + systemd).
- One Discord message per Telegram post; long posts are split on newlines.
- Edits/deletes in Telegram are not synced — only new posts are forwarded.
