# sports_manager

Telegram bot ([@sports_manager_bot](https://t.me/sports_manager_bot)) that organizes regular games in group chats: who's coming, who paid, random teams, player stats, and games created on a schedule.

This README is the runbook for running it in production. It contains no secrets: every command reads them from the systemd service on the server.

## How it works

- **`poll.py`** is the only entry point. It clears any webhook, then long-polls Telegram with `getUpdates` and passes each update to `TelegramApp` in `src/telegram_app.py`.
- **Why polling.** Telegram's webhook calls can't reach the server, but the server can reach Telegram. About 1 in 20 outgoing connections drops, so API calls retry on connection errors and a dropped poll recovers in about 6 seconds.
- **Scheduled games** run as threads inside the same process. Each chat's cron schedule is in **UTC**. The server clock is in Moscow time, which doesn't affect the bot.
- **MySQL 8.0** runs on the same server and listens on localhost only. The bot connects over the local socket.

| Path | What it is |
|---|---|
| `poll.py` | Entry point: polling loop |
| `src/telegram_app.py` | Commands and the game scheduler |
| `src/telegram_api.py` | Telegram Bot API calls, with retries |
| `src/db.py`, `db_scripts/` | Database access and SQL |
| `src/i18n.py`, `bot_help_*.txt` | Texts in Russian and English |
| `bot_commands.txt` | Command list to paste into BotFather's `/setcommands` |
| `requirements.in` | Direct dependencies |
| `requirements.txt` | Pinned versions, generated from `requirements.in` |

## Server

- **Host.** A Timeweb Cloud VPS running Ubuntu 24.04 with Python 3.12. The IP address is in the Timeweb panel.
- **Login.** SSH as root with a key only. Password login is off. If your key is lost, use the web console in the Timeweb panel.
- **Other software.** The server also runs an Outline VPN in Docker. Leave its containers and firewall ports alone.

SSH config on your machine, in `~/.ssh/config`:

```
Host sports-manager
    HostName <server IP from the Timeweb panel>
    User root
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

| On the server | What it is |
|---|---|
| `/root/sports_manager` | Git checkout of this repo, tracking `master` over HTTPS |
| `/root/sports_manager/.venv` | Python virtual environment |
| `/etc/systemd/system/sports_manager.service` | The service, including the secrets as `Environment=` lines |
| `journalctl -u sports_manager` | Bot logs, capped at 200 MB along with the rest of the journal |

### Secrets

The secrets live only in the service file on the server:

| Variable | What it is |
|---|---|
| `TELEGRAM_BOT_TOKEN` | The bot token from BotFather |
| `DB_PASSWORD` | Password of the MySQL user `admin@localhost` |

`TELEGRAM_BOT_NAME`, `DB_HOST` and `DB_USER` are set in the same file and aren't secret.

To use the same values in a shell on the server, define this helper. You can also add it to `/root/.bashrc`. It exports only the bot's own variables. The service also sets `PATH`, and copying that would hide normal tools like `curl`.

```bash
sm_env() {
  while IFS= read -r kv; do
    case "$kv" in TELEGRAM_*=*|DB_*=*) export "$kv";; esac
  done < <(systemctl show sports_manager -p Environment --value | tr ' ' '\n')
}
```

Never paste the token into a chat, an issue or a commit.

## Everyday commands

Run these on the server after `ssh sports-manager`.

```bash
systemctl status sports_manager                  # running? since when?
journalctl -u sports_manager -f                  # follow the logs live
journalctl -u sports_manager --since "-1h"       # recent logs
journalctl -u sports_manager --since today | grep -E "Traceback|failed"   # errors
systemctl restart sports_manager                 # restart (see the note below)
```

A restart makes the bot post "New game will be created at …" in every chat that has a schedule. Restart only when you need to.

## Health check

```bash
sm_env
systemctl is-active sports_manager mysql
# Telegram knows the bot:
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["username"])'
# No webhook set, nothing stuck in the queue:
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo" \
  | python3 -c 'import json,sys; r=json.load(sys.stdin)["result"]; print(repr(r["url"]), r["pending_update_count"], r.get("last_error_message"))'
