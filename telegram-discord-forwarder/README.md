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

---

## Run it locally first (to log in once)

The **first run is interactive** — Telegram texts you a login code. Do this on
your laptop first so it's easy, then copy the generated `*.session` file to EC2
(so the server never needs your phone).

```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                # Windows: copy .env.example .env
# edit .env with your real values

python forwarder.py
```

First run prompts:
```
Please enter your phone (or bot token): +1...
Please enter the code you received: 12345
# (2FA password if you have one)
```

After login it prints `Logged in as ...` and `Watching channel: ...`. Post
something in the channel (or wait for a pick) and it should appear in Discord.
A file like `forwarder_session.session` is now created — **that's your login**.

---

## Deploy to EC2 (Ubuntu, always-on)

### a. Launch
A **t4g.nano** or **t3.micro** is plenty (this is tiny). Ubuntu 22.04/24.04 AMI.

### b. Copy the project up
From your laptop, including the **already-logged-in** session file:

```bash
scp -i your-key.pem -r telegram-discord-forwarder ubuntu@<EC2_IP>:/home/ubuntu/
```

Make sure `.env` and `forwarder_session.session` came along (the `.gitignore`
excludes them from git, but `scp -r` copies them).

### c. Set up on the box

```bash
ssh -i your-key.pem ubuntu@<EC2_IP>
cd /home/ubuntu/telegram-discord-forwarder

sudo apt update && sudo apt install -y python3-venv
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# sanity check — should log in WITHOUT asking for a code (session reused)
./venv/bin/python forwarder.py
# Ctrl+C once you see "Waiting for new posts..."
```

If it asks for a phone code here, the session file didn't transfer — re-copy it.

### d. Install the service (auto-start + auto-restart)

```bash
sudo cp telegram-forwarder.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-forwarder
```

### e. Check it

```bash
systemctl status telegram-forwarder          # should be "active (running)"
tail -f /home/ubuntu/telegram-discord-forwarder/forwarder.log
```

That's it. It now starts on boot and restarts if it crashes.

---

## Config reference (`.env`)

| Variable | Required | Meaning |
|---|---|---|
| `TELEGRAM_API_ID` | yes | from my.telegram.org |
| `TELEGRAM_API_HASH` | yes | from my.telegram.org |
| `TELEGRAM_CHANNEL` | yes | `@user`, `t.me/...` link, or numeric id |
| `DISCORD_WEBHOOK_URL` | yes | Discord webhook URL |
| `DISCORD_MENTION` | no | `@here` (default), `@everyone`, or blank |
| `TELEGRAM_SESSION` | no | session filename (default `forwarder_session`) |
| `LOG_LEVEL` | no | `INFO` (default) or `DEBUG` |
| `FORWARD_LAST_ON_START` | no | `true` (default): on start, forward the most recent post so you see the latest pick immediately. `false` to skip. |
| `FORWARD_LAST_COUNT` | no | how many recent posts to forward on start (default `1`) |

---

## Troubleshooting

- **Asks for phone code on EC2** → session file not present/owned wrong. Re-`scp`
  the `*.session` file; make sure it's in the WorkingDirectory.
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
