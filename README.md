# Telegram Large File Splitter Bot

Sends you a file → bot downloads it on Oracle VM → compresses + splits into 1 GB RAR parts → sends them all back.

**Why Telethon instead of plain Bot API?**
Telegram's Bot API caps uploads at 2 GB and downloads at 20 MB. Telethon uses the MTProto protocol directly, so it handles files of any size (tested up to 4 GB+).

---

## Prerequisites (Oracle VM)

- Docker + Docker Compose v2
- At least as much free disk as 2× your largest expected file (one copy downloaded, one copy split)
- Ports: nothing special, the bot only makes outbound connections

---

## 1. Get Telegram credentials

### API credentials (once per account)
1. Go to https://my.telegram.org/apps
2. Log in with your phone number
3. Create an app → note **App api_id** and **App api_hash**

### Bot token
1. Open @BotFather in Telegram
2. `/newbot` → follow the prompts → copy the token

---

## 2. Deploy

```bash
# Clone / upload these files to your VM, then:
cd tg-split-bot

cp .env.example .env
nano .env          # fill in API_ID, API_HASH, BOT_TOKEN

# Build & start
docker compose up -d --build

# Watch logs
docker compose logs -f
```

First boot downloads ~3 MB of Python packages and the rar binary from RARLab.

---

## 3. Usage

1. Open your bot in Telegram
2. `/start` — shows help
3. **Send or forward any file ≥ 1 GB**
4. Bot replies with live progress, then sends each RAR part as a separate file message

### Example — 3.4 GB file
```
📥 Downloading file.mkv… 3.4 GB / 3.4 GB (100%)
⚙️ Compressing and splitting…
✅ Split into 4 part(s)
📤 Uploading part 1/4: file.part1.rar (1000 MB)
📤 Uploading part 2/4: file.part2.rar (1000 MB)
📤 Uploading part 3/4: file.part3.rar (1000 MB)
📤 Uploading part 4/4: file.part4.rar (400 MB)
🎉 Done!
```

---

## 4. Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `SPLIT_SIZE_MB` | 1000 | Size of each RAR volume in MB |
| `MIN_SIZE_MB` | 1000 | Ignore files smaller than this |
| `DOWNLOAD_DIR` | `/tmp/tgbot/downloads` | Temp download path |
| `OUTPUT_DIR` | `/tmp/tgbot/output` | Temp split output path |

### Using a larger disk
If your VM's `/tmp` is small, mount a bigger volume and point the env vars there:

```yaml
# docker-compose.yml — volumes section
volumes:
  - /mnt/large_disk/tgbot:/tmp/tgbot
```

---

## 5. Updating

```bash
docker compose pull        # if using a registry
docker compose up -d --build --no-cache
```

---

## 6. Troubleshooting

| Problem | Fix |
|---------|-----|
| `rar: command not found` | Dockerfile downloads from rarlab.com; check internet on build |
| Session auth loop | Delete `bot_session.session` in the `tgbot_session` volume, restart |
| Disk full mid-transfer | Increase VM storage or lower `SPLIT_SIZE_MB` |
| Upload stalls at 2 GB | Normal for individual parts; Telethon handles it — just wait |
| `FloodWaitError` | Telegram rate-limited you; bot will retry automatically |

---

## File structure

```
tg-split-bot/
├── bot.py              # main bot logic (Telethon)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```