# The bot's database login works:
MYSQL_PWD="$DB_PASSWORD" mysql -u "$DB_USER" -h "$DB_HOST" sports_manager -e 'SELECT COUNT(*) FROM `match`'
```

When everything is healthy:
- **`getMe`** prints `sports_manager_bot`.
- **`getWebhookInfo`** prints `'' 0 None`. A non-empty URL means someone set a webhook, and the poller can't receive updates until the next restart clears it. A pending count that keeps growing means the poller isn't fetching.
- **The database query** prints a row count.

Occasional `getUpdates failed to connect, retrying in 1s` lines in the logs are normal.

## Deploy

Merge to `master`, then:

```bash
ssh sports-manager
cd /root/sports_manager
git pull --ff-only
# only if requirements.txt changed:
.venv/bin/pip install -r requirements.txt
systemctl restart sports_manager
journalctl -u sports_manager --since "-1min"     # expect "webhook deleted, polling for updates"
```

Then send `/help` to the bot in a chat and check that it answers.

## Dependencies

`requirements.in` lists the direct dependencies. `requirements.txt` pins everything and is generated with [uv](https://docs.astral.sh/uv/):

```bash
uv pip compile requirements.in --upgrade --python-version 3.12 --no-header --no-annotate -o requirements.txt
```

To test locally before deploying:

```bash
uv venv --python 3.12 /tmp/smvenv && VIRTUAL_ENV=/tmp/smvenv uv pip install -r requirements.txt
/tmp/smvenv/bin/python -c "import poll"
```

Don't run `poll.py` locally with the production token. Telegram serves updates to only one poller at a time, so a local poller would take messages away from the server.

To rebuild the server's virtual environment from scratch, for example after a Python upgrade:

```bash
cd /root/sports_manager
rm -rf .venv && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
systemctl restart sports_manager
```

## Database

Open a MySQL shell. Root logs in from the server shell with no password:

```bash
mysql sports_manager
```

### Backup

From your Mac, save a dump to iCloud Drive:

```bash
D="$HOME/Library/Mobile Documents/com~apple~CloudDocs/sports_manager/$(date +%F)"
mkdir -p "$D"
ssh sports-manager 'mysqldump --single-transaction --routines --triggers --events --databases sports_manager | gzip -9' > "$D/sports_manager_db.sql.gz"
gunzip -t "$D/sports_manager_db.sql.gz" && echo ok
```

No Timeweb backups are kept, because they cost money, and panel snapshots last only 7 days. These dumps are the backups, so take one before any risky change.

### Restore

This replaces the tables in `sports_manager` with the dump's contents.

```bash
gunzip -c sports_manager_db.sql.gz | ssh sports-manager mysql
ssh sports-manager systemctl restart sports_manager
```

## Changing secrets

**Bot token.** In BotFather, use `/revoke` to get a new token. Then:

```bash
nano /etc/systemd/system/sports_manager.service   # update TELEGRAM_BOT_TOKEN
systemctl daemon-reload && systemctl restart sports_manager
```

**Database password:**

```bash
read -rs -p "New password: " P; echo
mysql -e "ALTER USER 'admin'@'localhost' IDENTIFIED BY '$P'"; unset P
nano /etc/systemd/system/sports_manager.service   # update DB_PASSWORD
systemctl daemon-reload && systemctl restart sports_manager
```

## Server maintenance

- **Security updates** install automatically every day through `unattended-upgrades`.
- **Other updates:** `apt update && apt full-upgrade`. Reboot if `/var/run/reboot-required` exists.
- **Disk space:** `df -h /` and `journalctl --disk-usage`. The journal is capped by `/etc/systemd/journald.conf.d/size.conf`.
- **Firewall:** `ufw status`. Only SSH and the Outline VPN ports are open. MySQL isn't reachable from outside.
- **SSH:** key-only login is set in `/etc/ssh/sshd_config.d/00-key-only.conf`. SSH starts on demand through `ssh.socket`, so `ssh.service` shows as disabled. That's normal.

After a reboot, check:

```bash
systemctl --failed
systemctl is-active sports_manager mysql docker ssh.socket
docker ps
```

## Troubleshooting

**The bot doesn't answer.**
1. Check `systemctl status sports_manager` and the error grep from Everyday commands.
2. Run the health check. A webhook URL means it needs `systemctl restart sports_manager`. A growing pending count means the poller is stuck or can't reach Telegram, so check the logs.
3. Check `systemctl is-active mysql`.

**MySQL won't start.** Run `journalctl -xeu mysql`. If its log folder is missing, recreate it:

```bash
install -d -o mysql -g adm -m 2750 /var/log/mysql
systemctl reset-failed mysql && systemctl start mysql
```

**The service gives up restarting.** It allows 3 restarts in 10 minutes. After fixing the cause:

```bash
systemctl reset-failed sports_manager && systemctl start sports_manager
```

## Gotchas

- **Restarts announce schedules.** See Everyday commands.
- **Purge old package configs one at a time.** Never run `dpkg --purge` over all `rc` packages at once. An old `mysql-server-5.7` entry once stopped and disabled MySQL that way and deleted its log folder.
- **Snapshots block backups.** In the Timeweb panel, a snapshot blocks every backup action until you delete it.
- **One SSH key.** Only one key is authorized. Add a second one to `/root/.ssh/authorized_keys` if you set up another machine.

## Rebuilding the server from scratch

1. Create an Ubuntu 24.04 server and add your SSH key.
2. Install the packages:
   ```bash
   apt install mysql-server python3-venv git
   ```
3. Restore the database dump as described under Restore. Then create the bot's database user:
   ```sql
   CREATE USER 'admin'@'localhost' IDENTIFIED BY '<password>';
   GRANT ALL ON sports_manager.* TO 'admin'@'localhost';
   ```
4. Clone the repo and create the environment:
   ```bash
   git clone https://github.com/dmdok/sports_manager.git /root/sports_manager
   ```
   Then create `.venv` as described under Dependencies.
5. Create `/etc/systemd/system/sports_manager.service`:
   ```ini
   [Unit]
   Description=sports_manager Telegram bot (long polling)
   After=network.target
   StartLimitIntervalSec=600
   StartLimitBurst=3

   [Service]
   User=root
   WorkingDirectory=/root/sports_manager
   Environment="PATH=/root/sports_manager/.venv/bin"
   Environment="TELEGRAM_BOT_TOKEN=<token>"
   Environment="TELEGRAM_BOT_NAME=sports_manager_bot"
   Environment="DB_HOST=localhost"
   Environment="DB_USER=admin"
   Environment="DB_PASSWORD=<password>"
   Environment="PYTHONUNBUFFERED=1"
   ExecStart=/root/sports_manager/.venv/bin/python poll.py
   Restart=on-failure
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```
6. Start it:
   ```bash
   systemctl daemon-reload && systemctl enable --now sports_manager
   ```
   Then run the health check.
