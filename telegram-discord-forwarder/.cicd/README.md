# CI/CD — `.cicd/`

Everything needed to deploy this app to EC2 lives here. Deploys run on a
**self-hosted GitHub Actions runner installed on the EC2 box itself**, so the
job executes locally on the server — **no SSH, no connection secrets, no open
ports.** The workflow (`.github/workflows/deploy-forwarder.yml`, at the repo
root — Actions only discovers workflows under `.github/workflows/`) is a thin
wrapper that calls these scripts.

| File | Runs where | Purpose |
|---|---|---|
| `telegram-forwarder.service` | EC2 | systemd unit (auto-start + auto-restart). User/paths are templated at deploy time. |
| `build-env.sh` | EC2 (runner) | Writes `.env` from GitHub Secrets (fails if a required secret is missing). |
| `deploy.sh` | EC2 (runner) | venv + `pip install`, installs the systemd unit, restarts the service. Idempotent. |
| `health-check.sh` | EC2 (runner) | Waits for the service to go `active`; dumps logs and fails the job if not. |

## How a deploy flows

```
push to main (telegram-discord-forwarder/**)
  └─ self-hosted runner ON the EC2 box
       ├─ py_compile           (syntax gate)
       ├─ rsync checkout → ~/telegram-discord-forwarder  (keeps live .env + *.session)
       ├─ build-env.sh         → ~/telegram-discord-forwarder/.env  (from Secrets)
       ├─ deploy.sh            (deps + systemctl restart)
       └─ health-check.sh      (confirm active)
```

The Telegram `*.session` login file and the live `.env` are **never** deleted
by the rsync (`--delete` protects `--exclude`d paths), so the one-time Discord
login survives every deploy.

## Required GitHub Secrets

Set under **Repo → Settings → Secrets and variables → Actions → Secrets**.
Because the runner lives on the box, there are **no connection secrets** — only
the app config below.

### App config (was your `.env`)
| Secret | Required |
|---|---|
| `TELEGRAM_API_ID` | yes |
| `TELEGRAM_API_HASH` | yes |
| `TELEGRAM_CHANNEL` | yes |
| `DISCORD_WEBHOOK_URL` | yes |
| `DISCORD_BOT_TOKEN` | yes (first login) |
| `DISCORD_AUTH_CHANNEL_ID` | yes (first login) |
| `DISCORD_OWNER_ID` | optional |

### Optional tuning (non-secret) — set as **Variables**, not Secrets
`DISCORD_MENTION` (default `@here`), `LOG_LEVEL` (`INFO`), `FORWARD_LAST_ON_START`
(`true`), `FORWARD_LAST_COUNT` (`1`). Omit to use the defaults.

## One-time EC2 prep

The deploy scripts auto-detect the package manager, so **Amazon Linux 2023**
(`dnf`, user `ec2-user`) and **Ubuntu** (`apt`, user `ubuntu`) both work.

1. Launch a `t3.micro` / `t4g.nano` (Amazon Linux 2023 or Ubuntu 22.04/24.04).
   Inbound: **SSH (22) from your IP only** (just for the one-time runner install
   + the Telegram login); the app and runner are outbound-only otherwise.
2. SSH in (`ec2-user@…` on Amazon Linux, `ubuntu@…` on Ubuntu) and install the
   **self-hosted runner**. GitHub gives you the exact commands (with a
   registration token) at:
   **Repo → Settings → Actions → Runners → New self-hosted runner → Linux**.
   Use the **Linux x64** tarball (not Windows):
   ```bash
   mkdir actions-runner && cd actions-runner
   curl -o runner.tar.gz -L https://github.com/actions/runner/releases/download/vX.Y.Z/actions-runner-linux-x64-X.Y.Z.tar.gz
   tar xzf runner.tar.gz
   ./config.sh --url https://github.com/<you>/<repo> --token <TOKEN> --labels self-hosted,linux --unattended
   sudo ./svc.sh install        # run as a service (starts on boot)
   sudo ./svc.sh start
   ```
   Whichever user installs the runner is the user the deploy runs as — use the
   default login user (`ec2-user` / `ubuntu`); both have passwordless `sudo`,
   needed for `systemctl`. The workflow's `runs-on: [self-hosted, linux]`
   matches the labels above.
3. Push to `main` (or run the workflow manually). The first deploy installs the
   venv, deps, and systemd service automatically.

## First Telegram login

CI can't do the one-time Telegram phone/code login. On the **first** deploy the
service starts but the session isn't authorized yet — the Discord login bot
posts in your `DISCORD_AUTH_CHANNEL_ID` channel asking for your phone + code.
Reply there; once you see `✅ Logged in`, the `*.session` file is created on the
box and every later deploy reuses it silently.

Watch it happen:
```bash
ssh ubuntu@<EC2_HOST> 'journalctl -u telegram-forwarder -f'
```

## Manual deploy / rollback

- **Manual run:** Actions tab → *Deploy forwarder to EC2* → *Run workflow*.
- **Rollback:** revert the commit and push (re-deploys the previous code), or on
  the box `git`-independent — just `sudo systemctl restart telegram-forwarder`
  after restoring files.
